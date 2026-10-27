import random
import re
from datetime import date

import pytest

from fdrsynth.catalog import Branch
from fdrsynth.values import add_months, amount_in_words, branch_text, indian_format, random_values
from tests.conftest import ROOT, RULES

IFSC = re.compile(RULES["fields"]["ifsc"]["pattern"])
FDR_NO = re.compile(RULES["fields"]["fdr_no"]["pattern"])
AMOUNT = re.compile(RULES["fields"]["amount"]["pattern"])
# The API's canonical IFSC check (checks/canonical.py), read from its source.
CANONICAL_IFSC = re.compile(
    re.search(
        r'IFSC_RE = re\.compile\(r"([^"]+)"\)',
        (ROOT / "apps/api/app/modules/checks/canonical.py").read_text(encoding="utf-8"),
    ).group(1)
)


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (50_000, "Rupees Fifty Thousand Only"),
        (100_000, "Rupees One Lakh Only"),
        (1_500_000, "Rupees Fifteen Lakh Only"),
        (2_550_000, "Rupees Twenty Five Lakh Fifty Thousand Only"),
        (10_000_000, "Rupees One Crore Only"),
        (
            12_345_678,
            "Rupees One Crore Twenty Three Lakh Forty Five Thousand Six Hundred Seventy Eight Only",
        ),
        (1_000_000_000, "Rupees One Hundred Crore Only"),
    ],
)
def test_amount_in_words(amount, expected):
    assert amount_in_words(amount) == expected


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (500, "Rs. 500/-"),
        (50_000, "Rs. 50,000/-"),
        (1_500_000, "Rs. 15,00,000/-"),
        (12_345_678, "Rs. 1,23,45,678/-"),
        (1_000_000_000, "Rs. 1,00,00,00,000/-"),
    ],
)
def test_indian_format(amount, expected):
    assert indian_format(amount) == expected


@pytest.mark.parametrize(
    ("start", "months", "expected"),
    [
        (date(2024, 1, 31), 1, date(2024, 2, 29)),
        (date(2023, 1, 31), 1, date(2023, 2, 28)),
        (date(2024, 3, 15), 12, date(2025, 3, 15)),
        (date(2024, 11, 30), 3, date(2025, 2, 28)),
    ],
)
def test_add_months_clamps_to_month_end(start, months, expected):
    assert add_months(start, months) == expected


def test_values_are_well_formed(catalog):
    rng = random.Random(1)
    for _ in range(200):
        v = random_values(rng, catalog)
        assert IFSC.fullmatch(v.ifsc)
        assert CANONICAL_IFSC.match(v.ifsc)
        assert FDR_NO.match(v.fdr_no)
        assert AMOUNT.match(v.amount_text)
        assert v.amount > 0
        assert v.maturity_date_iso > v.deposit_date_iso


def test_bank_and_depositor_come_from_the_master_data(catalog):
    v = random_values(random.Random(2), catalog)
    assert (v.bank, v.ifsc) in {(b.bank, b.ifsc) for b in catalog.branches}
    assert (v.depositor, v.depositor_aicte_id) in {
        (i.name, i.aicte_id) for i in catalog.institutions
    }


def test_mockbank_record_uses_iso_dates_and_a_string_amount(catalog):
    v = random_values(random.Random(3), catalog)
    record = v.mockbank_record()
    assert record["issue_date"] == v.deposit_date_iso
    assert record["maturity_date"] == v.maturity_date_iso
    assert record["amount"] == str(v.amount)


def test_same_seed_same_values(catalog):
    assert random_values(random.Random(42), catalog) == random_values(random.Random(42), catalog)


def test_dates_use_the_extractors_formats(catalog):
    v = random_values(random.Random(5), catalog)
    assert catalog.date_formats == tuple(RULES["date_formats"])
    assert any(
        date.fromisoformat(v.deposit_date_iso).strftime(f) == v.deposit_date
        for f in catalog.date_formats
    )


@pytest.mark.parametrize(
    ("name", "expected"),
    [("AMBUR", "AMBUR Branch, Chennai"), ("KATARGAM BRANCH", "KATARGAM BRANCH, Chennai")],
)
def test_branch_word_is_not_printed_twice(name, expected):
    assert branch_text(Branch("Bank", "BARB0AAMBUR", name, "Chennai")) == expected


def test_zero_amount_has_no_words():
    with pytest.raises(ValueError):
        amount_in_words(0)
