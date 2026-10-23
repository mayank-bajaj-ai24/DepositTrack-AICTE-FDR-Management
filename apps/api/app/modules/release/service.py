"""Release / discharge / refund workflow (M9, N5).

request -> checklist from the policy version -> evidence -> approval with mandatory
reason -> release letter -> bank removes the lien -> Released. Approval is blocked while
any checklist item is open or any critical flag is unresolved.
"""

import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.policy import Policy
from app.models import Attestation, Case, Document, Flag, Institution, Instrument
from app.modules.audit.service import SYSTEM, Actor, record_event
from app.modules.bank.client import BankChannelError, BankClient
from app.modules.lifecycle.service import move
from app.modules.lifecycle.states import InstrumentState as S
from app.modules.release.letter import render_release_letter
from app.modules.storage.store import DocumentStore

CASE_TYPES = {"release", "discharge", "refund"}
REQUESTABLE_STATES = {S.ACTIVE, S.MATURED}
EVIDENCE_ROLES = {
    "document": "institution",
    "declaration": "institution",
    "officer": "scrutiny_officer",
}


def _now() -> datetime:
    return datetime.now(UTC)


def open_case(
    session: Session,
    instrument: Instrument,
    policy: Policy,
    actor: Actor,
    case_type: str,
    reason: str,
) -> Case:
    if case_type not in CASE_TYPES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"case_type must be one of {sorted(CASE_TYPES)}"
        )
    if S(instrument.state) not in REQUESTABLE_STATES:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Cannot request {case_type} in state {instrument.state}"
        )
    checklist = policy.release_checklist
    if checklist is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Release conditions are awaiting AICTE policy (plan §14 Q4)"
        )
    existing = session.scalars(
        select(Case).where(
            Case.instrument_id == instrument.id,
            Case.case_type.in_(CASE_TYPES),
            Case.state == "open",
        )
    ).first()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "A release request is already open")
    days = policy.officer_action_days
    case = Case(
        id=uuid.uuid4(),
        case_type=case_type,
        instrument_id=instrument.id,
        state="open",
        assignee_role="scrutiny_officer",
        due_at=_now() + timedelta(days=days) if days else None,
        policy_version=policy.version,
        checklist=[
            {
                "id": i.id,
                "label": i.label,
                "evidence": i.evidence,
                "done": False,
                "by": None,
                "at": None,
                "ref": None,
            }
            for i in checklist
        ],
        opened_by=actor.username,
        reason=reason,
    )
    session.add(case)
    session.flush()
    record_event(
        session,
        actor=actor,
        action="release.requested",
        instrument_id=instrument.id,
        case_id=case.id,
        after={"case_type": case_type, "policy_version": policy.version},
        reason=reason,
    )
    return case


def complete_item(
    session: Session,
    case: Case,
    item_id: str,
    actor: Actor,
    roles: frozenset[str],
    ref: str | None = None,
) -> Case:
    if case.state != "open":
        raise HTTPException(status.HTTP_409_CONFLICT, "Case is not open")
    items = [dict(i) for i in case.checklist or []]
    item = next((i for i in items if i["id"] == item_id), None)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such checklist item")
    needed = EVIDENCE_ROLES[item["evidence"]]
    if needed not in roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Only {needed} can complete this item")
    if item["evidence"] == "document" and not ref:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Upload the evidence document first"
        )
    item.update(done=True, by=actor.username, at=_now().isoformat(), ref=ref)
    case.checklist = items
    record_event(
        session,
        actor=actor,
        action="release.checklist_item_done",
        instrument_id=case.instrument_id,
        case_id=case.id,
        after={"item": item_id, "ref": ref},
    )
    return case


def blockers(session: Session, case: Case) -> list[str]:
    reasons = [f"checklist item open: {i['label']}" for i in case.checklist or [] if not i["done"]]
    critical = session.scalars(
        select(Flag).where(
            Flag.instrument_id == case.instrument_id,
            Flag.status == "open",
            Flag.severity == "critical",
        )
    ).all()
    reasons += [f"critical flag open: {f.reason_text}" for f in critical]
    return reasons


def decide(
    session: Session,
    *,
    case: Case,
    policy: Policy,
    actor: Actor,
    roles: frozenset[str],
    approve: bool,
    reason: str,
    store: DocumentStore,
    bank: BankClient | None,
    today: date,
) -> Case:
    approver = policy.release_approver_role
    if approver is None or approver not in roles:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the competent authority can decide")
    if not reason or not reason.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "A reason is mandatory")
    if case.state != "open":
        raise HTTPException(status.HTTP_409_CONFLICT, "Case is not open")
    instrument = session.get(Instrument, case.instrument_id)
    if approve:
        blocking = blockers(session, case)
        if blocking:
            raise HTTPException(
                status.HTTP_409_CONFLICT, {"message": "Approval blocked", "blockers": blocking}
            )
    case.state = "approved" if approve else "rejected"
    case.decision = case.state
    case.decided_by = actor.username
    case.decision_reason = reason
    record_event(
        session,
        actor=actor,
        action=f"release.{case.state}",
        instrument_id=instrument.id,
        case_id=case.id,
        after={"policy_version": case.policy_version},
        reason=reason,
    )
    if not approve:
        return case

    move(session, instrument, S.RELEASING, SYSTEM, {"system"}, f"{case.case_type} approved")
    institution = session.get(Institution, instrument.institution_id)
    pdf = render_release_letter(
        case_id=str(case.id),
        case_type=case.case_type,
        institution_name=institution.name,
        aicte_id=institution.aicte_id,
        fdr_no=instrument.instrument_no,
        ifsc=instrument.bank_ifsc or "",
        bank_name=instrument.bank_name,
        amount=str(instrument.amount),
        approved_by=actor.username,
        reason=reason,
        policy_version=case.policy_version or policy.version,
        issued_on=today,
    )
    key, digest = store.save(pdf)
    letter = Document(
        instrument_id=instrument.id,
        version=1,
        kind="release_letter",
        sha256=digest,
        storage_key=key,
        uploaded_by="system",
    )
    session.add(letter)
    session.flush()
    record_event(
        session,
        actor=SYSTEM,
        action="release.letter_issued",
        instrument_id=instrument.id,
        case_id=case.id,
        after={"document_id": str(letter.id), "sha256": digest},
    )
    if bank is not None and instrument.bank_ifsc:
        try:
            result = bank.remove_lien(instrument.bank_ifsc, instrument.instrument_no)
        except BankChannelError as exc:
            record_event(
                session,
                actor=SYSTEM,
                action="bank.lien_removal_failed",
                instrument_id=instrument.id,
                reason=str(exc),
            )
            return case
        for attestation in session.scalars(
            select(Attestation).where(Attestation.instrument_id == instrument.id)
        ):
            attestation.revoked_at = _now()
        record_event(
            session,
            actor=SYSTEM,
            action="bank.lien_removed",
            instrument_id=instrument.id,
            after=result,
        )
        move(session, instrument, S.RELEASED, SYSTEM, {"system"}, "bank confirmed lien removal")
    return case
