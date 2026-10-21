import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKey, utcnow


class Document(UUIDPrimaryKey, Base):
    """An uploaded file. Versions are append-only; files are never overwritten (M2)."""

    __tablename__ = "document"
    __table_args__ = (
        UniqueConstraint("instrument_id", "kind", "version", name="uq_document_version"),
    )

    instrument_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("instrument.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    kind: Mapped[str] = mapped_column(String(50))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    storage_key: Mapped[str] = mapped_column(String(300))
    uploaded_by: Mapped[str] = mapped_column(String(100))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    forgery_score: Mapped[float | None] = mapped_column(Float)


class Attestation(UUIDPrimaryKey, Base):
    """A bank-signed e-FDR credential and its revocation (N3)."""

    __tablename__ = "attestation"

    instrument_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("instrument.id"), index=True)
    issuer_key_id: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict] = mapped_column(JSON)
    signature: Mapped[str] = mapped_column(Text)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_update: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
