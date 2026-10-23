"""Merkle anchoring with immudb receipts (N4). immudb is replaced by an in-memory fake."""

import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.core import security
from app.core.config import get_settings
from app.db.session import get_session
from app.main import create_app
from app.models import Anchor, AnchorEvent, Event
from app.modules.audit import anchoring
from app.modules.audit.anchoring import (
    ImmudbStore,
    anchor_new_events,
    recompute_root,
    verify_anchor,
    write_receipt,
)
from app.modules.audit.hashchain import event_hash, merkle_root
from app.modules.audit.service import SYSTEM, event_payload, record_event
from tests.flow_support import make_sessionmaker, make_settings

IMMUDB_PASSWORD = "dev-only-test-password"


class FakeCorruptedData(Exception):
    """Stands in for immudb.exceptions.ErrCorruptedData."""


class FakeImmudb:
    """In-memory immudb: one entry per transaction, verified reads and writes."""

    def __init__(self):
        self.entries: dict[int, tuple[bytes, bytes]] = {}
        self.down = False
        self.corrupt_proofs = False
        self.login_attempts = 0
        self.timeout = None

    def module(self):
        server = self

        class Client:
            def __init__(self, url, timeout=None):
                server.url, server.timeout = url, timeout

            def login(self, user, password):
                server.login_attempts += 1
                if server.down:
                    raise ConnectionError("failed to connect to all addresses")
                if (user, password) != ("immudb", IMMUDB_PASSWORD):
                    raise PermissionError("invalid user name or password")

            def verifiedSet(self, key, value):  # noqa: N802 (immudb-py method name)
                tx = len(server.entries) + 1
                server.entries[tx] = (key, value)
                return SimpleNamespace(id=tx, verified=True)

            def verifiedGetAt(self, key, tx):  # noqa: N802
                if server.corrupt_proofs:
                    raise FakeCorruptedData()
                stored = server.entries.get(tx)
                if stored is None or stored[0] != key:
                    raise LookupError("key not found")
                return SimpleNamespace(id=tx, key=key, value=stored[1], verified=True)

            def logout(self):
                pass

        return SimpleNamespace(
            ImmudbClient=Client, exceptions=SimpleNamespace(ErrCorruptedData=FakeCorruptedData)
        )


@pytest.fixture
def immudb(monkeypatch):
    fake = FakeImmudb()
    monkeypatch.setattr(anchoring, "_load_client_module", fake.module)
    monkeypatch.setattr(anchoring, "client_installed", lambda: True)
    return fake


def _settings(tmp_path, **overrides):
    base = {"immudb_enabled": True, "immudb_password": IMMUDB_PASSWORD} | overrides
    return make_settings(tmp_path).model_copy(update=base)


def _events(session, n=3):
    """Events on the system chain, so no instrument rows are needed."""
    for i in range(n):
        record_event(session, actor=SYSTEM, action=f"test.event{i}")
    session.commit()


# --- batch membership -------------------------------------------------------------------


def test_each_event_is_anchored_exactly_once():
    factory = make_sessionmaker()
    with factory() as s:
        _events(s, 3)
        first = anchor_new_events(s)
        s.commit()
        assert anchor_new_events(s) is None
        _events(s, 2)
        second = anchor_new_events(s)
        s.commit()
        counts = dict(
            s.execute(
                select(AnchorEvent.anchor_id, func.count()).group_by(AnchorEvent.anchor_id)
            ).all()
        )
        assert counts == {first.id: 3, second.id: 2}
        assert s.scalar(select(func.count()).select_from(Event)) == 5


