"""Dashboard, reports and notifications (M10, M8)."""

import csv
import io
from collections import Counter, defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import serializers as ser
from app.api.instruments import coverage_payload
from app.core import clock
from app.core.access import Scope, get_scope, scope_institutions, scope_instruments
from app.core.permissions import Action, Role, is_allowed
from app.db.session import get_session
from app.models import Case, Event, Flag, Institution, Instrument, Notification, Obligation
from app.modules.lifecycle import coverage
from app.modules.lifecycle.states import InstrumentState as S

router = APIRouter(prefix="/api/v1", tags=["dashboard"])

PENDING_STATES = {S.SUBMITTED, S.SCRUTINY, S.DISCREPANCY}


def _open_coverage(
    session: Session, scope: Scope, today: date
) -> list[tuple[Obligation, Institution, coverage.CoverageReport]]:
    """Coverage of the open obligations of every institution the caller may see, with or
    without deposits. A fixed number of queries, however many obligations there are."""
    query = (
        select(Obligation, Institution)
        .join(Institution, Institution.id == Obligation.institution_id)
        .where(Obligation.status == "open")
        # Stable order for the coverage strips and for ties in the dashboard's gap list.
        .order_by(Institution.aicte_id, Obligation.required_from, Obligation.id)
    )
    rows = session.execute(scope_institutions(query, scope)).all()
    reports = coverage.reports(session, [o for o, _ in rows], today)
    return [(o, inst, rep) for (o, inst), rep in zip(rows, reports, strict=True)]


def _visible(session: Session, scope: Scope) -> list[tuple[Instrument, Institution]]:
    query = select(Instrument, Institution).join(
        Institution, Institution.id == Instrument.institution_id
    )
    return list(session.execute(scope_instruments(query, scope)).all())


