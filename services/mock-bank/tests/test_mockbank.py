import base64

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi.testclient import TestClient

from mockbank import files
from mockbank.app import app
from mockbank.ledger import Ledger
from mockbank.records import FdrRecord, record_issued_fdr
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
    "depositor": "Synthetic Institute of Technology",
}


@pytest.fixture
def bank(tmp_path):
    """Start the mock bank with the given settings and an empty ledger."""

    def start(**overrides) -> tuple[TestClient, Settings]:
        values = {
            "api_token": TOKEN,
            "operator_token": OPERATOR,
            "ledger_file": str(tmp_path / "ledger.json"),
            "keys_dir": str(tmp_path / "keys"),
        }
        settings = Settings(**(values | overrides))
        app.dependency_overrides[get_settings] = lambda: settings
        return TestClient(app), settings

    yield start
    app.dependency_overrides.clear()


@pytest.fixture
def client(bank):
    client, settings = bank()
    record_issued_fdr(FdrRecord(**RECORD), settings)
    return client


AUTH = {"Authorization": f"Bearer {TOKEN}"}
OP = {"Authorization": f"Bearer {OPERATOR}"}


def _verify(public_b64: str, payload: dict) -> None:
    body = {k: v for k, v in payload.items() if k != "signature"}
    signature = base64.b64decode(payload["signature"].removeprefix("ed25519:"))
    Ed25519PublicKey.from_public_bytes(base64.b64decode(public_b64)).verify(
        signature, canonical_json(body)
    )


def _credential(client, ifsc: str, fdr_no: str):
    return client.get("/credentials", params={"ifsc": ifsc, "fdr_no": fdr_no}, headers=AUTH)


def test_requires_token(client):
    assert client.get("/keys").status_code == 401


def test_credential_is_signed_by_published_key(client):
    keys = client.get("/keys", headers=AUTH).json()
    cred = _credential(client, RECORD["ifsc"], RECORD["fdr_no"]).json()
    assert cred["subject"]["amount_inr"] == 500000
    _verify(keys[cred["issuer"]], cred)


def test_tampered_credential_fails_verification(client):
    keys = client.get("/keys", headers=AUTH).json()
    cred = _credential(client, RECORD["ifsc"], RECORD["fdr_no"]).json()
    cred["subject"]["amount_inr"] = 1500000
    with pytest.raises(Exception):  # noqa: B017 - cryptography raises InvalidSignature
        _verify(keys[cred["issuer"]], cred)


def test_unknown_fdr_is_404(client):
    assert _credential(client, "XNBK0001234", "NOPE").status_code == 404
    ref = {"ifsc": "XNBK0001234", "fdr_no": "NOPE"}
    assert client.post("/lien/remove", json=ref, headers=AUTH).status_code == 404


def test_lien_removal_revokes(client):
    ref = {"ifsc": RECORD["ifsc"], "fdr_no": RECORD["fdr_no"]}
    assert client.post("/lien/remove", json=ref, headers=AUTH).json()["status"] == "revoked"
    status = client.get("/status", params=ref, headers=AUTH).json()
    assert status["status"] == "revoked"
    assert status["lien_status"] == "REMOVED"
    assert status["next_update"] > status["last_update"]


def test_bank_operator_records_an_fdr_it_issued(client):
    record = RECORD | {"fdr_no": "NEW0000001"}
    r = client.post("/fdrs", json=record, headers=OP)
    assert r.status_code == 201
    assert r.json()["lien_status"] == "MARKED"
    cred = _credential(client, record["ifsc"], record["fdr_no"])
    assert cred.json()["subject"]["amount_inr"] == record["amount"]


def test_depositrack_token_cannot_write_the_bank_ledger(client):
    record = RECORD | {"fdr_no": "NEW0000002"}
    assert client.post("/fdrs", json=record, headers=AUTH).status_code == 401
    assert client.post("/fdrs", json=record).status_code == 401
    assert client.get("/ledger", headers=AUTH).status_code == 401


