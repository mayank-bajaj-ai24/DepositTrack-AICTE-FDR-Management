"""Attribute-based access rules on top of the role matrix (M1 ABAC).

- institution users see only their own institution's instruments;
- officers with a region see only institutions in that region (no region = all);
- auditors, competent authority and admins see everything (read rights per role matrix);
- bank service accounts see only instruments of their own bank.
"""

import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.core.permissions import Role
from app.core.security import Principal, get_current_principal
from app.db.session import get_session
from app.models import Institution, Instrument, UserAccount


@dataclass(frozen=True)
class Scope:
    principal: Principal
    institution_id: uuid.UUID | None
    region: str | None
    bank_code: str | None

    @property
    def role(self) -> str:
        """Primary role used for audit records (the first known role, alphabetically)."""
        return sorted(self.principal.roles)[0] if self.principal.roles else "unknown"

    def has(self, role: Role) -> bool:
        return role.value in self.principal.roles


def get_scope(
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> Scope:
    account = session.scalars(
        select(UserAccount).where(UserAccount.username == principal.username)
    ).first()
    if principal.roles == {Role.INSTITUTION.value} and (
        account is None or not account.institution_id
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User is not linked to an institution")
    return Scope(
        principal=principal,
        institution_id=account.institution_id if account else None,
        region=account.region if account else None,
        bank_code=account.bank_code if account else None,
    )


def _only(scope: Scope, role: Role) -> bool:
    return scope.has(role) and len(scope.principal.roles) == 1


def visible_institution_ids(scope: Scope) -> Select | None:
    """Ids of the institutions the caller may see, as a subquery; None means no restriction.

    This is the one place where the institution-level ABAC rules live. `scope_instruments`
    and `scope_institutions` both filter against it, so the instrument views and the
    coverage views cannot drift apart.
    """
    if _only(scope, Role.INSTITUTION):
        return select(Institution.id).where(Institution.id == scope.institution_id)
    if _only(scope, Role.BANK_SERVICE):
        return select(Instrument.institution_id).where(Instrument.canonical_bank == scope.bank_code)
    if scope.region and (scope.has(Role.SCRUTINY_OFFICER) or scope.has(Role.VERIFYING_OFFICER)):
        return select(Institution.id).where(Institution.region == scope.region)
    return None


def scope_instruments(query: Select, scope: Scope) -> Select:
    """Restrict an Instrument query to what the caller may see."""
    if _only(scope, Role.BANK_SERVICE):
        # Bank accounts are scoped per instrument: their own bank's only.
        return query.where(Instrument.canonical_bank == scope.bank_code)
    visible = visible_institution_ids(scope)
    return query if visible is None else query.where(Instrument.institution_id.in_(visible))


def scope_institutions(query: Select, scope: Scope) -> Select:
    """Restrict an Institution query to what the caller may see.

    Unlike deriving institutions from visible instruments, this includes institutions that
    have submitted nothing yet, whose whole requirement is uncovered.
    """
    visible = visible_institution_ids(scope)
    return query if visible is None else query.where(Institution.id.in_(visible))


def get_visible_instrument(session: Session, scope: Scope, instrument_id: uuid.UUID) -> Instrument:
    query = scope_instruments(select(Instrument).where(Instrument.id == instrument_id), scope)
    instrument = session.scalars(query).first()
    if instrument is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Instrument not found")
    return instrument
