"""Per-instrument audit hash chain and Merkle roots (M6, N4).

hash = SHA256(prev_hash || canonical_json(event))
"""

import hashlib
import json
from collections.abc import Iterable, Sequence
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

GENESIS = "0" * 64


def _default(value):
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal | UUID):
        return str(value)
    raise TypeError(f"Not serialisable for audit: {type(value).__name__}")


def canonical_json(payload: dict) -> str:
    """Deterministic JSON: sorted keys, no whitespace, UTF-8 preserved."""
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=_default
    )


def event_hash(prev_hash: str | None, payload: dict) -> str:
    data = (prev_hash or GENESIS) + canonical_json(payload)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def build_chain(payloads: Iterable[dict]) -> list[tuple[str, str]]:
    """Return (prev_hash, hash) for each payload in order."""
    links: list[tuple[str, str]] = []
    prev = GENESIS
    for payload in payloads:
        current = event_hash(prev, payload)
        links.append((prev, current))
        prev = current
    return links


def first_break(payloads: Sequence[dict], hashes: Sequence[str]) -> int | None:
    """Index of the first event whose stored hash does not match, or None if intact."""
    if len(payloads) != len(hashes):
        return min(len(payloads), len(hashes))
    prev = GENESIS
    for index, (payload, stored) in enumerate(zip(payloads, hashes, strict=True)):
        if event_hash(prev, payload) != stored:
            return index
        prev = stored
    return None


def merkle_root(leaf_hashes: Sequence[str]) -> str:
    """Merkle root over hex SHA-256 leaves; an odd node is paired with itself."""
    if not leaf_hashes:
        return hashlib.sha256(b"").hexdigest()
    level = [bytes.fromhex(h) for h in leaf_hashes]
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [hashlib.sha256(level[i] + level[i + 1]).digest() for i in range(0, len(level), 2)]
    return level[0].hex()
