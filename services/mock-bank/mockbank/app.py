"""HTTP API of the mock bank.

GET  /                              the bank operator's page (record FDRs, see the ledger)
POST /fdrs                         operator: record an FDR the bank issued (its own ledger)
GET  /ledger                       operator: every FDR on the ledger with its status
GET  /keys                         public keys per bank code (AICTE pins these; they never change)
GET  /credentials?ifsc=&fdr_no=    signed FDRAttestation for one FDR
GET  /status?ifsc=&fdr_no=         signed status record with last/next update (freshness)
POST /lien/remove                  remove AICTE's lien (on release); revokes the credential
POST /simulate/close               operator, demo: the depositor closed the FDR early

DepositTrack's token (MB_API_TOKEN) reads the bank's records and removes AICTE's lien on
release; only the bank operator's token (MB_OPERATOR_TOKEN) writes the bank's own records.
"""

import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from mockbank.files import Busy
from mockbank.ledger import AlreadyRecorded, Ledger
from mockbank.records import FdrRecord, NotIssuedHere, record_issued_fdr
from mockbank.settings import Settings, get_settings
from mockbank.signing import KeyStore

app = FastAPI(title="Mock bank (simulation only)", version="0.1.0")
STATIC_DIR = Path(__file__).parent / "static"


@app.exception_handler(Busy)
def _ledger_busy(_: Request, exc: Busy) -> JSONResponse:
    return JSONResponse({"detail": f"{exc}; try again"}, status.HTTP_503_SERVICE_UNAVAILABLE)


def _check_bearer(authorization: str | None, configured: str, env_name: str) -> None:
    """Fail closed (503) while the token is not configured; constant-time comparison."""
    if not configured:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"{env_name} is not configured")
    expected = f"Bearer {configured}"
    if authorization is None or not secrets.compare_digest(authorization, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid token (expected {env_name})")


def require_token(
    authorization: str | None = Header(default=None), settings: Settings = Depends(get_settings)
) -> None:
    """DepositTrack: read the bank's records and remove AICTE's lien on release."""
    _check_bearer(authorization, settings.api_token, "MB_API_TOKEN")


def require_operator(
    authorization: str | None = Header(default=None), settings: Settings = Depends(get_settings)
) -> None:
    """The bank's own operator: record FDRs and bank-side events on the bank's ledger."""
    _check_bearer(authorization, settings.operator_token, "MB_OPERATOR_TOKEN")


def ledger(settings: Settings = Depends(get_settings)) -> Ledger:
    return Ledger(settings.ledger_file)


def keys(settings: Settings = Depends(get_settings)) -> KeyStore:
    return KeyStore(settings.keys_dir)


class FdrRef(BaseModel):
    ifsc: str
    fdr_no: str


def _entry_or_404(entry: dict | None) -> dict:
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such FDR at this bank")
    return entry


def _status_record(entry: dict, settings: Settings) -> dict:
    now = datetime.now(UTC)
    return {
        "registry": f"bank:{entry['ifsc'][:4]}:fdr-status",
        "index": entry["status_index"],
        "status": entry["status"],
        "lien_status": entry["lien_status"],
        "last_update": now.isoformat(),
        "next_update": (now + timedelta(hours=settings.freshness_hours)).isoformat(),
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "simulation": True}


@app.get("/", include_in_schema=False)
def operator_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "operator.html", media_type="text/html")


@app.get("/ledger", dependencies=[Depends(require_operator)])
def ledger_entries(book: Ledger = Depends(ledger)) -> list[dict]:
    return sorted(book.entries(), key=lambda e: e["status_index"], reverse=True)


@app.post("/fdrs", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_operator)])
def register_fdr(record: FdrRecord, settings: Settings = Depends(get_settings)) -> dict:
    try:
        return record_issued_fdr(record, settings)
    except AlreadyRecorded as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except NotIssuedHere as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


@app.get("/keys", dependencies=[Depends(require_token)])
def public_keys(
    book: Ledger = Depends(ledger),
    store: KeyStore = Depends(keys),
    settings: Settings = Depends(get_settings),
) -> dict:
    """One key per bank code this bank manages: configured (MB_BANK_CODES), already keyed, or
    on the ledger. Configured codes are published even while the ledger is empty, so a pin
    right after start-up covers them. A key never changes once created."""
    banks = set(settings.issuing_banks) | set(store.known_banks())
    banks |= {e["ifsc"][:4] for e in book.entries()}
    return {store.key_id(b): store.public_b64(b) for b in sorted(banks)}


@app.get("/credentials", dependencies=[Depends(require_token)])
def credential(
    ifsc: str,
    fdr_no: str,
    book: Ledger = Depends(ledger),
    store: KeyStore = Depends(keys),
    settings: Settings = Depends(get_settings),
) -> dict:
    entry = _entry_or_404(book.get(ifsc, fdr_no))
    bank = entry["ifsc"][:4]
    payload = {
        "type": "FDRAttestation",
        "issuer": store.key_id(bank),
        "issued_at": datetime.now(UTC).isoformat(),
        "subject": {
            "instrument_no": entry["fdr_no"],
            "ifsc": entry["ifsc"],
            "amount_inr": entry["amount"],
            "issue_date": entry["issue_date"],
            "maturity_date": entry["maturity_date"],
            "beneficiary": entry["beneficiary"],
            "lien_status": entry["lien_status"],
        },
        "status": _status_record(entry, settings),
    }
    return payload | {"signature": store.sign(bank, payload)}


@app.get("/status", dependencies=[Depends(require_token)])
def status_record(
    ifsc: str,
    fdr_no: str,
    book: Ledger = Depends(ledger),
    store: KeyStore = Depends(keys),
    settings: Settings = Depends(get_settings),
) -> dict:
    entry = _entry_or_404(book.get(ifsc, fdr_no))
    record = _status_record(entry, settings) | {
        "instrument_no": entry["fdr_no"],
        "ifsc": entry["ifsc"],
        "issuer": store.key_id(entry["ifsc"][:4]),
    }
    return record | {"signature": store.sign(entry["ifsc"][:4], record)}


@app.post("/lien/remove", dependencies=[Depends(require_token)])
def remove_lien(ref: FdrRef, book: Ledger = Depends(ledger)) -> dict:
    entry = _entry_or_404(
        book.set_status(ref.ifsc, ref.fdr_no, status="revoked", lien_status="REMOVED")
    )
    return {"status": entry["status"], "lien_status": entry["lien_status"]}


@app.post("/simulate/close", dependencies=[Depends(require_operator)])
def simulate_close(ref: FdrRef, book: Ledger = Depends(ledger)) -> dict:
    """A bank-side event (the depositor closed the FDR early), so only the operator records it."""
    entry = _entry_or_404(
        book.set_status(ref.ifsc, ref.fdr_no, status="closed", lien_status="REMOVED")
    )
    return {"status": entry["status"], "lien_status": entry["lien_status"]}
