"""End-to-end flow through the API: the six SIH test scenarios plus audit and access."""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select, update

from app.api import deps
from app.core import security
from app.core.config import get_settings
from app.db.session import get_session
from app.main import create_app
from app.models import (
    Coverage,
    Event,
    FieldValue,
    Institution,
    Instrument,
    Notification,
    Obligation,
)
from tests.flow_support import (
    FakeBank,
    fake_extractor,
    make_sessionmaker,
    make_settings,
    seed,
    submit,
    values,
)


@pytest.fixture
def env(tmp_path, rsa_key, monkeypatch, make_token):
    monkeypatch.setattr(security, "get_signing_key", lambda token, settings: rsa_key.public_key())
    settings = make_settings(tmp_path)
    factory = make_sessionmaker()
    ids = seed(factory, date.today())
    bank = FakeBank()
    extracted = {"values": values()}

    app = create_app()

    def session_override():
        with factory() as s:
            yield s

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[deps.extractor_dep] = lambda: fake_extractor(extracted["values"])
    app.dependency_overrides[deps.bank_dep] = lambda: bank
    deps._stores.clear()

    tokens = {
        "inst_a": make_token(["institution"], username="inst.a"),
        "inst_b": make_token(["institution"], username="inst.b"),
        "scrutiny": make_token(["scrutiny_officer"], username="scrutiny.any"),
        "west": make_token(["scrutiny_officer"], username="officer.west"),
        "verifier": make_token(["verifying_officer"], username="verifier"),
        "authority": make_token(["competent_authority"], username="authority"),
        "auditor": make_token(["auditor"], username="auditor"),
        "admin": make_token(["admin"], username="admin"),
        "bank": make_token(["bank_service"], username="bank.xnbk"),
        # Only Keycloak default roles, which DepositTrack ignores: no role at all.
        "nobody": make_token(["offline_access", "uma_authorization"], username="nobody"),
        "west_inst_b": make_token(
            ["institution", "scrutiny_officer"], username="officer.west.inst.b"
        ),
    }

    class Env:
        pass

    e = Env()
    e.client, e.factory, e.ids, e.bank, e.tokens, e.extracted = (
        TestClient(app),
        factory,
        ids,
        bank,
        tokens,
        extracted,
    )
    e.h = lambda who: {"Authorization": f"Bearer {tokens[who]}"}
    return e


def _detail(env, instrument_id, who="scrutiny"):
    return env.client.get(f"/api/v1/instruments/{instrument_id}", headers=env.h(who)).json()


def _activate(env, instrument_id):
    for target, who in (("verified", "scrutiny"), ("active", "verifier")):
        r = env.client.post(
            f"/api/v1/instruments/{instrument_id}/transition",
            json={"target": target, "reason": "checked"},
            headers=env.h(who),
        )
        assert r.status_code == 200, r.text


def test_new_submission_reaches_scrutiny_machine_checked(env):
    r = submit(env.client, env.tokens["inst_a"], values())
    assert r.status_code == 201, r.text
    detail = _detail(env, r.json()["id"])
    assert detail["instrument"]["state"] == "scrutiny"
    assert detail["instrument"]["trust_level"] == 1
    assert detail["chain"]["intact"]
    actions = [e["action"] for e in detail["events"]]
    assert actions[:3] == ["instrument.created", "document.uploaded", "extraction.completed"]
    assert detail["flags"] == []


def test_declared_value_that_differs_from_scan_is_flagged(env):
    r = submit(env.client, env.tokens["inst_a"], values(amount="1500000"))
    detail = _detail(env, r.json()["id"])
    types = {f["type"] for f in detail["flags"]}
    assert "declared_mismatch" in types
    amount = next(f for f in detail["fields"] if f["field"] == "amount")
    assert amount["trust_level"] == 0


def test_amount_below_demo_requirement_is_flagged(env):
    env.extracted["values"] = values(amount="100000", amount_words="Rupees One Lakh Only")
    r = submit(
        env.client,
        env.tokens["inst_a"],
        values(amount="100000", amount_words="Rupees One Lakh Only"),
    )
    assert "amount_below_requirement" in {f["type"] for f in _detail(env, r.json()["id"])["flags"]}


