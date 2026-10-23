"""Serve the renewal-risk model (N9): probability of a missed renewal, with reasons.

Loads a model from <models_dir>/renewal_risk/ when one trained on DepositTrack's own
renewal history is placed there; until then live scoring is off. ml/risk/train.py
measures the method on a public proxy log and writes to renewal_risk_proxy/, which is
not loaded here. Reasons are the features with the largest SHAP contributions towards
"late", in plain language.
"""

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from app.modules.risk.features import FEATURE_NAMES, History, describe, features

MODEL_SUBDIR = "renewal_risk"


@dataclass(frozen=True)
class RiskResult:
    probability: float
    expected_days_late: float | None
    reasons: list[dict]


@lru_cache
def _load(models_dir: str):
    path = Path(models_dir) / MODEL_SUBDIR
    if not (path / "classifier.txt").exists():
        return None
    import lightgbm as lgb

    meta = json.loads((path / "meta.json").read_text(encoding="utf-8"))
    if meta["features"] != FEATURE_NAMES:
        return None
    classifier = lgb.Booster(model_file=str(path / "classifier.txt"))
    regressor_path = path / "regressor.txt"
    regressor = lgb.Booster(model_file=str(regressor_path)) if regressor_path.exists() else None
    return classifier, regressor, meta


def is_available(models_dir: str) -> bool:
    return _load(models_dir) is not None


def predict(history: History, models_dir: str, top: int = 3) -> RiskResult | None:
    loaded = _load(models_dir)
    if loaded is None:
        return None
    classifier, regressor, _ = loaded
    row = np.array([features(history)])
    probability = float(classifier.predict(row)[0])
    contributions = classifier.predict(row, pred_contrib=True)[0][:-1]  # last is the bias
    order = np.argsort(-contributions)
    reasons = [
        {
            "feature": FEATURE_NAMES[i],
            "value": float(row[0][i]),
            "contribution": round(float(contributions[i]), 4),
            "text": describe(FEATURE_NAMES[i], float(row[0][i])),
        }
        for i in order[:top]
        if contributions[i] > 0
    ]
    late = float(regressor.predict(row)[0]) if regressor is not None else None
    return RiskResult(round(probability, 4), round(late, 1) if late is not None else None, reasons)
