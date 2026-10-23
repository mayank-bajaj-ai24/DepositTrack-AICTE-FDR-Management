"""Obligation-Coverage model (N2).

C(t) = sum of amounts allocated from instruments valid on day t.
Declared coverage counts every live instrument; attested coverage counts only
instruments at Trust Ladder L3 or above. Verification exposure = declared - attested.
"""

import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Coverage, Instrument, Obligation
from app.modules.lifecycle.states import InstrumentState, TrustLevel

# Obligation ids per allocation query when reporting on many obligations at once.
_ID_BATCH = 500

# States in which an instrument still covers an obligation.
LIVE_STATES = {
    InstrumentState.SUBMITTED,
    InstrumentState.SCRUTINY,
    InstrumentState.DISCREPANCY,
    InstrumentState.VERIFIED,
    InstrumentState.ACTIVE,
    InstrumentState.EXPIRING,
    InstrumentState.MATURED,
}


@dataclass(frozen=True)
class Segment:
    start: date
    end: date  # inclusive
    declared: Decimal
    attested: Decimal
    required: Decimal

    @property
    def gap(self) -> Decimal:
        return max(Decimal(0), self.required - self.declared)


@dataclass(frozen=True)
class CoverageReport:
    obligation_id: str
    required: Decimal
    segments: list[Segment]
    declared_today: Decimal
    attested_today: Decimal
    first_gap: date | None

    @property
    def exposure_today(self) -> Decimal:
        return self.declared_today - self.attested_today


def _allocations(
    session: Session, obligations: Sequence[Obligation]
) -> dict[uuid.UUID, list[tuple[Coverage, Instrument]]]:
    """Live allocations of many obligations, grouped by obligation id.

    One query per batch of `_ID_BATCH` ids, so the cost does not grow with every obligation
    on a dashboard and the IN list stays under the drivers' bind-parameter limits.
    """
    ids = list(dict.fromkeys(o.id for o in obligations))
    grouped: dict[uuid.UUID, list[tuple[Coverage, Instrument]]] = defaultdict(list)
    for start in range(0, len(ids), _ID_BATCH):
        rows = session.execute(
            select(Coverage, Instrument)
            .join(Instrument, Instrument.id == Coverage.instrument_id)
            .where(Coverage.obligation_id.in_(ids[start : start + _ID_BATCH]))
        )
        for c, i in rows:
            if InstrumentState(i.state) in LIVE_STATES:
                grouped[c.obligation_id].append((c, i))
    return grouped


def segments(
    allocations: list[tuple[Coverage, Instrument]], start: date, end: date, required: Decimal
) -> list[Segment]:
    """Piecewise-constant coverage between start and end (inclusive)."""
    points = {start, end + timedelta(days=1)}
    for cov, _ in allocations:
        for point in (cov.valid_from, cov.valid_to + timedelta(days=1)):
            if start <= point <= end + timedelta(days=1):
                points.add(point)
    ordered = sorted(points)
    out = []
    for left, right in zip(ordered, ordered[1:], strict=False):
        declared = attested = Decimal(0)
        for cov, inst in allocations:
            if cov.valid_from <= left <= cov.valid_to:
                declared += cov.allocated_amount
                if inst.trust_level >= TrustLevel.BANK_ATTESTED:
                    attested += cov.allocated_amount
        out.append(Segment(left, right - timedelta(days=1), declared, attested, required))
    return out


def report(session: Session, obligation: Obligation, today: date) -> CoverageReport:
    return reports(session, [obligation], today)[0]


def reports(
    session: Session, obligations: Sequence[Obligation], today: date
) -> list[CoverageReport]:
    """Coverage of many obligations, in the given order, loading allocations in bulk."""
    allocations = _allocations(session, obligations)
    return [_report(o, allocations.get(o.id, []), today) for o in obligations]


def _report(
    obligation: Obligation, allocations: list[tuple[Coverage, Instrument]], today: date
) -> CoverageReport:
    end = obligation.required_until or (today + timedelta(days=5 * 365))
    start = min(obligation.required_from, today)
    segs = segments(allocations, start, end, Decimal(obligation.required_amount))
    current = next((s for s in segs if s.start <= today <= s.end), None)
    first_gap = next(
        (
            max(s.start, today, obligation.required_from)
            for s in segs
            if s.end >= today and s.end >= obligation.required_from and s.gap > 0
        ),
        None,
    )
    return CoverageReport(
        obligation_id=str(obligation.id),
        required=Decimal(obligation.required_amount),
        segments=segs,
        declared_today=current.declared if current else Decimal(0),
        attested_today=current.attested if current else Decimal(0),
        first_gap=first_gap,
    )


def allocate(session: Session, instrument: Instrument) -> Coverage | None:
    """Allocate an active instrument to its institution's open obligation, once."""
    if (
        instrument.amount is None
        or instrument.issue_date is None
        or instrument.maturity_date is None
    ):
        return None
    existing = session.scalars(
        select(Coverage).where(Coverage.instrument_id == instrument.id)
    ).first()
    if existing:
        return existing
    obligation = session.scalars(
        select(Obligation)
        .where(Obligation.institution_id == instrument.institution_id, Obligation.status == "open")
        .order_by(Obligation.required_from)
    ).first()
    if obligation is None:
        return None
    coverage = Coverage(
        obligation_id=obligation.id,
        instrument_id=instrument.id,
        allocated_amount=instrument.amount,
        valid_from=instrument.issue_date,
        valid_to=instrument.maturity_date,
    )
    session.add(coverage)
    session.flush()
    return coverage


def obligation_ends_by(session: Session, instrument: Instrument) -> bool:
    """True when every obligation this instrument covers ends on or before its maturity.

    Such an instrument matures (and can be released) instead of needing a renewal.
    """
    rows = session.execute(
        select(Obligation)
        .join(Coverage, Coverage.obligation_id == Obligation.id)
        .where(Coverage.instrument_id == instrument.id)
    ).scalars()
    obligations = list(rows)
    if not obligations or instrument.maturity_date is None:
        return False
    return all(
        o.required_until is not None and o.required_until <= instrument.maturity_date
        for o in obligations
    )