def test_double_pledge_flags_both_and_blocks_verification(env):
    first = submit(env.client, env.tokens["inst_a"], values()).json()["id"]
    second = submit(
        env.client, env.tokens["inst_b"], values(depositor="Synthetic Institute B")
    ).json()["id"]
    for instrument_id in (first, second):
        flags = _detail(env, instrument_id)["flags"]
        assert any(f["type"] == "duplicate_pledge" and f["severity"] == "critical" for f in flags)
    r = env.client.post(
        f"/api/v1/instruments/{second}/transition",
        json={"target": "verified", "reason": "looks fine"},
        headers=env.h("scrutiny"),
    )
    assert r.status_code == 409


def test_institution_cannot_see_another_institutions_instrument(env):
    instrument_id = submit(env.client, env.tokens["inst_a"], values()).json()["id"]
    assert (
        env.client.get(f"/api/v1/instruments/{instrument_id}", headers=env.h("inst_b")).status_code
        == 404
    )
    listing = env.client.get("/api/v1/instruments", headers=env.h("inst_b")).json()
    assert listing["total"] == 0


def test_regional_officer_sees_only_their_region(env):
    submit(env.client, env.tokens["inst_a"], values())  # West
    submit(env.client, env.tokens["inst_b"], values(fdr_no="XN9999999999"))  # East
    assert env.client.get("/api/v1/instruments", headers=env.h("west")).json()["total"] == 1
    assert env.client.get("/api/v1/instruments", headers=env.h("scrutiny")).json()["total"] == 2


def test_institution_cannot_verify_its_own_instrument(env):
    instrument_id = submit(env.client, env.tokens["inst_a"], values()).json()["id"]
    r = env.client.post(
        f"/api/v1/instruments/{instrument_id}/transition",
        json={"target": "verified", "reason": "trust me"},
        headers=env.h("inst_a"),
    )
    assert r.status_code == 403


def test_officer_verification_and_observation(env):
    instrument_id = submit(env.client, env.tokens["inst_a"], values()).json()["id"]
    r = env.client.post(
        f"/api/v1/instruments/{instrument_id}/observations",
        json={"text": "Lien wording checked against the scan."},
        headers=env.h("scrutiny"),
    )
    assert r.status_code == 201
    r = env.client.post(
        f"/api/v1/instruments/{instrument_id}/fields/amount",
        json={"verify": True, "reason": "matches scan"},
        headers=env.h("scrutiny"),
    )
    assert r.json()["trust_level"] == 2
    r = env.client.post(
        f"/api/v1/instruments/{instrument_id}/fields/amount",
        json={"value": "1", "reason": "typo"},
        headers=env.h("scrutiny"),
    )
    assert r.status_code == 403  # amount is not an editable field


def test_bank_attestation_raises_trust_and_catches_tampering(env):
    good = values()
    env.bank.add(good)
    instrument_id = submit(env.client, env.tokens["inst_a"], good).json()["id"]
    pinned = env.client.post("/api/v1/admin/bank-keys/pin", headers=env.h("admin"))
    assert pinned.status_code == 200 and pinned.json()["added"]
    r = env.client.post(
        f"/api/v1/instruments/{instrument_id}/bank-verification", headers=env.h("verifier")
    )
    assert r.json()["result"] == "attested"
    assert r.json()["trust_level"] == 4

    tampered = values(fdr_no="XN5555555555")
    env.bank.add(tampered)
    env.extracted["values"] = tampered | {
        "amount": "1500000",
        "amount_words": "Rupees Fifteen Lakh Only",
    }
    forged = submit(
        env.client,
        env.tokens["inst_a"],
        tampered | {"amount": "1500000", "amount_words": "Rupees Fifteen Lakh Only"},
    ).json()["id"]
    r = env.client.post(
        f"/api/v1/instruments/{forged}/bank-verification", headers=env.h("verifier")
    )
    assert r.json()["result"] == "mismatch"
    assert "amount" in r.json()["mismatched"]
    flags = _detail(env, forged)["flags"]
    assert any(f["type"] == "bank_mismatch" and f["severity"] == "critical" for f in flags)


