"""Pass B of extraction (N6): caption, position and pattern rules from config/extraction.yaml."""

import re
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import yaml

from app.modules.extraction.ocr import OcrLine


@dataclass(frozen=True)
class ExtractedField:
    raw: str
    normalized: str
    confidence: float


@lru_cache
def load_rules(path: str) -> dict:
    with open(Path(path), encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _rows(lines: list[OcrLine], tolerance: float) -> list[list[OcrLine]]:
    rows: list[list[OcrLine]] = []
    for line in sorted(lines, key=lambda line: line.y_center):
        if rows and abs(rows[-1][0].y_center - line.y_center) < tolerance:
            rows[-1].append(line)
        else:
            rows.append([line])
    return [sorted(row, key=lambda line: line.box[0]) for row in rows]


def _strip_caption(text: str, caption: str) -> str:
    rest = text[len(caption) :]
    return rest.lstrip(" .:-").strip()


AMOUNT_NUMBER = re.compile(r"[0-9][0-9,]*(?:\.[0-9]{1,2})?")


def normalize_amount(raw: str) -> str | None:
    """'Rs. 35,00,000/-' -> '3500000'; '₹ 1,250.50' -> '1250.50'."""
    found = AMOUNT_NUMBER.search(raw)
    if not found:
        return None
    value = float(found.group(0).replace(",", ""))
    return str(int(value)) if value.is_integer() else f"{value:.2f}"


def normalize_date(raw: str, formats: list[str]) -> str | None:
    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _normalize(field: str, raw: str, rules: dict) -> str | None:
    if field == "amount":
        return normalize_amount(raw)
    if field in ("issue_date", "maturity_date"):
        return normalize_date(raw, rules["date_formats"])
    if field in ("ifsc", "fdr_no"):
        return raw.replace(" ", "").upper()
    return " ".join(raw.split())


def _match_pattern(spec: dict, text: str) -> str | None:
    pattern = spec.get("pattern")
    if not pattern:
        return text
    found = re.search(pattern, text)
    return found.group(0) if found else None


def extract_fields(lines: list[OcrLine], rules: dict) -> dict[str, ExtractedField]:
    contains = [s.lower() for s in rules.get("ignore_lines_containing", [])]
    equal = {s.lower() for s in rules.get("ignore_lines_equal", [])}
    usable = [
        line
        for line in lines
        if line.text
        and line.text.lower() not in equal
        and not any(s in line.text.lower() for s in contains)
    ]
    rows = _rows(usable, rules["row_tolerance_px"])
    out: dict[str, ExtractedField] = {}

    def keep(field: str, raw: str, score: float) -> None:
        normalized = _normalize(field, raw, rules)
        if normalized and field not in out:
            out[field] = ExtractedField(raw=raw, normalized=normalized, confidence=round(score, 3))

    for field, spec in rules["fields"].items():
        # 1. caption on a line; value after it on the same line or the next line in the row
        for caption in spec.get("captions", []):
            for row in rows:
                for index, line in enumerate(row):
                    if not line.text.lower().startswith(caption.lower()):
                        continue
                    candidates = [_strip_caption(line.text, caption)]
                    candidates += [other.text for other in row[index + 1 :]]
                    for candidate, score in zip(
                        candidates, [line.score] + [o.score for o in row[index + 1 :]], strict=True
                    ):
                        value = _match_pattern(spec, candidate) if candidate else None
                        if value:
                            keep(field, value, score)
                            break
            if field in out:
                break
        if field in out:
            continue
        # 2. line starts with / contains a keyword
        for line in usable:
            text = line.text.lower()
            if any(text.startswith(k.lower()) for k in spec.get("starts_with", [])) or any(
                k.lower() in text for k in spec.get("contains", [])
            ):
                keep(field, line.text, line.score)
                break
        if field in out:
            continue
        # 3. positional rule
        if spec.get("position") == "top" and usable:
            top = min(usable, key=lambda line: line.box[1])
            keep(field, top.text, top.score)
            continue
        # 4. pattern anywhere on the page
        if spec.get("search_anywhere"):
            for line in usable:
                value = _match_pattern(spec, line.text)
                if value:
                    keep(field, value, line.score * 0.9)  # weaker: no caption context
                    break
    return out
