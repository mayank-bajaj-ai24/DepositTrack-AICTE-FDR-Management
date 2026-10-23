"""OCR front end (M3): image or PDF bytes -> text lines with boxes and confidence."""

import io
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from PIL import Image


@dataclass(frozen=True)
class OcrLine:
    text: str
    box: tuple[int, int, int, int]  # x0, y0, x1, y1
    score: float

    @property
    def y_center(self) -> float:
        return (self.box[1] + self.box[3]) / 2


class UnsupportedDocumentError(ValueError):
    pass


@lru_cache
def _engine():
    from rapidocr import RapidOCR

    return RapidOCR()


def load_image(data: bytes, content_type: str | None) -> Image.Image:
    if (content_type or "").lower() == "application/pdf" or data[:4] == b"%PDF":
        raise UnsupportedDocumentError(
            "PDF upload needs a PDF renderer that is not installed yet; upload a PNG or JPG scan."
        )
    try:
        return Image.open(io.BytesIO(data)).convert("RGB")
    except Exception as exc:  # noqa: BLE001 - Pillow raises several types
        raise UnsupportedDocumentError("File is not a readable image") from exc


def run_ocr(image: Image.Image) -> list[OcrLine]:
    result = _engine()(np.asarray(image))
    if result.boxes is None:
        return []
    lines = []
    for box, text, score in zip(result.boxes, result.txts, result.scores, strict=True):
        xs = [int(p[0]) for p in box]
        ys = [int(p[1]) for p in box]
        lines.append(OcrLine(text.strip(), (min(xs), min(ys), max(xs), max(ys)), float(score)))
    return sorted(lines, key=lambda line: (line.box[1], line.box[0]))