def test_recorded_values_are_validated(client):
    record = RECORD | {"fdr_no": "NEW0000003"}
    bad = record | {"maturity_date": record["issue_date"]}
    assert client.post("/fdrs", json=bad, headers=OP).status_code == 422
    assert client.post("/fdrs", json=record | {"ifsc": "bad"}, headers=OP).status_code == 422


def test_an_fdr_cannot_be_registered_twice_and_is_not_overwritten(bank):
    client, _ = bank()
    record = RECORD | {"fdr_no": "TWICE00001"}
    assert client.post("/fdrs", json=record, headers=OP).status_code == 201
    again = record | {"amount": 999999, "beneficiary": "Someone else"}
    assert client.post("/fdrs", json=again, headers=OP).status_code == 409
    # Same FDR, different spelling of the key: still the same ledger entry.
    lower = record | {"ifsc": record["ifsc"].lower(), "fdr_no": record["fdr_no"].lower()}
    assert client.post("/fdrs", json=lower, headers=OP).status_code == 409
    subject = _credential(client, record["ifsc"], record["fdr_no"]).json()["subject"]
    assert subject["amount_inr"] == record["amount"]
    assert subject["beneficiary"] == record["beneficiary"]


def test_ifsc_is_uppercased_and_text_is_trimmed(bank):
    client, _ = bank()
    record = RECORD | {
        "fdr_no": "  XN555  ",
        "ifsc": " xnbk0001234 ",
        "beneficiary": "  AICTE, New Delhi ",
        "depositor": " Depositor ",
    }
    r = client.post("/fdrs", json=record, headers=OP)
    assert r.status_code == 201
    entry = r.json()
    assert (entry["fdr_no"], entry["ifsc"]) == ("XN555", "XNBK0001234")
    assert (entry["beneficiary"], entry["depositor"]) == ("AICTE, New Delhi", "Depositor")
    # The OCR-extracted number, without the spaces, finds the record.
    assert _credential(client, "XNBK0001234", "XN555").status_code == 200


@pytest.mark.parametrize("field", ["fdr_no", "beneficiary", "depositor", "ifsc"])
def test_blank_text_is_refused(bank, field):
    client, _ = bank()
    assert client.post("/fdrs", json=RECORD | {field: "   "}, headers=OP).status_code == 422


def test_amounts_with_paise_are_recorded(bank):
    client, _ = bank()
    for fdr_no, amount, expected in [
        ("PAISE00001", 500000.5, 500000.5),
        ("PAISE00002", "1250.75", 1250.75),
        ("PAISE00003", "500000.00", 500000),
    ]:
        r = client.post("/fdrs", json=RECORD | {"fdr_no": fdr_no, "amount": amount}, headers=OP)
        assert r.status_code == 201, r.text
        assert r.json()["amount"] == expected
        subject = _credential(client, RECORD["ifsc"], fdr_no).json()["subject"]
        assert subject["amount_inr"] == expected
    whole = _credential(client, RECORD["ifsc"], "PAISE00003").json()["subject"]["amount_inr"]
    assert type(whole) is int  # whole rupees stay a JSON integer


@pytest.mark.parametrize("amount", [0, -1, "1.234", "abc", "NaN"])
def test_bad_amounts_are_refused(bank, amount):
    client, _ = bank()
    record = RECORD | {"amount": amount}
    assert client.post("/fdrs", json=record, headers=OP).status_code == 422


def test_keys_of_configured_banks_are_published_before_any_fdr(bank):
    client, _ = bank(bank_codes="xnbk, ZDFB")
    keys = client.get("/keys", headers=AUTH).json()
    assert sorted(keys) == ["bank:XNBK:key-1", "bank:ZDFB:key-1"]
    # The key pinned on the empty ledger is the one that later signs the bank's credentials.
    assert client.post("/fdrs", json=RECORD, headers=OP).status_code == 201
    cred = _credential(client, RECORD["ifsc"], RECORD["fdr_no"]).json()
    _verify(keys[cred["issuer"]], cred)
    assert client.get("/keys", headers=AUTH).json() == keys


