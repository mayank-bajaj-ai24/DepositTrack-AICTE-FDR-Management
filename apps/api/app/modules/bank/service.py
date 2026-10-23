"""Bank verification (M5): attest fields (L3), live status (L4), closure and lien removal."""

from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.configfiles import checks
from app.models import Attestation, FieldValue, Instrument
from app.modules.audit.service import Actor, record_event
from app.modules.bank.client import BankChannelError, BankClient
from app.modules.bank.credentials import CredentialError, compare, load_pinned, verify_signature
from app.modules.checks.engine import FlagSpec
from app.modules.instruments.intake import raise_flag
from app.modules.instruments.trust import instrument_level
from app.modules.lifecycle.states import TrustLevel


def _parse_ts(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _fields(session: Session, instrument: Instrument) -> dict[str, FieldValue]:
    rows = session.scalars(select(FieldValue).where(FieldValue.instrument_id == instrument.id))
    return {fv.field: fv for fv in rows}


def _declared(fields: dict[str, FieldValue]) -> dict[str, str | None]:
    return {name: fv.declared for name, fv in fields.items()}


def _bank_problem(status_record: dict) -> str | None:
    if status_record.get("status") == "closed":
        return "the bank reports this FDR as closed"
    if status_record.get("lien_status") != "MARKED":
        return "the bank reports AICTE's lien is no longer marked"
    return None


def verify_with_bank(
    session: Session, instrument: Instrument, actor: Actor, client: BankClient, pinned_file: str
) -> dict:
    if not instrument.bank_ifsc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Instrument has no IFSC")
    pinned = load_pinned(pinned_file)
    if not pinned:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "No bank keys are pinned yet; an admin must pin them first"
        )
    try:
        credential = client.credential(instrument.bank_ifsc, instrument.instrument_no)
        verify_signature(credential, pinned)
    except BankChannelError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    except CredentialError as exc:
        record_event(
            session,
            actor=actor,
            action="bank.credential_rejected",
            instrument_id=instrument.id,
            reason=str(exc),
        )
        raise_flag(
            session,
            instrument,
            FlagSpec(
                "bank_mismatch",
                checks()["severity"]["bank_mismatch"],
                f"bank credential rejected: {exc}",
                rule_id="credential_invalid",
            ),
            actor,
        )
        session.flush()
        return {"result": "rejected", "reason": str(exc)}

    fields = _fields(session, instrument)
    comparison = compare(credential["subject"], _declared(fields))
    status_record = credential.get("status", {})
    problem = _bank_problem(status_record)
    attestation = Attestation(
        instrument_id=instrument.id,
        issuer_key_id=credential["issuer"],
        payload=credential,
        signature=credential["signature"],
        verified_at=datetime.now(UTC),
        next_update=_parse_ts(status_record.get("next_update")),
        revoked_at=datetime.now(UTC) if problem else None,
    )
    session.add(attestation)

    for name, value in comparison.bank_values.items():
        if name in fields:
            fields[name].bank_value = value
    for name in comparison.mismatched:
        raise_flag(
            session,
            instrument,
            FlagSpec(
                "bank_mismatch",
                checks()["severity"]["bank_mismatch"],
                f"{name}: institution declared '{fields[name].declared}' but the bank confirms "
                f"'{comparison.bank_values[name]}'",
                fact={"declared": fields[name].declared, "bank": comparison.bank_values[name]},
                rule_id="bank_mismatch",
                field=name,
            ),
            actor,
        )
    if problem:
        raise_flag(
            session,
            instrument,
            FlagSpec(
                "bank_mismatch",
                checks()["severity"]["bank_mismatch"],
                problem,
                fact=status_record,
                rule_id="bank_status",
            ),
            actor,
        )

    fresh_until = attestation.next_update
    for name, ok in comparison.matches.items():
        fv = fields.get(name)
        if fv is None:
            continue
        if problem:
            fv.trust_level = int(TrustLevel.DECLARED)
        elif ok:
            fv.trust_level = int(TrustLevel.LIVE_CONFIRMED)
            fv.fresh_until = fresh_until
    session.flush()
    instrument.trust_level = instrument_level(list(fields.values()))
    record_event(
        session,
        actor=actor,
        action="bank.verified",
        instrument_id=instrument.id,
        after={
            "issuer": credential["issuer"],
            "matches": comparison.matches,
            "status": status_record.get("status"),
            "lien_status": status_record.get("lien_status"),
            "trust_level": instrument.trust_level,
        },
    )
    result = "mismatch" if comparison.mismatched or problem else "attested"
    return {"result": result, "mismatched": comparison.mismatched, "problem": problem}


def refresh_status(
    session: Session, instrument: Instrument, actor: Actor, client: BankClient, pinned_file: str
) -> dict:
    """Live re-check (L4): renew freshness, or drop trust if the bank reports a problem."""
    pinned = load_pinned(pinned_file)
    record = client.status(instrument.bank_ifsc, instrument.instrument_no)
    verify_signature(record, pinned)
    fields = _fields(session, instrument)
    problem = _bank_problem(record)
    for fv in fields.values():
        if fv.trust_level >= TrustLevel.BANK_ATTESTED:
            if problem:
                fv.trust_level = int(TrustLevel.DECLARED)
                fv.fresh_until = None
            else:
                fv.trust_level = int(TrustLevel.LIVE_CONFIRMED)
                fv.fresh_until = _parse_ts(record.get("next_update"))
    if problem:
        raise_flag(
            session,
            instrument,
            FlagSpec(
                "bank_mismatch",
                checks()["severity"]["bank_mismatch"],
                problem,
                fact=record,
                rule_id="bank_status",
            ),
            actor,
        )
    session.flush()
    instrument.trust_level = instrument_level(list(fields.values()))
    record_event(
        session,
        actor=actor,
        action="bank.status_checked",
        instrument_id=instrument.id,
        after={
            "status": record.get("status"),
            "lien_status": record.get("lien_status"),
            "trust_level": instrument.trust_level,
        },
    )
    return {"status": record.get("status"), "problem": problem}
