"""The mock bank's own records: one entry per FDR, keyed by IFSC + FDR number."""

import json
import threading
from datetime import UTC, datetime
from pathlib import Path

_lock = threading.Lock()


def _key(ifsc: str, fdr_no: str) -> str:
    return f"{ifsc.upper()}|{fdr_no.upper()}"


class Ledger:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _read(self) -> dict:
        if not self.path.exists():
            return {"entries": {}, "next_index": 1}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def upsert(self, record: dict) -> dict:
        with _lock:
            data = self._read()
            key = _key(record["ifsc"], record["fdr_no"])
            existing = data["entries"].get(key)
            if existing is None:
                record = record | {
                    "status_index": data["next_index"],
                    "status": "active",
                    "lien_status": "MARKED",
                    "last_update": datetime.now(UTC).isoformat(),
                }
                data["next_index"] += 1
            else:
                record = existing | record
            data["entries"][key] = record
            self._write(data)
            return record

    def entries(self) -> list[dict]:
        return list(self._read()["entries"].values())

    def get(self, ifsc: str, fdr_no: str) -> dict | None:
        return self._read()["entries"].get(_key(ifsc, fdr_no))

    def set_status(self, ifsc: str, fdr_no: str, status: str, lien_status: str) -> dict | None:
        with _lock:
            data = self._read()
            entry = data["entries"].get(_key(ifsc, fdr_no))
            if entry is None:
                return None
            entry.update(
                status=status, lien_status=lien_status, last_update=datetime.now(UTC).isoformat()
            )
            self._write(data)
            return entry
