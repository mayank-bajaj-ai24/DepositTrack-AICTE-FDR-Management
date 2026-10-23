import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.modules.lifecycle.states import InstrumentKind, InstrumentState, TrustLevel


def _str_enum(enum_cls) -> Enum:
    """Store enum values as plain strings so the schema is portable across databases."""
    return Enum(
        enum_cls, native_enum=False, length=32, values_callable=lambda e: [m.value for m in e]
    )


class Instrument(UUIDPrimaryKey, Timestamps, Base):
    """A security deposit / FDR. Lifecycle per plan §7.1."""

    __tablename__ = "instrument"
    # Canonical key (N7). Not unique on purpose: a second submission of the same FDR is
    # stored and both are flagged as a double pledge, so officers can see it.
    __table_args__ = (Index("ix_instrument_canonical", "canonical_bank", "instrument_no_norm"),)

    institution_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institution.id"), index=True)
    kind: Mapped[InstrumentKind] = mapped_column(_str_enum(InstrumentKind))
    bank_ifsc: Mapped[str | None] = mapped_column(String(11))
    bank_name: Mapped[str | None] = mapped_column(String(200))
    canonical_bank: Mapped[str | None] = mapped_column(String(50))
    instrument_no: Mapped[str] = mapped_column(String(64))
    instrument_no_norm: Mapped[str] = mapped_column(String(64), index=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    issue_date: Mapped[date | None] = mapped_column(Date)
    maturity_date: Mapped[date | None] = mapped_column(Date, index=True)
    auto_renew: Mapped[bool | None] = mapped_column(Boolean)
    lien_marked: Mapped[bool | None] = mapped_column(Boolean)
    beneficiary_text: Mapped[str | None] = mapped_column(Text)
    state: Mapped[InstrumentState] = mapped_column(
        _str_enum(InstrumentState),
        default=InstrumentState.DRAFT,
        index=True,
    )
    trust_level: Mapped[int] = mapped_column(Integer, default=int(TrustLevel.DECLARED))
    replaces_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("instrument.id"))
    risk_score: Mapped[float | None] = mapped_column(Float)
    # {as_of, expected_days_late, reasons: [{feature, value, contribution, text}]} (N9)
    risk_reasons: Mapped[dict | None] = mapped_column(JSON)


class FieldValue(Base):
    """Per-field provenance (N1): declared, extracted (two passes, N6) and bank values."""

    __tablename__ = "field_value"
    __table_args__ = (UniqueConstraint("instrument_id", "field", name="uq_field_value_field"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    instrument_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("instrument.id"), index=True)
    field: Mapped[str] = mapped_column(String(64))
    declared: Mapped[str | None] = mapped_column(Text)
    extracted_a: Mapped[str | None] = mapped_column(Text)
    extracted_b: Mapped[str | None] = mapped_column(Text)
    bank_value: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    trust_level: Mapped[int] = mapped_column(Integer, default=int(TrustLevel.DECLARED))
    fresh_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IfscLineage(Base):
    """Maps old IFSC codes to current ones after bank mergers (N7)."""

    __tablename__ = "ifsc_lineage"

    old_ifsc: Mapped[str] = mapped_column(String(11), primary_key=True)
    current_ifsc: Mapped[str] = mapped_column(String(11))
    canonical_bank: Mapped[str] = mapped_column(String(50))
    effective_from: Mapped[date | None] = mapped_column(Date)
