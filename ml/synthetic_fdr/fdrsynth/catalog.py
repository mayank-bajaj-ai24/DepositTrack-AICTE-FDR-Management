"""Load what a synthetic FDR is made from.

- Branches (bank name, IFSC, branch, city) from the RBI IFSC master that
  `python -m app.masterdata fetch-banks` saves to data/open/ifsc/.
- Depositor institutions from the AICTE snapshot that
  `python -m app.masterdata fetch-institutions` saves to data/open/aicte/.
- Captions and date formats from the API's config/extraction.yaml, and merged banks from its
  config/bank_mergers.yaml, so the pages print what the extractor reads.
- Generated-value ranges and wording from fdrsynth/data/placeholders.json.

Default paths are resolved only when used, from the DepositTrack checkout this package runs
from; outside a checkout every path must be given.
"""

import csv
import json
import re
from dataclasses import dataclass
from datetime import date
from importlib import resources
from pathlib import Path

import yaml

REQUIRED_KEYS = {
    "bank_types",
    "beneficiary",
    "lien_text",
    "amount",
    "tenure_months",
    "deposit_date",
}

# Rows of the IFSC master that are payment or office entries, not branches that issue FDRs
# (e.g. "Bank of Baroda IMPS", "RTGS-HO AMALGAMATED OBC", "HEAD OFFICE-SERVICE CENTER").
NOT_A_BRANCH = re.compile(r"\b(?:IMPS|RTGS|NEFT|TREASURY|SERVICE|CPPC|HO)\b")
# UTF-8 text that was decoded as Latin-1 somewhere upstream ("WOMENâ\x80\x99S").
MOJIBAKE = re.compile("[Â-ô][\u0080-¿]")


def repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "apps" / "api" / "config" / "extraction.yaml").exists():
            return parent
    raise FileNotFoundError(
        "fdrsynth is not running from a DepositTrack checkout: "
        "pass --ifsc-dir, --institutions, --api-config and --out"
    )


def default_ifsc_dir() -> Path:
    return repo_root() / "data" / "open" / "ifsc"


def default_api_config() -> Path:
    return repo_root() / "apps" / "api" / "config"


def default_institutions(api_config: Path) -> Path:
    """The snapshot fetch-institutions writes for master_data.yaml's academic year."""
    cfg = yaml.safe_load((api_config / "master_data.yaml").read_text(encoding="utf-8"))
    year = cfg["aicte"]["academic_year"]
    return repo_root() / "data" / "open" / "aicte" / f"institutions_{year}.json"


@dataclass(frozen=True)
class Branch:
    bank: str
    ifsc: str
    branch: str
    city: str


@dataclass(frozen=True)
class Institution:
    aicte_id: str
    name: str


@dataclass(frozen=True)
class Catalog:
    branches: tuple[Branch, ...]
    institutions: tuple[Institution, ...]
    fields: tuple[str, ...]
    captions: dict[str, tuple[str, ...]]
    date_formats: tuple[str, ...]
    beneficiary: tuple[str, ...]
    lien_text: tuple[str, ...]
    amount_step: int
    amount_min_steps: int
    amount_max_steps: int
    tenure_months: tuple[int, ...]
    deposit_start: date
    deposit_span_days: int


def _positive_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def load_placeholders(path: Path | None = None) -> dict:
    if path is None:
        text = resources.files("fdrsynth").joinpath("data/placeholders.json").read_text("utf-8")
        source = "fdrsynth/data/placeholders.json"
    else:
        text, source = path.read_text(encoding="utf-8"), str(path)
    data = json.loads(text)
    missing = REQUIRED_KEYS - data.keys()
    if missing:
        raise ValueError(f"{source}: missing keys {sorted(missing)}")
    for key in ("bank_types", "beneficiary", "lien_text", "tenure_months"):
        if not data[key]:
            raise ValueError(f"{source}: {key} must not be empty")
    if not all(_positive_int(m) for m in data["tenure_months"]):
        raise ValueError(f"{source}: tenure_months must be positive whole months")
    amount = data["amount"]
    if not all(_positive_int(amount.get(k)) for k in ("step_inr", "min_steps", "max_steps")):
        raise ValueError(f"{source}: amount needs positive step_inr, min_steps and max_steps")
    if amount["min_steps"] > amount["max_steps"]:
        raise ValueError(f"{source}: amount.min_steps is above amount.max_steps")
    deposit = data["deposit_date"]
    span = deposit.get("span_days")
    if not isinstance(span, int) or isinstance(span, bool) or span < 0:
        raise ValueError(f"{source}: deposit_date.span_days must be a whole number >= 0")
    try:
        date.fromisoformat(deposit.get("start", ""))
    except (TypeError, ValueError):
        raise ValueError(f"{source}: deposit_date.start must be a YYYY-MM-DD date") from None
    return data


@dataclass(frozen=True)
class ApiConfig:
    fields: tuple[str, ...]
    captions: dict[str, tuple[str, ...]]
    date_formats: tuple[str, ...]
    merged_banks: frozenset[str]


