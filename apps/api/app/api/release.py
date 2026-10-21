"""Release / discharge / refund endpoints (M9)."""

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api import serializers as ser
from app.api.deps import actor_of, bank_dep, policy_dep, store_dep
from app.core import clock
from app.core.access import Scope, get_scope, get_visible_instrument, scope_instruments
from app.core.config import Settings, get_settings
from app.core.permissions import Action, is_allowed
from app.core.policy import Policy
from app.db.session import get_session
from app.models import Case, Document, Institution, Instrument
from app.modules.audit.service import record_event
from app.modules.bank.client import BankClient
from app.modules.release.service import blockers, complete_item, decide, open_case
from app.modules.storage.store import DocumentStore

router = APIRouter(prefix="/api/v1", tags=["release"])


class ReleaseRequestIn(BaseModel):
    case_type: str = "release"
    reason: str


@router.post("/instruments/{instrument_id}/release-requests", status_code=201)
def request_release(
    instrument_id: uuid.UUID,
    body: ReleaseRequestIn,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
    policy: Policy = Depends(policy_dep),
) -> dict:
    if not is_allowed(scope.principal.roles, Action.RELEASE_REQUEST):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")
    instrument = get_visible_instrument(session, scope, instrument_id)
    case = open_case(session, instrument, policy, actor_of(scope), body.case_type, body.reason)
    session.commit()
    return ser.case(case, blockers(session, case))


def _case(session: Session, scope: Scope, case_id: uuid.UUID) -> Case:
    case = session.get(Case, case_id)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")
    get_visible_instrument(session, scope, case.instrument_id)
    return case


@router.get("/cases")
def list_cases(
    state: str | None = "open",
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> dict:
    query = (
        select(Case, Instrument, Institution)
        .join(Instrument, Instrument.id == Case.instrument_id)
        .join(Institution, Institution.id == Instrument.institution_id)
    )
    query = scope_instruments(query, scope)
    if state:
        query = query.where(Case.state == state)
    rows = session.execute(query.order_by(Case.due_at)).all()
    return {
        "total": len(rows),
        "items": [
            ser.case(c, blockers(session, c) if c.state == "open" else [])
            | {"instrument": ser.instrument_summary(i, inst)}
            for c, i, inst in rows
        ],
    }


@router.get("/cases/{case_id}")
def get_case(
    case_id: uuid.UUID, scope: Scope = Depends(get_scope), session: Session = Depends(get_session)
) -> dict:
    case = _case(session, scope, case_id)
    return ser.case(case, blockers(session, case) if case.state == "open" else [])


@router.post("/cases/{case_id}/evidence", status_code=201)
def upload_evidence(
    case_id: uuid.UUID,
    item_id: str,
    file: UploadFile = File(...),
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    store: DocumentStore = Depends(store_dep),
) -> dict:
    case = _case(session, scope, case_id)
    data = file.file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if not data or len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Empty or oversized file")
    key, digest = store.save(data)
    kind = f"evidence:{item_id}"
    version = (
        session.scalar(
            select(func.max(Document.version)).where(
                Document.instrument_id == case.instrument_id, Document.kind == kind
            )
        )
        or 0
    ) + 1
    document = Document(
        instrument_id=case.instrument_id,
        version=version,
        kind=kind,
        sha256=digest,
        storage_key=key,
        uploaded_by=scope.principal.username,
    )
    session.add(document)
    session.flush()
    record_event(
        session,
        actor=actor_of(scope),
        action="document.uploaded",
        instrument_id=case.instrument_id,
        case_id=case.id,
        after={"document_id": str(document.id), "sha256": digest, "kind": kind, "version": version},
    )
    complete_item(
        session, case, item_id, actor_of(scope), scope.principal.roles, ref=str(document.id)
    )
    session.commit()
    return ser.case(case, blockers(session, case))


class ItemIn(BaseModel):
    note: str | None = None


@router.post("/cases/{case_id}/checklist/{item_id}")
def tick_item(
    case_id: uuid.UUID,
    item_id: str,
    body: ItemIn,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> dict:
    case = _case(session, scope, case_id)
    complete_item(session, case, item_id, actor_of(scope), scope.principal.roles, ref=body.note)
    session.commit()
    return ser.case(case, blockers(session, case))


class DecisionIn(BaseModel):
    approve: bool
    reason: str


@router.post("/cases/{case_id}/decision")
def decide_case(
    case_id: uuid.UUID,
    body: DecisionIn,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
    policy: Policy = Depends(policy_dep),
    store: DocumentStore = Depends(store_dep),
    bank: BankClient | None = Depends(bank_dep),
) -> dict:
    if not is_allowed(scope.principal.roles, Action.RELEASE_APPROVE):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")
    case = _case(session, scope, case_id)
    decide(
        session,
        case=case,
        policy=policy,
        actor=actor_of(scope),
        roles=scope.principal.roles,
        approve=body.approve,
        reason=body.reason,
        store=store,
        bank=bank,
        today=clock.today(session),
    )
    session.commit()
    return ser.case(case)
