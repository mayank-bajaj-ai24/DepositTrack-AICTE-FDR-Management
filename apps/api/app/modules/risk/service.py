"""Build risk histories from the database and score live instruments (N9)."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Event, Flag, Instrument
from app.modules.lifecycle.states import InstrumentState as S
from app.modules.risk.features import History
from app.modules.risk.model import RiskResult, is_available, predict

SCORED_STATES = {S.ACTIVE, S.EXPIRING}


def _day(ts) -> date:
    return ts.date() if hasattr(ts, "date") else ts


def history_for(session: Session, instrument: Instrument, as_of: date) -> History:
    institution_instruments = list(
        session.scalars(
            select(Instrument).where(Instrument.institution_id == instrument.institution_id)
        )
    )
    ids = [i.id for i in institution_instruments]
    replacements = {i.replaces_id: i for i in institution_instruments if i.replaces_id}

    renewals = []
    for prior in institution_instruments:
        if prior.id == instrument.id or prior.maturity_date is None or prior.maturity_date >= as_of:
            continue
        replacement = replacements.get(prior.id)
        submitted = _day(replacement.created_at) if replacement else None
        renewals.append((prior.maturity_date, submitted))

    events = list(
        session.scalars(
            select(Event)
            .where(Event.instrument_id.in_(ids))
            .order_by(Event.instrument_id, Event.seq)
        )
    )
    actions = [_day(e.ts) for e in events if e.role == "institution"]
    responses = []
    asked: dict = {}
    for e in events:
        after = e.after or {}
        if e.action == "instrument.state_changed" and after.get("state") == "discrepancy":
            asked[e.instrument_id] = _day(e.ts)
        elif (
            e.action == "instrument.state_changed"
            and e.instrument_id in asked
            and after.get("state") == "scrutiny"
        ):
            responses.append(float((_day(e.ts) - asked.pop(e.instrument_id)).days))

    open_flags = len(
        session.scalars(
            select(Flag).where(Flag.instrument_id == instrument.id, Flag.status == "open")
        ).all()
    )
    return History(
        as_of=as_of,
        maturity=instrument.maturity_date,
        amount=float(instrument.amount or 0),
        open_flags=open_flags,
        renewals=renewals,
        response_days=responses,
        action_dates=actions,
    )


def score_live(
    session: Session, models_dir: str, today: date
) -> list[tuple[Instrument, RiskResult]]:
    """Score active instruments; with no loadable model, clear scores left by an earlier one."""
    if not is_available(models_dir):
        for instrument in session.scalars(
            select(Instrument).where(Instrument.risk_score.is_not(None))
        ):
            instrument.risk_score = None
            instrument.risk_reasons = None
        session.flush()
        return []
    scored = []
    for instrument in session.scalars(
        select(Instrument).where(Instrument.state.in_(SCORED_STATES))
    ):
        if instrument.maturity_date is None:
            continue
        result = predict(history_for(session, instrument, today), models_dir)
        if result is None:
            return []
        instrument.risk_score = result.probability
        instrument.risk_reasons = {
            "as_of": today.isoformat(),
            "expected_days_late": result.expected_days_late,
            "reasons": result.reasons,
        }
        scored.append((instrument, result))
    session.flush()
    return scored
