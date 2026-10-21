"""Notifications (M8). One notification per (instrument, kind, dedupe key, audience)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.configfiles import load_config
from app.models import Instrument, Notification
from app.modules.audit.service import SYSTEM, record_event


def notify(session: Session, instrument: Instrument, kind: str, key: str, message: str) -> int:
    """Create the notification for every audience of `kind` unless it already exists."""
    created = 0
    for role in load_config("alerts.yaml")["audiences"][kind]:
        dedupe = f"{key}:{role}"
        exists = session.scalars(
            select(Notification).where(
                Notification.instrument_id == instrument.id,
                Notification.kind == kind,
                Notification.dedupe_key == dedupe,
            )
        ).first()
        if exists:
            continue
        session.add(
            Notification(
                instrument_id=instrument.id,
                kind=kind,
                dedupe_key=dedupe,
                audience_role=role,
                message=message,
            )
        )
        created += 1
    if created:
        session.flush()
        record_event(
            session,
            actor=SYSTEM,
            action="alert.sent",
            instrument_id=instrument.id,
            after={"kind": kind, "key": key, "message": message},
        )
    return created
