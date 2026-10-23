"""Attribute-based access rules on top of the role matrix (M1 ABAC).

- institution users see only their own institution's instruments;
- officers with a region see only institutions in that region (no region = all), plus
  their own institution when they also hold the institution role;
- auditors, competent authority and admins see everything (read rights per role matrix);
- bank service accounts see only instruments of their own bank, and no institution-level
  data (obligations, coverage) because their only permission is posting attestations;
- anything else is denied: a caller without a broad read permission sees only its own
  institution (with the institution role) or nothing, whatever mix of roles it holds.
"""

import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from sqlalchemy import Select, false, or_, select
from sqlalchemy.orm import Session

from app.core.permissions import Action, Role, is_allowed
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


# Permissions that read across institutions; without one, a caller sees at most its own.
BROAD_READ = (Action.INSTRUMENT_READ_ALL, Action.REPORT_VIEW, Action.AUDIT_READ)


def reads_broadly(scope: Scope) -> bool:
    return any(is_allowed(scope.principal.roles, action) for action in BROAD_READ)


def visible_institution_ids(scope: Scope) -> Select | None:
    """Ids of the institutions the caller may see, as a subquery; None means no restriction.

    This is the one place where the institution-level ABAC rules live. `scope_instruments`
    and `scope_institutions` both filter against it, so the instrument views and the
    coverage views cannot drift apart.
    """
    own = scope.institution_id if scope.has(Role.INSTITUTION) else None
    if not reads_broadly(scope):
        # Default deny. An institution sees itself; a bank account (attestation only) or a
        # caller with no DepositTrack role sees no institution as a whole, so never another
        # bank's amounts summed into an institution's coverage. Unknown role mixes land here.
        if own:
            return select(Institution.id).where(Institution.id == own)
        return select(Institution.id).where(false())
    if scope.region and (scope.has(Role.SCRUTINY_OFFICER) or scope.has(Role.VERIFYING_OFFICER)):
        visible = Institution.region == scope.region
        if scope.has(Role.INSTITUTION) and scope.institution_id:
            # Mixed roles: the institution role still reads its own records, in any region.
            visible = or_(visible, Institution.id == scope.institution_id)
        return select(Institution.id).where(visible)
    return None


def scope_instruments(query: Select, scope: Scope) -> Select:
    """Restrict an Instrument query to what the caller may see."""
    visible = visible_institution_ids(scope)
    if visible is None:
        return query
    allowed = Instrument.institution_id.in_(visible)
    if scope.has(Role.BANK_SERVICE) and scope.bank_code:
        # Bank accounts are scoped per instrument: their own bank's, never other banks'.
        allowed = or_(allowed, Instrument.canonical_bank == scope.bank_code)
    return query.where(allowed)


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
