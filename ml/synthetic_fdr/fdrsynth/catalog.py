"""Load what a synthetic FDR is made from.

- Branches (bank name, IFSC, branch, city) from the RBI IFSC master that
  `python -m app.masterdata fetch-banks` saves to data/open/ifsc/.
- Depositor institutions from the AICTE snapshot that
  `python -m app.masterdata fetch-institutions` saves to data/open/aicte/.
- Generated-value ranges and wording from fdrsynth/data/placeholders.json.
"""

import csv
import json
from dataclasses import dataclass
from datetime import date
from importlib import resources
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_IFSC_DIR = ROOT / "data" / "open" / "ifsc"
DEFAULT_INSTITUTIONS = ROOT / "data" / "open" / "aicte" / "institutions_2024-2025.json"

REQUIRED_KEYS = {
    "bank_types",
    "beneficiary",
    "lien_text",
    "amount",
    "tenure_months",
    "deposit_date",
    "date_formats",
}


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
    district: str
    state: str


@dataclass(frozen=True)
class Catalog:
    branches: tuple[Branch, ...]
    institutions: tuple[Institution, ...]
    beneficiary: tuple[str, ...]
    lien_text: tuple[str, ...]
    amount_step: int
    amount_min_steps: int
    amount_max_steps: int
    tenure_months: tuple[int, ...]
    deposit_start: date
    deposit_span_days: int
    date_formats: tuple[str, ...]


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
    for key in REQUIRED_KEYS - {"amount", "deposit_date"}:
        if not data[key]:
            raise ValueError(f"{source}: {key} must not be empty")
    return data


def load_branches(ifsc_dir: Path, bank_types: list[str]) -> tuple[Branch, ...]:
    """Branches of banks of the given RBI types, sublet IFSCs excluded (their BANK column
    names the sub-member bank, not the IFSC's owner)."""
    csv_path, banks_path = ifsc_dir / "IFSC.csv", ifsc_dir / "banks.json"
    for path in (csv_path, banks_path):
        if not path.exists():
            raise FileNotFoundError(
                f"{path} not found: run `python -m app.masterdata fetch-banks` in apps/api"
            )
    banks = json.loads(banks_path.read_text(encoding="utf-8"))
    sublet_path = ifsc_dir / "sublet.json"
    sublet = json.loads(sublet_path.read_text(encoding="utf-8")) if sublet_path.exists() else {}
    wanted = {code for code, bank in banks.items() if bank.get("type") in bank_types}
    out = []
    with open(csv_path, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            ifsc = row["IFSC"].strip()
            if ifsc[:4] in wanted and ifsc not in sublet and row["BRANCH"].strip():
                out.append(
                    Branch(
                        bank=row["BANK"].strip(),
                        ifsc=ifsc,
                        branch=" ".join(row["BRANCH"].split()),
                        city=(row["CITY"] or row["CENTRE"]).strip().title(),
                    )
                )
    if not out:
        raise ValueError(f"{csv_path}: no branches for bank types {bank_types}")
    return tuple(out)


def load_institutions(path: Path) -> tuple[Institution, ...]:
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found: run `python -m app.masterdata fetch-institutions` in apps/api"
        )
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    columns = snapshot["columns"]
    out = []
    for item in snapshot["rows"]:
        row = dict(zip(columns, item["row"], strict=False))
        out.append(
            Institution(
                aicte_id=row["aicte_id"],
                name=" ".join(row["name"].split()),
                district=row["district"].strip().title(),
                state=item["state"],
            )
        )
    if not out:
        raise ValueError(f"{path}: no institutions")
    return tuple(out)


def load_catalog(
    ifsc_dir: Path = DEFAULT_IFSC_DIR,
    institutions: Path = DEFAULT_INSTITUTIONS,
    placeholders: Path | None = None,
) -> Catalog:
    data = load_placeholders(placeholders)
    return Catalog(
        branches=load_branches(ifsc_dir, data["bank_types"]),
        institutions=load_institutions(institutions),
        beneficiary=tuple(data["beneficiary"]),
        lien_text=tuple(data["lien_text"]),
        amount_step=data["amount"]["step_inr"],
        amount_min_steps=data["amount"]["min_steps"],
        amount_max_steps=data["amount"]["max_steps"],
        tenure_months=tuple(data["tenure_months"]),
        deposit_start=date.fromisoformat(data["deposit_date"]["start"]),
        deposit_span_days=data["deposit_date"]["span_days"],
        date_formats=tuple(data["date_formats"]),
    )
