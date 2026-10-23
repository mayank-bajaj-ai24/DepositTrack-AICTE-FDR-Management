"""ABAC scoping (M1): instrument views and institution views follow one rule set."""

import uuid
from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.core.access import (
    INSTRUMENT_READ,
    Scope,
    acting_roles,
    require,
    scope_institutions,
    scope_instruments,
)
from app.core.permissions import Action, Role
from app.core.security import Principal
from app.models import Institution, Instrument
from app.modules.lifecycle.states import InstrumentKind
from tests.flow_support import make_sessionmaker, seed


@pytest.fixture
def db():
    """Synthetic A (West, XNBK deposit), B (East, YBNK deposit), C (West, nothing yet)."""
    factory = make_sessionmaker()
    ids = seed(factory, date.today())
    with factory() as s:
        c = Institution(
            aicte_id="SYN-C", name="Synthetic Institute C", institution_type="any", region="West"
        )
        s.add(c)
        for institution_id, bank, number in ((ids["a"], "XNBK", "A1"), (ids["b"], "YBNK", "B1")):
            s.add(
                Instrument(
                    institution_id=institution_id,
                    kind=InstrumentKind.FDR,
                    canonical_bank=bank,
                    instrument_no=number,
                    instrument_no_norm=number,
                )
            )
        s.commit()
        yield s, ids


def _scope(roles, institution_id=None, region=None, bank_code=None) -> Scope:
    principal = Principal(subject=str(uuid.uuid4()), username="t", roles=frozenset(roles))
    return Scope(principal, institution_id, region, bank_code)


def _visible(session, scope, actions=INSTRUMENT_READ) -> tuple[set[str], set[str]]:
    institutions = set(
        session.scalars(scope_institutions(select(Institution.aicte_id), scope, actions))
    )
    instruments = set(
        session.scalars(scope_instruments(select(Instrument.instrument_no), scope, actions))
    )
    return institutions, instruments


@pytest.mark.parametrize(
    ("roles", "link", "region", "institutions", "instruments"),
    [
        (["institution"], "a", None, {"SYN-A"}, {"A1"}),
        (["scrutiny_officer"], None, "West", {"SYN-A", "SYN-C"}, {"A1"}),
        (["verifying_officer"], None, "East", {"SYN-B"}, {"B1"}),
        (["scrutiny_officer"], None, None, {"SYN-A", "SYN-B", "SYN-C"}, {"A1", "B1"}),
        (["auditor"], None, None, {"SYN-A", "SYN-B", "SYN-C"}, {"A1", "B1"}),
        (["competent_authority"], None, None, {"SYN-A", "SYN-B", "SYN-C"}, {"A1", "B1"}),
        # West officer who is also institution B (East): region plus their own institution.
        (
            ["institution", "scrutiny_officer"],
            "b",
            "West",
            {"SYN-A", "SYN-B", "SYN-C"},
            {"A1", "B1"},
        ),
        (["institution", "verifying_officer"], "a", "East", {"SYN-A", "SYN-B"}, {"A1", "B1"}),
    ],
)
def test_scope_by_role(db, roles, link, region, institutions, instruments):
    session, ids = db
    scope = _scope(roles, institution_id=ids[link] if link else None, region=region)
    assert _visible(session, scope) == (institutions, instruments)


def test_bank_service_reads_nothing_and_attests_only_its_own_banks_instruments(db):
    # Its only permission is attestation: no reads, and never an institution as a whole
    # (A's coverage would add up allocations from every bank).
    session, _ = db
    bank = _scope(["bank_service"], bank_code="XNBK")
    assert _visible(session, bank) == (set(), set())
    assert _visible(session, bank, (Action.ATTESTATION_POST,)) == (set(), {"A1"})


@pytest.mark.parametrize(
    ("roles", "link", "region"),
    [
        (["institution"], "a", None),
        (["institution"], "b", None),
        (["scrutiny_officer"], None, "West"),
        (["verifying_officer"], None, "East"),
        (["scrutiny_officer"], None, None),
        (["institution", "scrutiny_officer"], "b", "West"),
        (["auditor"], None, None),
        (["institution", "bank_service"], "a", None),
        (["verifying_officer", "bank_service"], None, "East"),
        (["bank_service"], None, None),
    ],
)
def test_instrument_and_institution_views_agree(db, roles, link, region):
    # Every visible instrument belongs to a visible institution, and every visible
    # institution's instruments are visible: the two views come from one rule.
    session, ids = db
    scope = _scope(
        roles, institution_id=ids[link] if link else None, region=region, bank_code="XNBK"
    )
    institutions = set(
        session.scalars(scope_institutions(select(Institution.id), scope, INSTRUMENT_READ))
    )
    owners = set(
        session.scalars(
            scope_instruments(select(Instrument.institution_id), scope, INSTRUMENT_READ)
        )
    )
    with_deposits = set(session.scalars(select(Instrument.institution_id)))
    assert owners == institutions & with_deposits


@pytest.mark.parametrize(
    ("roles", "link", "region", "bank", "institutions", "instruments"),
    [
        # Institution A that is also a bank account (YBNK issued B's deposit): reads only A.
        # The bank role grants no read, so it adds nothing (review of #12: it used to add B1).
        (["institution", "bank_service"], "a", None, "YBNK", {"SYN-A"}, {"A1"}),
        # An East verifier who is also a bank account (XNBK issued A's deposit, in the West):
        # still only the East; the bank role never widens an officer's region.
        (["verifying_officer", "bank_service"], None, "East", "XNBK", {"SYN-B"}, {"B1"}),
        # No DepositTrack role at all: nothing.
        ([], None, None, None, set(), set()),
        # Admin reads the audit trail across institutions: everything, with or without a bank.
        (["admin"], None, None, None, {"SYN-A", "SYN-B", "SYN-C"}, {"A1", "B1"}),
        (["admin", "bank_service"], None, None, "XNBK", {"SYN-A", "SYN-B", "SYN-C"}, {"A1", "B1"}),
    ],
)
def test_only_roles_granting_the_action_widen_what_a_mixed_caller_reads(
    db, roles, link, region, bank, institutions, instruments
):
    session, ids = db
    scope = _scope(roles, institution_id=ids[link] if link else None, region=region, bank_code=bank)
    assert _visible(session, scope) == (institutions, instruments)


def test_institution_and_bank_mix_attests_only_through_the_bank_role(db):
    # For attestation the bank role acts (its own bank's B1); the institution role does not
    # grant attestation, so A's own A1 (another bank's) is not reachable for it.
    session, ids = db
    scope = _scope(["institution", "bank_service"], institution_id=ids["a"], bank_code="YBNK")
    assert _visible(session, scope, (Action.ATTESTATION_POST,)) == (set(), {"B1"})


def test_a_caller_with_no_role_granting_the_action_is_refused():
    with pytest.raises(HTTPException) as refused:
        require(_scope(["bank_service"], bank_code="XNBK"), INSTRUMENT_READ)
    assert refused.value.status_code == 403
    assert acting_roles(_scope(["institution", "bank_service"]), INSTRUMENT_READ) == {
        Role.INSTITUTION
    }


def test_a_lookup_must_say_what_it_is_for():
    with pytest.raises(ValueError, match="actions or roles"):
        acting_roles(_scope(["auditor"]))
