import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import JSON, Date, ForeignKey, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey


class Obligation(UUIDPrimaryKey, Timestamps, Base):
    """What an institution owes: an amount over a time window (N2).

    Amounts and windows come from policy rules; real values are pending AICTE (plan §14).
    """

    __tablename__ = "obligation"

    institution_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institution.id"), index=True)
    basis_ref: Mapped[str] = mapped_column(String(200))
    rule_version: Mapped[str | None] = mapped_column(String(50))
    required_amount: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    required_from: Mapped[date] = mapped_column(Date)
    required_until: Mapped[date | None] = mapped_column(Date)
    conditions: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), default="open")


class Coverage(Base):
    """Allocation of (part of) an instrument to an obligation over its validity (N2)."""

    __tablename__ = "coverage"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    obligation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("obligation.id"), index=True)
    instrument_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("instrument.id"), index=True)
    allocated_amount: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date] = mapped_column(Date)
