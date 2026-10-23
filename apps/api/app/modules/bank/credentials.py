"""Verify bank-signed FDR credentials against pinned keys (N3).

Pure functions: no network. The adapter in client.py fetches credentials; this module
decides whether to trust them and how they compare with the instrument.
"""

import base64
import json
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.modules.audit.hashchain import canonical_json

# Credential subject field -> instrument field name used in DepositTrack.
SUBJECT_FIELDS = {
    "instrument_no": "fdr_no",
    "ifsc": "ifsc",
    "amount_inr": "amount",
    "issue_date": "issue_date",
    "maturity_date": "maturity_date",
    "beneficiary": "beneficiary",
}


class CredentialError(ValueError):
    pass


def load_pinned(path: str | Path) -> dict[str, str]:
    path = Path(path)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_pinned(path: str | Path, keys: dict[str, str]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(keys, indent=2, sort_keys=True), encoding="utf-8")


def verify_signature(document: dict, pinned: dict[str, str]) -> None:
    """Raise CredentialError unless `document` is signed by a pinned bank key."""
    issuer = document.get("issuer")
    if issuer not in pinned:
        raise CredentialError(f"issuer {issuer!r} is not a pinned bank key")
    signature = document.get("signature", "")
    if not signature.startswith("ed25519:"):
        raise CredentialError("unsupported signature format")
    body = {k: v for k, v in document.items() if k != "signature"}
    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(pinned[issuer])).verify(
            base64.b64decode(signature.removeprefix("ed25519:")),
            canonical_json(body).encode("utf-8"),
        )
    except (InvalidSignature, ValueError) as exc:
        raise CredentialError("signature does not verify") from exc


@dataclass(frozen=True)
class Comparison:
    matches: dict[str, bool]
    bank_values: dict[str, str]

    @property
    def mismatched(self) -> list[str]:
        return [name for name, ok in self.matches.items() if not ok]


def _norm(name: str, value) -> str:
    if value is None:
        return ""
    if name == "amount":
        number = float(value)
        return str(int(number)) if number.is_integer() else f"{number:.2f}"
    return str(value).replace(" ", "").upper()


def compare(subject: dict, declared: dict[str, str | None]) -> Comparison:
    """Compare the bank's values with the institution's declared values, field by field."""
    matches, bank_values = {}, {}
    for key, name in SUBJECT_FIELDS.items():
        if key not in subject:
            continue
        bank_values[name] = str(subject[key])
        if name == "beneficiary":
            continue  # free text; shown side by side, not used for a match decision
        matches[name] = _norm(name, subject[key]) == _norm(name, declared.get(name))
    return Comparison(matches, bank_values)
