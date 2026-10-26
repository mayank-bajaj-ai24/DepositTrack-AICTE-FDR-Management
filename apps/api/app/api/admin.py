"""System status, institutions and admin actions (demo clock, sweep, bank key pinning)."""

import base64
import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import serializers as ser
from app.api.deps import actor_of, bank_dep, policy_dep
from app.core import clock
from app.core.access import Scope, get_scope
from app.core.config import Settings, get_settings
from app.core.configfiles import load_config
from app.core.permissions import Action, is_allowed
from app.core.policy import Policy
from app.db.session import get_session
from app.models import Institution
from app.modules.audit.anchoring import immudb_status
from app.modules.audit.service import SYSTEM, record_event
from app.modules.bank.client import BankChannelError, BankClient
from app.modules.bank.credentials import load_pinned, save_pinned
from app.modules.extraction import layoutlm
from app.modules.forgery import model as forgery_model
from app.modules.lifecycle.sweep import run_sweep
from app.modules.risk import model as risk_model
from app.modules.risk.service import score_live

router = APIRouter(prefix="/api/v1", tags=["admin"])


def _admin(scope: Scope) -> None:
    if not is_allowed(scope.principal.roles, Action.CONFIG_MANAGE):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not permitted")


def _fingerprint(public_b64: str) -> str:
    return hashlib.sha256(base64.b64decode(public_b64)).hexdigest()[:16]


@router.get("/system/status")
def system_status(
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    policy: Policy = Depends(policy_dep),
) -> dict:
    """Public status for the UI banner: demo policy, unconfirmed values, clock, integrations."""
    immudb = immudb_status(settings)
    return {
        "policy_version": policy.version,
        "demo_policy": policy.is_demo,
        "unconfirmed": policy.unconfirmed,
        "today": clock.today(session).isoformat(),
        "clock_offset_days": clock.offset_days(session),
        "bank_channel_configured": bool(settings.bank_api_token),
        "bank_keys_pinned": len(load_pinned(settings.bank_keys_file)),
        "layoutlm_available": bool(load_config("extraction.yaml").get("pass_a_enabled"))
        and layoutlm.is_available(settings.models_dir),
        # What the approved pass A model was trained on, for the "trained on ..." label.
        "layoutlm_training_data": layoutlm.training_data(
            Path(settings.models_dir) / layoutlm.MODEL_SUBDIR
        ),
        "forgery_model_available": forgery_model.is_available(settings.models_dir),
        "forgery_model_training_data": forgery_model.training_data(settings.models_dir),
        "risk_model_available": risk_model.is_available(settings.models_dir),
        "immudb_enabled": immudb.enabled,
        # Detected with importlib.util.find_spec, without importing the client.
        "immudb_client_installed": immudb.client_installed,
        # Set when anchoring cannot write receipts as configured (e.g. the client is missing).
        "immudb_problem": immudb.problem,
    }


@router.get("/institutions")
def institutions(
    scope: Scope = Depends(get_scope), session: Session = Depends(get_session)
) -> dict:
    if scope.institution_id and len(scope.principal.roles) == 1:
        rows = [session.get(Institution, scope.institution_id)]
    else:
        query = select(Institution).order_by(Institution.name)
        if scope.region:
            query = query.where(Institution.region == scope.region)
        rows = list(session.scalars(query))
    return {"items": [ser.institution(i) for i in rows]}


class ClockIn(BaseModel):
    days: int


@router.post("/admin/clock")
def set_clock(
    body: ClockIn,
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
    policy: Policy = Depends(policy_dep),
) -> dict:
    _admin(scope)
    if not policy.is_demo:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "The clock can only be moved with the demo policy"
        )
    if body.days < 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The clock only moves forward")
    clock.set_offset(session, body.days, scope.principal.username)
    record_event(
        session, actor=actor_of(scope), action="demo.clock_set", after={"offset_days": body.days}
    )
    session.commit()
    return {"today": clock.today(session).isoformat(), "offset_days": body.days}


@router.post("/admin/sweep")
def sweep(
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
    policy: Policy = Depends(policy_dep),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Score renewal risk (if the model is available), then run the lifecycle sweep."""
    _admin(scope)
    today = clock.today(session)
    scored = score_live(session, settings.models_dir, today)
    report = run_sweep(session, policy, today)
    record_event(
        session,
        actor=SYSTEM,
        action="lifecycle.sweep",
        after={
            "today": report.today.isoformat(),
            "moved": len(report.moved),
            "notifications": report.notifications,
            "risk_scored": len(scored),
        },
    )
    session.commit()
    return {
        "today": report.today.isoformat(),
        "moved": [{"instrument_id": i, "from": a, "to": b} for i, a, b in report.moved],
        "notifications": report.notifications,
        "risk_scored": len(scored),
        "awaiting_policy": report.awaiting_policy,
    }


@router.post("/admin/bank-keys/pin")
def pin_bank_keys(
    scope: Scope = Depends(get_scope),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    bank: BankClient | None = Depends(bank_dep),
) -> dict:
    """Fetch the bank channel's public keys once and pin them. Already pinned keys never change."""
    _admin(scope)
    if bank is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Bank channel is not configured")
    try:
        offered = bank.public_keys()
    except BankChannelError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    pinned = load_pinned(settings.bank_keys_file)
    changed = [k for k, v in offered.items() if k in pinned and pinned[k] != v]
    added = {k: v for k, v in offered.items() if k not in pinned}
    pinned.update(added)
    save_pinned(settings.bank_keys_file, pinned)
    record_event(
        session,
        actor=actor_of(scope),
        action="bank.keys_pinned",
        after={
            "added": {k: _fingerprint(v) for k, v in added.items()},
            "rejected_changes": changed,
        },
    )
    session.commit()
    return {
        "pinned": {k: _fingerprint(v) for k, v in pinned.items()},
        "added": sorted(added),
        "rejected_changes": changed,
    }
