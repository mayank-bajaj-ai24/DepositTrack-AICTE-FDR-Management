"""Bank master and IFSC lineage (M12, N7) from the RBI IFSC master (Razorpay IFSC dataset).

- `bank`: every bank code with its name (from IFSC.csv) and RBI type (from banks.json).
- `ifsc_lineage`: sublet IFSCs, i.e. IFSCs issued under one bank's prefix that belong to
  another bank (sublet.json), so the canonical key uses the real bank.
- `bank_merger`: bank-level amalgamations from config/bank_mergers.yaml, each cited to RBI.

Bank and sublet rows are added and updated; rows that disappear from a later release are
kept (an FDR issued under a since-withdrawn IFSC must still resolve to its bank). Merger
rows are replaced by the config's list, which is their only source.
"""

import csv
import json
import shutil
import tempfile
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Bank, BankMerger, IfscLineage
from app.modules.audit.service import SYSTEM, record_event


class MasterDataError(RuntimeError):
    pass


def fetch_ifsc(cfg: dict, out_dir: Path, client: httpx.Client | None = None) -> list[Path]:
    own_client = client is None
    client = client or httpx.Client(timeout=300, follow_redirects=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    # Download everything first, then move into place, so a failed download never leaves
    # files of two releases under one release.json.
    with tempfile.TemporaryDirectory(dir=out_dir.parent) as staging:
        staged = Path(staging)
        try:
            for name in cfg["files"]:
                url = cfg["download_url"].format(release=cfg["release"], file=name)
                response = client.get(url)
                response.raise_for_status()
                (staged / name).write_bytes(response.content)
        finally:
            if own_client:
                client.close()
        (staged / "release.json").write_text(
            json.dumps({"source": cfg["source"], "release": cfg["release"]}), encoding="utf-8"
        )
        paths = []
        for name in [*cfg["files"], "release.json"]:
            target = out_dir / name
            shutil.move(staged / name, target)
            paths.append(target)
    return paths


def _check_mergers(mergers: list[dict], known: set[str]) -> None:
    unknown = sorted({m[k] for m in mergers for k in ("old_bank", "canonical_bank")} - known)
    if unknown:
        raise MasterDataError(f"bank_mergers.yaml names codes not in the IFSC master: {unknown}")
    old = [m["old_bank"] for m in mergers]
    repeated = sorted({code for code in old if old.count(code) > 1})
    if repeated:
        raise MasterDataError(f"bank_mergers.yaml lists a bank more than once: {repeated}")


def _check_cycles(target: dict[str, str]) -> None:
    for start in target:
        seen, bank = {start}, target[start]
        while bank in target:
            if bank in seen:
                raise MasterDataError(f"bank mergers form a cycle through {start}")
            seen.add(bank)
            bank = target[bank]


def _sync_mergers(session: Session, mergers: list[dict]) -> int:
    """Make `bank_merger` exactly the config's list; return how many rows were removed.

    config/bank_mergers.yaml is the source of truth: a merger corrected or withdrawn there
    must not linger in the table that canonical_bank() reads.
    """
    wanted = {m["old_bank"]: m for m in mergers}
    existing = {row.old_bank: row for row in session.scalars(select(BankMerger))}
    stale = [row for code, row in existing.items() if code not in wanted]
    for row in stale:
        session.delete(row)
    for code, m in wanted.items():
        values = {
            "canonical_bank": m["canonical_bank"],
            "effective_from": m.get("effective_from"),
            "source": m["source"],
        }
        row = existing.get(code)
        if row is None:
            session.add(BankMerger(old_bank=code, **values))
        else:
            for key, value in values.items():
                setattr(row, key, value)
    session.flush()
    # Check the table canonical_bank() actually reads, not only the config list.
    rows = session.execute(select(BankMerger.old_bank, BankMerger.canonical_bank))
    _check_cycles({old: new for old, new in rows})
    return len(stale)


def _bank_names(ifsc_csv: Path) -> dict[str, str]:
    names: dict[str, str] = {}
    with open(ifsc_csv, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            code, name = row["IFSC"][:4].upper(), (row["BANK"] or "").strip()
            if name and code not in names:
                names[code] = name
    return names


def import_banks(session: Session, data_dir: Path, mergers: list[dict]) -> dict[str, int]:
    meta = json.loads((data_dir / "release.json").read_text(encoding="utf-8"))
    source = f"{meta['source']} ({meta['release']})"
    banks = json.loads((data_dir / "banks.json").read_text(encoding="utf-8"))
    names = _bank_names(data_dir / "IFSC.csv")
    sublet = json.loads((data_dir / "sublet.json").read_text(encoding="utf-8"))
    unknown_sublet = sorted(set(sublet.values()) - set(banks))
    if unknown_sublet:
        raise MasterDataError(f"sublet.json names unknown bank codes: {unknown_sublet[:10]}")
    _check_mergers(mergers, set(banks))

    # Existing rows are loaded once and updated in memory; the flush then sends batched
    # INSERTs and UPDATEs (only for rows that changed) instead of one SELECT per row.
    existing_banks = {b.code: b for b in session.scalars(select(Bank))}
    for code, info in banks.items():
        values = {"name": names.get(code), "bank_type": info.get("type"), "source": source}
        row = existing_banks.get(code)
        if row is None:
            session.add(Bank(code=code, **values))
            continue
        for key, value in values.items():
            if value is not None:
                setattr(row, key, value)
    existing_lineage = {row.old_ifsc: row for row in session.scalars(select(IfscLineage))}
    for ifsc, bank in sublet.items():
        ifsc = ifsc.upper()
        row = existing_lineage.get(ifsc)
        if row is None:
            session.add(IfscLineage(old_ifsc=ifsc, current_ifsc=ifsc, canonical_bank=bank))
        else:
            row.current_ifsc, row.canonical_bank = ifsc, bank
    removed = _sync_mergers(session, mergers)
    counts = {
        "banks": len(banks),
        "sublet_ifsc": len(sublet),
        "mergers": len(mergers),
        "mergers_removed": removed,
    }
    record_event(
        session, actor=SYSTEM, action="masterdata.banks_imported", after=counts | {"source": source}
    )
    return counts