def test_late_event_with_an_old_timestamp_goes_into_the_next_anchor():
    """An event committed after an anchor but stamped at (or before) its batch_end.

    The old `ts > batch_end` selection skipped it forever, and the old `ts BETWEEN` check
    then counted it in the earlier batch and reported a false mismatch.
    """
    factory = make_sessionmaker()
    with factory() as s:
        _events(s, 2)
        first = anchor_new_events(s)
        s.commit()
        late = record_event(s, actor=SYSTEM, action="test.late")
        late.ts = first.batch_end
        late.hash = event_hash(late.prev_hash, event_payload(late))
        same_time = record_event(s, actor=SYSTEM, action="test.earlier")
        same_time.ts = first.batch_start - timedelta(seconds=1)
        same_time.hash = event_hash(same_time.prev_hash, event_payload(same_time))
        s.commit()

        second = anchor_new_events(s)
        s.commit()
        assert second is not None
        members = set(
            s.scalars(select(AnchorEvent.event_id).where(AnchorEvent.anchor_id == second.id))
        )
        assert members == {late.id, same_time.id}
        assert verify_anchor(s, first).valid
        assert verify_anchor(s, second).valid


def test_root_is_recomputed_in_the_anchored_leaf_order():
    factory = make_sessionmaker()
    with factory() as s:
        _events(s, 3)
        anchor = anchor_new_events(s)
        s.commit()
        ordered = s.scalars(
            select(Event)
            .join(AnchorEvent, AnchorEvent.event_id == Event.id)
            .order_by(AnchorEvent.position)
        ).all()
        assert recompute_root(s, anchor) == merkle_root([e.hash for e in ordered])
        assert anchor.merkle_root == recompute_root(s, anchor)


# --- receipts ----------------------------------------------------------------------------


def test_receipt_is_written_and_read_back(tmp_path, immudb):
    settings = _settings(tmp_path)
    factory = make_sessionmaker()
    with factory() as s:
        _events(s)
        anchor = anchor_new_events(s)
        s.commit()
        with ImmudbStore(settings) as store:
            write_receipt(anchor, store)
        s.commit()
        assert anchor.store_tx == "1"
        assert anchor.store_error is None
        assert immudb.entries[1] == (
            f"depositrack:anchor:{anchor.id}".encode(),
            anchor.merkle_root.encode(),
        )
        assert immudb.timeout == settings.immudb_timeout_seconds
        with ImmudbStore(settings) as store:
            check = verify_anchor(s, anchor, store)
        assert (check.valid, check.receipt) == (True, "verified")


def test_insider_editing_events_and_anchor_row_together_is_caught_by_the_receipt(tmp_path, immudb):
    settings = _settings(tmp_path)
    factory = make_sessionmaker()
    with factory() as s:
        _events(s)
        anchor = anchor_new_events(s)
        s.commit()
        with ImmudbStore(settings) as store:
            write_receipt(anchor, store)
        s.commit()

        s.execute(update(Event).where(Event.action == "test.event1").values(reason="edited"))
        s.expire_all()
        anchor.merkle_root = recompute_root(s, anchor)  # the anchor row is edited to match
        s.commit()

        with ImmudbStore(settings) as store:
            check = verify_anchor(s, anchor, store)
        assert check.root_matches  # the database alone looks consistent
        assert check.receipt == "mismatch"
        assert not check.valid
        # Without the external receipt only the local check is possible.
        local_only = verify_anchor(s, anchor)
        assert (local_only.valid, local_only.receipt) == (True, "unchecked")


def test_failed_immudb_proof_counts_as_a_mismatch(tmp_path, immudb):
    settings = _settings(tmp_path)
    factory = make_sessionmaker()
    with factory() as s:
        _events(s)
        anchor = anchor_new_events(s)
        with ImmudbStore(settings) as store:
            write_receipt(anchor, store)
        s.commit()
        immudb.corrupt_proofs = True
        with ImmudbStore(settings) as store:
            check = verify_anchor(s, anchor, store)
        assert (check.valid, check.receipt) == (False, "mismatch")
        assert "did not verify" in check.detail


