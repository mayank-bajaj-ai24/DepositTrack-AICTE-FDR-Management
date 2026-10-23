"""Pass B extraction rules on hand-built OCR lines (no OCR engine needed)."""

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
