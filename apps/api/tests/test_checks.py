from pathlib import Path

import pytest

from app.core.configfiles import checks
from app.core.policy import Policy, load_policy
from app.modules.checks.canonical import edit_distance, normalize_instrument_no
from app.modules.checks.engine import Snapshot, evaluate
from app.modules.checks.words import words_to_amount

CONFIG = Path(__file__).resolve().parents[1] / "config"
REAL = Policy(load_policy(CONFIG / "policy.example.yaml"))
DEMO = Policy(load_policy(CONFIG / "policy.demo.yaml"))

GOOD = {
    "fdr_no": "XN1",
    "bank": "Example National Bank",
    "ifsc": "XNBK0001234",
    "amount": "500000",
    "issue_date": "2025-01-01",
    "maturity_date": "2028-01-01",
    "beneficiary": "AICTE, New Delhi",
}


def types(snapshot, policy=DEMO):
    return {f.flag_type for f in evaluate(snapshot, policy, checks())}


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("Rupees Five Lakh Only", 500000),
        ("Rupees Twenty Four Lakh Fifty Thousand Only", 2450000),
        (
            "Rupees One Crore Twenty Three Lakh Forty Five Thousand Six Hundred Seventy Eight Only",
            12345678,
        ),
        ("Rupees Seven Hundred Only", 700),
        ("gibberish words", None),
    ],
)
def test_words_to_amount(text, value):
    assert words_to_amount(text) == value


def test_clean_snapshot_has_no_flags():
    snap = Snapshot("fdr", GOOD, dict(GOOD, amount_words="Rupees Five Lakh Only"), ["scan"])
    assert types(snap) == set()


def test_missing_field_and_document():
    snap = Snapshot("fdr", {**GOOD, "ifsc": None}, {}, [])
    assert {"missing_field", "missing_document"} <= types(snap)


def test_words_and_figures_disagree():
    snap = Snapshot("fdr", GOOD, {**GOOD, "amount_words": "Rupees Fifteen Lakh Only"}, ["scan"])
    assert "amount_words_mismatch" in types(snap)


def test_maturity_before_issue():
    snap = Snapshot("fdr", {**GOOD, "maturity_date": "2024-01-01"}, {}, ["scan"])
    assert "dates_inconsistent" in types(snap)


def test_policy_rules_skipped_while_unconfirmed():
    snap = Snapshot("bank_guarantee", {**GOOD, "beneficiary": "Someone else"}, {}, ["scan"])
    assert not {"kind_not_accepted", "beneficiary_wording_missing"} & types(snap, REAL)
    assert {"kind_not_accepted", "beneficiary_wording_missing"} <= types(snap, DEMO)


def test_canonical_number_and_distance():
    assert normalize_instrument_no("xn-123 456") == "XN123456"
    assert edit_distance("XN123456", "XN123457") == 1
    assert edit_distance("XN123456", "XN123456") == 0


def test_demo_policy_is_labelled_on_every_value():
    for key, entry in DEMO.raw.items():
        if isinstance(entry, dict):
            assert "DEMO PLACEHOLDER" in entry["source"], key
