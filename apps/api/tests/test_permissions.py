"""Allow/deny matrix for M1 (plan DoD: at least 20 cases)."""

import pytest

from app.core.permissions import PERMISSIONS, Action, Role, is_allowed

A = Action
R = Role

CASES = [
    # Institution
    (R.INSTITUTION, A.INSTRUMENT_SUBMIT, True),
    (R.INSTITUTION, A.INSTRUMENT_READ_OWN, True),
    (R.INSTITUTION, A.RELEASE_REQUEST, True),
    (R.INSTITUTION, A.INSTRUMENT_READ_ALL, False),
    (R.INSTITUTION, A.RELEASE_APPROVE, False),
    (R.INSTITUTION, A.VERIFICATION_RECORD, False),
    (R.INSTITUTION, A.AUDIT_READ, False),
    # Scrutiny officer
    (R.SCRUTINY_OFFICER, A.SCRUTINY_REVIEW, True),
    (R.SCRUTINY_OFFICER, A.OBSERVATION_RECORD, True),
    (R.SCRUTINY_OFFICER, A.DISCREPANCY_RAISE, True),
    (R.SCRUTINY_OFFICER, A.RELEASE_APPROVE, False),
    (R.SCRUTINY_OFFICER, A.INSTRUMENT_SUBMIT, False),
    # Verifying officer
    (R.VERIFYING_OFFICER, A.VERIFICATION_RECORD, True),
    (R.VERIFYING_OFFICER, A.RELEASE_APPROVE, False),
    (R.VERIFYING_OFFICER, A.ATTESTATION_POST, False),
    # Competent authority
    (R.COMPETENT_AUTHORITY, A.RELEASE_APPROVE, True),
    (R.COMPETENT_AUTHORITY, A.CONFIG_MANAGE, False),
    # Auditor is strictly read-only
    (R.AUDITOR, A.AUDIT_READ, True),
    (R.AUDITOR, A.INSTRUMENT_READ_ALL, True),
    (R.AUDITOR, A.INSTRUMENT_EDIT_PERMITTED_FIELDS, False),
    (R.AUDITOR, A.RELEASE_APPROVE, False),
    # Admin manages configuration but does not decide cases
    (R.ADMIN, A.CONFIG_MANAGE, True),
    (R.ADMIN, A.USER_MANAGE, True),
    (R.ADMIN, A.RELEASE_APPROVE, False),
    (R.ADMIN, A.SCRUTINY_REVIEW, False),
    # Bank service can only post attestations
    (R.BANK_SERVICE, A.ATTESTATION_POST, True),
    (R.BANK_SERVICE, A.INSTRUMENT_READ_ALL, False),
    (R.BANK_SERVICE, A.RELEASE_APPROVE, False),
]


@pytest.mark.parametrize(("role", "action", "expected"), CASES)
def test_permission_matrix(role, action, expected):
    assert is_allowed({role.value}, action) is expected


def test_at_least_twenty_cases():
    assert len(CASES) >= 20


def test_every_role_has_permissions():
    assert set(PERMISSIONS) == set(Role)


def test_auditor_has_no_write_actions():
    read_only = {A.AUDIT_READ, A.INSTRUMENT_READ_ALL, A.REPORT_VIEW}
    assert PERMISSIONS[R.AUDITOR] <= read_only


def test_unknown_roles_grant_nothing():
    assert not is_allowed({"offline_access", "uma_authorization"}, A.INSTRUMENT_READ_ALL)


def test_multiple_roles_combine():
    roles = {R.SCRUTINY_OFFICER.value, R.VERIFYING_OFFICER.value}
    assert is_allowed(roles, A.SCRUTINY_REVIEW)
    assert is_allowed(roles, A.VERIFICATION_RECORD)
