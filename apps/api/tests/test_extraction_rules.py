"""Pass B extraction rules on hand-built OCR lines (no OCR engine needed)."""

import pytest

from app.core.configfiles import load_config
from app.modules.extraction.ocr import OcrLine
from app.modules.extraction.rules import extract_fields, normalize_amount, normalize_date

RULES = load_config("extraction.yaml")


def line(text, x, y, score=0.99):
    return OcrLine(text, (x, y, x + 10 * len(text), y + 24), score)


RECEIPT = [
    line("Sample Co-operative Bank", 56, 51),
    line("Kochi Main Branch", 57, 102),
    line("IFSC: XSCB0673047", 757, 103),
    line("FIXED DEPOSIT RECEIPT", 59, 155),
    line("FDR No.", 56, 217),
    line("XS6194323272", 416, 218),
    line("INSTRUMENT", 812, 228),
    line("Depositor", 57, 267),
    line("Synthetic Institute of Technology, Bhopal", 417, 267),
    line("Beneficiary", 56, 315),
    line("AICTE, New Delhi", 417, 318),
    line("Amount", 57, 367),
    line("Rs. 24,50,000/-", 416, 368),
    line("Date of Deposit", 58, 418),
    line("09/05/2024", 416, 418),
    line("Date of Maturity", 57, 468),
    line("09/05/2026", 417, 467),
    line("Amount in words:", 58, 526),
    line("Rupees Twenty Four Lakh Fifty Thousand Only", 58, 562),
    line("Lien marked in favour of AICTE (synthetic placeholder wording)", 57, 616),
]


def test_extracts_every_field_from_a_receipt():
    got = {k: v.normalized for k, v in extract_fields(RECEIPT, RULES).items()}
    assert got == {
        "fdr_no": "XS6194323272",
        "ifsc": "XSCB0673047",
        "amount": "2450000",
        "amount_words": "Rupees Twenty Four Lakh Fifty Thousand Only",
        "issue_date": "2024-05-09",
        "maturity_date": "2026-05-09",
        "depositor": "Synthetic Institute of Technology, Bhopal",
        "beneficiary": "AICTE, New Delhi",
        "lien_text": "Lien marked in favour of AICTE (synthetic placeholder wording)",
        "branch": "Kochi Main Branch",
        "bank": "Sample Co-operative Bank",
    }


def test_configured_ignore_text_is_never_a_value():
    rules = RULES | {"ignore_lines_equal": ["INSTRUMENT"]}
    got = extract_fields([line("INSTRUMENT", 10, 10), line("Real Bank", 10, 40)], rules)
    assert got["bank"].normalized == "Real Bank"


def test_longer_caption_wins_when_captions_share_a_prefix():
    lines = [line("Depositor Name: ABC INSTITUTE OF TECHNOLOGY", 10, 10)]
    got = extract_fields(lines, RULES)
    assert got["depositor"].normalized == "ABC INSTITUTE OF TECHNOLOGY"


def test_shorter_caption_is_not_used_when_the_longer_one_has_no_value():
    lines = [line("Depositor Name", 10, 200), line("ABC INSTITUTE", 10, 240)]
    assert "depositor" not in extract_fields(lines, RULES)


def test_longer_caption_shadows_only_when_it_ends_at_a_word_boundary():
    lines = [line("Depositor Namespace Trust", 10, 10)]
    assert extract_fields(lines, RULES)["depositor"].normalized == "Namespace Trust"


def test_caption_priority_follows_the_config_order():
    lines = [line("Receipt No. A123456", 10, 10), line("FDR No. 9988776655", 10, 60)]
    assert extract_fields(lines, RULES)["fdr_no"].normalized == "9988776655"
    lines = [line("Date of Issue 05/03/2025", 10, 10), line("Deposit Date 01/01/2024", 10, 60)]
    assert extract_fields(lines, RULES)["issue_date"].normalized == "2024-01-01"


def test_ifsc_with_letter_o_as_fifth_character_is_read_as_zero_next_to_a_caption():
    got = extract_fields([line("IFSC Code: BARBOBANGAX", 10, 10)], RULES)
    assert got["ifsc"].normalized == "BARB0BANGAX"


@pytest.mark.parametrize(
    "text", ["CORPORATION BANK", "GUJARAT TECHNOLOGICAL UNIVERSITY", "METHODOLOGY"]
)
def test_ordinary_words_are_never_an_ifsc(text):
    assert "ifsc" not in extract_fields([line(text, 10, 10)], RULES)


@pytest.mark.parametrize(
    "caption_line, beside",
    [
        ("IFSC: SBIN 0001234", "Branch: CORPORATION ROAD"),
        ("IFSC:", "Depositor: GUJARAT TECHNOLOGICAL UNIVERSITY"),
    ],
)
def test_loose_ifsc_pattern_is_only_for_the_caption_line(caption_line, beside):
    lines = [line(caption_line, 10, 10), line(beside, 400, 10)]
    assert "ifsc" not in extract_fields(lines, RULES)


def test_header_word_does_not_hide_the_ifsc_further_down():
    lines = [line("CORPORATION BANK", 10, 10), line("IFS Code: CORP0001234", 10, 60)]
    assert extract_fields(lines, RULES)["ifsc"].normalized == "CORP0001234"


def test_synthetic_banner_is_never_the_bank():
    lines = [
        line("SYNTHETIC - NOT A REAL DEPOSIT", 480, 18),
        line("Punjab National Bank", 70, 70),
        line("SYNTHETIC", 480, 860),
    ]
    assert extract_fields(lines, RULES)["bank"].normalized == "Punjab National Bank"


def test_ifsc_found_without_caption_has_lower_confidence():
    got = extract_fields([line("Ref XNBK0001234 issued", 10, 10, score=1.0)], RULES)
    assert got["ifsc"].normalized == "XNBK0001234"
    assert got["ifsc"].confidence < 1.0


def test_amount_and_date_normalisation():
    assert normalize_amount("Rs. 35,00,000/-") == "3500000"
    assert normalize_amount("INR 1,250.50") == "1250.50"
    assert normalize_amount("no number") is None
    assert normalize_date("09-05-2024", RULES["date_formats"]) == "2024-05-09"
    assert normalize_date("2024/05/09", RULES["date_formats"]) is None
