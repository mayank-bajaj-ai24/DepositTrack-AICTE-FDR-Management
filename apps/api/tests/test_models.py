import uuid
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401  (registers tables)
from app.db.base import Base
from app.models import Institution, Instrument
from app.modules.lifecycle.states import InstrumentKind, InstrumentState

EXPECTED_TABLES = {
    "user_account",
    "notification",
    "system_setting",
    "institution",
    "obligation",
    "instrument",
    "coverage",
    "field_value",
    "document",
    "attestation",
    "flag",
    "observation",
    "case",
    "event",
    "anchor",
    "policy_version",
    "ifsc_lineage",
    "field_permission",
}


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_all_plan_tables_exist():
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def _instrument(institution_id, number="FDR001"):
    return Instrument(
        institution_id=institution_id,
        kind=InstrumentKind.FDR,
        canonical_bank="XMPL",
        instrument_no=number,
        instrument_no_norm=number.upper(),
        amount=Decimal("1.00"),
    )


def test_new_instrument_defaults_to_draft_and_declared(session):
    inst = Institution(aicte_id="TEST-1", name="Synthetic Test Institute")
    session.add(inst)
    session.flush()
    fdr = _instrument(inst.id)
    session.add(fdr)
    session.flush()
    assert fdr.state == InstrumentState.DRAFT
    assert fdr.trust_level == 0
    assert isinstance(fdr.id, uuid.UUID)


def test_same_fdr_can_be_stored_twice_so_it_can_be_flagged(session):
    """The canonical key is indexed, not unique: double pledges are flagged, not rejected."""
    a = Institution(aicte_id="TEST-A", name="Synthetic A")
    b = Institution(aicte_id="TEST-B", name="Synthetic B")
    session.add_all([a, b])
    session.flush()
    session.add_all([_instrument(a.id), _instrument(b.id)])
    session.flush()
    indexes = {ix.name for ix in Base.metadata.tables["instrument"].indexes}
    assert "ix_instrument_canonical" in indexes
