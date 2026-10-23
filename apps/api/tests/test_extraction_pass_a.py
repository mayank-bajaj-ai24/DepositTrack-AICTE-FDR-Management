"""Ignore rules shared by extraction and forgery, and the guards around pass A (N6)."""

import json

import pytest
from PIL import Image

from app.core.configfiles import load_config
from app.modules.extraction import layoutlm, service
from app.modules.extraction.ocr import OcrLine
from app.modules.extraction.rules import extract_fields, is_ignored
from app.modules.forgery.model import text_regions

RULES = load_config("extraction.yaml")
FDR_LABELS = {0: "O"} | {
    i + 1: f"{p}-{f.upper()}"
    for i, (p, f) in enumerate((p, f) for f in service.FIELDS for p in "BI")
}
FUNSD_LABELS = dict(enumerate(["O", "B-HEADER", "I-HEADER", "B-QUESTION", "I-QUESTION"]))


def line(text, x, y):
    return OcrLine(text, (x, y, x + 10 * len(text), y + 24), 0.99)


@pytest.mark.parametrize("value", [None, []])
def test_null_or_empty_ignore_lists_do_not_crash(value):
    rules = RULES | {"ignore_lines_equal": value, "ignore_lines_containing": value}
    lines = [line("Real Bank", 10, 40)]
    assert extract_fields(lines, rules)["bank"].normalized == "Real Bank"
    assert [t for t, _ in text_regions(lines, rules)] == ["Real Bank"]


def test_extraction_and_forgery_skip_the_same_padded_stamp_text():
    rules = RULES | {"ignore_lines_equal": ["Stamp Bank"], "ignore_lines_containing": ["copy"]}
    assert is_ignored(" STAMP BANK ", rules)
    assert is_ignored("Duplicate Copy", rules)
    assert not is_ignored("Stamp Bank Ltd", rules)
    lines = [line(" Stamp Bank ", 10, 10), line("Real Bank", 10, 40)]
    assert extract_fields(lines, rules)["bank"].normalized == "Real Bank"
    assert [t for t, _ in text_regions(lines, rules)] == ["Real Bank"]


def test_shipped_config_keeps_pass_a_off():
    assert RULES["pass_a_enabled"] is False


def test_labels_must_map_onto_fdr_fields():
    assert layoutlm.labels_match_fields(FDR_LABELS, service.FIELDS)
    assert not layoutlm.labels_match_fields(FUNSD_LABELS, service.FIELDS)
    assert not layoutlm.labels_match_fields({0: "O"}, service.FIELDS)


def _model_dir(tmp_path, id2label, metrics=None):
    path = tmp_path / layoutlm.MODEL_SUBDIR
    path.mkdir()
    (path / "config.json").write_text(json.dumps({"id2label": id2label}), encoding="utf-8")
    if metrics is not None:
        (path / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
    return path


def test_fdr_labelled_model_is_usable(tmp_path):
    assert layoutlm.model_is_usable(_model_dir(tmp_path, FDR_LABELS))


def test_funsd_proxy_model_is_refused(tmp_path):
    path = _model_dir(tmp_path, FUNSD_LABELS, {"live_extraction": False})
    assert not layoutlm.model_is_usable(path)
    assert not layoutlm.is_available(str(tmp_path))


def test_model_marked_not_live_is_refused_even_with_fdr_labels(tmp_path):
    assert not layoutlm.model_is_usable(
        _model_dir(tmp_path, FDR_LABELS, {"live_extraction": False})
    )


def test_missing_folder_is_not_usable(tmp_path):
    assert not layoutlm.model_is_usable(tmp_path / "absent")


def test_pass_a_is_not_called_when_disabled(monkeypatch, tmp_path):
    lines = [line("Real Bank", 10, 40)]
    monkeypatch.setattr(service, "run_ocr", lambda image: lines)
    calls = []
    monkeypatch.setattr(layoutlm, "extract", lambda *a: calls.append(a) or {"bank": "Other"})
    image = Image.new("RGB", (600, 100), "white")

    result = service.extract(image, RULES | {"pass_a_enabled": False}, str(tmp_path))
    assert calls == []
    assert result.pass_a_available is False
    assert result.fields["bank"].reason is None or "disagree" not in result.fields["bank"].reason

    result = service.extract(image, RULES | {"pass_a_enabled": True}, str(tmp_path))
    assert len(calls) == 1
    assert result.fields["bank"].reason == "the two extraction passes disagree"
