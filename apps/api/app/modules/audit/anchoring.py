"""Periodic Merkle anchoring of new audit events and document hashes (N4).

The root is stored in the `anchor` table and, when enabled, written to immudb so an
auditor can prove that no anchored event was changed later.
"""

from datetime import UTC

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.base import utcnow
from app.models import Anchor, Event
from app.modules.audit.hashchain import event_hash, merkle_root
from app.modules.audit.service import event_payload


def _write_immudb(settings: Settings, key: str, value: str) -> str | None:
    from immudb import ImmudbClient

    client = ImmudbClient(f"{settings.immudb_host}:{settings.immudb_port}")
    client.login(settings.immudb_user, settings.immudb_password)
    try:
        result = client.verifiedSet(key.encode(), value.encode())
        return str(result.id)
    finally:
        client.logout()


def anchor_new_events(session: Session, settings: Settings) -> Anchor | None:
    last = session.scalars(select(Anchor).order_by(Anchor.batch_end.desc()).limit(1)).first()
    query = select(Event).order_by(Event.ts, Event.seq)
    if last:
        query = query.where(Event.ts > last.batch_end)
    events = list(session.scalars(query))
    if not events:
        return None
    root = merkle_root([e.hash for e in events])
    start = events[0].ts if events[0].ts.tzinfo else events[0].ts.replace(tzinfo=UTC)
    end = events[-1].ts if events[-1].ts.tzinfo else events[-1].ts.replace(tzinfo=UTC)
    store_tx = None
    if settings.immudb_enabled:
        store_tx = _write_immudb(settings, f"depositrack:anchor:{end.isoformat()}", root)
    anchor = Anchor(
        batch_start=start, batch_end=end, merkle_root=root, store_tx=store_tx, ts=utcnow()
    )
    session.add(anchor)
    session.flush()
    return anchor


def verify_anchor(session: Session, anchor: Anchor) -> bool:
    """Recompute every event hash from the row's contents, then the batch's Merkle root.

    The stored `hash` column is not trusted: an insider could edit a row and its hash
    together, but cannot change the root already anchored.
    """
    start = anchor.batch_start
    end = anchor.batch_end
    events = session.scalars(
        select(Event).where(Event.ts >= start, Event.ts <= end).order_by(Event.ts, Event.seq)
    )
    leaves = [event_hash(e.prev_hash, event_payload(e)) for e in events]
    return merkle_root(leaves) == anchor.merkle_root
