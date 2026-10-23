"""AICTE institution master (M12) from AICTE's public approved-institutions dashboard.

fetch_institutions() downloads the all-India list and the list for every configured state,
and refuses to save a snapshot unless the state lists add up to the all-India list: every
all-India ID in exactly one state row, no AICTE ID repeated within or across states, and no
state row whose ID the all-India list lacks (a state name the dashboard no longer accepts
would otherwise drop institutions silently). import_institutions() checks a saved snapshot
the same way and upserts it into the `institution` table.
"""

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Institution
from app.modules.audit.service import SYSTEM, record_event


class SnapshotError(RuntimeError):
    pass


def _query(client: httpx.Client, cfg: dict, state: str) -> list[list]:
    params = cfg["params"] | {"year": cfg["academic_year"], "state": state}
    response = client.get(cfg["endpoint"], params=params)
    response.raise_for_status()
    rows = response.json()
    if rows is None:
        return []
    if not isinstance(rows, list):
        raise SnapshotError(f"Unexpected response for state {state!r}: {str(rows)[:200]}")
    return rows


def check_state_rows(all_india_ids: list[str], state_ids: list[str]) -> None:
    """The state rows must be the all-India list exactly: each ID once, nothing extra."""
    if len(set(all_india_ids)) != len(all_india_ids):
        raise SnapshotError("The all-India list repeats AICTE IDs")
    counts = Counter(state_ids)
    known = set(all_india_ids)
    problems = []
    repeated = sorted(i for i, n in counts.items() if n > 1)
    if repeated:
        problems.append(
            f"{len(repeated)} AICTE IDs appear more than once in the state lists "
            f"(e.g. {repeated[:3]})"
        )
    extra = sorted(set(counts) - known)
    if extra:
        problems.append(
            f"{len(extra)} AICTE IDs in the state lists are not in the all-India list "
            f"(e.g. {extra[:3]})"
        )
    missing = [i for i in all_india_ids if i not in counts]
    if missing:
        problems.append(
            f"{len(missing)} institutions in the all-India list are in no configured state "
            f"(e.g. {missing[:3]}); check aicte.states in config/master_data.yaml"
        )
    if problems or len(state_ids) != len(all_india_ids):
        raise SnapshotError(
            f"The state lists ({len(state_ids)} rows) do not add up to the all-India list "
            f"({len(all_india_ids)}): " + "; ".join(problems)
        )


def fetch_institutions(cfg: dict, out_dir: Path, client: httpx.Client | None = None) -> Path:
    own_client = client is None
    client = client or httpx.Client(timeout=120)
    try:
        all_india = _query(client, cfg, cfg["all_india_state"])
        rows: list[dict] = []
        for state in cfg["states"]:
            for raw in _query(client, cfg, state):
                rows.append({"state": state, "row": raw})
    finally:
        if own_client:
            client.close()

    if not all_india:
        raise SnapshotError("The all-India list is empty; the dashboard may be down")
    width = len(cfg["columns"])
    short = [r for r in all_india + [r["row"] for r in rows] if len(r) < width]
    if short:
        raise SnapshotError(f"{len(short)} rows have fewer than {width} columns: {short[:1]}")
    check_state_rows([raw[0] for raw in all_india], [r["row"][0] for r in rows])

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"institutions_{cfg['academic_year']}.json"
    snapshot = {
        "source": cfg["source"],
        "academic_year": cfg["academic_year"],
        "fetched_at": datetime.now(UTC).isoformat(),
        "all_india_count": len(all_india),
        "columns": cfg["columns"],
        "rows": rows,
    }
    path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
    return path


def parse_snapshot(snapshot: dict) -> list[dict]:
    columns = snapshot["columns"]
    parsed = []
    for item in snapshot["rows"]:
        if len(item["row"]) < len(columns):
            raise SnapshotError(f"Row has fewer than {len(columns)} columns: {item['row']}")
        # The endpoint appends extra columns (the AICTE ID again); only the named ones are kept.
        record = dict(zip(columns, item["row"][: len(columns)], strict=True))
        record["state"] = item["state"]
        parsed.append(record)
    return parsed


def import_institutions(session: Session, snapshot_path: Path, cfg: dict) -> dict[str, int]:
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    records = parse_snapshot(snapshot)
    ids = [r["aicte_id"] for r in records]
    repeated = sorted(i for i, n in Counter(ids).items() if n > 1)
    if repeated:
        raise SnapshotError(f"The snapshot repeats AICTE IDs (e.g. {repeated[:3]})")
    if len(ids) != snapshot["all_india_count"]:
        raise SnapshotError(
            f"The snapshot has {len(ids)} rows but the all-India list had "
            f"{snapshot['all_india_count']}"
        )
    regions = cfg.get("regions") or {}
    existing = {i.aicte_id: i for i in session.scalars(select(Institution))}
    source = f"{snapshot['source']} ({snapshot['academic_year']})"
    created = updated = 0
    for record in records:
        values = {
            "name": record["name"].strip(),
            "institution_type": (record.get("institution_type") or "").strip() or None,
            "state": record["state"],
            "region": regions.get(record["state"]),
        }
        listing = {
            "address": (record.get("address") or "").strip() or None,
            "district": (record.get("district") or "").strip() or None,
            "source": source,
        }
        inst = existing.get(record["aicte_id"])
        if inst is None:
            inst = Institution(aicte_id=record["aicte_id"], contacts=listing, **values)
            session.add(inst)
            existing[inst.aicte_id] = inst
            created += 1
        else:
            # Keep values the source does not provide (e.g. a region set by hand, contacts
            # added later); refresh everything it does provide.
            for key, value in values.items():
                if value is not None:
                    setattr(inst, key, value)
            inst.contacts = (inst.contacts or {}) | {
                k: v for k, v in listing.items() if v is not None
            }
            updated += 1
    session.flush()
    counts = {"created": created, "updated": updated}
    record_event(
        session,
        actor=SYSTEM,
        action="masterdata.institutions_imported",
        after=counts | {"source": source, "fetched_at": snapshot.get("fetched_at")},
    )
    return counts
