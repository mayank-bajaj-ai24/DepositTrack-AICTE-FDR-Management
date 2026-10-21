"""Load the trained forgery classifier and score a document (one signal among several).

The model is trained by ml/forgery/train.py and saved to <models_dir>/forgery/.
Without it, forgery scoring is reported as unavailable; the bank cross-check remains
the final word on a document in any case.
"""

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image

from app.modules.forgery.features import FEATURE_NAMES, page_features

MODEL_SUBDIR = "forgery"


def text_regions(lines, rules: dict) -> list[tuple[str, tuple[int, int, int, int]]]:
    """Every OCR text line except watermark fragments: the regions the model scores.

    All lines are scored (not only the ones a field was read from), so a re-typed value
    that extraction no longer recognises is still examined.
    """
    contains = [s.lower() for s in rules.get("ignore_lines_containing", [])]
    equal = {s.lower() for s in rules.get("ignore_lines_equal", [])}
    out = []
    for line in lines:
        text = line.text.strip()
        low = text.lower()
        if len(text) < 2 or low in equal or any(s in low for s in contains):
            continue
        out.append((text, line.box))
    return out


@dataclass(frozen=True)
class ForgeryResult:
    score: float  # highest region probability of tampering, 0..1
    band: str  # genuine | grey | suspicious
    region_index: int | None
    region_text: str | None
    region_box: tuple[int, int, int, int] | None


@lru_cache
def _load(models_dir: str):
    path = Path(models_dir) / MODEL_SUBDIR
    if not (path / "model.joblib").exists():
        return None
    import joblib

    meta = json.loads((path / "meta.json").read_text(encoding="utf-8"))
    if meta["features"] != FEATURE_NAMES:
        return None
    return joblib.load(path / "model.joblib"), meta


def is_available(models_dir: str) -> bool:
    return _load(models_dir) is not None


def score(
    image: Image.Image, regions: list[tuple[str, tuple[int, int, int, int]]], models_dir: str
) -> ForgeryResult | None:
    loaded = _load(models_dir)
    if loaded is None or len(regions) < 3:
        return None
    model, meta = loaded
    matrix = page_features(image, [box for _, box in regions])
    probabilities = model.predict_proba(matrix)[:, 1]
    index = int(probabilities.argmax())
    top = float(probabilities[index])
    grey, suspicious = meta["bands"]["grey"], meta["bands"]["suspicious"]
    band = "suspicious" if top >= suspicious else "grey" if top >= grey else "genuine"
    return ForgeryResult(
        score=round(top, 4),
        band=band,
        region_index=index if band != "genuine" else None,
        region_text=regions[index][0] if band != "genuine" else None,
        region_box=regions[index][1] if band != "genuine" else None,
    )
