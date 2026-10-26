"""Load the trained forgery classifier and score a document (one signal among several).

The model is trained by ml/forgery/train.py and saved to <models_dir>/forgery/.
Without it, forgery scoring is reported as unavailable; the bank cross-check remains
the final word on a document in any case. A model is loaded only when its meta.json lists
FEATURE_NAMES, sets "live_scoring": true (the maintainer sets it after reviewing the result,
AGENTS.md rule 5; train.py writes false), names its "training_data" and has both bands. The
training data goes into the system status and every forgery flag's reason, so a live model is
always labelled with what it was trained on. The files are re-read when they change, so
switching a model on or off takes effect without restarting the API.
"""

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image

from app.modules.extraction.rules import is_ignored
from app.modules.forgery.features import FEATURE_NAMES, page_features

MODEL_SUBDIR = "forgery"


def text_regions(lines, rules: dict) -> list[tuple[str, tuple[int, int, int, int]]]:
    """Every OCR text line except configured ignore text: the regions the model scores.

    All lines are scored (not only the ones a field was read from), so a re-typed value
    that extraction no longer recognises is still examined. The ignore rule is the one
    extraction uses (rules.is_ignored), so both skip the same lines.
    """
    out = []
    for line in lines:
        text = line.text.strip()
        if len(text) < 2 or is_ignored(text, rules):
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
    training_data: str | None = None  # what the model was trained on, for the flag's reason


MODEL_FILES = ("model.joblib", "meta.json")


def _stamp(path: Path) -> tuple:
    return tuple(
        (path / name).stat().st_mtime_ns if (path / name).exists() else None for name in MODEL_FILES
    )


def _meta_is_live(meta) -> bool:
    if not isinstance(meta, dict) or meta.get("live_scoring") is not True:
        return False
    if meta.get("features") != FEATURE_NAMES:
        return False
    if not isinstance(meta.get("training_data"), str) or not meta["training_data"]:
        return False
    bands = meta.get("bands")
    return isinstance(bands, dict) and all(
        isinstance(bands.get(k), int | float) for k in ("grey", "suspicious")
    )


@lru_cache(maxsize=4)
def _read(path_str: str, stamp: tuple):
    path = Path(path_str)
    if not (path / "model.joblib").exists():
        return None
    try:
        meta = json.loads((path / "meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not _meta_is_live(meta):
        return None
    import joblib

    return joblib.load(path / "model.joblib"), meta


def _load(models_dir: str):
    path = Path(models_dir) / MODEL_SUBDIR
    return _read(str(path), _stamp(path))


def status(models_dir: str) -> dict:
    """Availability and training data from one load, so they always agree."""
    loaded = _load(models_dir)
    return {
        "available": loaded is not None,
        "training_data": loaded[1]["training_data"] if loaded else None,
    }


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
        training_data=meta["training_data"],
    )
