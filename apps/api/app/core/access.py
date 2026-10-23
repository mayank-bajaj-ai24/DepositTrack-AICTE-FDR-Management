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


def scope_instruments(query: Select, scope: Scope) -> Select:
    """Restrict an Instrument query to what the caller may see."""
    if scope.has(Role.INSTITUTION) and len(scope.principal.roles) == 1:
        return query.where(Instrument.institution_id == scope.institution_id)
    if scope.has(Role.BANK_SERVICE) and len(scope.principal.roles) == 1:
        return query.where(Instrument.canonical_bank == scope.bank_code)
    if scope.region and (scope.has(Role.SCRUTINY_OFFICER) or scope.has(Role.VERIFYING_OFFICER)):
        regional = select(Institution.id).where(Institution.region == scope.region)
        return query.where(Instrument.institution_id.in_(regional))
    return query


def scope_institutions(query: Select, scope: Scope) -> Select:
    """Restrict an Institution query with the same rules as `scope_instruments`.

    Unlike deriving institutions from visible instruments, this includes institutions that
    have submitted nothing yet, whose whole requirement is uncovered.
    """
    if scope.has(Role.INSTITUTION) and len(scope.principal.roles) == 1:
        return query.where(Institution.id == scope.institution_id)
    if scope.has(Role.BANK_SERVICE) and len(scope.principal.roles) == 1:
        banked = select(Instrument.institution_id).where(
            Instrument.canonical_bank == scope.bank_code
        )
        return query.where(Institution.id.in_(banked))
    if scope.region and (scope.has(Role.SCRUTINY_OFFICER) or scope.has(Role.VERIFYING_OFFICER)):
        return query.where(Institution.region == scope.region)
    return query


def get_visible_instrument(session: Session, scope: Scope, instrument_id: uuid.UUID) -> Instrument:
    query = scope_instruments(select(Instrument).where(Instrument.id == instrument_id), scope)
    instrument = session.scalars(query).first()
    if instrument is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Instrument not found")
    return instrument