def test_lifecycle_reminders_overdue_and_renewal(env):
    maturity = date.today() + timedelta(days=100)
    v = values(maturity_date=maturity.isoformat())
    env.extracted["values"] = v
    instrument_id = submit(env.client, env.tokens["inst_a"], v).json()["id"]
    _activate(env, instrument_id)

    def advance(days):
        env.client.post("/api/v1/admin/clock", json={"days": days}, headers=env.h("admin"))
        return env.client.post("/api/v1/admin/sweep", headers=env.h("admin")).json()

    advance(70)  # 30 days to maturity
    assert _detail(env, instrument_id)["instrument"]["state"] == "expiring"
    advance(70)  # sweep again on the same day: no duplicate reminders
    with env.factory() as s:
        keys = [
            n.dedupe_key
            for n in s.scalars(select(Notification).where(Notification.kind == "maturity_reminder"))
        ]
    assert sorted(k.split(":")[0] for k in keys) == sorted(
        ["T-90", "T-90", "T-60", "T-60", "T-30", "T-30"]
    )

    advance(101)  # maturity passed
    detail = _detail(env, instrument_id)
    assert detail["instrument"]["state"] == "overdue"
    assert any(n["kind"] == "overdue" for n in detail["notifications"])

    renewal = values(
        fdr_no="XN7777777777",
        issue_date=(maturity - timedelta(days=1)).isoformat(),
        maturity_date=(maturity + timedelta(days=3 * 365)).isoformat(),
    )
    env.extracted["values"] = renewal
    new_id = submit(env.client, env.tokens["inst_a"], renewal, replaces_id=instrument_id).json()[
        "id"
    ]
    _activate(env, new_id)
    advance(102)
    detail = _detail(env, instrument_id)
    assert detail["instrument"]["state"] == "renewed"
    assert detail["replaced_by"][0]["id"] == new_id


def test_release_is_blocked_until_checklist_complete(env):
    v = values()
    env.bank.add(v)
    instrument_id = submit(env.client, env.tokens["inst_a"], v).json()["id"]
    _activate(env, instrument_id)

    case = env.client.post(
        f"/api/v1/instruments/{instrument_id}/release-requests",
        json={"case_type": "release", "reason": "approval withdrawn by the institution"},
        headers=env.h("inst_a"),
    ).json()
    blocked = env.client.post(
        f"/api/v1/cases/{case['id']}/decision",
        json={"approve": True, "reason": "ok"},
        headers=env.h("authority"),
    )
    assert blocked.status_code == 409

    r = env.client.post(
        f"/api/v1/cases/{case['id']}/evidence",
        params={"item_id": "closure_order"},
        files={"file": ("order.pdf", b"%PDF-1.4 synthetic order", "application/pdf")},
        headers=env.h("inst_a"),
    )
    assert r.status_code == 201, r.text
    env.client.post(
        f"/api/v1/cases/{case['id']}/checklist/no_pending_dues",
        json={"note": "declared"},
        headers=env.h("inst_a"),
    )
    officer_by_institution = env.client.post(
        f"/api/v1/cases/{case['id']}/checklist/officer_scrutiny", json={}, headers=env.h("inst_a")
    )
    assert officer_by_institution.status_code == 403
    env.client.post(
        f"/api/v1/cases/{case['id']}/checklist/officer_scrutiny", json={}, headers=env.h("scrutiny")
    )

    no_reason = env.client.post(
        f"/api/v1/cases/{case['id']}/decision",
        json={"approve": True, "reason": " "},
        headers=env.h("authority"),
    )
    assert no_reason.status_code == 422
    approved = env.client.post(
        f"/api/v1/cases/{case['id']}/decision",
        json={"approve": True, "reason": "conditions met"},
        headers=env.h("authority"),
    )
    assert approved.status_code == 200, approved.text
    detail = _detail(env, instrument_id)
    assert detail["instrument"]["state"] == "released"
    assert any(d["kind"] == "release_letter" for d in detail["documents"])
    assert env.bank.records[(v["ifsc"], v["fdr_no"])]["lien_status"] == "REMOVED"


def test_dashboard_reports_and_notifications(env):
    submit(env.client, env.tokens["inst_a"], values())
    submit(env.client, env.tokens["inst_b"], values(depositor="B"))  # double pledge
    dash = env.client.get("/api/v1/dashboard", headers=env.h("scrutiny")).json()
    assert dash["total"] == 2
    assert dash["tiles"]["pending_verification"] == 2
    assert dash["tiles"]["flagged"] == 2
    rep = env.client.get("/api/v1/reports/interventions", headers=env.h("scrutiny")).json()
    assert len(rep["rows"]) == 2
    xlsx = env.client.get(
        "/api/v1/reports/pending-verifications?format=xlsx", headers=env.h("scrutiny")
    )
    assert xlsx.status_code == 200 and xlsx.content[:2] == b"PK"
    csv = env.client.get(
        "/api/v1/reports/upcoming-maturities?format=csv", headers=env.h("scrutiny")
    )
    assert csv.text.startswith("Institution,")


