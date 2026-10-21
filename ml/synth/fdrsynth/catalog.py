"""Load the synthetic data lists (banks, cities, wording, ranges) from a JSON file.

The default file ships with the package (fdrsynth/data/synthetic_lists.json); pass a
different path to generate data from another catalogue without changing code.
"""

import json
from dataclasses import dataclass
from datetime import date
from importlib import resources
from pathlib import Path

REQUIRED_KEYS = {
    "banks",
    "branch_suffix",
    "cities",
    "institution_words",
    "institution_kinds",
    "beneficiary",
    "lien_text",
    "amount",
    "tenure_months",
    "deposit_date",
    "date_format",
}


@dataclass(frozen=True)
class Bank:
    name: str
    ifsc_prefix: str


@dataclass(frozen=True)
class Catalog:
    banks: tuple[Bank, ...]
    branch_suffix: str
    cities: tuple[str, ...]
    institution_words: tuple[str, ...]
    institution_kinds: tuple[str, ...]
    beneficiary: str
    lien_text: str
    amount_step: int
    amount_min_steps: int
    amount_max_steps: int
    tenure_months: tuple[int, ...]
    deposit_start: date
    deposit_span_days: int
    date_format: str


def _validate(data: dict, source: str) -> None:
    missing = REQUIRED_KEYS - data.keys()
    if missing:
        raise ValueError(f"{source}: missing keys {sorted(missing)}")
    for bank in data["banks"]:
        prefix = bank["ifsc_prefix"]
        if len(prefix) != 4 or not prefix.isalpha() or not prefix.isupper():
            raise ValueError(f"{source}: IFSC prefix must be 4 uppercase letters: {prefix!r}")
    for key in ("banks", "cities", "institution_words", "institution_kinds", "tenure_months"):
        if not data[key]:
            raise ValueError(f"{source}: {key} must not be empty")


def load_catalog(path: str | Path | None = None) -> Catalog:
    if path is None:
        text = resources.files("fdrsynth").joinpath("data/synthetic_lists.json").read_text("utf-8")
        source = "fdrsynth/data/synthetic_lists.json"
    else:
        text = Path(path).read_text(encoding="utf-8")
        source = str(path)
    data = json.loads(text)
    _validate(data, source)
    return Catalog(
        banks=tuple(Bank(b["name"], b["ifsc_prefix"]) for b in data["banks"]),
        branch_suffix=data["branch_suffix"],
        cities=tuple(data["cities"]),
        institution_words=tuple(data["institution_words"]),
        institution_kinds=tuple(data["institution_kinds"]),
        beneficiary=data["beneficiary"],
        lien_text=data["lien_text"],
        amount_step=data["amount"]["step_inr"],
        amount_min_steps=data["amount"]["min_steps"],
        amount_max_steps=data["amount"]["max_steps"],
        tenure_months=tuple(data["tenure_months"]),
        deposit_start=date.fromisoformat(data["deposit_date"]["start"]),
        deposit_span_days=data["deposit_date"]["span_days"],
        date_format=data["date_format"],
    )
