"""Renewal-risk model loading (N9): only an explicitly live model is served."""

import json
from datetime import date, timedelta

import numpy as np
import pytest

from app.models import Instrument
from app.modules.lifecycle.states import InstrumentKind, InstrumentState
from app.modules.risk import model as risk_model
from app.modules.risk.features import FEATURE_NAMES
from app.modules.risk.service import score_live
from tests.flow_support import make_sessionmaker, seed

lgb = pytest.importorskip("lightgbm")


def _place(models_dir, meta: dict | None, *, classifier: bool = True):
    path = models_dir / risk_model.MODEL_SUBDIR
    path.mkdir(parents=True, exist_ok=True)
    if classifier:
        rng = np.random.default_rng(0)
        X = rng.normal(size=(200, len(FEATURE_NAMES)))
        y = (X[:, 0] > 0).astype(int)
        booster = lgb.train(
            {"objective": "binary", "verbose": -1, "min_data_in_leaf": 5},
            lgb.Dataset(X, y, feature_name=FEATURE_NAMES),
            num_boost_round=3,
        )
        booster.save_model(str(path / "classifier.txt"))
    if meta is not None:
        (path / "meta.json").write_text(json.dumps(meta), encoding="utf-8")


LIVE = {"features": FEATURE_NAMES, "alarm_threshold": 0.5, "live_scoring": True}


def test_no_model_directory_is_unavailable(tmp_path):
    assert not risk_model.is_available(str(tmp_path))


def test_classifier_without_meta_is_unavailable_not_an_error(tmp_path):
    _place(tmp_path, None)
    assert not risk_model.is_available(str(tmp_path))


@pytest.mark.parametrize(
    "meta",
    [
        {"features": FEATURE_NAMES, "alarm_threshold": 0.7},  # older simulator-trained model
        LIVE | {"live_scoring": False},
        LIVE | {"features": FEATURE_NAMES[:-1]},
    ],
)
def test_model_not_marked_live_or_with_other_features_is_refused(tmp_path, meta):
    _place(tmp_path, meta)
    assert not risk_model.is_available(str(tmp_path))


def test_model_placed_while_running_is_picked_up(tmp_path):
    assert not risk_model.is_available(str(tmp_path))
    _place(tmp_path, LIVE)
    assert risk_model.is_available(str(tmp_path))
    _place(tmp_path, LIVE | {"live_scoring": False}, classifier=False)
    assert not risk_model.is_available(str(tmp_path))


def test_scores_from_an_earlier_model_are_cleared_when_none_is_loaded(tmp_path):
    factory = make_sessionmaker()
    ids = seed(factory, date.today())
    with factory() as s:
        inst = Instrument(
            institution_id=ids["a"],
            kind=InstrumentKind.FDR,
            instrument_no="R1",
            instrument_no_norm="R1",
            amount=100000,
            maturity_date=date.today() + timedelta(days=30),
            state=InstrumentState.ACTIVE,
            risk_score=0.8,
            risk_reasons={"reasons": []},
        )
        s.add(inst)
        s.commit()
        assert score_live(s, str(tmp_path), date.today()) == []
        s.refresh(inst)
        assert inst.risk_score is None
        assert inst.risk_reasons is None
