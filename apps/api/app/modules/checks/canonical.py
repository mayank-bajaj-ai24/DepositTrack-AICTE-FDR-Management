"""Canonical instrument identity (N7): bank resolved through IFSC lineage + normalised number."""

import re
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.models import BankMerger, IfscLineage

IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")

LineageLookup = Callable[[str], IfscLineage | None]
MergerLookup = Callable[[str], str | None]


def normalize_instrument_no(number: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", number.upper())


def follow_mergers(bank: str, merged_into: MergerLookup) -> str:
    """Follow bank-level mergers (A -> B -> C). The importer rejects cycles; `seen` guards."""
    seen = {bank}
    while (target := merged_into(bank)) is not None and target not in seen:
        bank = target
        seen.add(bank)
    return bank


def resolve_bank(
    ifsc: str | None, lineage_of: LineageLookup, merged_into: MergerLookup
) -> tuple[str, str] | None:
    """(issuing bank, canonical bank) for an IFSC.

    The issuing bank is the bank whose FDR number series the instrument belongs to: the bank
    a sublet IFSC is let to (same code, used by another bank), otherwise the IFSC's prefix
    (also for a branch re-coded after a merger, which issued under the old prefix). The
    canonical bank is where the IFSC belongs today: the lineage entry's bank, or the prefix,
    followed through bank-level mergers.
    """
    if not ifsc:
        return None
    ifsc = ifsc.upper()
    lineage = lineage_of(ifsc)
    if lineage is None:
        issuing = start = ifsc[:4]
    else:
        start = lineage.canonical_bank
        issuing = start if lineage.current_ifsc == lineage.old_ifsc else ifsc[:4]
    return issuing, follow_mergers(start, merged_into)


def _session_lookups(session: Session) -> tuple[LineageLookup, MergerLookup]:
    def merged_into(bank: str) -> str | None:
        merger = session.get(BankMerger, bank)
        return merger.canonical_bank if merger else None

    return (lambda ifsc: session.get(IfscLineage, ifsc)), merged_into


def canonical_bank(session: Session, ifsc: str | None) -> str | None:
    """Current bank code for an IFSC, following recorded lineage.

    An IFSC-level entry (a sublet IFSC, or a branch re-coded after a merger) wins; otherwise
    the IFSC's bank prefix is followed through bank-level mergers.
    """
    resolved = resolve_bank(ifsc, *_session_lookups(session))
    return resolved[1] if resolved else None


def issuing_bank(session: Session, ifsc: str | None) -> str | None:
    """Bank whose number series an FDR under this IFSC belongs to (before any merger)."""
    resolved = resolve_bank(ifsc, *_session_lookups(session))
    return resolved[0] if resolved else None


def edit_distance(a: str, b: str) -> int:
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]
