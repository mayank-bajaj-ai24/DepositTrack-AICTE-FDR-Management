"""Tests for ml/download_open_data.py (no network: kagglehub is replaced by a fake)."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import download_open_data as dod  # noqa: E402

GOOD = {
    "kaggle": "owner/slug/versions/2",
    "licence": "CC BY 4.0",
    "licence_confirmed": True,
    "citation": "A. Author, A dataset, 2020",
}


def write(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_shipped_catalog_is_valid_and_pinned():
    catalog = dod.load_catalog()
    assert catalog
    for entry in catalog.values():
        assert "/versions/" in entry["kaggle"]


def test_comment_keys_are_skipped_and_empty_key_is_reported(tmp_path):
    assert list(dod.load_catalog(write(tmp_path, {"_c": "x", "a": GOOD}))) == ["a"]
    with pytest.raises(dod.CatalogError, match="must not be empty"):
        dod.load_catalog(write(tmp_path, {"": GOOD}))


@pytest.mark.parametrize("key", ["kaggle", "licence", "licence_confirmed", "citation"])
def test_missing_key_is_a_clear_error(tmp_path, key):
    entry = {k: v for k, v in GOOD.items() if k != key}
    with pytest.raises(dod.CatalogError, match=f"missing {key}"):
        dod.load_catalog(write(tmp_path, {"a": entry}))


def test_unpinned_handle_is_rejected(tmp_path):
    with pytest.raises(dod.CatalogError, match="pin a version"):
        dod.load_catalog(write(tmp_path, {"a": GOOD | {"kaggle": "owner/slug"}}))


def test_target_dir_is_under_repo_data():
    assert dod.target_dir("bpi-2017", Path("/repo")) == Path("/repo/data/bpi-2017")


class FakeKaggle:
    def __init__(self, error: Exception | None = None):
        self.error, self.calls = error, []

    def dataset_download(self, handle, output_dir=None):
        self.calls.append((handle, output_dir))
        if self.error:
            raise self.error
        return output_dir


def test_download_passes_pinned_handle_and_output_dir(tmp_path):
    fake = FakeKaggle()
    out = tmp_path / "data" / "a"
    assert dod.download("a", GOOD, out, kagglehub=fake) == str(out)
    assert fake.calls == [("owner/slug/versions/2", str(out))]
    assert out.is_dir()


def test_auth_failure_exits_with_setup_steps(tmp_path):
    pytest.importorskip("kagglehub")
    from kagglehub.exceptions import UnauthenticatedError

    fake = FakeKaggle(UnauthenticatedError())
    with pytest.raises(SystemExit, match="access_token"):
        dod.download("a", GOOD, tmp_path, kagglehub=fake)


def test_unconfirmed_licence_is_refused_without_flag(monkeypatch, tmp_path):
    catalog = {"a": GOOD | {"licence_confirmed": False}}
    monkeypatch.setattr(dod, "load_catalog", lambda: catalog)
    calls = []
    monkeypatch.setattr(dod, "download", lambda *a, **k: calls.append(a) or "path")
    with pytest.raises(SystemExit, match="licence not confirmed"):
        dod.main(["a"])
    assert calls == []
    dod.main(["a", "--accept-unconfirmed-licence"])
    assert len(calls) == 1
