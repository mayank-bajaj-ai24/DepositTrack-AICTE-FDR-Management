"""Instrument submission (M2): store the scan, extract, check, and open scrutiny."""

import uuid
from collections.abc import Callable
from datetime import date
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.configfiles import checks, load_config
from app.core.policy import Policy
from app.models import Document, FieldValue, Flag, Institution, Instrument
from app.modules.audit.service import SYSTEM, Actor, record_event
from app.modules.checks.canonical import (
    canonical_bank,
    edit_distance,
    issuing_bank,
    normalize_instrument_no,
)
from app.modules.checks.engine import FlagSpec, Snapshot, amount_below_requirement, evaluate
from app.modules.extraction.service import FIELDS, ExtractionResult
from app.modules.instruments.trust import instrument_level, machine_level
from app.modules.lifecycle.service import move
from app.modules.lifecycle.states import InstrumentKind, InstrumentState
from app.modules.storage.store import DocumentStore

Extractor = Callable[[bytes, str | None], ExtractionResult | None]


def _to_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _to_amount(value: str | None) -> Decimal | None:
    return Decimal(value) if value else None


def raise_flag(session: Session, instrument: Instrument, spec: FlagSpec, actor: Actor) -> Flag:
    flag = Flag(
        instrument_id=instrument.id,
        flag_type=spec.flag_type,
        severity=spec.severity,
        fact=spec.fact | ({"field": spec.field} if spec.field else {}),
        rule_id=spec.rule_id,
        clause_ref=spec.clause_ref,
        reason_text=spec.reason,
        status="open",
        raised_by=actor.username,
    )
    session.add(flag)
    session.flush()
    record_event(
        session,
        actor=actor,
        action="flag.raised",
        instrument_id=instrument.id,
        after={"flag_id": str(flag.id), "type": spec.flag_type, "severity": spec.severity},
        reason=spec.reason,
    )
    return flag


def requirement_for(policy: Policy, institution: Institution) -> dict | None:
    for req in policy.deposit_requirements or []:
        if req.get("institution_type") in ("any", institution.institution_type):
            return req
    return None


def _same_deposit(a: Instrument, b: Instrument, fields: list[str]) -> bool:
    """No configured field disagrees (a value missing on either side is no disagreement)."""
    for name in fields:
        left, right = getattr(a, name), getattr(b, name)
        if left is not None and right is not None and left != right:
            return False
    return True


def duplicate_flags(session: Session, instrument: Instrument) -> list[tuple[Instrument, FlagSpec]]:
    """Same FDR already held for any institution (critical), or a near-identical number.

    Instruments that share a canonical bank only through a merger (different issuing banks,
    so different number series) must also agree on `cross_merger_match_fields`.
    """
    cfg = checks()
    sev = cfg["severity"]
    max_distance = cfg["near_duplicate_max_distance"]
    match_fields = cfg["cross_merger_match_fields"]
    issuer = issuing_bank(session, instrument.bank_ifsc)
    found: list[tuple[Instrument, FlagSpec]] = []
    others = session.scalars(
        select(Instrument).where(
            Instrument.canonical_bank == instrument.canonical_bank,
            Instrument.id != instrument.id,
        )
    ).all()
    for other in others:
        exact = other.instrument_no_norm == instrument.instrument_no_norm
        if not exact and (
            edit_distance(other.instrument_no_norm, instrument.instrument_no_norm) > max_distance
        ):
            continue
        fact: dict = {}
        note = ""
        other_issuer = issuing_bank(session, other.bank_ifsc)
        if other_issuer != issuer:
            if not _same_deposit(instrument, other, match_fields):
                continue  # same number in two banks' series that a merger later joined
            fact = {"issuing_banks": [issuer, other_issuer]}
            note = (
                f"; issued under {issuer} and {other_issuer}, joined by a bank merger, "
                f"with no difference in {', '.join(match_fields)}"
            )
        if exact:
            spec = FlagSpec(
                "duplicate_pledge",
                sev["duplicate_pledge"],
                f"the same FDR {instrument.instrument_no} at bank {instrument.canonical_bank} "
                f"is already recorded (instrument {other.id}){note}",
                fact={"other_instrument_id": str(other.id), "fdr_no": instrument.instrument_no}
                | fact,
                rule_id="duplicate_pledge",
            )
        else:
            spec = FlagSpec(
                "near_duplicate",
                sev["near_duplicate"],
                f"FDR number {instrument.instrument_no} is one character away from "
                f"{other.instrument_no} at the same bank{note}",
                fact={"other_instrument_id": str(other.id), "other_fdr_no": other.instrument_no}
                | fact,
                rule_id="near_duplicate",
            )
        found.append((other, spec))
    return found


def continuity_gap(replaces: Instrument | None, new: Instrument) -> FlagSpec | None:
    """A replacement must start on or before the old instrument's maturity (N2)."""
    if replaces is None or replaces.maturity_date is None or new.issue_date is None:
        return None
    if new.issue_date <= replaces.maturity_date:
        return None
    days = (new.issue_date - replaces.maturity_date).days
    return FlagSpec(
        "continuity_gap",
        checks()["severity"]["continuity_gap"],
        f"the replacement starts {days} day(s) after the old instrument matured "
        f"({replaces.maturity_date.isoformat()} to {new.issue_date.isoformat()}); "
        "the requirement was uncovered in between",
        fact={
            "old_maturity": replaces.maturity_date.isoformat(),
            "new_issue": new.issue_date.isoformat(),
            "gap_days": days,
        },
        rule_id="continuity_gap",
        field="issue_date",
    )


