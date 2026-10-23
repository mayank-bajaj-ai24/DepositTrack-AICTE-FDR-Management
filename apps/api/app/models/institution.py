from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey


class Institution(UUIDPrimaryKey, Timestamps, Base):
    """An AICTE-approved institution (imported from AICTE master data, M12)."""

    __tablename__ = "institution"

    aicte_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(300))
    institution_type: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(100))
    region: Mapped[str | None] = mapped_column(String(100), index=True)
    contacts: Mapped[dict | None] = mapped_column(JSON)
