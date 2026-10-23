"""Attribute-based access rules on top of the role matrix (M1 ABAC).

Scoping depends on the action. Every lookup says what it is for (an action from the role
matrix, or the roles a workflow step allows), and only the caller's roles that grant it
contribute visibility; their scopes are united:

- institution: its own institution;
- scrutiny / verifying officer: their region (no region = every institution);
- competent authority, auditor, admin: every institution;
- bank service: no institution; for an action it grants (attestation only) the instruments
  of its own bank.

A role that does not grant the action adds nothing, so a mix such as institution + bank
service reads only its own institution, and a bank role never widens an officer's region.
A caller with no role granting the action sees nothing: `require` and
`get_visible_instrument` refuse it (403), and scoped queries return no rows.
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from sqlalchemy import Select, false, or_, select
from sqlalchemy.orm import Session

from app.core.permissions import PERMISSIONS, Action, Role, known_roles
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


# Action groups used by the read endpoints.
INSTRUMENT_READ = (Action.INSTRUMENT_READ_ALL, Action.INSTRUMENT_READ_OWN, Action.AUDIT_READ)
REPORT_READ = (Action.REPORT_VIEW, Action.INSTRUMENT_READ_OWN)
CASE_READ = (*INSTRUMENT_READ, Action.RELEASE_REQUEST, Action.RELEASE_APPROVE)

_EVERY_INSTITUTION = {Role.COMPETENT_AUTHORITY, Role.AUDITOR, Role.ADMIN}
_REGIONAL = {Role.SCRUTINY_OFFICER, Role.VERIFYING_OFFICER}
_ROLE_NAMES = {r.value for r in Role}


def acting_roles(
    scope: Scope, actions: Iterable[Action] = (), roles: Iterable[str | Role] = ()
) -> frozenset[Role]:
    """The caller's roles that may perform the step: those granting one of `actions`, or
    named in `roles` (for steps the workflow config gates by role, such as transitions)."""
    wanted = set(actions)
    named = {Role(r) for r in roles if r in _ROLE_NAMES}
    if not wanted and not named:
        raise ValueError("A scoped lookup must name the actions or roles it is for")
    return frozenset(
        role
        for role in known_roles(scope.principal.roles)
        if PERMISSIONS[role] & wanted or role in named
    )


def require(scope: Scope, actions: Iterable[Action] = (), roles: Iterable[str] = ()) -> None:
    """403 unless one of the caller's roles may perform the step."""
    if not acting_roles(scope, actions, roles):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")


def _visible_ids(scope: Scope, acting: frozenset[Role]) -> Select | None:
    """Ids of the institutions the acting roles may see; None means every institution."""
    conditions = []
    for role in acting:
        if role in _EVERY_INSTITUTION:
            return None
        if role in _REGIONAL:
            if not scope.region:
                return None
            conditions.append(Institution.region == scope.region)
        elif role is Role.INSTITUTION and scope.institution_id:
            conditions.append(Institution.id == scope.institution_id)
        # Role.BANK_SERVICE: no institution as a whole (its obligations, or coverage summed
        # over every bank); it is scoped per instrument in scope_instruments.
    return select(Institution.id).where(or_(*conditions) if conditions else false())


def visible_institution_ids(
    scope: Scope, actions: Iterable[Action] = (), roles: Iterable[str] = ()
) -> Select | None:
    """The one place the institution-level rules live; instrument and institution views
    both filter against it, so they agree for every role mix."""
    return _visible_ids(scope, acting_roles(scope, actions, roles))


def _scoped_instruments(query: Select, scope: Scope, acting: frozenset[Role]) -> Select:
    visible = _visible_ids(scope, acting)
    if visible is None:
        return query
    allowed = Instrument.institution_id.in_(visible)
    if Role.BANK_SERVICE in acting and scope.bank_code:
        # Only for an action the bank role itself grants: its own bank's instruments.
        allowed = or_(allowed, Instrument.canonical_bank == scope.bank_code)
    return query.where(allowed)


def scope_instruments(
    query: Select,
    scope: Scope,
    actions: Iterable[Action] = (),
    roles: Iterable[str] = (),
    acting: frozenset[Role] | None = None,
) -> Select:
    """Restrict an Instrument query to what the roles performing the step may see."""
    if acting is None:
        acting = acting_roles(scope, actions, roles)
    return _scoped_instruments(query, scope, acting)


def scope_institutions(
    query: Select, scope: Scope, actions: Iterable[Action] = (), roles: Iterable[str] = ()
) -> Select:
    """Restrict an Institution query, including institutions that have deposited nothing."""
    visible = visible_institution_ids(scope, actions, roles)
    return query if visible is None else query.where(Institution.id.in_(visible))


def get_visible_instrument(
    session: Session,
    scope: Scope,
    instrument_id: uuid.UUID,
    actions: Iterable[Action] = (),
    roles: Iterable[str] = (),
) -> Instrument:
    """The instrument, if a role that may perform the step can see it: 403 when no role
    may perform it at all, 404 when the instrument is outside what those roles see."""
    acting = acting_roles(scope, actions, roles)
    if not acting:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")
    query = _scoped_instruments(
        select(Instrument).where(Instrument.id == instrument_id), scope, acting
    )
    instrument = session.scalars(query).first()
    if instrument is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Instrument not found")
    return instrument
