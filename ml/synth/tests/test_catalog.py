import json
import random
from importlib import resources

import pytest

from fdrsynth.catalog import load_catalog
from fdrsynth.values import random_values


def _default_data() -> dict:
    text = resources.files("fdrsynth").joinpath("data/synthetic_lists.json").read_text("utf-8")
    return json.loads(text)


def _write(tmp_path, **overrides):
    data = _default_data() | overrides
    path = tmp_path / "lists.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_default_catalog_loads():
    catalog = load_catalog()
    assert catalog.banks
    assert catalog.cities


def test_custom_catalog_drives_values(tmp_path):
    path = _write(
        tmp_path,
        banks=[{"name": "Only Test Bank", "ifsc_prefix": "XOTB"}],
        cities=["Testpur"],
        beneficiary="Test Beneficiary",
    )
    values = random_values(random.Random(1), load_catalog(path))
    assert values.bank == "Only Test Bank"
    assert values.ifsc.startswith("XOTB0")
    assert values.branch.startswith("Testpur")
    assert values.beneficiary == "Test Beneficiary"


def test_missing_key_rejected(tmp_path):
    data = _default_data()
    del data["cities"]
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="cities"):
        load_catalog(path)


def test_bad_ifsc_prefix_rejected(tmp_path):
    path = _write(tmp_path, banks=[{"name": "Bad", "ifsc_prefix": "X1"}])
    with pytest.raises(ValueError, match="IFSC prefix"):
        load_catalog(path)


def test_empty_list_rejected(tmp_path):
    path = _write(tmp_path, tenure_months=[])
    with pytest.raises(ValueError, match="tenure_months"):
        load_catalog(path)
