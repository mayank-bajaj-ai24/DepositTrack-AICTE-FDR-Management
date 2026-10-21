import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
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
    """Receipt for a Merkle root of a batch of events written to immudb (N4)."""

    __tablename__ = "anchor"

    batch_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    batch_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    merkle_root: Mapped[str] = mapped_column(String(64))
    store_tx: Mapped[str | None] = mapped_column(String(100))
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
