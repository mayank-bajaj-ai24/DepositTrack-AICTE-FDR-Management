"""AICTE institution master (M12) from AICTE's public approved-institutions dashboard.

fetch_institutions() downloads the all-India list and the list for every configured state,
and refuses to save a snapshot whose state lists do not add up to the all-India count (a
state name the dashboard no longer accepts would otherwise drop institutions silently).
import_institutions() upserts the snapshot into the `institution` table.
"""

import json
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
    ids = [raw[0] for raw in all_india]
    if len(set(ids)) != len(ids):
        raise SnapshotError("The all-India list repeats AICTE IDs")
    known = {r["row"][0] for r in rows}
    missing = [raw[0] for raw in all_india if raw[0] not in known]
    if missing:
        raise SnapshotError(
            f"{len(missing)} institutions in the all-India list are in no configured state "
            f"(e.g. {missing[:3]}); check aicte.states in config/master_data.yaml"
        )

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
    regions = cfg.get("regions") or {}
    existing = {i.aicte_id: i for i in session.scalars(select(Institution))}
    source = f"{snapshot['source']} ({snapshot['academic_year']})"
    created = updated = 0
    for record in parse_snapshot(snapshot):
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
