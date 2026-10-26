"""Tests for the scoring in ml/extraction/evaluate.py (no OCR engine needed)."""

import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "extraction_evaluate", Path(__file__).resolve().parents[1] / "extraction" / "evaluate.py"
)
ev = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ev)

VALUES = {
    "fdr_no": "FD123456789",
    "bank": "Punjab  National Bank",
    "branch": "KOZHIKODE Branch, Calicut",
    "ifsc": "PUNB0440200",
    "amount": 550000,
    "amount_words": "Rupees Five Lakh Fifty Thousand Only",
    "deposit_date_iso": "2025-11-13",
    "maturity_date_iso": "2028-11-13",
    "depositor": "NIELIT JORHAT EC",
    "beneficiary": "AICTE, New Delhi",
    "lien_text": "Under lien to AICTE",
}


def test_expected_fields_use_the_normalised_forms():
    expected = ev.expected_fields(VALUES)
    assert expected["amount"] == "550000"
    assert expected["issue_date"] == "2025-11-13"
    assert expected["bank"] == "Punjab National Bank"
    assert set(expected) == set(ev.FIELDS)


def test_missing_and_wrong_fields_count_as_misses():
    expected = ev.expected_fields(VALUES)
    extracted = dict(expected, amount="55000")
    del extracted["lien_text"]
    match = ev.score_page(expected, extracted)
    assert not match["amount"] and not match["lien_text"]
    assert sum(match.values()) == len(ev.FIELDS) - 2


def test_summary_rates():
    expected = ev.expected_fields(VALUES)
    perfect = ev.score_page(expected, expected)
    one_wrong = ev.score_page(expected, dict(expected, issue_date="2025-11-14"))
    pages = [
        {"layout": "classic", "match": perfect, "seconds": 1.0},
        {"layout": "inline", "match": one_wrong, "seconds": 3.0},
    ]
    summary = ev.summarise(pages)
    assert summary["pages_all_fields_correct"] == 0.5
    assert summary["exact_match_amount_and_dates"] == round(5 / 6, 4)
    assert summary["exact_match_by_field"]["issue_date"] == 0.5
    assert summary["exact_match_by_layout"]["classic"] == 1.0
    assert summary["seconds_per_page_mean"] == 2.0


def _summary_of_times(times):
    expected = ev.expected_fields(VALUES)
    page = ev.score_page(expected, expected)
    return ev.summarise([{"layout": "classic", "match": page, "seconds": s} for s in times])


def test_p95_is_the_nearest_rank():
    assert _summary_of_times([1.0, 2.0])["seconds_per_page_p95"] == 2.0
    assert _summary_of_times([float(i) for i in range(1, 11)])["seconds_per_page_p95"] == 10.0
    assert _summary_of_times([float(i) for i in range(1, 101)])["seconds_per_page_p95"] == 95.0
