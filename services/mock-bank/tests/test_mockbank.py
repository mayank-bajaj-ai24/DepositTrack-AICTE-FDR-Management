import base64

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi.testclient import TestClient

from mockbank.app import app
from mockbank.ledger import Ledger
from mockbank.settings import Settings, get_settings
from mockbank.signing import canonical_json

TOKEN = "test-token"
OPERATOR = "test-operator-token"
RECORD = {
    "fdr_no": "XN1234567890",
    "ifsc": "XNBK0001234",
    "amount": 500000,
    "issue_date": "2025-01-10",
    "maturity_date": "2028-01-10",
    "beneficiary": "AICTE, New Delhi",
}


@pytest.fixture
def client(tmp_path):
    settings = Settings(
        api_token=TOKEN,
        operator_token=OPERATOR,
        ledger_file=str(tmp_path / "ledger.json"),
        keys_dir=str(tmp_path / "keys"),
    )
    app.dependency_overrides[get_settings] = lambda: settings
    Ledger(settings.ledger_file).upsert(dict(RECORD))
    yield TestClient(app)
    app.dependency_overrides.clear()


AUTH = {"Authorization": f"Bearer {TOKEN}"}
OP = {"Authorization": f"Bearer {OPERATOR}"}


def _verify(public_b64: str, payload: dict) -> None:
    body = {k: v for k, v in payload.items() if k != "signature"}
    signature = base64.b64decode(payload["signature"].removeprefix("ed25519:"))
    Ed25519PublicKey.from_public_bytes(base64.b64decode(public_b64)).verify(
        signature, canonical_json(body)
    )


def test_requires_token(client):
    assert client.get("/keys").status_code == 401


def test_credential_is_signed_by_published_key(client):
    keys = client.get("/keys", headers=AUTH).json()
    cred = client.get(
        "/credentials", params={"ifsc": RECORD["ifsc"], "fdr_no": RECORD["fdr_no"]}, headers=AUTH
    ).json()
    assert cred["subject"]["amount_inr"] == 500000
    _verify(keys[cred["issuer"]], cred)


def test_tampered_credential_fails_verification(client):
    keys = client.get("/keys", headers=AUTH).json()
    cred = client.get(
        "/credentials", params={"ifsc": RECORD["ifsc"], "fdr_no": RECORD["fdr_no"]}, headers=AUTH
    ).json()
    cred["subject"]["amount_inr"] = 1500000
    with pytest.raises(Exception):  # noqa: B017 - cryptography raises InvalidSignature
        _verify(keys[cred["issuer"]], cred)


def test_unknown_fdr_is_404(client):
    response = client.get(
        "/credentials", params={"ifsc": "XNBK0001234", "fdr_no": "NOPE"}, headers=AUTH
    )
    assert response.status_code == 404


def test_lien_removal_revokes(client):
    ref = {"ifsc": RECORD["ifsc"], "fdr_no": RECORD["fdr_no"]}
    assert client.post("/lien/remove", json=ref, headers=AUTH).json()["status"] == "revoked"
    status = client.get("/status", params=ref, headers=AUTH).json()
    assert status["status"] == "revoked"
    assert status["lien_status"] == "REMOVED"
    assert status["next_update"] > status["last_update"]


def test_bank_operator_records_an_fdr_it_issued(client):
    record = RECORD | {"fdr_no": "NEW0000001", "depositor": "Depositor"}
    r = client.post("/fdrs", json=record, headers=OP)
    assert r.status_code == 201
    assert r.json()["lien_status"] == "MARKED"
    cred = client.get(
        "/credentials", params={"ifsc": record["ifsc"], "fdr_no": record["fdr_no"]}, headers=AUTH
    )
    assert cred.json()["subject"]["amount_inr"] == record["amount"]


def test_depositrack_token_cannot_write_the_bank_ledger(client):
    record = RECORD | {"fdr_no": "NEW0000002", "depositor": "Depositor"}
    assert client.post("/fdrs", json=record, headers=AUTH).status_code == 401
    assert client.post("/fdrs", json=record).status_code == 401
    assert client.get("/ledger", headers=AUTH).status_code == 401


def test_recorded_values_are_validated(client):
    record = RECORD | {"fdr_no": "NEW0000003", "depositor": "Depositor"}
    bad = record | {"maturity_date": record["issue_date"]}
    assert client.post("/fdrs", json=bad, headers=OP).status_code == 422
    assert client.post("/fdrs", json=record | {"ifsc": "bad"}, headers=OP).status_code == 422


def test_an_fdr_cannot_be_recorded_twice(client):
    record = RECORD | {"depositor": "Depositor"}
    assert client.post("/fdrs", json=record, headers=OP).status_code == 409


def test_operator_sees_the_ledger_and_the_page(client):
    rows = client.get("/ledger", headers=OP).json()
    assert [r["fdr_no"] for r in rows] == [RECORD["fdr_no"]]
    page = client.get("/")
    assert page.status_code == 200 and "Simulation only" in page.text
