"""Instrument endpoints (M2, M3, M4, M5, M7)."""

import json
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api import serializers as ser
from app.api.deps import actor_of, bank_dep, extractor_dep, policy_dep, store_dep
from app.core import clock
from app.core.access import Scope, get_scope, get_visible_instrument, scope_instruments
from app.core.config import Settings, get_settings
from app.core.configfiles import load_config, workflow
from app.core.permissions import Action, Role, is_allowed
from app.core.policy import Policy
from app.db.session import get_session
from app.models import (
    Case,
    Coverage,
    Document,
    Event,
    FieldValue,
    Flag,
    Institution,
    Instrument,
    Notification,
    Obligation,
    Observation,
)
from app.modules.audit.service import record_event, verify_chain
from app.modules.bank.client import BankClient
from app.modules.bank.service import refresh_status, verify_with_bank
from app.modules.extraction.service import FIELDS
from app.modules.instruments.intake import submit_instrument
from app.modules.instruments.trust import instrument_level
from app.modules.lifecycle import coverage
from app.modules.lifecycle.service import move
from app.modules.lifecycle.states import InstrumentKind, InstrumentState, TrustLevel
from app.modules.release.service import blockers
from app.modules.storage.store import DocumentStore

router = APIRouter(prefix="/api/v1", tags=["instruments"])


def _require(scope: Scope, action: Action) -> None:
    if not is_allowed(scope.principal.roles, action):
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Not permitted: {action.value}")


def _read_upload(file: UploadFile, settings: Settings) -> bytes:
    data = file.file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE, f"File exceeds {settings.max_upload_mb} MB"
        )
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Empty file")
    return data


@router.post("/extract")
def extract_preview(
    file: UploadFile = File(...),
    scope: Scope = Depends(get_scope),
    settings: Settings = Depends(get_settings),
    extractor=Depends(extractor_dep),
) -> dict:
    """Run OCR + extraction on a scan without saving anything (auto-fill for the form)."""
    _require(scope, Action.INSTRUMENT_SUBMIT)
    result = extractor(_read_upload(file, settings), file.content_type)
    if result is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Upload a PNG or JPG scan")
    return {
        "pass_a_available": result.pass_a_available,
        "fields": {
            name: {
                "value": r.value,
                "pass_a": r.pass_a,
                "pass_b": r.pass_b,
                "confidence": r.confidence,
                "needs_review": r.needs_review,
                "reason": r.reason,
            }
            for name, r in result.fields.items()
        },
    }


@router.post("/instruments", status_code=201)
def submit(
    file: UploadFile = File(...),
    declared: str = Form(..., description="JSON object of confirmed field values"),
    kind: InstrumentKind = Form(InstrumentKind.FDR),
    replaces_id: uuid.UUID | None = Form(None),
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    store: DocumentStore = Depends(store_dep),
    policy: Policy = Depends(policy_dep),
    extractor=Depends(extractor_dep),
) -> dict:
    _require(scope, Action.INSTRUMENT_SUBMIT)
    try:
        values = json.loads(declared)
    except json.JSONDecodeError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "declared must be JSON") from exc
    values = {
        k: (str(v).strip() if v not in (None, "") else None)
        for k, v in values.items()
        if k in FIELDS
    }
    replaces = get_visible_instrument(session, scope, replaces_id) if replaces_id else None
    instrument = submit_instrument(
        session,
        store=store,
        policy=policy,
        actor=actor_of(scope),
        roles=scope.principal.roles,
        institution_id=scope.institution_id,
        kind=kind,
        declared=values,
        file_bytes=_read_upload(file, settings),
        content_type=file.content_type,
        extractor=extractor,
        replaces=replaces,
    )
    session.commit()
    return {
        "id": str(instrument.id),
        "state": str(instrument.state),
        "trust_level": instrument.trust_level,
    }


