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
    box: tuple[int, int, int, int] | None = None  # OCR line the value was read from


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


def _fix_characters(value: str, spec: dict) -> str:
    """Set the characters a field always has at a position (`fixed_characters` in the YAML)."""
    chars = list(value)
    for position, char in (spec.get("fixed_characters") or {}).items():
        if int(position) < len(chars):
            chars[int(position)] = char
    return "".join(chars)


def _normalize(field: str, raw: str, rules: dict) -> str | None:
    if field == "amount":
        return normalize_amount(raw)
    if field in ("issue_date", "maturity_date"):
        return normalize_date(raw, rules["date_formats"])
    if field in ("ifsc", "fdr_no"):
        return _fix_characters(raw.replace(" ", "").upper(), rules["fields"][field])
    return " ".join(raw.split())


def _match_pattern(spec: dict, text: str, captioned: bool = False) -> str | None:
    """The value in `text`. Next to a caption, a looser `caption_pattern` may apply."""
    pattern = (captioned and spec.get("caption_pattern")) or spec.get("pattern")
    if not pattern:
        return text
    found = re.search(pattern, text)
    return found.group(0) if found else None


def _starts_with(text: str, caption: str) -> bool:
    return text.lower().startswith(caption.lower())


def _starts_with_word(text: str, caption: str) -> bool:
    """`caption` starts `text` and ends at a non-letter: "Depositor Name: X" yes,
    "Depositor Namespace Trust" no."""
    rest = text[len(caption) :]
    return _starts_with(text, caption) and not (rest and rest[0].isalpha())


def _shadowed(text: str, caption: str, captions: list[str]) -> bool:
    """True when a longer caption of the same field that begins with `caption` also starts
    `text`: "Depositor Name: X" is never read as "Depositor" + "Name: X", even when the
    longer caption finds no value on that line."""
    return any(
        len(other) > len(caption)
        and _starts_with(other, caption)
        and _starts_with_word(text, other)
        for other in captions
    )


def is_ignored(text: str, rules: dict) -> bool:
    """True for text that is never a field value (configured watermark or stamp text).

    Compared stripped and case-insensitively. A list key that is present but empty or null
    in the YAML means "nothing to ignore".
    """
    low = text.strip().lower()
    if not low:
        return True
    if low in {s.lower() for s in rules.get("ignore_lines_equal") or []}:
        return True
    return any(s.lower() in low for s in rules.get("ignore_lines_containing") or [])


def extract_fields(lines: list[OcrLine], rules: dict) -> dict[str, ExtractedField]:
    usable = [line for line in lines if line.text and not is_ignored(line.text, rules)]
    rows = _rows(usable, rules["row_tolerance_px"])
    out: dict[str, ExtractedField] = {}

    def keep(field: str, raw: str, score: float, box=None) -> None:
        normalized = _normalize(field, raw, rules)
        if normalized and field not in out:
            out[field] = ExtractedField(
                raw=raw, normalized=normalized, confidence=round(score, 3), box=box
            )

    for field, spec in rules["fields"].items():
        # 1. caption on a line; value after it on the same line or the next line in the row.
        # Captions are tried in the YAML's order (its priority).
        captions = spec.get("captions", [])
        for caption in captions:
            for row in rows:
                for index, line in enumerate(row):
                    if not _starts_with(line.text, caption) or _shadowed(
                        line.text, caption, captions
                    ):
                        continue
                    sources = [(_strip_caption(line.text, caption), line)]
                    sources += [(other.text, other) for other in row[index + 1 :]]
                    # The looser caption_pattern applies only to the caption's own line;
                    # other lines in the row are ordinary text and use the strict pattern.
                    for position, (candidate, source) in enumerate(sources):
                        value = (
                            _match_pattern(spec, candidate, captioned=position == 0)
                            if candidate
                            else None
                        )
                        if value:
                            keep(field, value, source.score, source.box)
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
                keep(field, line.text, line.score, line.box)
                break
        if field in out:
            continue
        # 3. positional rule
        if spec.get("position") == "top" and usable:
            top = min(usable, key=lambda line: line.box[1])
            keep(field, top.text, top.score, top.box)
            continue
        # 4. pattern anywhere on the page
        if spec.get("search_anywhere"):
            for line in usable:
                value = _match_pattern(spec, line.text)
                if value:
                    keep(field, value, line.score * 0.9, line.box)  # weaker: no caption context
                    break
    return out
