"""Audit endpoints (M6): chain verification, file verifier, Merkle anchors."""

import hashlib
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api import serializers as ser
from app.api.deps import actor_of
from app.core.access import Scope, get_scope, scope_instruments
from app.core.config import Settings, get_settings
from app.core.configfiles import load_config
from app.core.permissions import Action, is_allowed
from app.db.session import get_session
from app.models import Anchor, AnchorEvent, Document, Event, Institution, Instrument
from app.modules.audit.anchoring import (
    ImmudbStore,
    anchor_new_events,
    immudb_status,
    verify_anchor,
    write_receipt,
)
from app.modules.audit.conformance import replay
from app.modules.audit.service import record_event, verify_chain

router = APIRouter(prefix="/api/v1", tags=["audit"])


def _require_audit(scope: Scope) -> None:
    if not is_allowed(scope.principal.roles, Action.AUDIT_READ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")


@router.get("/audit/chains")
def check_all_chains(
    scope: Scope = Depends(get_scope), session: Session = Depends(get_session)
) -> dict:
    """Recompute every instrument's hash chain; list any that are broken."""
    _require_audit(scope)
    results = []
    for instrument, institution in session.execute(
        scope_instruments(
            select(Instrument, Institution).join(
                Institution, Institution.id == Instrument.institution_id
            ),
            scope,
        )
    ):
        chain = verify_chain(session, instrument.id)
        results.append(
            {
                "instrument": ser.instrument_summary(instrument, institution),
                "intact": chain.intact,
                "length": chain.length,
                "broken_at_seq": chain.broken_at_seq,
            }
        )
    system = verify_chain(session, None)
    return {
        "checked": len(results),
        "broken": [r for r in results if not r["intact"]],
        "system_chain": {"intact": system.intact, "length": system.length},
    }


@router.post("/verify-file")
def verify_file(
    file: UploadFile = File(...),
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
) -> dict:
    """Is this exact file the one submitted? Match by SHA-256, then check the chain."""
    data = file.file.read()
    digest = hashlib.sha256(data).hexdigest()
    matches = []
    for document in session.scalars(select(Document).where(Document.sha256 == digest)):
        instrument = session.scalars(
            scope_instruments(
                select(Instrument).where(Instrument.id == document.instrument_id), scope
            )
        ).first()
        if instrument is None:
            continue
        chain = verify_chain(session, instrument.id)
        matches.append(
            {
                "document": ser.document(document),
                "instrument": ser.instrument_summary(
                    instrument, session.get(Institution, instrument.institution_id)
                ),
                "chain_intact": chain.intact,
                "broken_at_seq": chain.broken_at_seq,
            }
        )
    return {"sha256": digest, "matched": bool(matches), "matches": matches}


@router.post("/audit/anchors", status_code=201)
def create_anchor(
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Anchor every event not anchored yet; with immudb on, also write an immudb receipt.

    The anchor row is committed first, so an immudb outage or failed login leaves the anchor
    stored without a receipt and the reason in `store_error`, instead of losing it.
    """
    if not is_allowed(scope.principal.roles, Action.CONFIG_MANAGE):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")
    problem = immudb_status(settings).problem
    if problem:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, problem)
    try:
        anchor = anchor_new_events(session)
        if anchor is None:
            return {"anchored": False, "message": "No new events since the last anchor"}
        session.commit()
    except IntegrityError as exc:  # another anchor took the same events first
        session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Another anchor was created at the same time; try again"
        ) from exc
    if settings.immudb_enabled:
        with ImmudbStore(settings) as store:
            write_receipt(anchor, store)
    record_event(
        session,
        actor=actor_of(scope),
        action="audit.anchored",
        after={
            "merkle_root": anchor.merkle_root,
            "store_tx": anchor.store_tx,
            "store_error": anchor.store_error,
        },
    )
    session.commit()
    return {
        "anchored": True,
        "merkle_root": anchor.merkle_root,
        "events": session.scalar(
            select(func.count()).select_from(AnchorEvent).where(AnchorEvent.anchor_id == anchor.id)
        ),
        "store_tx": anchor.store_tx,
        "store_error": anchor.store_error,
    }


@router.get("/audit/anchors")
def list_anchors(
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Recent anchors, each re-checked against its events and its immudb receipt."""
    _require_audit(scope)
    # Newest first by creation: a batch of late events can end before an older batch.
    anchors = session.scalars(select(Anchor).order_by(Anchor.ts.desc()).limit(50)).all()
    items = []
    with ImmudbStore(settings) as store:
        for a in anchors:
            check = verify_anchor(session, a, store)
            items.append(
                {
                    "id": str(a.id),
                    "batch_start": a.batch_start.isoformat(),
                    "batch_end": a.batch_end.isoformat(),
                    "merkle_root": a.merkle_root,
                    "store_tx": a.store_tx,
                    "store_error": a.store_error,
                    "valid": check.valid,
                    "root_matches": check.root_matches,
                    "receipt": check.receipt,
                    "receipt_detail": check.detail,
                }
            )
    return {"items": items}


@router.get("/audit/conformance")
def conformance(scope: Scope = Depends(get_scope), session: Session = Depends(get_session)) -> dict:
    """Replay every visible instrument's audit log against the procedural constraints (N10)."""
    _require_audit(scope)
    config = load_config("conformance.yaml")
    now = datetime.now(UTC)
    cases, violated_cases = [], 0
    by_constraint = {c["id"]: 0 for c in config["constraints"]}
    query = select(Instrument, Institution).join(
        Institution, Institution.id == Instrument.institution_id
    )
    for instrument, institution in session.execute(scope_instruments(query, scope)):
        events = list(
            session.scalars(
                select(Event).where(Event.instrument_id == instrument.id).order_by(Event.seq)
            )
        )
        violations = replay(events, config["constraints"], now)
        for v in violations:
            by_constraint[v.constraint_id] += 1
        if violations:
            violated_cases += 1
            cases.append(
                {
                    "instrument": ser.instrument_summary(instrument, institution),
                    "violations": [
                        {
                            "constraint": v.constraint_id,
                            "seq": v.seq,
                            "action": v.action,
                            "explanation": v.explanation,
                        }
                        for v in violations
                    ],
                }
            )
    total = len(session.execute(scope_instruments(query, scope)).all())
    return {
        "constraints_version": config["version"],
        "validated_by": config["validated_by"],
        "constraints": [
            {"id": c["id"], "description": c["description"]} for c in config["constraints"]
        ],
        "checked": total,
        "conforming_share": round((total - violated_cases) / total, 4) if total else None,
        "violations_by_constraint": by_constraint,
        "cases": cases,
    }
