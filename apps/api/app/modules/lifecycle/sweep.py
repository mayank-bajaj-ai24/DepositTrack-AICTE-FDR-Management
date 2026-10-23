"""Daily lifecycle sweep (M7, M8, N2, N9).

Moves instruments through Active -> Expiring/Matured -> Overdue/Renewed, sends the
configured reminders once each, escalates overdue items, high-risk renewals and
forecast coverage gaps, and checks case time boxes. `today` is a parameter so the demo
can advance the clock.
"""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.configfiles import load_config
from app.core.policy import Policy
from app.models import Case, Instrument, Obligation
from app.modules.alerts.service import notify
from app.modules.audit.service import SYSTEM
from app.modules.lifecycle import coverage
from app.modules.lifecycle.service import move
from app.modules.lifecycle.states import InstrumentState as S

SYSTEM_ROLES = {"system"}
RENEWAL_DONE = {S.VERIFIED, S.ACTIVE}


@dataclass
class SweepReport:
    today: date
    moved: list[tuple[str, str, str]] = field(default_factory=list)
    notifications: int = 0
    awaiting_policy: list[str] = field(default_factory=list)


def _replacement_done(session: Session, instrument: Instrument) -> bool:
    replacements = session.scalars(
        select(Instrument).where(Instrument.replaces_id == instrument.id)
    )
    return any(S(r.state) in RENEWAL_DONE for r in replacements)


def _move(session, report, instrument, target, reason):
    before = instrument.state
    move(session, instrument, target, SYSTEM, SYSTEM_ROLES, reason)
    report.moved.append((str(instrument.id), str(before), target.value))


def run_sweep(session: Session, policy: Policy, today: date) -> SweepReport:
    report = SweepReport(today=today)
    alerts_cfg = load_config("alerts.yaml")
    reminder_days = policy.reminder_days
    if reminder_days is None:
        report.awaiting_policy.append("reminders.days_before_maturity")

    live = session.scalars(
        select(Instrument).where(Instrument.state.in_([S.ACTIVE, S.EXPIRING, S.OVERDUE]))
    )
    for inst in list(live):
        if inst.maturity_date is None:
            continue
        days = (inst.maturity_date - today).days
        state = S(inst.state)

        if state in (S.EXPIRING, S.OVERDUE) and _replacement_done(session, inst):
            _move(session, report, inst, S.RENEWED, "replacement instrument accepted")
            continue

        if state == S.ACTIVE:
            if coverage.obligation_ends_by(session, inst):
                if days < 0:
                    _move(session, report, inst, S.MATURED, "matured; obligation has ended")
                continue
            if reminder_days and days <= max(reminder_days):
                _move(session, report, inst, S.EXPIRING, f"{days} days to maturity")
                state = S.EXPIRING

        if state == S.EXPIRING:
            for threshold in reminder_days or []:
                if days <= threshold:
                    report.notifications += notify(
                        session,
                        inst,
                        "maturity_reminder",
                        f"T-{threshold}",
                        f"FDR {inst.instrument_no} matures on {inst.maturity_date.isoformat()} "
                        f"({days} days); submit the renewed or replacement instrument.",
                    )
            risk = inst.risk_score
            if (
                risk is not None
                and risk >= alerts_cfg["risk_escalation_threshold"]
                and days <= alerts_cfg["risk_escalation_days_before_maturity"]
            ):
                report.notifications += notify(
                    session,
                    inst,
                    "risk_escalation",
                    "risk",
                    f"High renewal risk ({risk:.0%}) for FDR {inst.instrument_no}, "
                    f"{days} days before maturity.",
                )
            if days < 0:
                _move(session, report, inst, S.OVERDUE, "maturity passed without replacement")
                state = S.OVERDUE

        if state == S.OVERDUE:
            report.notifications += notify(
                session,
                inst,
                "overdue",
                "overdue",
                f"FDR {inst.instrument_no} matured on {inst.maturity_date.isoformat()} and "
                "has not been renewed or replaced.",
            )

    # Forecast coverage gaps (N2)
    for obligation in session.scalars(select(Obligation).where(Obligation.status == "open")):
        cov = coverage.report(session, obligation, today)
        if cov.first_gap is None:
            continue
        horizon = max(reminder_days) if reminder_days else None
        if horizon is not None and (cov.first_gap - today).days > horizon:
            continue
        anchor = session.scalars(
            select(Instrument)
            .where(Instrument.institution_id == obligation.institution_id)
            .order_by(Instrument.maturity_date.desc())
        ).first()
        if anchor:
            report.notifications += notify(
                session,
                anchor,
                "coverage_gap",
                f"gap:{obligation.id}:{cov.first_gap.isoformat()}",
                f"Deposit requirement will be under-covered from {cov.first_gap.isoformat()}.",
            )

    # Case time boxes (N5)
    now = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
    for case in session.scalars(select(Case).where(Case.state == "open", Case.due_at.is_not(None))):
        due = case.due_at if case.due_at.tzinfo else case.due_at.replace(tzinfo=UTC)
        if due < now:
            case.escalation_level += 1
            case.due_at = now + timedelta(days=policy.officer_action_days or 1)
            inst = session.get(Instrument, case.instrument_id)
            report.notifications += notify(
                session,
                inst,
                "case_overdue",
                f"{case.id}:{case.escalation_level}",
                f"{case.case_type.capitalize()} case is past its time limit "
                f"(escalation level {case.escalation_level}).",
            )
    session.flush()
    return report
