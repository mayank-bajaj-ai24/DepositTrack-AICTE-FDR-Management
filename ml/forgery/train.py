"""Train the forgery signal on synthetic FDRs and report page-level metrics.

Run with the API's virtual environment (it holds the feature code and ML extras):

    ml/synth/.venv/Scripts/python -m fdrsynth --count 600 --out data/forgery-src --seed 2026
    apps/api/.venv/Scripts/python ml/forgery/train.py --data data/forgery-src --out models

Writes models/forgery/{model.joblib, meta.json, metrics.json}. All numbers are on
synthetic data and must be labelled as such.
"""

import argparse
import json
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from tamper import OPERATIONS, field_regions, recompress, tamper  # noqa: E402

from app.core.configfiles import load_config  # noqa: E402
from app.modules.extraction.ocr import run_ocr  # noqa: E402
from app.modules.extraction.rules import extract_fields  # noqa: E402
from app.modules.forgery.features import FEATURE_NAMES, page_features  # noqa: E402

RULES = load_config("extraction.yaml")


def _overlap(a, b) -> float:
    """Intersection over the smaller box's area."""
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    smaller = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1])) or 1
    return ix * iy / smaller


def runtime_regions(image):
    """The same regions the API scores: OCR lines that pass B read each field from."""
    lines = run_ocr(image)
    fields = extract_fields(lines, RULES)
    return [(name, f.box) for name, f in fields.items() if f.box is not None]


def build(records: list[Path], seed: int):
    rng = random.Random(seed)
    X, y, pages = [], [], []
    for page_index, path in enumerate(records):
        record = json.loads(path.read_text(encoding="utf-8"))
        image = Image.open(path.with_suffix(".png")).convert("RGB")
        truth = field_regions(record)
        if len(truth) < 3:
            continue
        forged = rng.random() < 0.5
        target = rng.randrange(len(truth)) if forged else None
        operation = rng.choice(OPERATIONS) if forged else None
        if forged:
            image = tamper(image, truth, target, operation, rng)
        image = recompress(image, rng)
        regions = runtime_regions(image)
        if len(regions) < 3:
            continue
        matrix = page_features(image, [box for _, box in regions])
        for (_, box), row in zip(regions, matrix, strict=True):
            X.append(row)
            y.append(int(forged and _overlap(box, truth[target][1]) > 0.5))
            pages.append((page_index, forged, operation))
        if page_index % 50 == 0:
            print(f"  {page_index} pages", flush=True)
    return np.array(X), np.array(y), pages


def page_scores(model, X, pages):
    probabilities = model.predict_proba(X)[:, 1]
    by_page: dict[int, tuple[bool, str | None, float]] = {}
    for (page, forged, op), p in zip(pages, probabilities, strict=True):
        current = by_page.get(page, (forged, op, 0.0))
        by_page[page] = (forged, op, max(current[2], float(p)))
    return by_page


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=ROOT / "models")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--target-false-alarm", type=float, default=0.05)
    args = parser.parse_args()

    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.svm import SVC

    records = sorted(args.data.glob("*.json"))
    split = int(len(records) * 0.7)
    X_train, y_train, _ = build(records[:split], args.seed)
    X_test, y_test, pages_test = build(records[split:], args.seed + 1)

    svm = SVC(kernel="rbf", C=4.0, class_weight="balanced", random_state=args.seed)
    model = make_pipeline(StandardScaler(), CalibratedClassifierCV(svm, cv=5))
    model.fit(X_train, y_train)

    scores = page_scores(model, X_test, pages_test)
    genuine = sorted(s for forged, _, s in scores.values() if not forged)
    # "suspicious" threshold keeps false alarms on genuine pages at the target rate
    suspicious = float(np.quantile(genuine, 1 - args.target_false_alarm)) if genuine else 0.5
    grey = float(np.quantile(genuine, 0.80)) if genuine else 0.3
    forged_pages = [(op, s) for forged, op, s in scores.values() if forged]
    recall = sum(s >= suspicious for _, s in forged_pages) / max(1, len(forged_pages))
    false_alarm = sum(s >= suspicious for s in genuine) / max(1, len(genuine))
    by_op: dict[str, list[int]] = {}
    for op, s in forged_pages:
        by_op.setdefault(op, []).append(int(s >= suspicious))

    metrics = {
        "data": "synthetic",
        "train_pages": split,
        "test_pages": len(records) - split,
        "suspicious_threshold": round(suspicious, 4),
        "grey_threshold": round(grey, 4),
        "page_recall_suspicious": round(recall, 4),
        "page_false_alarm_rate": round(false_alarm, 4),
        "recall_by_operation": {k: round(sum(v) / len(v), 3) for k, v in sorted(by_op.items())},
    }
    out = args.out / "forgery"
    out.mkdir(parents=True, exist_ok=True)
    import joblib

    joblib.dump(model, out / "model.joblib")
    (out / "meta.json").write_text(
        json.dumps({"features": FEATURE_NAMES, "bands": {"grey": grey, "suspicious": suspicious}, "classifier": "RBF SVM (Gornale et al. baseline) on RGB-GLCM + ELA + noise"}, indent=2),
        encoding="utf-8",
    )
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
