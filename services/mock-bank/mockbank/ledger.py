"""The mock bank's own records: one entry per FDR, keyed by IFSC + FDR number.

The file is shared by the HTTP server and the `register` CLI, which run as separate
processes. Every read-modify-write holds the inter-process lock in `mockbank.files`, and
every write replaces the file atomically, so readers never see a partial ledger.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

from mockbank.files import locked, read_bytes, write_atomic


class AlreadyRecorded(ValueError):
    """The bank already has this FDR on its ledger (records are insert-only)."""


def _key(ifsc: str, fdr_no: str) -> str:
    return f"{ifsc.upper()}|{fdr_no.upper()}"


class Ledger:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _read(self) -> dict:
        raw = read_bytes(self.path)
        if raw is None:
            return {"entries": {}, "next_index": 1}
        return json.loads(raw.decode("utf-8"))

    def _write(self, data: dict) -> None:
        write_atomic(self.path, json.dumps(data, indent=2).encode("utf-8"))

    def insert(self, record: dict) -> dict:
        """Add an FDR the bank issued. Raises AlreadyRecorded if it is on the ledger already.

        The existence check and the write happen under one lock, so two concurrent
        submissions of the same FDR cannot both succeed or overwrite each other.
        """
        key = _key(record["ifsc"], record["fdr_no"])
        with locked(self.path):
            data = self._read()
            if key in data["entries"]:
                raise AlreadyRecorded("This FDR is already on the bank's ledger")
            entry = record | {
                "status_index": data["next_index"],
                "status": "active",
                "lien_status": "MARKED",
                "last_update": datetime.now(UTC).isoformat(),
            }
            data["next_index"] += 1
            data["entries"][key] = entry
            self._write(data)
            return entry

    def entries(self) -> list[dict]:
        return list(self._read()["entries"].values())

    def get(self, ifsc: str, fdr_no: str) -> dict | None:
        return self._read()["entries"].get(_key(ifsc, fdr_no))

    def set_status(self, ifsc: str, fdr_no: str, status: str, lien_status: str) -> dict | None:
        with locked(self.path):
            data = self._read()
            entry = data["entries"].get(_key(ifsc, fdr_no))
            if entry is None:
                return None
            entry.update(
                status=status, lien_status=lien_status, last_update=datetime.now(UTC).isoformat()
            )
            self._write(data)
            return entry
