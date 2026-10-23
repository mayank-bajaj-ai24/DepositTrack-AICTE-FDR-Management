import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey


class UserAccount(UUIDPrimaryKey, Timestamps, Base):
    """Links a Keycloak user to the attributes used for access rules (M1 ABAC).

    institution users see only their institution; regional officers only their region;
    bank service accounts only their bank (by IFSC prefix).
    """

    __tablename__ = "user_account"

    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    institution_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("institution.id"))
    region: Mapped[str | None] = mapped_column(String(100))
    bank_code: Mapped[str | None] = mapped_column(String(4))
