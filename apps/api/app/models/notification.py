import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKey, utcnow


class Notification(UUIDPrimaryKey, Base):
    """A reminder or escalation sent about an instrument (M8).

    The unique key makes a second reminder for the same threshold impossible.
    """

    __tablename__ = "notification"
    __table_args__ = (
        UniqueConstraint("instrument_id", "kind", "dedupe_key", name="uq_notification_dedupe"),
    )

    instrument_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("instrument.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    dedupe_key: Mapped[str] = mapped_column(String(100))
    audience_role: Mapped[str] = mapped_column(String(50))
    channel: Mapped[str] = mapped_column(String(20), default="in_app")
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
