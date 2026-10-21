import uuid
from datetime import date

from sqlalchemy import JSON, Boolean, Date, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey


class PolicyVersion(UUIDPrimaryKey, Timestamps, Base):
    """Versioned policy-as-code rules per case type (N5, N10)."""

    __tablename__ = "policy_version"
    __table_args__ = (UniqueConstraint("case_type", "version", name="uq_policy_version"),)

    case_type: Mapped[str] = mapped_column(String(30))
    version: Mapped[str] = mapped_column(String(50))
    rules: Mapped[dict] = mapped_column(JSON)
    clause_refs: Mapped[list | None] = mapped_column(JSON)
    valid_from: Mapped[date] = mapped_column(Date)
    approved_by: Mapped[str | None] = mapped_column(String(100))


class FieldPermission(Base):
    """Which role may edit which instrument field ("update permitted fields", R-i)."""

    __tablename__ = "field_permission"
    __table_args__ = (UniqueConstraint("role", "field", name="uq_field_permission_role_field"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    role: Mapped[str] = mapped_column(String(50))
    field: Mapped[str] = mapped_column(String(64))
    can_edit: Mapped[bool] = mapped_column(Boolean, default=False)
