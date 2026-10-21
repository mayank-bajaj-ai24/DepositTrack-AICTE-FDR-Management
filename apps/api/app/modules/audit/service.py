"""Persist audit events on per-instrument hash chains and verify them (M6, N4)."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.models import Event
from app.modules.audit.hashchain import GENESIS, event_hash


@dataclass(frozen=True)
class Actor:
    """Who performed an action. `system` is used for scheduled jobs."""

    username: str
    role: str


SYSTEM = Actor(username="system", role="system")


def _utc_iso(ts: datetime) -> str:
    # SQLite returns naive datetimes; treat naive values as UTC so hashes are stable.
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts.astimezone(UTC).replace(tzinfo=None).isoformat(timespec="microseconds")


def event_payload(event: Event) -> dict:
    """The fields covered by the hash, in canonical form."""
    return {
        "id": str(event.id),
        "seq": event.seq,
        "instrument_id": str(event.instrument_id) if event.instrument_id else None,
        "case_id": str(event.case_id) if event.case_id else None,
        "actor_id": event.actor_id,
        "role": event.role,
        "action": event.action,
        "before": event.before,
        "after": event.after,
        "reason": event.reason,
        "ts": _utc_iso(event.ts),
    }


def _chain_query(instrument_id: uuid.UUID | None):
    query = select(Event)
    if instrument_id is None:
        return query.where(Event.instrument_id.is_(None))
    return query.where(Event.instrument_id == instrument_id)


def record_event(
    session: Session,
    *,
    actor: Actor,
    action: str,
    instrument_id: uuid.UUID | None = None,
    case_id: uuid.UUID | None = None,
    before: dict | None = None,
    after: dict | None = None,
    reason: str | None = None,
) -> Event:
    """Append an event to its chain. The caller commits the session."""
    last = session.scalars(_chain_query(instrument_id).order_by(Event.seq.desc()).limit(1)).first()
    event = Event(
        id=uuid.uuid4(),
        instrument_id=instrument_id,
        case_id=case_id,
        actor_id=actor.username,
        role=actor.role,
        action=action,
        before=before,
        after=after,
        reason=reason,
        ts=utcnow(),
        seq=(last.seq + 1) if last else 1,
        prev_hash=last.hash if last else GENESIS,
    )
    event.hash = event_hash(event.prev_hash, event_payload(event))
    session.add(event)
    session.flush()
    return event


@dataclass(frozen=True)
class ChainCheck:
    intact: bool
    length: int
    broken_at_seq: int | None
    head_hash: str | None


def verify_chain(session: Session, instrument_id: uuid.UUID | None) -> ChainCheck:
    """Recompute every hash on the chain; report the first event that does not match."""
    events = list(session.scalars(_chain_query(instrument_id).order_by(Event.seq)))
    prev = GENESIS
    for expected_seq, event in enumerate(events, start=1):
        recomputed = event_hash(prev, event_payload(event))
        if event.seq != expected_seq or event.prev_hash != prev or event.hash != recomputed:
            return ChainCheck(False, len(events), event.seq, events[-1].hash)
        prev = event.hash
    return ChainCheck(True, len(events), None, events[-1].hash if events else None)
