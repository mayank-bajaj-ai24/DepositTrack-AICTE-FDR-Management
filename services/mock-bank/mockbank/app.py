"""HTTP API of the mock bank.

POST /fdrs                         the bank records an FDR it issued (its own ledger)
GET  /keys                         public keys per bank code (AICTE pins these once)
GET  /credentials?ifsc=&fdr_no=    signed FDRAttestation for one FDR
GET  /status?ifsc=&fdr_no=         signed status record with last/next update (freshness)
POST /lien/remove                  remove AICTE's lien (on release); revokes the credential
POST /simulate/close               demo: the depositor closed the FDR early
"""

import secrets
from datetime import UTC, date, datetime, timedelta

from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field, model_validator

from mockbank.ledger import Ledger
from mockbank.settings import Settings, get_settings
from mockbank.signing import KeyStore

app = FastAPI(title="Mock bank (simulation only)", version="0.1.0")


def require_token(
    authorization: str | None = Header(default=None), settings: Settings = Depends(get_settings)
) -> None:
    if not settings.api_token:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "MB_API_TOKEN is not configured")
    expected = f"Bearer {settings.api_token}"
    if authorization is None or not secrets.compare_digest(authorization, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")


def ledger(settings: Settings = Depends(get_settings)) -> Ledger:
    return Ledger(settings.ledger_file)


def keys(settings: Settings = Depends(get_settings)) -> KeyStore:
    return KeyStore(settings.keys_dir)


class FdrRef(BaseModel):
    ifsc: str
    fdr_no: str


class FdrRecord(BaseModel):
    """What the issuing bank knows about an FDR it issued (entered by the bank, not AICTE)."""

    fdr_no: str = Field(min_length=1, max_length=64)
    ifsc: str = Field(pattern=r"^[A-Z]{4}0[A-Z0-9]{6}$")
    amount: int = Field(gt=0)
    issue_date: date
    maturity_date: date
    beneficiary: str = Field(min_length=1)
    depositor: str = Field(min_length=1)

    @model_validator(mode="after")
    def _maturity_after_issue(self) -> "FdrRecord":
        if self.maturity_date <= self.issue_date:
            raise ValueError("maturity_date must be after issue_date")
        return self


def _entry_or_404(book: Ledger, ifsc: str, fdr_no: str) -> dict:
    entry = book.get(ifsc, fdr_no)
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


@app.post("/fdrs", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_token)])
def register_fdr(record: FdrRecord, book: Ledger = Depends(ledger)) -> dict:
    if book.get(record.ifsc, record.fdr_no) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This FDR is already on the bank's ledger")
    return book.upsert(record.model_dump(mode="json"))


@app.get("/keys", dependencies=[Depends(require_token)])
def public_keys(book: Ledger = Depends(ledger), store: KeyStore = Depends(keys)) -> dict:
    banks = sorted({e["ifsc"][:4] for e in book._read()["entries"].values()})
    return {store.key_id(b): store.public_b64(b) for b in banks}


@app.get("/credentials", dependencies=[Depends(require_token)])
def credential(
    ifsc: str,
    fdr_no: str,
    book: Ledger = Depends(ledger),
    store: KeyStore = Depends(keys),
    settings: Settings = Depends(get_settings),
) -> dict:
    entry = _entry_or_404(book, ifsc, fdr_no)
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
    entry = _entry_or_404(book, ifsc, fdr_no)
    record = _status_record(entry, settings) | {
        "instrument_no": entry["fdr_no"],
        "ifsc": entry["ifsc"],
        "issuer": store.key_id(entry["ifsc"][:4]),
    }
    return record | {"signature": store.sign(entry["ifsc"][:4], record)}


@app.post("/lien/remove", dependencies=[Depends(require_token)])
def remove_lien(ref: FdrRef, book: Ledger = Depends(ledger)) -> dict:
    _entry_or_404(book, ref.ifsc, ref.fdr_no)
    entry = book.set_status(ref.ifsc, ref.fdr_no, status="revoked", lien_status="REMOVED")
    return {"status": entry["status"], "lien_status": entry["lien_status"]}


@app.post("/simulate/close", dependencies=[Depends(require_token)])
def simulate_close(ref: FdrRef, book: Ledger = Depends(ledger)) -> dict:
    _entry_or_404(book, ref.ifsc, ref.fdr_no)
    entry = book.set_status(ref.ifsc, ref.fdr_no, status="closed", lien_status="REMOVED")
    return {"status": entry["status"], "lien_status": entry["lien_status"]}
