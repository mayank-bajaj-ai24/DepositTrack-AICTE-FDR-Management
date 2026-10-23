"""Canonical instrument identity (N7): bank resolved through IFSC lineage + normalised number."""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import IfscLineage

IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")


def normalize_instrument_no(number: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", number.upper())


def canonical_bank(session: Session, ifsc: str | None) -> str | None:
    """Current bank code for an IFSC, following merger lineage when it is recorded."""
    if not ifsc:
        return None
    ifsc = ifsc.upper()
    lineage = session.scalars(select(IfscLineage).where(IfscLineage.old_ifsc == ifsc)).first()
    if lineage:
        return lineage.canonical_bank
    return ifsc[:4]


def edit_distance(a: str, b: str) -> int:
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]
