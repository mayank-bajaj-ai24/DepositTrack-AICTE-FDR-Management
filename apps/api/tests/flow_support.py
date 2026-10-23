"""Test doubles for end-to-end flow tests: an in-memory database, a fake extractor and a
fake bank that signs credentials with a real Ed25519 key."""

import base64
import json
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.config import Settings
from app.db.base import Base
from app.models import Institution, Obligation, UserAccount
from app.modules.audit.hashchain import canonical_json
from app.modules.extraction.service import FIELDS, ExtractionResult, FieldResult

API_ROOT = Path(__file__).resolve().parents[1]


def make_settings(tmp_path) -> Settings:
    return Settings(
        database_url="sqlite://",
        storage_backend="local",
        storage_local_dir=str(tmp_path / "storage"),
        storage_encryption_key=Fernet.generate_key().decode(),
        policy_file=str(API_ROOT / "config" / "policy.demo.yaml"),
        bank_api_token="test-bank-token",
        bank_keys_file=str(tmp_path / "pinned.json"),
        models_dir=str(tmp_path / "no-models"),
    )


def make_sessionmaker():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def seed(session_factory, today: date) -> dict:
    """Two institutions in two regions, one obligation each, and linked user accounts."""
    with session_factory() as s:
        a = Institution(
            aicte_id="SYN-A", name="Synthetic Institute A", institution_type="any", region="West"
        )
        b = Institution(
            aicte_id="SYN-B", name="Synthetic Institute B", institution_type="any", region="East"
        )
        s.add_all([a, b])
        s.flush()
        for inst in (a, b):
            s.add(
                Obligation(
                    institution_id=inst.id,
                    basis_ref="demo approval case",
                    rule_version="demo-0.1",
                    required_amount=500000,
                    required_from=today - timedelta(days=30),
                    required_until=today + timedelta(days=5 * 365),
                )
            )
        s.add_all(
            [
                UserAccount(username="inst.a", institution_id=a.id),
                UserAccount(username="inst.b", institution_id=b.id),
                UserAccount(username="officer.west", region="West"),
                UserAccount(username="bank.xnbk", bank_code="XNBK"),
                # Mixed roles: a West officer whose own institution (B) is in the East.
                UserAccount(username="officer.west.inst.b", region="West", institution_id=b.id),
            ]
        )
        s.commit()
        return {"a": a.id, "b": b.id}


def values(**overrides) -> dict:
    base = {
        "fdr_no": "XN1234567890",
        "bank": "Example National Bank",
        "branch": "Pune Main Branch",
        "ifsc": "XNBK0001234",
        "amount": "500000",
        "amount_words": "Rupees Five Lakh Only",
        "issue_date": (date.today() - timedelta(days=10)).isoformat(),
        "maturity_date": (date.today() + timedelta(days=3 * 365)).isoformat(),
        "depositor": "Synthetic Institute A",
        "beneficiary": "AICTE, New Delhi",
        "lien_text": "Lien marked in favour of AICTE",
    }
    return base | overrides


def fake_extractor(extracted: dict):
    """An extractor that 'reads' the given values from any upload."""

    def run(data: bytes, content_type: str | None) -> ExtractionResult:
        result = ExtractionResult(pass_a_available=False)
        for name in FIELDS:
            value = extracted.get(name)
            result.fields[name] = FieldResult(
                pass_a=None,
                pass_b=value,
                value=value,
                confidence=0.98 if value else 0.0,
                needs_review=value is None,
            )
        return result

    return run


class FakeBank:
    """Signs credentials exactly like services/mock-bank, from its own records."""

    def __init__(self):
        self.key = Ed25519PrivateKey.generate()
        self.records: dict[tuple[str, str], dict] = {}

    def add(self, v: dict) -> None:
        self.records[(v["ifsc"], v["fdr_no"])] = {
            "fdr_no": v["fdr_no"],
            "ifsc": v["ifsc"],
            "amount": int(v["amount"]),
            "issue_date": v["issue_date"],
            "maturity_date": v["maturity_date"],
            "beneficiary": v["beneficiary"],
            "status": "active",
            "lien_status": "MARKED",
        }

    def key_id(self, ifsc: str) -> str:
        return f"bank:{ifsc[:4]}:key-1"

    def _sign(self, payload: dict) -> dict:
        signature = self.key.sign(canonical_json(payload).encode("utf-8"))
        return payload | {"signature": "ed25519:" + base64.b64encode(signature).decode()}

    def public_keys(self) -> dict[str, str]:
        raw = self.key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        return {self.key_id(ifsc): base64.b64encode(raw).decode() for ifsc, _ in self.records}

    def _status(self, entry: dict) -> dict:
        now = datetime.now(UTC)
        return {
            "registry": "test",
            "index": 1,
            "status": entry["status"],
            "lien_status": entry["lien_status"],
            "last_update": now.isoformat(),
            "next_update": (now + timedelta(hours=24)).isoformat(),
        }

    def credential(self, ifsc: str, fdr_no: str) -> dict:
        e = self.records[(ifsc, fdr_no)]
        return self._sign(
            {
                "type": "FDRAttestation",
                "issuer": self.key_id(ifsc),
                "issued_at": datetime.now(UTC).isoformat(),
                "subject": {
                    "instrument_no": e["fdr_no"],
                    "ifsc": e["ifsc"],
                    "amount_inr": e["amount"],
                    "issue_date": e["issue_date"],
                    "maturity_date": e["maturity_date"],
                    "beneficiary": e["beneficiary"],
                    "lien_status": e["lien_status"],
                },
                "status": self._status(e),
            }
        )

    def status(self, ifsc: str, fdr_no: str) -> dict:
        e = self.records[(ifsc, fdr_no)]
        return self._sign(self._status(e) | {"issuer": self.key_id(ifsc), "instrument_no": fdr_no})

    def remove_lien(self, ifsc: str, fdr_no: str) -> dict:
        self.records[(ifsc, fdr_no)].update(status="revoked", lien_status="REMOVED")
        return {"status": "revoked", "lien_status": "REMOVED"}


def submit(client, token, declared: dict, *, replaces_id: str | None = None):
    data = {"declared": json.dumps(declared), "kind": "fdr"}
    if replaces_id:
        data["replaces_id"] = replaces_id
    return client.post(
        "/api/v1/instruments",
        data=data,
        files={"file": ("scan.png", b"\x89PNG fake scan " + uuid.uuid4().bytes, "image/png")},
        headers={"Authorization": f"Bearer {token}"},
    )
