"""Audit endpoints (M6): chain verification, file verifier, Merkle anchors."""

import hashlib

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import serializers as ser
from app.api.deps import actor_of
from app.core.access import Scope, get_scope, scope_instruments
from app.core.config import Settings, get_settings
from app.core.permissions import Action, is_allowed
from app.db.session import get_session
from app.models import Anchor, Document, Institution, Instrument
from app.modules.audit.anchoring import anchor_new_events, verify_anchor
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
    if not is_allowed(scope.principal.roles, Action.CONFIG_MANAGE):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")
    anchor = anchor_new_events(session, settings)
    if anchor is None:
        return {"anchored": False, "message": "No new events since the last anchor"}
    record_event(
        session,
        actor=actor_of(scope),
        action="audit.anchored",
        after={"merkle_root": anchor.merkle_root, "store_tx": anchor.store_tx},
    )
    session.commit()
    return {"anchored": True, "merkle_root": anchor.merkle_root, "store_tx": anchor.store_tx}


@router.get("/audit/anchors")
def list_anchors(
    scope: Scope = Depends(get_scope), session: Session = Depends(get_session)
) -> dict:
    _require_audit(scope)
    anchors = session.scalars(select(Anchor).order_by(Anchor.batch_end.desc()).limit(50)).all()
    return {
        "items": [
            {
                "id": str(a.id),
                "batch_start": a.batch_start.isoformat(),
                "batch_end": a.batch_end.isoformat(),
                "merkle_root": a.merkle_root,
                "store_tx": a.store_tx,
                "valid": verify_anchor(session, a),
            }
            for a in anchors
        ]
    }
