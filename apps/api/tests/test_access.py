"""ABAC scoping (M1): instrument views and institution views follow one rule set."""

import uuid
from datetime import date

import pytest
from sqlalchemy import select

from app.core.access import Scope, scope_institutions, scope_instruments
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


def _visible(session, scope) -> tuple[set[str], set[str]]:
    institutions = set(session.scalars(scope_institutions(select(Institution.aicte_id), scope)))
    instruments = set(session.scalars(scope_instruments(select(Instrument.instrument_no), scope)))
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


def test_bank_service_sees_its_own_banks_instruments_and_no_institution(db):
    # No institution-level view: A's coverage would add up allocations from every bank.
    session, _ = db
    assert _visible(session, _scope(["bank_service"], bank_code="XNBK")) == (set(), {"A1"})


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
    ],
)
def test_instrument_and_institution_views_agree(db, roles, link, region):
    # Every visible instrument belongs to a visible institution, and every visible
    # institution's instruments are visible: the two views come from one rule.
    session, ids = db
    scope = _scope(roles, institution_id=ids[link] if link else None, region=region)
    institutions = set(session.scalars(scope_institutions(select(Institution.id), scope)))
    owners = set(session.scalars(scope_instruments(select(Instrument.institution_id), scope)))
    with_deposits = set(session.scalars(select(Instrument.institution_id)))
    assert owners == institutions & with_deposits


@pytest.mark.parametrize(
    ("roles", "link", "bank", "institutions", "instruments"),
    [
        # An institution that is also a bank account: its own institution, plus its bank's
        # instruments; never every institution (an unknown mix used to be unrestricted).
        (["institution", "bank_service"], "a", "YBNK", {"SYN-A"}, {"A1", "B1"}),
        (["institution", "bank_service"], "a", None, {"SYN-A"}, {"A1"}),
        # No DepositTrack role at all: nothing.
        ([], None, None, set(), set()),
        # A bank account that is not linked to a bank: nothing.
        (["bank_service"], None, None, set(), set()),
        # Admin reads reports and the audit trail across institutions: everything.
        (["admin"], None, None, {"SYN-A", "SYN-B", "SYN-C"}, {"A1", "B1"}),
        (["admin", "bank_service"], None, "XNBK", {"SYN-A", "SYN-B", "SYN-C"}, {"A1", "B1"}),
    ],
)
def test_unusual_role_mixes_are_denied_by_default(db, roles, link, bank, institutions, instruments):
    session, ids = db
    scope = _scope(roles, institution_id=ids[link] if link else None, bank_code=bank)
    assert _visible(session, scope) == (institutions, instruments)