def test_file_verifier_and_tamper_detection(env):
    scan = b"\x89PNG exact scan bytes"
    import json

    r = env.client.post(
        "/api/v1/instruments",
        data={"declared": json.dumps(values()), "kind": "fdr"},
        files={"file": ("scan.png", scan, "image/png")},
        headers=env.h("inst_a"),
    )
    instrument_id = r.json()["id"]
    found = env.client.post(
        "/api/v1/verify-file",
        files={"file": ("x.png", scan, "image/png")},
        headers=env.h("auditor"),
    ).json()
    assert found["matched"] and found["matches"][0]["chain_intact"]
    missing = env.client.post(
        "/api/v1/verify-file",
        files={"file": ("x.png", b"other", "image/png")},
        headers=env.h("auditor"),
    ).json()
    assert not missing["matched"]

    anchor = env.client.post("/api/v1/audit/anchors", headers=env.h("admin")).json()
    assert anchor["anchored"]

    with env.factory() as s:  # an insider edits an audit row directly
        s.execute(update(Event).where(Event.action == "instrument.created").values(reason="edited"))
        s.commit()
    chains = env.client.get("/api/v1/audit/chains", headers=env.h("auditor")).json()
    assert chains["broken"][0]["instrument"]["id"] == instrument_id
    anchors = env.client.get("/api/v1/audit/anchors", headers=env.h("auditor")).json()["items"]
    assert anchors[0]["valid"] is False


def test_field_values_keep_declared_and_extracted_separately(env):
    env.extracted["values"] = values(branch="Pune City Branch")
    instrument_id = submit(env.client, env.tokens["inst_a"], values()).json()["id"]
    with env.factory() as s:
        branch = s.scalars(select(FieldValue).where(FieldValue.field == "branch")).first()
    assert branch.declared == "Pune Main Branch"
    assert branch.extracted_b == "Pune City Branch"
    assert _detail(env, instrument_id)["instrument"]["id"] == instrument_id


def test_clock_cannot_move_backwards_or_without_admin(env):
    assert (
        env.client.post(
            "/api/v1/admin/clock", json={"days": -1}, headers=env.h("admin")
        ).status_code
        == 422
    )
    assert (
        env.client.post(
            "/api/v1/admin/clock", json={"days": 5}, headers=env.h("scrutiny")
        ).status_code
        == 403
    )


def test_late_renewal_is_flagged_as_a_continuity_gap(env):
    old = values(maturity_date=(date.today() + timedelta(days=40)).isoformat())
    env.extracted["values"] = old
    old_id = submit(env.client, env.tokens["inst_a"], old).json()["id"]
    late = values(
        fdr_no="XN4444444444",
        issue_date=(date.today() + timedelta(days=55)).isoformat(),
        maturity_date=(date.today() + timedelta(days=800)).isoformat(),
    )
    env.extracted["values"] = late
    new_id = submit(env.client, env.tokens["inst_a"], late, replaces_id=old_id).json()["id"]
    flags = _detail(env, new_id)["flags"]
    gap = next(f for f in flags if f["type"] == "continuity_gap")
    assert gap["fact"]["gap_days"] == 15


def test_double_pledge_detected_across_a_bank_merger(env):
    from app.models import IfscLineage

    with env.factory() as s:
        s.add(
            IfscLineage(old_ifsc="XOLD0001234", current_ifsc="XNBK0001234", canonical_bank="XNBK")
        )
        s.commit()
    submit(env.client, env.tokens["inst_a"], values())
    merged = values(ifsc="XOLD0001234", depositor="Synthetic Institute B")
    env.extracted["values"] = merged
    second = submit(env.client, env.tokens["inst_b"], merged).json()["id"]
    assert any(f["type"] == "duplicate_pledge" for f in _detail(env, second)["flags"])


