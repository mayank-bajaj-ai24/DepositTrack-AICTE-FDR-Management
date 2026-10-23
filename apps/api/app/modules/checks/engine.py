"""Discrepancy rules (M4, N8): every flag carries the fact, the rule, the clause and a reason.

The engine is pure: it takes a snapshot of the instrument's values and returns flag specs.
`flag_type` plus `fact` let the UI render the reason in any language; `reason` is the
English text stored with the flag.
"""

from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path

import yaml

from app.core.policy import Policy
from app.modules.checks.canonical import IFSC_RE
from app.modules.checks.words import words_to_amount


@dataclass(frozen=True)
class FlagSpec:
    flag_type: str
    severity: str
    reason: str
    fact: dict = field(default_factory=dict)
    rule_id: str = ""
    clause_ref: str | None = None
    field: str | None = None


@dataclass
class Snapshot:
    """Values of one instrument: declared by the institution and extracted from its scan."""

    kind: str
    declared: dict[str, str | None]
    extracted: dict[str, str | None]
    documents: list[str]

    def best(self, name: str) -> str | None:
        return self.declared.get(name) or self.extracted.get(name)


@lru_cache
def load_check_config(path: str) -> dict:
    with open(Path(path), encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _same(name: str, a: str, b: str) -> bool:
    if name == "amount":
        try:
            return float(a) == float(b)
        except ValueError:
            return False
    return a.replace(" ", "").upper() == b.replace(" ", "").upper()


def evaluate(snapshot: Snapshot, policy: Policy, cfg: dict) -> list[FlagSpec]:
    sev = cfg["severity"]
    flags: list[FlagSpec] = []

    def add(flag_type: str, reason: str, **kwargs) -> None:
        flags.append(FlagSpec(flag_type, sev[flag_type], reason, rule_id=flag_type, **kwargs))

    # Completeness (R-c)
    for name in cfg["required_fields"]:
        if not snapshot.best(name):
            add("missing_field", f"{name} is missing", fact={"field": name}, field=name)
    for doc in cfg["required_documents"]:
        if doc not in snapshot.documents:
            add("missing_document", f"required document '{doc}' not uploaded", fact={"doc": doc})

    # Declared vs extracted (N1 L0 vs L1)
    for name in cfg["compare_fields"]:
        declared, extracted = snapshot.declared.get(name), snapshot.extracted.get(name)
        if declared and extracted and not _same(name, declared, extracted):
            add(
                "declared_mismatch",
                f"{name}: declared '{declared}' but the document shows '{extracted}'",
                fact={"field": name, "declared": declared, "extracted": extracted},
                field=name,
            )

    # Amount in words vs figures
    words = snapshot.extracted.get("amount_words")
    figures = snapshot.best("amount")
    if words and figures:
        spelled = words_to_amount(words)
        if spelled is not None and float(figures) != float(spelled):
            add(
                "amount_words_mismatch",
                f"amount in figures {figures} does not match amount in words ({spelled})",
                fact={"figures": figures, "words": words, "words_value": spelled},
                field="amount",
            )

    ifsc = snapshot.best("ifsc")
    if ifsc and not IFSC_RE.match(ifsc.upper()):
        add("invalid_ifsc", f"IFSC '{ifsc}' is not in the 11-character format", fact={"ifsc": ifsc})

    issue, maturity = snapshot.best("issue_date"), snapshot.best("maturity_date")
    if issue and maturity and date.fromisoformat(maturity) <= date.fromisoformat(issue):
        add(
            "dates_inconsistent",
            f"maturity date {maturity} is not after issue date {issue}",
            fact={"issue_date": issue, "maturity_date": maturity},
        )

    # Policy rules: skipped while AICTE values are unconfirmed (null).
    if policy.accepted_kinds is not None and snapshot.kind not in policy.accepted_kinds:
        add(
            "kind_not_accepted",
            f"instrument kind '{snapshot.kind}' is not in the accepted list",
            fact={"kind": snapshot.kind, "accepted": policy.accepted_kinds},
        )
    wording = policy.beneficiary_wording
    text = " ".join(
        filter(None, [snapshot.best("beneficiary"), snapshot.extracted.get("lien_text")])
    )
    if wording and text and wording.lower() not in text.lower():
        add(
            "beneficiary_wording_missing",
            f"beneficiary / lien text does not contain the required wording '{wording}'",
            fact={"required": wording, "found": text},
        )
    return flags


def amount_below_requirement(
    amount: str | None, required: float | None, clause_ref: str | None, cfg: dict
) -> FlagSpec | None:
    if amount is None or required is None or float(amount) >= required:
        return None
    return FlagSpec(
        "amount_below_requirement",
        cfg["severity"]["amount_below_requirement"],
        f"amount {amount} is below the required {required:g}",
        fact={"amount": amount, "required": required},
        rule_id="amount_below_requirement",
        clause_ref=clause_ref,
        field="amount",
    )