def submit_instrument(
    session: Session,
    *,
    store: DocumentStore,
    policy: Policy,
    actor: Actor,
    roles: frozenset[str],
    institution_id: uuid.UUID,
    kind: InstrumentKind,
    declared: dict[str, str | None],
    file_bytes: bytes,
    content_type: str | None,
    extractor: Extractor,
    replaces: Instrument | None = None,
) -> Instrument:
    institution = session.get(Institution, institution_id)
    if institution is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Institution not found")
    if not declared.get("fdr_no"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "fdr_no is required")

    extraction = extractor(file_bytes, content_type)
    extracted = {k: v.value for k, v in extraction.fields.items()} if extraction else {}

    instrument = Instrument(
        id=uuid.uuid4(),
        institution_id=institution_id,
        kind=kind,
        bank_ifsc=(declared.get("ifsc") or "").upper() or None,
        bank_name=declared.get("bank"),
        instrument_no=declared["fdr_no"],
        instrument_no_norm=normalize_instrument_no(declared["fdr_no"]),
        amount=_to_amount(declared.get("amount")),
        issue_date=_to_date(declared.get("issue_date")),
        maturity_date=_to_date(declared.get("maturity_date")),
        beneficiary_text=declared.get("beneficiary"),
        lien_marked=bool(extracted.get("lien_text")) or None,
        state=InstrumentState.DRAFT,
        replaces_id=replaces.id if replaces else None,
    )
    instrument.canonical_bank = canonical_bank(session, instrument.bank_ifsc)
    session.add(instrument)
    session.flush()
    record_event(
        session,
        actor=actor,
        action="instrument.created",
        instrument_id=instrument.id,
        after={
            "declared": declared,
            "kind": kind.value,
            "replaces": str(replaces.id) if replaces else None,
        },
    )

    storage_key, digest = store.save(file_bytes)
    document = Document(
        instrument_id=instrument.id,
        version=1,
        kind="scan",
        sha256=digest,
        storage_key=storage_key,
        uploaded_by=actor.username,
    )
    session.add(document)
    session.flush()
    record_event(
        session,
        actor=actor,
        action="document.uploaded",
        instrument_id=instrument.id,
        after={"document_id": str(document.id), "sha256": digest, "kind": "scan", "version": 1},
    )
    if extraction:
        record_event(
            session,
            actor=SYSTEM,
            action="extraction.completed",
            instrument_id=instrument.id,
            after={
                "pass_a_available": extraction.pass_a_available,
                "fields": {k: v.value for k, v in extraction.fields.items()},
                "needs_review": [k for k, v in extraction.fields.items() if v.needs_review],
            },
        )

    # Checks
    snapshot = Snapshot(kind=kind.value, declared=declared, extracted=extracted, documents=["scan"])
    specs = evaluate(snapshot, policy, checks())
    requirement = requirement_for(policy, institution)
    if requirement:
        low = amount_below_requirement(
            declared.get("amount"),
            float(requirement["amount_inr"]),
            requirement.get("clause_ref"),
            checks(),
        )
        if low:
            specs.append(low)
    forgery = extraction.forgery if extraction else None
    if forgery is not None:
        document.forgery_score = forgery.score
        if forgery.band in ("suspicious", "grey"):
            flag_type = "forgery_suspected" if forgery.band == "suspicious" else "forgery_grey"
            specs.append(
                FlagSpec(
                    flag_type,
                    checks()["severity"][flag_type],
                    f"image analysis marks the region '{forgery.region_text}' as "
                    f"{forgery.band} (score {forgery.score:.2f}); compare with the bank's record",
                    fact={
                        "score": forgery.score,
                        "band": forgery.band,
                        "region": forgery.region_text,
                        "box": list(forgery.region_box) if forgery.region_box else None,
                    },
                    rule_id="forgery_signal",
                    field=extraction.forgery_field,
                )
            )
    gap = continuity_gap(replaces, instrument)
    if gap:
        specs.append(gap)
    for spec in specs:
        raise_flag(session, instrument, spec, SYSTEM)
    for other, spec in duplicate_flags(session, instrument):
        raise_flag(session, instrument, spec, SYSTEM)
        mirrored = FlagSpec(
            spec.flag_type,
            spec.severity,
            spec.reason.replace(str(other.id), str(instrument.id)),
            fact=spec.fact | {"other_instrument_id": str(instrument.id)},
            rule_id=spec.rule_id,
        )
        raise_flag(session, other, mirrored, SYSTEM)

    # Field values with Trust Ladder levels
    flagged_fields = {s.field for s in specs if s.field}
    threshold = load_config("extraction.yaml")["human_review_below"]
    values = []
    for name in FIELDS:
        result = extraction.fields.get(name) if extraction else None
        fv = FieldValue(
            instrument_id=instrument.id,
            field=name,
            declared=declared.get(name),
            extracted_a=result.pass_a if result else None,
            extracted_b=result.pass_b if result else None,
            confidence=result.confidence if result else None,
        )
        fv.trust_level = int(machine_level(fv, name in flagged_fields, threshold))
        session.add(fv)
        values.append(fv)
    session.flush()
    instrument.trust_level = instrument_level(values)

    move(session, instrument, InstrumentState.SUBMITTED, actor, roles, "submitted by institution")
    move(session, instrument, InstrumentState.SCRUTINY, SYSTEM, {"system"}, "queued for scrutiny")
    return instrument