def load_api_config(api_config: Path) -> ApiConfig:
    """Field labels and captions, the extractor's date formats, and merged-away bank codes."""
    rules = yaml.safe_load((api_config / "extraction.yaml").read_text(encoding="utf-8"))
    captions = {
        name.upper(): tuple(spec["captions"])
        for name, spec in rules["fields"].items()
        if spec.get("captions")
    }
    mergers = yaml.safe_load((api_config / "bank_mergers.yaml").read_text(encoding="utf-8"))
    return ApiConfig(
        fields=tuple(name.upper() for name in rules["fields"]),
        captions=captions,
        date_formats=tuple(rules["date_formats"]),
        merged_banks=frozenset(m["old_bank"] for m in mergers.get("mergers") or []),
    )


def _tidy(text: str) -> str:
    """One space between words and none before a comma ("KOVUR ,NELLORE" -> "KOVUR,NELLORE"),
    as a branch name is printed; the raw IFSC list carries stray spaces."""
    return re.sub(r"\s+,", ",", " ".join(text.split()))


def repair_text(text: str) -> str | None:
    """Undo UTF-8-read-as-Latin-1; None when the text cannot be repaired."""
    text = " ".join(text.split())
    if not MOJIBAKE.search(text):
        return text
    try:
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return None


def load_branches(
    ifsc_dir: Path, bank_types: list[str], merged: set | frozenset = frozenset()
) -> tuple[Branch, ...]:
    """Branches of banks of the given RBI types that issue FDRs under their own name.

    Each bank code is named the way the API's importer names it (`banks._bank_names`): by the
    first non-sublet row of its prefix. Rows whose BANK names another bank (a co-operative
    bank using a sponsor bank's IFSC without a sublet entry), sublet IFSCs, payment and office
    entries, member banks listed as branches, and banks merged away (bank_mergers.yaml) are
    left out, so the bank on the page always matches the IFSC's bank.
    """
    paths = [ifsc_dir / name for name in ("IFSC.csv", "banks.json", "sublet.json")]
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(
                f"{path} not found: run `python -m app.masterdata fetch-banks` in apps/api"
            )
    csv_path, banks_path, sublet_path = paths
    banks = json.loads(banks_path.read_text(encoding="utf-8"))
    sublet = {ifsc.upper() for ifsc in json.loads(sublet_path.read_text(encoding="utf-8"))}
    wanted = {code for code, bank in banks.items() if bank.get("type") in bank_types} - set(merged)
    names: dict[str, str] = {}
    rows = []
    with open(csv_path, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            ifsc, name = row["IFSC"].strip().upper(), (row["BANK"] or "").strip()
            if ifsc in sublet or not name:
                continue
            names.setdefault(ifsc[:4], name)
            rows.append((ifsc, name, row))
    out = []
    for ifsc, name, row in rows:
        branch = _tidy(row["BRANCH"] or "")
        upper = branch.upper()
        if (
            ifsc[:4] in wanted
            and name == names[ifsc[:4]]
            and branch
            and "BANK" not in upper
            and not NOT_A_BRANCH.search(upper)
        ):
            out.append(
                Branch(
                    bank=name,
                    ifsc=ifsc,
                    branch=branch,
                    city=(row["CITY"] or row["CENTRE"]).strip().title(),
                )
            )
    if not out:
        raise ValueError(f"{csv_path}: no branches for bank types {bank_types}")
    return tuple(out)


def load_institutions(path: Path) -> tuple[Institution, ...]:
    """Institutions from the AICTE snapshot, checked like the API's `aicte.parse_snapshot`."""
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found: run `python -m app.masterdata fetch-institutions` in apps/api"
        )
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    columns = snapshot["columns"]
    out = []
    for item in snapshot["rows"]:
        if len(item["row"]) < len(columns):
            raise ValueError(f"{path}: row has fewer than {len(columns)} columns: {item['row']}")
        row = dict(zip(columns, item["row"][: len(columns)], strict=True))
        name = repair_text(row["name"])
        if name:
            out.append(Institution(aicte_id=row["aicte_id"], name=name))
    if not out:
        raise ValueError(f"{path}: no institutions")
    return tuple(out)


def load_catalog(
    ifsc_dir: Path | None = None,
    institutions: Path | None = None,
    placeholders: Path | None = None,
    api_config: Path | None = None,
) -> Catalog:
    api_config = api_config or default_api_config()
    config = load_api_config(api_config)
    data = load_placeholders(placeholders)
    return Catalog(
        branches=load_branches(
            ifsc_dir or default_ifsc_dir(), data["bank_types"], config.merged_banks
        ),
        institutions=load_institutions(institutions or default_institutions(api_config)),
        fields=config.fields,
        captions=config.captions,
        date_formats=config.date_formats,
        beneficiary=tuple(data["beneficiary"]),
        lien_text=tuple(data["lien_text"]),
        amount_step=data["amount"]["step_inr"],
        amount_min_steps=data["amount"]["min_steps"],
        amount_max_steps=data["amount"]["max_steps"],
        tenure_months=tuple(data["tenure_months"]),
        deposit_start=date.fromisoformat(data["deposit_date"]["start"]),
        deposit_span_days=data["deposit_date"]["span_days"],
    )
