"""Dual-pass extraction (M3, N6): OCR, then rules (pass B) and LayoutLMv3 (pass A).

A field is routed to human confirmation when the passes disagree, when its confidence
is below the configured threshold, or when it is missing.
"""

from dataclasses import dataclass, field

from PIL import Image

from app.modules.extraction import layoutlm
from app.modules.extraction.ocr import OcrLine, run_ocr
from app.modules.extraction.rules import _normalize, extract_fields
from app.modules.forgery import model as forgery_model
from app.modules.forgery.model import ForgeryResult

FIELDS = (
    "fdr_no",
    "bank",
    "branch",
    "ifsc",
    "amount",
    "amount_words",
    "issue_date",
    "maturity_date",
    "depositor",
    "beneficiary",
    "lien_text",
)
# Model labels (ml/synth: FDR_NO, ISSUE_DATE, ...) lower-cased are these field names.


@dataclass
class FieldResult:
    pass_a: str | None
    pass_b: str | None
    value: str | None
    confidence: float
    needs_review: bool
    reason: str | None = None


@dataclass
class ExtractionResult:
    fields: dict[str, FieldResult] = field(default_factory=dict)
    pass_a_available: bool = False
    ocr_lines: list[OcrLine] = field(default_factory=list)
    forgery: ForgeryResult | None = None
    forgery_field: str | None = None  # field read from the suspicious region, if any


def extract(image: Image.Image, rules: dict, models_dir: str) -> ExtractionResult:
    lines = run_ocr(image)
    pass_b = extract_fields(lines, rules)
    raw_a = layoutlm.extract(image, lines, models_dir)
    threshold = rules["human_review_below"]
    regions = forgery_model.text_regions(lines, rules)
    result = ExtractionResult(
        pass_a_available=raw_a is not None,
        ocr_lines=lines,
        forgery=forgery_model.score(image, regions, models_dir),
    )
    if result.forgery and result.forgery.region_box:
        result.forgery_field = next(
            (n for n, f in pass_b.items() if f.box == result.forgery.region_box), None
        )

    for name in FIELDS:
        b = pass_b.get(name)
        a_raw = (raw_a or {}).get(name)
        a = _normalize(name, a_raw, rules) if a_raw else None
        value = b.normalized if b else a
        confidence = b.confidence if b else (0.5 if a else 0.0)
        reason = None
        if value is None:
            reason = "not found on the document"
        elif raw_a is not None and a != (b.normalized if b else None):
            reason = "the two extraction passes disagree"
        elif confidence < threshold:
            reason = f"confidence {confidence:.2f} below {threshold}"
        result.fields[name] = FieldResult(
            pass_a=a,
            pass_b=b.normalized if b else None,
            value=value,
            confidence=confidence,
            needs_review=reason is not None,
            reason=reason,
        )
    return result
