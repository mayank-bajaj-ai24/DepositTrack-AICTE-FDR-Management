"""Apply lifecycle transitions with role checks and audit events (M7)."""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.configfiles import workflow
from app.models import Instrument
from app.modules.audit.service import Actor, record_event
from app.modules.lifecycle.state_machine import IllegalTransitionError, transition
from app.modules.lifecycle.states import InstrumentState


def allowed_roles(current: InstrumentState, target: InstrumentState) -> list[str]:
    return workflow()["transitions"].get(f"{current.value}->{target.value}", [])


def move(
    session: Session,
    instrument: Instrument,
    target: InstrumentState,
    actor: Actor,
    roles: set[str] | frozenset[str],
    reason: str | None = None,
) -> Instrument:
    """Move an instrument to `target` if the state machine and the workflow allow it."""
    current = InstrumentState(instrument.state)
    permitted = allowed_roles(current, target)
    if not set(roles) & set(permitted):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, f"Your role cannot move {current.value} -> {target.value}"
        )
    try:
        result = transition(current, target, reason)
    except IllegalTransitionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    instrument.state = result.new_state
    record_event(
        session,
        actor=actor,
        action=result.audit_action,
        instrument_id=instrument.id,
        before=result.audit_before,
        after=result.audit_after,
        reason=reason,
    )
    return instrument