@router.get("/instruments")
def list_instruments(
    state: list[InstrumentState] | None = Query(None),
    q: str | None = None,
    min_trust: int | None = None,
    flagged: bool | None = None,
    institution_id: uuid.UUID | None = None,
    limit: int = Query(50, le=500),
    offset: int = 0,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> dict:
    if not (
        is_allowed(scope.principal.roles, Action.INSTRUMENT_READ_ALL)
        or is_allowed(scope.principal.roles, Action.INSTRUMENT_READ_OWN)
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")
    open_flags = (
        select(Flag.instrument_id, func.count().label("n"))
        .where(Flag.status == "open")
        .group_by(Flag.instrument_id)
        .subquery()
    )
    query = (
        select(Instrument, Institution, func.coalesce(open_flags.c.n, 0))
        .join(Institution, Institution.id == Instrument.institution_id)
        .outerjoin(open_flags, open_flags.c.instrument_id == Instrument.id)
    )
    query = scope_instruments(query, scope)
    if state:
        query = query.where(Instrument.state.in_(state))
    if institution_id:
        query = query.where(Instrument.institution_id == institution_id)
    if min_trust is not None:
        query = query.where(Instrument.trust_level >= min_trust)
    if flagged is True:
        query = query.where(open_flags.c.n > 0)
    if q:
        like = f"%{q.strip()}%"
        query = query.where(
            or_(
                Instrument.instrument_no.ilike(like),
                Instrument.bank_ifsc.ilike(like),
                Instrument.bank_name.ilike(like),
                Institution.name.ilike(like),
                Institution.aicte_id.ilike(like),
            )
        )
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    rows = session.execute(query.order_by(Instrument.maturity_date).limit(limit).offset(offset))
    return {
        "total": total,
        "items": [ser.instrument_summary(i, inst, n) for i, inst, n in rows],
    }


def _require_instrument_read(scope: Scope) -> None:
    """Opening one instrument (its fields, history, documents) needs a read permission;
    visibility alone is not enough (a bank account may see that an instrument exists)."""
    roles = scope.principal.roles
    if not any(
        is_allowed(roles, action)
        for action in (Action.INSTRUMENT_READ_ALL, Action.INSTRUMENT_READ_OWN, Action.AUDIT_READ)
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")


@router.get("/instruments/{instrument_id}")
def detail(
    instrument_id: uuid.UUID,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> dict:
    _require_instrument_read(scope)
    instrument = get_visible_instrument(session, scope, instrument_id)
    institution = session.get(Institution, instrument.institution_id)
    fields = session.scalars(
        select(FieldValue).where(FieldValue.instrument_id == instrument.id)
    ).all()
    flags = session.scalars(
        select(Flag).where(Flag.instrument_id == instrument.id).order_by(Flag.created_at)
    ).all()
    cases = session.scalars(
        select(Case).where(Case.instrument_id == instrument.id).order_by(Case.created_at)
    ).all()
    events = session.scalars(
        select(Event).where(Event.instrument_id == instrument.id).order_by(Event.seq)
    ).all()
    chain = verify_chain(session, instrument.id)
    replaced_by = session.scalars(
        select(Instrument).where(Instrument.replaces_id == instrument.id)
    ).all()
    notifications = session.scalars(
        select(Notification)
        .where(Notification.instrument_id == instrument.id)
        .order_by(Notification.created_at)
    ).all()
    can_audit = is_allowed(scope.principal.roles, Action.AUDIT_READ) or is_allowed(
        scope.principal.roles, Action.INSTRUMENT_READ_ALL
    )
    cov = None
    obligation = session.scalars(
        select(Obligation)
        .join(Coverage, Coverage.obligation_id == Obligation.id)
        .where(Coverage.instrument_id == instrument.id)
    ).first()
    if obligation:
        cov = coverage_payload(coverage.report(session, obligation, clock.today(session)))
    return {
        "instrument": ser.instrument_summary(
            instrument, institution, sum(f.status == "open" for f in flags)
        ),
        "today": clock.today(session).isoformat(),
        "beneficiary_text": instrument.beneficiary_text,
        "lien_marked": instrument.lien_marked,
        "fields": [
            ser.field_value(fv) for fv in sorted(fields, key=lambda f: FIELDS.index(f.field))
        ],
        "documents": [
            ser.document(d)
            for d in session.scalars(
                select(Document).where(Document.instrument_id == instrument.id)
            )
        ],
        "flags": [ser.flag(f) for f in flags],
        "observations": [
            ser.observation(o)
            for o in session.scalars(
                select(Observation)
                .where(Observation.instrument_id == instrument.id)
                .order_by(Observation.created_at)
            )
        ],
        "cases": [ser.case(c, blockers(session, c) if c.state == "open" else []) for c in cases],
        "events": [ser.event(e) for e in events] if can_audit else [],
        "chain": {
            "intact": chain.intact,
            "length": chain.length,
            "broken_at_seq": chain.broken_at_seq,
            "head_hash": chain.head_hash,
        },
        "replaced_by": [ser.instrument_summary(r) for r in replaced_by],
        "notifications": [ser.notification(n) for n in notifications],
        "coverage": cov,
        "editable_fields": sorted(
            {
                f
                for role in scope.principal.roles
                for f in workflow()["editable_fields"].get(role, [])
            }
        ),
        "next_states": [
            t.split("->")[1]
            for t, roles in workflow()["transitions"].items()
            if t.startswith(f"{instrument.state}->") and set(roles) & set(scope.principal.roles)
        ],
    }


def coverage_payload(report) -> dict:
    return {
        "obligation_id": report.obligation_id,
        "required": str(report.required),
        "declared_today": str(report.declared_today),
        "attested_today": str(report.attested_today),
        "exposure_today": str(report.exposure_today),
        "first_gap": report.first_gap.isoformat() if report.first_gap else None,
        "segments": [
            {
                "start": s.start.isoformat(),
                "end": s.end.isoformat(),
                "declared": str(s.declared),
                "attested": str(s.attested),
                "required": str(s.required),
            }
            for s in report.segments
        ],
    }


@router.get("/instruments/{instrument_id}/documents/{document_id}")
def download(
    instrument_id: uuid.UUID,
    document_id: uuid.UUID,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
    store: DocumentStore = Depends(store_dep),
) -> Response:
    _require_instrument_read(scope)
    instrument = get_visible_instrument(session, scope, instrument_id)
    document = session.get(Document, document_id)
    if document is None or document.instrument_id != instrument.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    data = store.load(document.storage_key)
    media = (
        "application/pdf"
        if data[:4] == b"%PDF"
        else "image/png"
        if data[:4] == b"\x89PNG"
        else "image/jpeg"
    )
    record_event(
        session,
        actor=actor_of(scope),
        action="document.downloaded",
        instrument_id=instrument.id,
        after={"document_id": str(document.id)},
    )
    session.commit()
    return Response(content=data, media_type=media, headers={"X-Content-SHA256": document.sha256})


class TransitionIn(BaseModel):
    target: InstrumentState
    reason: str


@router.post("/instruments/{instrument_id}/transition")
def change_state(
    instrument_id: uuid.UUID,
    body: TransitionIn,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
    policy: Policy = Depends(policy_dep),
) -> dict:
    instrument = get_visible_instrument(session, scope, instrument_id)
    if not body.reason.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "A reason is required")
    if (
        body.target == InstrumentState.ACTIVE
        and policy.require_bank_attestation_for_active
        and instrument.trust_level < TrustLevel.BANK_ATTESTED
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Policy requires bank attestation before activation"
        )
    if body.target == InstrumentState.VERIFIED:
        critical = session.scalars(
            select(Flag).where(
                Flag.instrument_id == instrument.id,
                Flag.status == "open",
                Flag.severity == "critical",
            )
        ).first()
        if critical:
            raise HTTPException(
                status.HTTP_409_CONFLICT, f"Resolve the critical flag first: {critical.reason_text}"
            )
    move(session, instrument, body.target, actor_of(scope), scope.principal.roles, body.reason)
    if body.target == InstrumentState.ACTIVE:
        coverage.allocate(session, instrument)
    session.commit()
    return {"id": str(instrument.id), "state": str(instrument.state)}


class ObservationIn(BaseModel):
    text: str


@router.post("/instruments/{instrument_id}/observations", status_code=201)
def add_observation(
    instrument_id: uuid.UUID,
    body: ObservationIn,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> dict:
    _require(scope, Action.OBSERVATION_RECORD)
    instrument = get_visible_instrument(session, scope, instrument_id)
    obs = Observation(
        instrument_id=instrument.id, officer_id=scope.principal.username, text=body.text.strip()
    )
    session.add(obs)
    session.flush()
    record_event(
        session,
        actor=actor_of(scope),
        action="observation.recorded",
        instrument_id=instrument.id,
        after={"observation_id": str(obs.id)},
        reason=obs.text,
    )
    session.commit()
    return ser.observation(obs)


class ResolveIn(BaseModel):
    resolution: str


@router.post("/instruments/{instrument_id}/flags/{flag_id}/resolve")
def resolve_flag(
    instrument_id: uuid.UUID,
    flag_id: uuid.UUID,
    body: ResolveIn,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> dict:
    _require(scope, Action.SCRUTINY_REVIEW)
    instrument = get_visible_instrument(session, scope, instrument_id)
    flag = session.get(Flag, flag_id)
    if flag is None or flag.instrument_id != instrument.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Flag not found")
    if not body.resolution.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "A resolution note is required")
    flag.status = "resolved"
    flag.resolved_by = scope.principal.username
    record_event(
        session,
        actor=actor_of(scope),
        action="flag.resolved",
        instrument_id=instrument.id,
        after={"flag_id": str(flag.id), "type": flag.flag_type},
        reason=body.resolution,
    )
    session.commit()
    return ser.flag(flag)


class FieldEditIn(BaseModel):
    value: str | None = None
    reason: str
    verify: bool = False


@router.post("/instruments/{instrument_id}/fields/{field}")
def edit_field(
    instrument_id: uuid.UUID,
    field: str,
    body: FieldEditIn,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> dict:
    """Officer correction of a permitted field, or officer verification (Trust Ladder L2)."""
    instrument = get_visible_instrument(session, scope, instrument_id)
    fv = session.scalars(
        select(FieldValue).where(
            FieldValue.instrument_id == instrument.id, FieldValue.field == field
        )
    ).first()
    if fv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown field")
    if not body.reason.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "A reason is required")
    roles = scope.principal.roles
    before = ser.field_value(fv)
    if body.verify:
        if not (Role.SCRUTINY_OFFICER.value in roles or Role.VERIFYING_OFFICER.value in roles):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only officers can verify fields")
        fv.trust_level = max(fv.trust_level, int(TrustLevel.OFFICER_VERIFIED))
    else:
        editable = {f for role in roles for f in workflow()["editable_fields"].get(role, [])}
        if field not in editable:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Your role cannot edit {field}")
        fv.declared = body.value
        fv.trust_level = int(TrustLevel.OFFICER_VERIFIED)
        if field == "beneficiary":
            instrument.beneficiary_text = body.value
    values = session.scalars(
        select(FieldValue).where(FieldValue.instrument_id == instrument.id)
    ).all()
    instrument.trust_level = instrument_level(list(values))
    record_event(
        session,
        actor=actor_of(scope),
        action="field.verified" if body.verify else "field.edited",
        instrument_id=instrument.id,
        before=before,
        after=ser.field_value(fv),
        reason=body.reason,
    )
    session.commit()
    return ser.field_value(fv)


@router.post("/instruments/{instrument_id}/bank-verification")
def bank_verification(
    instrument_id: uuid.UUID,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    bank: BankClient | None = Depends(bank_dep),
) -> dict:
    _require(scope, Action.VERIFICATION_RECORD)
    if bank is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Bank channel is not configured (DT_BANK_API_TOKEN)",
        )
    instrument = get_visible_instrument(session, scope, instrument_id)
    result = verify_with_bank(session, instrument, actor_of(scope), bank, settings.bank_keys_file)
    session.commit()
    return result | {"trust_level": instrument.trust_level}


@router.post("/instruments/{instrument_id}/bank-status")
def bank_status(
    instrument_id: uuid.UUID,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    bank: BankClient | None = Depends(bank_dep),
) -> dict:
    _require(scope, Action.VERIFICATION_RECORD)
    if bank is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Bank channel is not configured (DT_BANK_API_TOKEN)",
        )
    instrument = get_visible_instrument(session, scope, instrument_id)
    result = refresh_status(session, instrument, actor_of(scope), bank, settings.bank_keys_file)
    session.commit()
    return result | {"trust_level": instrument.trust_level}


@router.get("/extraction/config")
def extraction_config() -> dict:
    """Fields the submit form shows and the review threshold."""
    return {
        "fields": list(FIELDS),
        "human_review_below": load_config("extraction.yaml")["human_review_below"],
    }
