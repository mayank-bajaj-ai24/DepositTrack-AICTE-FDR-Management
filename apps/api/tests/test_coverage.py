"""Obligation coverage (N2) for many obligations at once."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Coverage, Instrument, Obligation
from app.modules.lifecycle import coverage
from app.modules.lifecycle.states import InstrumentKind, InstrumentState, TrustLevel
from tests.flow_support import make_sessionmaker, seed

TODAY = date.today()


def _allocate(s, obligation, number, amount, state, trust):
    instrument = Instrument(
        institution_id=obligation.institution_id,
        kind=InstrumentKind.FDR,
        instrument_no=number,
        instrument_no_norm=number,
        amount=amount,
        state=state,
        trust_level=int(trust),
    )
    s.add(instrument)
    s.flush()
    s.add(
        Coverage(
            obligation_id=obligation.id,
            instrument_id=instrument.id,
            allocated_amount=amount,
            valid_from=TODAY - timedelta(days=10),
            valid_to=TODAY + timedelta(days=400),
        )
    )


@pytest.fixture
def db():
    """Synthetic A: attested 500000. B: declared 300000 plus a released 200000 (not live)."""
    factory = make_sessionmaker()
    ids = seed(factory, TODAY)
    with factory() as s:
        by_inst = {o.institution_id: o for o in s.scalars(select(Obligation))}
        a, b = by_inst[ids["a"]], by_inst[ids["b"]]
        _allocate(s, a, "A1", 500000, InstrumentState.ACTIVE, TrustLevel.BANK_ATTESTED)
        _allocate(s, b, "B1", 300000, InstrumentState.ACTIVE, TrustLevel.DECLARED)
        _allocate(s, b, "B0", 200000, InstrumentState.RELEASED, TrustLevel.BANK_ATTESTED)
        s.commit()
        yield s, a, b


@pytest.mark.parametrize("batch", [1, 500])
def test_bulk_reports_match_one_by_one_and_keep_order(db, monkeypatch, batch):
    session, a, b = db
    monkeypatch.setattr(coverage, "_ID_BATCH", batch)
    bulk = coverage.reports(session, [b, a], TODAY)
    assert bulk == [coverage.report(session, b, TODAY), coverage.report(session, a, TODAY)]
    assert [(r.declared_today, r.attested_today) for r in bulk] == [
        (Decimal(300000), Decimal(0)),
        (Decimal(500000), Decimal(500000)),
    ]
    # B is short today; A is covered until its deposit's validity ends.
    assert [r.first_gap for r in bulk] == [TODAY, TODAY + timedelta(days=401)]


def test_reports_of_no_obligations_are_empty(db):
    session, _, _ = db
    assert coverage.reports(session, [], TODAY) == []
