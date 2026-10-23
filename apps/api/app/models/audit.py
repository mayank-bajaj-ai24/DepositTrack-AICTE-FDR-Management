import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKey, utcnow


class Event(UUIDPrimaryKey, Base):
    """Append-only audit event, hash-chained per instrument (M6, N4).

    Also serves as the event log for conformance replay (N10) and risk models (N9).
    """

    __tablename__ = "event"

    case_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("case.id"), index=True)
    instrument_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("instrument.id"), index=True)
    actor_id: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(50))
    action: Mapped[str] = mapped_column(String(100))
    before: Mapped[dict | None] = mapped_column(JSON)
    after: Mapped[dict | None] = mapped_column(JSON)
    reason: Mapped[str | None] = mapped_column(Text)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    # Position in its chain (per instrument, or the system chain when instrument_id is null).
    seq: Mapped[int] = mapped_column(Integer, default=0)
    prev_hash: Mapped[str | None] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True)


class Anchor(UUIDPrimaryKey, Base):
    """Merkle root over a batch of events, plus its immudb receipt when one was written (N4).

    The batch is the set of `AnchorEvent` rows; `batch_start` and `batch_end` are only
    informational.
    """

    __tablename__ = "anchor"

    batch_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    batch_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    merkle_root: Mapped[str] = mapped_column(String(64))
    # immudb key and transaction of the receipt; store_tx stays null when none was written.
    store_key: Mapped[str | None] = mapped_column(String(200))
    store_tx: Mapped[str | None] = mapped_column(String(100))
    # Why the immudb write failed, so a missing receipt is never silent.
    store_error: Mapped[str | None] = mapped_column(Text)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AnchorEvent(Base):
    """An event's place in exactly one anchor batch, at a fixed Merkle leaf position.

    Batches are defined by membership, not by a timestamp range, so an event committed late
    with an older `ts` goes into the next anchor instead of being skipped or counted twice.
    """

    __tablename__ = "anchor_event"
    __table_args__ = (UniqueConstraint("anchor_id", "position"),)

    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("event.id"), primary_key=True)
    anchor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("anchor.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
