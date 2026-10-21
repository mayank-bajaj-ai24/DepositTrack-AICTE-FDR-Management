import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey, utcnow


class Flag(UUIDPrimaryKey, Timestamps, Base):
    """A discrepancy flag: fact, failed rule, clause and plain-language reason (N8)."""

    __tablename__ = "flag"

    instrument_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("instrument.id"), index=True)
    flag_type: Mapped[str] = mapped_column(String(50))
    severity: Mapped[str] = mapped_column(String(20))
    fact: Mapped[dict | None] = mapped_column(JSON)
    rule_id: Mapped[str | None] = mapped_column(String(100))
    clause_ref: Mapped[str | None] = mapped_column(String(200))
    reason_text: Mapped[str] = mapped_column(Text)
    evidence_ref: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20), default="open")
    raised_by: Mapped[str] = mapped_column(String(100))
    resolved_by: Mapped[str | None] = mapped_column(String(100))


class Observation(UUIDPrimaryKey, Base):
    """A scrutiny observation recorded by an officer (PS requirement R-i)."""

    __tablename__ = "observation"

    instrument_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("instrument.id"), index=True)
    officer_id: Mapped[str] = mapped_column(String(100))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Case(UUIDPrimaryKey, Timestamps, Base):
    """A unit of work: scrutiny, renewal, release, discharge, refund or query (M8, M9)."""

    __tablename__ = "case"

    case_type: Mapped[str] = mapped_column(String(30))
    instrument_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("instrument.id"), index=True)
    state: Mapped[str] = mapped_column(String(30), default="open")
    assignee_role: Mapped[str | None] = mapped_column(String(50))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    escalation_level: Mapped[int] = mapped_column(Integer, default=0)
    policy_version: Mapped[str | None] = mapped_column(String(50))
