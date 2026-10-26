"""Guards on loading the forgery model: features, live_scoring and the training-data label."""

import json

import joblib
import pytest

from app.modules.forgery import model as forgery_model
from app.modules.forgery.features import FEATURE_NAMES

LIVE = {
    "features": FEATURE_NAMES,
    "bands": {"grey": 0.3, "suspicious": 0.6},
    "training_data": "synthetic FDRs (ml/synthetic_fdr)",
    "live_scoring": True,
}


def _place(tmp_path, meta) -> str:
    path = tmp_path / forgery_model.MODEL_SUBDIR
    path.mkdir()
    joblib.dump({"stand-in": "classifier"}, path / "model.joblib")
    (path / "meta.json").write_text(
        meta if isinstance(meta, str) else json.dumps(meta), encoding="utf-8"
    )
    return str(tmp_path)


def test_live_model_loads_and_names_its_training_data(tmp_path):
    models_dir = _place(tmp_path, LIVE)
    assert forgery_model.status(models_dir) == {
        "available": True,
        "training_data": "synthetic FDRs (ml/synthetic_fdr)",
    }


@pytest.mark.parametrize(
    "meta",
    [
        LIVE | {"live_scoring": False},
        {k: v for k, v in LIVE.items() if k != "live_scoring"},
        LIVE | {"live_scoring": "true"},
        LIVE | {"features": FEATURE_NAMES[:-1]},
        {k: v for k, v in LIVE.items() if k != "training_data"},
        LIVE | {"training_data": ""},
        {k: v for k, v in LIVE.items() if k != "bands"},
        LIVE | {"bands": {"grey": 0.3}},
        "not json",
        [],
    ],
)
def test_model_without_approval_or_matching_features_is_refused(tmp_path, meta):
    models_dir = _place(tmp_path, meta)
    assert forgery_model.status(models_dir) == {"available": False, "training_data": None}


def test_no_model_means_unavailable(tmp_path):
    assert not forgery_model.is_available(str(tmp_path))


def test_switching_the_model_on_and_off_needs_no_restart(tmp_path):
    import os

    models_dir = _place(tmp_path, LIVE | {"live_scoring": False})
    assert not forgery_model.is_available(models_dir)
    meta = tmp_path / forgery_model.MODEL_SUBDIR / "meta.json"
    for live, step in ((True, 1), (False, 2)):
        meta.write_text(json.dumps(LIVE | {"live_scoring": live}), encoding="utf-8")
        stat = meta.stat()
        os.utime(meta, ns=(stat.st_atime_ns, stat.st_mtime_ns + step * 1_000_000_000))
        assert forgery_model.is_available(models_dir) is live