def test_receipt_pointing_at_another_tx_is_a_mismatch(tmp_path, immudb):
    settings = _settings(tmp_path)
    factory = make_sessionmaker()
    with factory() as s:
        _events(s)
        anchor = anchor_new_events(s)
        with ImmudbStore(settings) as store:
            write_receipt(anchor, store)
            store.put("depositrack:anchor:other", "0" * 64)
        anchor.store_tx = "not-a-number"
        assert verify_anchor(s, anchor, ImmudbStore(settings)).receipt == "mismatch"
        anchor.store_key = "depositrack:anchor:other"
        anchor.store_tx = "2"
        with ImmudbStore(settings) as store:
            check = verify_anchor(s, anchor, store)
        assert (check.valid, check.receipt) == (False, "mismatch")
        assert "different root" in check.detail
        anchor.store_tx = "99"  # immudb has no such entry
        with ImmudbStore(settings) as store:
            check = verify_anchor(s, anchor, store)
        assert (check.valid, check.receipt) == (False, "mismatch")
        assert "no entry" in check.detail


def test_login_failure_keeps_the_anchor_and_records_why(tmp_path, immudb):
    settings = _settings(tmp_path, immudb_password="dev-only-wrong")
    factory = make_sessionmaker()
    with factory() as s:
        _events(s)
        anchor = anchor_new_events(s)
        s.commit()
        with ImmudbStore(settings) as store:
            write_receipt(anchor, store)
        s.commit()
        assert anchor.store_tx is None
        assert "invalid user name or password" in anchor.store_error
        assert "IMMUDB_ADMIN_PASSWORD" in anchor.store_error
        assert s.get(Anchor, anchor.id) is not None
        check = verify_anchor(s, anchor)
        assert (check.valid, check.receipt) == (True, "none")
        assert "the immudb write failed" in check.detail


def test_unreachable_immudb_is_tried_once_per_request(tmp_path, immudb):
    settings = _settings(tmp_path)
    factory = make_sessionmaker()
    with factory() as s:
        anchors = []
        for _ in range(3):
            _events(s, 1)
            anchor = anchor_new_events(s)
            with ImmudbStore(settings) as store:
                write_receipt(anchor, store)
            anchors.append(anchor)
        s.commit()
        immudb.down = True
        immudb.login_attempts = 0
        with ImmudbStore(settings) as store:
            checks = [verify_anchor(s, a, store) for a in anchors]
        assert immudb.login_attempts == 1
        assert {c.receipt for c in checks} == {"unchecked"}
        assert all(c.valid for c in checks)  # local check still runs
        assert "failed to connect" in checks[0].detail


def test_store_reports_disabled_or_missing_client(tmp_path, monkeypatch):
    disabled = ImmudbStore(_settings(tmp_path, immudb_enabled=False))
    with pytest.raises(anchoring.ReceiptError, match="disabled"):
        disabled.get_at("k", 1)
    monkeypatch.setattr(anchoring, "CLIENT_MODULE", "depositrack_no_such_module")
    missing = ImmudbStore(_settings(tmp_path))
    with pytest.raises(anchoring.ReceiptError, match=r"\.\[anchoring\]"):
        missing.put("k", "v")


# --- API ---------------------------------------------------------------------------------


@pytest.fixture
def api(tmp_path, rsa_key, monkeypatch, make_token):
    monkeypatch.setattr(security, "get_signing_key", lambda token, settings: rsa_key.public_key())
    factory = make_sessionmaker()
    with factory() as s:
        _events(s)
    holder = {"settings": _settings(tmp_path, immudb_enabled=False)}
    app = create_app()

    def session_override():
        with factory() as s:
            yield s

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_settings] = lambda: holder["settings"]
    tokens = {
        "admin": make_token(["admin"], username="admin"),
        "auditor": make_token(["auditor"], username="auditor"),
    }
    return SimpleNamespace(
        client=TestClient(app),
        factory=factory,
        holder=holder,
        tmp_path=tmp_path,
        h=lambda who: {"Authorization": f"Bearer {tokens[who]}"},
    )


def _anchor(api):
    return api.client.post("/api/v1/audit/anchors", headers=api.h("admin"))


def _listed(api):
    return api.client.get("/api/v1/audit/anchors", headers=api.h("auditor")).json()["items"]


