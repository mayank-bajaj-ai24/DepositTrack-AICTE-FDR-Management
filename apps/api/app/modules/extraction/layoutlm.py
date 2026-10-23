"""Pass A of extraction (N6): a fine-tuned LayoutLMv3 token classifier, when enabled.

Pass A is off unless `pass_a_enabled: true` is set in config/extraction.yaml (it stays off
until a model trained on labelled real FDRs exists). Such a model is saved to
<models_dir>/layoutlmv3-fdr/ and must label words with "O" or B-/I- tags whose suffix,
lower-cased, is a field in service.FIELDS (FDR_NO, BANK, ..., LIEN_TEXT); a folder whose
labels do not map onto those fields, or whose metrics.json says "live_extraction": false
(as the FUNSD proxy from ml/layoutlm/train_layoutlmv3_funsd_proxy.ipynb does), is refused.
Without a valid folder, or without `transformers` and `torch` installed, pass A is
reported as unavailable and pass B is used alone.
"""

import json
from functools import lru_cache
from pathlib import Path

from PIL import Image

from app.modules.extraction.ocr import OcrLine

MODEL_SUBDIR = "layoutlmv3-fdr"


def labels_match_fields(id2label: dict, fields) -> bool:
    """True when every label is "O" or B-/I- plus a field name (upper case), and some are."""
    wanted = {f.upper() for f in fields}
    tags = set()
    for label in id2label.values():
        if label == "O":
            continue
        prefix, _, tag = str(label).partition("-")
        if prefix not in ("B", "I") or tag not in wanted:
            return False
        tags.add(tag)
    return bool(tags)


def model_is_usable(path: Path) -> bool:
    """Checks on the saved files alone, before any model library is imported."""
    from app.modules.extraction.service import FIELDS

    try:
        config = json.loads((path / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    metrics_path = path / "metrics.json"
    if metrics_path.exists():
        try:
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        except ValueError:
            return False
        if isinstance(metrics, dict) and metrics.get("live_extraction") is False:
            return False
    return labels_match_fields(config.get("id2label") or {}, FIELDS)


@lru_cache
def _load(model_dir: str):
    path = Path(model_dir) / MODEL_SUBDIR
    if not model_is_usable(path):
        return None
    try:
        import torch  # noqa: F401
        from transformers import AutoModelForTokenClassification, AutoProcessor
    except ImportError:
        return None
    processor = AutoProcessor.from_pretrained(path, apply_ocr=False)
    model = AutoModelForTokenClassification.from_pretrained(path)
    model.eval()
    return processor, model


def is_available(model_dir: str) -> bool:
    return _load(model_dir) is not None


def extract(image: Image.Image, lines: list[OcrLine], model_dir: str) -> dict[str, str] | None:
    """Return {field: text} predicted by the model, or None when pass A is unavailable."""
    loaded = _load(model_dir)
    if loaded is None or not lines:
        return None
    import torch

    processor, model = loaded
    width, height = image.size
    words, boxes, owners = [], [], []
    for line in lines:
        for token in line.text.split():
            words.append(token)
            x0, y0, x1, y1 = line.box
            boxes.append(
                [
                    int(1000 * x0 / width),
                    int(1000 * y0 / height),
                    int(1000 * x1 / width),
                    int(1000 * y1 / height),
                ]
            )
            owners.append(len(words) - 1)
    encoding = processor(
        image, words, boxes=boxes, return_tensors="pt", truncation=True, padding="max_length"
    )
    with torch.no_grad():
        logits = model(**encoding).logits[0]
    predictions = logits.argmax(-1).tolist()
    word_ids = encoding.word_ids(0)
    labels: dict[int, str] = {}
    for token_index, word_id in enumerate(word_ids):
        if word_id is not None and word_id not in labels:
            labels[word_id] = model.config.id2label[predictions[token_index]]
    fields: dict[str, list[str]] = {}
    for word_id, label in sorted(labels.items()):
        if label == "O":
            continue
        name = label.split("-", 1)[-1].lower()
        fields.setdefault(name, []).append(words[word_id])
    return {name: " ".join(tokens) for name, tokens in fields.items()}
