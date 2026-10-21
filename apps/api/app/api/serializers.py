"""Plain-dict serialisers for API responses. Codes (states, flag types) are returned as-is
so the UI can translate them; English reason text is included as a fallback."""

from datetime import date, datetime

from app.models import (
    Case,
    Document,
    Event,
    FieldValue,
    Flag,
    Institution,
    Instrument,
    Notification,
    Observation,
)
from app.modules.instruments.trust import effective_level


def _iso(value: date | datetime | None) -> str | None:
    return value.isoformat() if value else None


def institution(i: Institution | None) -> dict | None:
    if i is None:
        return None
    return {
        "id": str(i.id),
        "aicte_id": i.aicte_id,
        "name": i.name,
        "institution_type": i.institution_type,
        "state": i.state,
        "region": i.region,
    }


def instrument_summary(i: Instrument, inst: Institution | None = None, open_flags: int = 0) -> dict:
    return {
        "id": str(i.id),
        "institution": institution(inst),
        "kind": str(i.kind),
        "instrument_no": i.instrument_no,
        "bank_name": i.bank_name,
        "bank_ifsc": i.bank_ifsc,
        "amount": str(i.amount) if i.amount is not None else None,
        "issue_date": _iso(i.issue_date),
        "maturity_date": _iso(i.maturity_date),
        "state": str(i.state),
        "trust_level": i.trust_level,
        "risk_score": i.risk_score,
        "replaces_id": str(i.replaces_id) if i.replaces_id else None,
        "open_flags": open_flags,
        "created_at": _iso(i.created_at),
    }


def field_value(fv: FieldValue) -> dict:
    return {
        "field": fv.field,
        "declared": fv.declared,
        "extracted_a": fv.extracted_a,
        "extracted_b": fv.extracted_b,
        "bank_value": fv.bank_value,
        "confidence": fv.confidence,
        "trust_level": effective_level(fv),
        "fresh_until": _iso(fv.fresh_until),
    }


def document(d: Document) -> dict:
    return {
        "id": str(d.id),
        "kind": d.kind,
        "version": d.version,
        "sha256": d.sha256,
        "uploaded_by": d.uploaded_by,
        "uploaded_at": _iso(d.uploaded_at),
        "forgery_score": d.forgery_score,
    }


def flag(f: Flag) -> dict:
    return {
        "id": str(f.id),
        "type": f.flag_type,
        "severity": f.severity,
        "fact": f.fact,
        "rule_id": f.rule_id,
        "clause_ref": f.clause_ref,
        "reason": f.reason_text,
        "status": f.status,
        "raised_by": f.raised_by,
        "resolved_by": f.resolved_by,
        "created_at": _iso(f.created_at),
    }


def observation(o: Observation) -> dict:
    return {
        "id": str(o.id),
        "officer": o.officer_id,
        "text": o.text,
        "created_at": _iso(o.created_at),
    }


def case(c: Case, blockers: list[str] | None = None) -> dict:
    return {
        "id": str(c.id),
        "type": c.case_type,
        "state": c.state,
        "instrument_id": str(c.instrument_id),
        "assignee_role": c.assignee_role,
        "due_at": _iso(c.due_at),
        "escalation_level": c.escalation_level,
        "policy_version": c.policy_version,
        "checklist": c.checklist or [],
        "opened_by": c.opened_by,
        "reason": c.reason,
        "decision": c.decision,
        "decided_by": c.decided_by,
        "decision_reason": c.decision_reason,
        "blockers": blockers or [],
        "created_at": _iso(c.created_at),
    }


def event(e: Event) -> dict:
    return {
        "id": str(e.id),
        "seq": e.seq,
        "action": e.action,
        "actor": e.actor_id,
        "role": e.role,
        "before": e.before,
        "after": e.after,
        "reason": e.reason,
        "ts": _iso(e.ts),
        "hash": e.hash,
        "prev_hash": e.prev_hash,
    }


def notification(n: Notification) -> dict:
    return {
        "id": str(n.id),
        "instrument_id": str(n.instrument_id),
        "kind": n.kind,
        "audience_role": n.audience_role,
        "message": n.message,
        "created_at": _iso(n.created_at),
        "read_at": _iso(n.read_at),
    }