def test_missing_client_makes_anchoring_return_503(api, monkeypatch):
    monkeypatch.setattr(anchoring, "CLIENT_MODULE", "depositrack_no_such_module")
    api.holder["settings"] = _settings(api.tmp_path)
    r = _anchor(api)
    assert r.status_code == 503
    assert "immudb client is not installed" in r.json()["detail"]
    with api.factory() as s:
        assert s.scalar(select(func.count()).select_from(Anchor)) == 0


def test_anchor_without_immudb_has_no_external_receipt(api):
    r = _anchor(api)
    assert r.status_code == 201
    body = r.json()
    assert body["anchored"] and body["events"] == 3
    assert (body["store_tx"], body["store_error"]) == (None, None)
    [item] = _listed(api)
    assert item["valid"] is True
    assert item["receipt"] == "none"
    assert item["receipt_detail"] == "No external receipt"


def test_immudb_down_still_stores_the_anchor_and_surfaces_the_error(api, immudb):
    api.holder["settings"] = _settings(api.tmp_path)
    immudb.down = True
    r = _anchor(api)
    assert r.status_code == 201
    body = r.json()
    assert body["anchored"] and body["store_tx"] is None
    assert "Could not log in to immudb" in body["store_error"]
    with api.factory() as s:
        assert s.scalar(select(func.count()).select_from(Anchor)) == 1
        logged = s.scalars(select(Event).where(Event.action == "audit.anchored")).one()
        assert logged.after["store_error"] == body["store_error"]
    [item] = _listed(api)
    assert (item["valid"], item["receipt"]) == (True, "none")
    assert item["store_error"] == body["store_error"]


def test_anchor_with_immudb_is_verified_against_the_receipt(api, immudb):
    api.holder["settings"] = _settings(api.tmp_path)
    body = _anchor(api).json()
    assert body["store_tx"] == "1" and body["store_error"] is None
    [item] = _listed(api)
    assert (item["valid"], item["receipt"]) == (True, "verified")

    with api.factory() as s:  # an insider edits an event and the anchor row together
        s.execute(update(Event).where(Event.action == "test.event0").values(reason="edited"))
        anchor = s.scalars(select(Anchor)).one()
        anchor.merkle_root = recompute_root(s, anchor)
        s.commit()
    [item] = _listed(api)
    assert item["root_matches"] is True
    assert (item["valid"], item["receipt"]) == (False, "mismatch")


def test_second_anchor_takes_only_new_events(api):
    assert _anchor(api).json()["events"] == 3
    # The first anchor's own audit.anchored event is the only new one.
    assert _anchor(api).json()["events"] == 1
    assert _anchor(api).json()["events"] == 1
    assert all(item["valid"] for item in _listed(api))


def test_an_event_cannot_join_two_anchors():
    factory = make_sessionmaker()
    with factory() as s:
        _events(s, 1)
        first = anchor_new_events(s)
        s.commit()
        event_id = s.scalars(select(AnchorEvent.event_id)).one()
        second = Anchor(batch_start=first.batch_start, batch_end=first.batch_end, merkle_root="0")
        s.add(second)
        s.flush()
        s.add(AnchorEvent(event_id=event_id, anchor_id=second.id, position=0))
        with pytest.raises(IntegrityError):
            s.flush()


def test_concurrent_anchor_conflict_returns_409(api, monkeypatch):
    def racing(session):  # another request anchored the same events first
        raise IntegrityError("INSERT INTO anchor_event", {}, Exception("duplicate key"))

    monkeypatch.setattr("app.api.audit.anchor_new_events", racing)
    r = _anchor(api)
    assert r.status_code == 409
    assert "try again" in r.json()["detail"]


def test_anchor_key_is_derived_from_the_anchor_id():
    factory = make_sessionmaker()
    with factory() as s:
        _events(s, 1)
        anchor = anchor_new_events(s)
        assert isinstance(anchor.id, uuid.UUID)
        assert anchoring.anchor_key(anchor) == f"depositrack:anchor:{anchor.id}"