def _require_coverage_view(scope: Scope) -> None:
    """Dashboard and coverage figures need report view (officers, reviewers) or read-own
    (institutions). Bank service accounts and callers with no DepositTrack role are refused."""
    if not (
        is_allowed(scope.principal.roles, Action.REPORT_VIEW)
        or is_allowed(scope.principal.roles, Action.INSTRUMENT_READ_OWN)
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")


@router.get("/dashboard")
def dashboard(scope: Scope = Depends(get_scope), session: Session = Depends(get_session)) -> dict:
    _require_coverage_view(scope)
    today = clock.today(session)
    rows = _visible(session, scope)
    ids = {i.id for i, _ in rows}
    states = Counter(str(i.state) for i, _ in rows)
    open_flags = session.scalars(
        select(Flag).where(Flag.status == "open", Flag.instrument_id.in_(ids))
    ).all()
    flagged_ids = {f.instrument_id for f in open_flags}
    critical_ids = {f.instrument_id for f in open_flags if f.severity == "critical"}

    def expiring_within(days: int) -> int:
        return sum(
            1
            for i, _ in rows
            if i.maturity_date
            and S(i.state) in (S.ACTIVE, S.EXPIRING)
            and 0 <= (i.maturity_date - today).days <= days
        )

    # Coverage across the visible institutions' obligations (N2)
    required = declared = attested = 0
    gaps = []
    for _, inst, rep in _open_coverage(session, scope, today):
        required += rep.required
        declared += rep.declared_today
        attested += rep.attested_today
        if rep.first_gap:
            gaps.append(
                {
                    "institution": ser.institution(inst),
                    "first_gap": rep.first_gap.isoformat(),
                    "required": str(rep.required),
                }
            )

    # Ageing of pending scrutiny (days since submission)
    ageing = Counter()
    for i, _ in rows:
        if S(i.state) in PENDING_STATES and i.created_at:
            created = i.created_at.date()
            age = (today - created).days
            ageing["0-7" if age <= 7 else "8-30" if age <= 30 else "31+"] += 1

    # Bank verification turnaround: submission -> first bank.verified event, in hours
    turnaround = defaultdict(list)
    verified_events = session.scalars(
        select(Event).where(Event.action == "bank.verified", Event.instrument_id.in_(ids))
    ).all()
    first_verified = {}
    for e in verified_events:
        first_verified.setdefault(e.instrument_id, e)
    for i, _ in rows:
        e = first_verified.get(i.id)
        if e and i.created_at:
            hours = (
                e.ts.replace(tzinfo=None) - i.created_at.replace(tzinfo=None)
            ).total_seconds() / 3600
            turnaround[i.bank_name or i.canonical_bank or "unknown"].append(hours)

    risk_by_region = defaultdict(list)
    for i, inst in rows:
        if i.risk_score is not None:
            risk_by_region[inst.region or "unassigned"].append(i.risk_score)

    trust = Counter(i.trust_level for i, _ in rows)
    return {
        "today": today.isoformat(),
        "clock_offset_days": clock.offset_days(session),
        "total": len(rows),
        "states": dict(states),
        "tiles": {
            "active": states.get("active", 0),
            "expiring_30": expiring_within(30),
            "expiring_60": expiring_within(60),
            "expiring_90": expiring_within(90),
            "matured": states.get("matured", 0),
            "renewed": states.get("renewed", 0),
            "released": states.get("released", 0),
            "overdue": states.get("overdue", 0),
            "pending_verification": sum(states.get(s.value, 0) for s in PENDING_STATES),
            "flagged": len(flagged_ids),
            "critical": len(critical_ids),
            "coverage_gaps": len(gaps),
        },
        "coverage": {
            "required": str(required),
            "declared": str(declared),
            "attested": str(attested),
            "exposure": str(declared - attested),
        },
        "gaps": sorted(gaps, key=lambda g: g["first_gap"]),
        "trust_distribution": {str(level): trust.get(level, 0) for level in range(5)},
        "flags_by_type": dict(Counter(f.flag_type for f in open_flags)),
        "ageing": dict(ageing),
        "bank_turnaround_hours": {k: round(sum(v) / len(v), 2) for k, v in turnaround.items()},
        "risk_by_region": {k: round(sum(v) / len(v), 3) for k, v in risk_by_region.items()},
    }


@router.get("/notifications")
def notifications(
    scope: Scope = Depends(get_scope), session: Session = Depends(get_session)
) -> dict:
    ids = {i.id for i, _ in _visible(session, scope)}
    roles = set(scope.principal.roles)
    rows = session.scalars(
        select(Notification)
        .where(Notification.instrument_id.in_(ids), Notification.audience_role.in_(roles))
        .order_by(Notification.created_at.desc())
        .limit(200)
    ).all()
    return {"items": [ser.notification(n) for n in rows]}


REPORTS = {
    "pending-verifications": "Instruments waiting for scrutiny or verification",
    "upcoming-maturities": "Instruments maturing in the next 90 days",
    "missing-documents": "Instruments with missing fields or documents",
    "interventions": "Cases requiring intervention: overdue, critical flags, overdue cases",
}


def _report_rows(name: str, session: Session, scope: Scope) -> tuple[list[str], list[list]]:
    today = clock.today(session)
    rows = _visible(session, scope)
    header = [
        "Institution",
        "AICTE ID",
        "FDR number",
        "Bank",
        "IFSC",
        "Amount",
        "Maturity",
        "State",
        "Trust level",
        "Detail",
    ]

    def base(i, inst, detail=""):
        return [
            inst.name,
            inst.aicte_id,
            i.instrument_no,
            i.bank_name,
            i.bank_ifsc,
            str(i.amount or ""),
            i.maturity_date.isoformat() if i.maturity_date else "",
            str(i.state),
            i.trust_level,
            detail,
        ]

    out = []
    if name == "pending-verifications":
        out = [base(i, inst) for i, inst in rows if S(i.state) in PENDING_STATES | {S.VERIFIED}]
    elif name == "upcoming-maturities":
        horizon = today + timedelta(days=90)
        out = [
            base(i, inst, f"{(i.maturity_date - today).days} days")
            for i, inst in rows
            if i.maturity_date
            and today <= i.maturity_date <= horizon
            and S(i.state) in (S.ACTIVE, S.EXPIRING)
        ]
    elif name == "missing-documents":
        flags = session.scalars(
            select(Flag).where(
                Flag.status == "open", Flag.flag_type.in_(["missing_field", "missing_document"])
            )
        ).all()
        by_inst = defaultdict(list)
        for f in flags:
            by_inst[f.instrument_id].append(f.reason_text)
        out = [base(i, inst, "; ".join(by_inst[i.id])) for i, inst in rows if i.id in by_inst]
    elif name == "interventions":
        critical = {
            f.instrument_id: f.reason_text
            for f in session.scalars(
                select(Flag).where(Flag.status == "open", Flag.severity == "critical")
            )
        }
        late_cases = {
            c.instrument_id
            for c in session.scalars(
                select(Case).where(Case.state == "open", Case.escalation_level > 0)
            )
        }
        for i, inst in rows:
            reasons = []
            if S(i.state) == S.OVERDUE:
                reasons.append("overdue: matured without renewal")
            if i.id in critical:
                reasons.append(f"critical flag: {critical[i.id]}")
            if i.id in late_cases:
                reasons.append("case past its time limit")
            if reasons:
                out.append(base(i, inst, "; ".join(reasons)))
    else:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown report")
    return header, out


@router.get("/reports")
def list_reports() -> dict:
    return {"items": [{"name": k, "title": v} for k, v in REPORTS.items()]}


@router.get("/reports/{name}")
def report(
    name: str,
    format: str = "json",
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
):
    if not (is_allowed(scope.principal.roles, Action.REPORT_VIEW) or scope.has(Role.INSTITUTION)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")
    header, rows = _report_rows(name, session, scope)
    if format == "json":
        return {"name": name, "title": REPORTS[name], "header": header, "rows": rows}
    if format == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(header)
        writer.writerows(rows)
        return Response(
            buffer.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{name}.csv"'},
        )
    if format == "xlsx":
        book = Workbook()
        sheet = book.active
        sheet.title = name[:31]
        sheet.append(header)
        for row in rows:
            sheet.append(row)
        buffer = io.BytesIO()
        book.save(buffer)
        return Response(
            buffer.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'},
        )
    raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "format must be json, csv or xlsx")


@router.get("/coverage")
def coverage_reports(
    scope: Scope = Depends(get_scope), session: Session = Depends(get_session)
) -> dict:
    """Coverage of every open obligation the caller may see (N2): one strip per obligation."""
    _require_coverage_view(scope)
    today = clock.today(session)
    items = []
    for obligation, institution, rep in _open_coverage(session, scope, today):
        items.append(
            {
                "institution": ser.institution(institution),
                "basis_ref": obligation.basis_ref,
                "coverage": coverage_payload(rep),
            }
        )
    return {"today": today.isoformat(), "items": items}
