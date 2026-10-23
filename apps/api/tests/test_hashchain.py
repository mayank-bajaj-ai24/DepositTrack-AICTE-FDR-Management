import hashlib
from datetime import UTC, datetime
from decimal import Decimal

from app.modules.audit.hashchain import (
    GENESIS,
    build_chain,
    canonical_json,
    event_hash,
    first_break,
    merkle_root,
)

EVENTS = [
    {"action": "instrument.submitted", "actor": "inst-1", "amount": Decimal("100.00")},
    {"action": "instrument.state_changed", "after": {"state": "scrutiny"}},
    {"action": "observation.recorded", "ts": datetime(2026, 1, 1, tzinfo=UTC)},
]


def test_canonical_json_is_key_order_independent():
    assert canonical_json({"b": 1, "a": 2}) == canonical_json({"a": 2, "b": 1})


def test_first_link_uses_genesis():
    (prev, _), *_ = build_chain(EVENTS)
    assert prev == GENESIS


def test_intact_chain_has_no_break():
    hashes = [h for _, h in build_chain(EVENTS)]
    assert first_break(EVENTS, hashes) is None


def test_edited_event_is_detected():
    hashes = [h for _, h in build_chain(EVENTS)]
    tampered = [dict(e) for e in EVENTS]
    tampered[1]["after"] = {"state": "active"}
    assert first_break(tampered, hashes) == 1


def test_deleted_event_is_detected():
    hashes = [h for _, h in build_chain(EVENTS)]
    assert first_break(EVENTS[:2], hashes) is not None


def test_hash_depends_on_previous():
    assert event_hash("a" * 64, EVENTS[0]) != event_hash("b" * 64, EVENTS[0])


def test_merkle_root_single_leaf_is_leaf():
    leaf = hashlib.sha256(b"x").hexdigest()
    assert merkle_root([leaf]) == leaf


def test_merkle_root_changes_when_a_leaf_changes():
    leaves = [h for _, h in build_chain(EVENTS)]
    changed = leaves[:-1] + [hashlib.sha256(b"other").hexdigest()]
    assert merkle_root(leaves) != merkle_root(changed)
