"""Role-based permission matrix (M1).

Roles match the Keycloak realm in infra/keycloak/depositrack-realm.json.
Attribute rules (own institution, region, own bank) are layered on top of this
matrix in later phases.
"""

from enum import StrEnum


class Role(StrEnum):
    INSTITUTION = "institution"
    SCRUTINY_OFFICER = "scrutiny_officer"
    VERIFYING_OFFICER = "verifying_officer"
    COMPETENT_AUTHORITY = "competent_authority"
    AUDITOR = "auditor"
    ADMIN = "admin"
    BANK_SERVICE = "bank_service"


class Action(StrEnum):
    INSTRUMENT_SUBMIT = "instrument:submit"
    INSTRUMENT_READ_OWN = "instrument:read_own"
    INSTRUMENT_READ_ALL = "instrument:read_all"
    INSTRUMENT_EDIT_PERMITTED_FIELDS = "instrument:edit_permitted_fields"
    SCRUTINY_REVIEW = "scrutiny:review"
    OBSERVATION_RECORD = "observation:record"
    DISCREPANCY_RAISE = "discrepancy:raise"
    QUERY_RESPOND = "query:respond"
    VERIFICATION_RECORD = "verification:record"
    ATTESTATION_POST = "attestation:post"
    RENEWAL_SUBMIT = "renewal:submit"
    RELEASE_REQUEST = "release:request"
    RELEASE_APPROVE = "release:approve"
    AUDIT_READ = "audit:read"
    REPORT_VIEW = "report:view"
    CONFIG_MANAGE = "config:manage"
    USER_MANAGE = "user:manage"


PERMISSIONS: dict[Role, frozenset[Action]] = {
    Role.INSTITUTION: frozenset(
        {
            Action.INSTRUMENT_SUBMIT,
            Action.INSTRUMENT_READ_OWN,
            Action.QUERY_RESPOND,
            Action.RENEWAL_SUBMIT,
            Action.RELEASE_REQUEST,
        }
    ),
    Role.SCRUTINY_OFFICER: frozenset(
        {
            Action.INSTRUMENT_READ_ALL,
            Action.INSTRUMENT_EDIT_PERMITTED_FIELDS,
            Action.SCRUTINY_REVIEW,
            Action.OBSERVATION_RECORD,
            Action.DISCREPANCY_RAISE,
            Action.REPORT_VIEW,
        }
    ),
    Role.VERIFYING_OFFICER: frozenset(
        {
            Action.INSTRUMENT_READ_ALL,
            Action.VERIFICATION_RECORD,
            Action.OBSERVATION_RECORD,
            Action.REPORT_VIEW,
        }
    ),
    Role.COMPETENT_AUTHORITY: frozenset(
        {
            Action.INSTRUMENT_READ_ALL,
            Action.RELEASE_APPROVE,
            Action.AUDIT_READ,
            Action.REPORT_VIEW,
        }
    ),
    Role.AUDITOR: frozenset(
        {
            Action.INSTRUMENT_READ_ALL,
            Action.AUDIT_READ,
            Action.REPORT_VIEW,
        }
    ),
    Role.ADMIN: frozenset(
        {
            Action.CONFIG_MANAGE,
            Action.USER_MANAGE,
            Action.AUDIT_READ,
            Action.REPORT_VIEW,
        }
    ),
    Role.BANK_SERVICE: frozenset({Action.ATTESTATION_POST}),
}


def known_roles(roles: list[str] | set[str]) -> set[Role]:
    """Keep only roles DepositTrack knows; Keycloak adds default roles we ignore."""
    valid = {r.value for r in Role}
    return {Role(r) for r in roles if r in valid}


def is_allowed(roles: list[str] | set[str], action: Action) -> bool:
    return any(action in PERMISSIONS[role] for role in known_roles(roles))


def actions_for(roles: list[str] | set[str]) -> set[Action]:
    allowed: set[Action] = set()
    for role in known_roles(roles):
        allowed |= PERMISSIONS[role]
    return allowed