def test_credential_from_an_unpinned_key_is_rejected(env):
    from tests.flow_support import FakeBank

    v = values()
    env.bank.add(v)
    instrument_id = submit(env.client, env.tokens["inst_a"], v).json()["id"]
    env.client.post("/api/v1/admin/bank-keys/pin", headers=env.h("admin"))
    impostor = FakeBank()  # same issuer id, different private key
    impostor.add(v)
    env.bank.key = impostor.key
    r = env.client.post(
        f"/api/v1/instruments/{instrument_id}/bank-verification", headers=env.h("verifier")
    )
    assert r.json()["result"] == "rejected"
    detail = _detail(env, instrument_id)
    assert detail["instrument"]["trust_level"] < 3
    assert any(f["type"] == "bank_mismatch" for f in detail["flags"])


def test_officers_see_requirements_of_institutions_with_no_deposit(env):
    # Nothing submitted yet: both obligations are fully uncovered and must still be visible.
    dash = env.client.get("/api/v1/dashboard", headers=env.h("scrutiny")).json()
    assert float(dash["coverage"]["required"]) == 1_000_000
    assert dash["tiles"]["coverage_gaps"] == 2
    items = env.client.get("/api/v1/coverage", headers=env.h("scrutiny")).json()["items"]
    assert len(items) == 2
    own = env.client.get("/api/v1/coverage", headers=env.h("inst_a")).json()["items"]
    assert [i["institution"]["aicte_id"] for i in own] == ["SYN-A"]


@pytest.mark.parametrize("who", ["nobody", "bank"])
def test_coverage_needs_report_view_or_own_read(env, who):
    # No DepositTrack role, or a bank service account (attestation only): no amounts at all.
    submit(env.client, env.tokens["inst_a"], values())  # XNBK instrument, the bank's own
    assert env.client.get("/api/v1/coverage", headers=env.h(who)).status_code == 403
    assert env.client.get("/api/v1/dashboard", headers=env.h(who)).status_code == 403


def test_mixed_role_user_keeps_their_own_institution_outside_their_region(env):
    # A West officer who is also institution B (East) sees West plus their own B.
    submit(env.client, env.tokens["inst_b"], values(depositor="Synthetic Institute B"))
    items = env.client.get("/api/v1/coverage", headers=env.h("west_inst_b")).json()["items"]
    assert sorted(i["institution"]["aicte_id"] for i in items) == ["SYN-A", "SYN-B"]
    listing = env.client.get("/api/v1/instruments", headers=env.h("west_inst_b")).json()
    assert [i["institution"]["aicte_id"] for i in listing["items"]] == ["SYN-B"]


def _add_institutions_with_deposits(env, numbers):
    """Synthetic West institutions, each with an obligation fully covered by one deposit."""
    today = date.today()
    with env.factory() as s:
        for n in numbers:
            inst = Institution(
                aicte_id=f"SYN-X{n:03}",
                name=f"Synthetic {n}",
                institution_type="any",
                region="West",
            )
            s.add(inst)
            s.flush()
            obligation = Obligation(
                institution_id=inst.id,
                basis_ref="demo approval case",
                required_amount=500000,
                required_from=today - timedelta(days=30),
                required_until=today + timedelta(days=365),
            )
            instrument = Instrument(
                institution_id=inst.id,
                kind="fdr",
                instrument_no=f"X{n}",
                instrument_no_norm=f"X{n}",
                amount=500000,
                state="active",
            )
            s.add_all([obligation, instrument])
            s.flush()
            s.add(
                Coverage(
                    obligation_id=obligation.id,
                    instrument_id=instrument.id,
                    allocated_amount=500000,
                    valid_from=today - timedelta(days=30),
                    valid_to=today + timedelta(days=365),
                )
            )
        s.commit()


def _queries(env, path, who="scrutiny"):
    engine = env.factory.kw["bind"]
    statements = []

    def count(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", count)
    try:
        assert env.client.get(path, headers=env.h(who)).status_code == 200
    finally:
        event.remove(engine, "before_cursor_execute", count)
    return len(statements)


@pytest.mark.parametrize("path", ["/api/v1/coverage", "/api/v1/dashboard"])
def test_coverage_query_count_does_not_grow_with_obligations(env, path):
    # Allocations are loaded in bulk, not once per obligation (no N+1).
    _add_institutions_with_deposits(env, range(0, 2))
    few = _queries(env, path)
    _add_institutions_with_deposits(env, range(2, 30))
    assert _queries(env, path) == few
    items = env.client.get("/api/v1/coverage", headers=env.h("scrutiny")).json()["items"]
    assert len(items) == 32