def test_an_fdr_of_a_bank_not_configured_is_refused(bank):
    client, _ = bank(bank_codes="ZDFB")
    r = client.post("/fdrs", json=RECORD, headers=OP)
    assert r.status_code == 422
    assert "MB_BANK_CODES" in r.json()["detail"]


def test_without_configured_banks_a_key_appears_with_the_first_fdr(bank):
    client, _ = bank()
    assert client.get("/keys", headers=AUTH).json() == {}
    assert client.post("/fdrs", json=RECORD, headers=OP).status_code == 201
    keys = client.get("/keys", headers=AUTH).json()
    assert list(keys) == ["bank:XNBK:key-1"]
    other = RECORD | {"fdr_no": "ANOTHER001"}
    assert client.post("/fdrs", json=other, headers=OP).status_code == 201
    assert client.get("/keys", headers=AUTH).json() == keys


def test_bank_codes_must_be_four_letters():
    with pytest.raises(ValueError, match="MB_BANK_CODES"):
        Settings(bank_codes="XNBK,TOOLONG")


def test_a_busy_ledger_answers_503(bank, monkeypatch):
    client, settings = bank()
    monkeypatch.setattr(files, "LOCK_TIMEOUT", 0.05)
    lock = Ledger(settings.ledger_file).path.with_name("ledger.json.lock")
    lock.write_text("another process", encoding="utf-8")
    r = client.post("/fdrs", json=RECORD, headers=OP)
    assert r.status_code == 503
    assert "try again" in r.json()["detail"]


def test_operator_sees_the_ledger_and_the_page(client):
    rows = client.get("/ledger", headers=OP).json()
    assert [r["fdr_no"] for r in rows] == [RECORD["fdr_no"]]
    page = client.get("/")
    assert page.status_code == 200 and "Simulation only" in page.text


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("post", "/fdrs", RECORD),
        ("get", "/ledger", None),
        ("post", "/simulate/close", {"ifsc": RECORD["ifsc"], "fdr_no": RECORD["fdr_no"]}),
    ],
)
def test_operator_endpoints_fail_closed_without_an_operator_token(bank, method, path, body):
    client, _ = bank(operator_token="")
    kwargs = {"json": body} if body else {}
    for headers in ({}, AUTH, {"Authorization": "Bearer "}):
        r = getattr(client, method)(path, headers=headers, **kwargs)
        assert r.status_code == 503
        assert "MB_OPERATOR_TOKEN" in r.json()["detail"]


def test_operator_token_cannot_use_depositrack_endpoints(client):
    ref = {"ifsc": RECORD["ifsc"], "fdr_no": RECORD["fdr_no"]}
    assert client.get("/keys", headers=OP).status_code == 401
    assert client.get("/credentials", params=ref, headers=OP).status_code == 401
    assert client.get("/status", params=ref, headers=OP).status_code == 401
    assert client.post("/lien/remove", json=ref, headers=OP).status_code == 401
    assert client.get("/status", params=ref, headers=AUTH).json()["lien_status"] == "MARKED"


def test_only_the_operator_records_an_early_closure(client):
    ref = {"ifsc": RECORD["ifsc"], "fdr_no": RECORD["fdr_no"]}
    assert client.post("/simulate/close", json=ref).status_code == 401
    assert client.post("/simulate/close", json=ref, headers=AUTH).status_code == 401
    assert client.get("/status", params=ref, headers=AUTH).json()["status"] == "active"
    r = client.post("/simulate/close", json=ref, headers=OP)
    assert r.json() == {"status": "closed", "lien_status": "REMOVED"}
    status = client.get("/status", params=ref, headers=AUTH).json()
    assert (status["status"], status["lien_status"]) == ("closed", "REMOVED")
    unknown = {"ifsc": RECORD["ifsc"], "fdr_no": "NOPE"}
    assert client.post("/simulate/close", json=unknown, headers=OP).status_code == 404


def test_operator_token_must_differ_from_the_depositrack_token():
    with pytest.raises(ValueError, match="must differ") as excinfo:
        Settings(api_token="same-value", operator_token="same-value", _env_file=None)
    assert "same-value" not in str(excinfo.value)  # the error never echoes the token
