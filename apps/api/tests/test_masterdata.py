"""M12 master data: AICTE institution import and RBI IFSC bank master / merger lineage.

Fixtures are small excerpts of the real public downloads (tests/fixtures/masterdata).
"""

import json
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from app.core.configfiles import load_config
from app.models import Bank, BankMerger, Event, IfscLineage, Institution
from app.modules.checks.canonical import canonical_bank
from app.modules.masterdata.aicte import (
    SnapshotError,
    fetch_institutions,
    import_institutions,
)
from app.modules.masterdata.banks import MasterDataError, import_banks
from tests.flow_support import make_sessionmaker

FIXTURES = Path(__file__).parent / "fixtures" / "masterdata"
SNAPSHOT = FIXTURES / "institutions_2024-2025.json"


@pytest.fixture
def session():
    with make_sessionmaker()() as s:
        yield s


def test_institutions_are_imported_with_state_and_source(session):
    cfg = load_config("master_data.yaml")["aicte"]
    result = import_institutions(session, SNAPSHOT, cfg)
    assert result == {"created": 3, "updated": 0}

    rows = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["rows"]
    first = session.scalars(
        select(Institution).where(Institution.aicte_id == rows[0]["row"][0])
    ).one()
    assert first.name == rows[0]["row"][1].strip()
    assert first.state == rows[0]["state"]
    assert first.institution_type == rows[0]["row"][4]
    assert first.region is None  # AICTE regions unconfirmed (config regions: {})
    assert "AICTE" in first.contacts["source"]


def test_institution_import_is_idempotent(session):
    cfg = load_config("master_data.yaml")["aicte"]
    import_institutions(session, SNAPSHOT, cfg)
    assert import_institutions(session, SNAPSHOT, cfg) == {"created": 0, "updated": 3}
    assert len(session.scalars(select(Institution)).all()) == 3


def test_configured_region_is_applied(session):
    cfg = load_config("master_data.yaml")["aicte"] | {"regions": {"Kerala": "South"}}
    import_institutions(session, SNAPSHOT, cfg)
    kerala = session.scalars(select(Institution).where(Institution.state == "Kerala")).one()
    assert kerala.region == "South"


def _dashboard(all_india: list, by_state: dict) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        state = request.url.params["state"]
        return httpx.Response(200, json=all_india if state == "1" else by_state.get(state, []))

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_refuses_a_snapshot_that_loses_institutions(tmp_path):
    rows = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["rows"]
    all_india = [r["row"] for r in rows]
    by_state = {rows[0]["state"]: [rows[0]["row"]]}  # the other two states return nothing
    cfg = load_config("master_data.yaml")["aicte"]
    with pytest.raises(SnapshotError, match="2 institutions"):
        fetch_institutions(cfg, tmp_path, client=_dashboard(all_india, by_state))


def test_fetch_saves_a_complete_snapshot(tmp_path):
    rows = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["rows"]
    by_state: dict = {}
    for r in rows:
        by_state.setdefault(r["state"], []).append(r["row"])
    cfg = load_config("master_data.yaml")["aicte"]
    path = fetch_institutions(cfg, tmp_path, client=_dashboard([r["row"] for r in rows], by_state))
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["all_india_count"] == 3
    assert {r["state"] for r in saved["rows"]} == {r["state"] for r in rows}


def test_banks_sublets_and_mergers_are_imported(session):
    mergers = load_config("bank_mergers.yaml")["mergers"]
    result = import_banks(session, FIXTURES, mergers)
    assert result["mergers"] == len(mergers)
    assert session.get(Bank, "BARB").name == "Bank of Baroda"
    assert session.get(Bank, "BARB").bank_type == "PSB"
    assert session.get(IfscLineage, "HDFC0CAACOB").canonical_bank == "AACX"
    assert all(m.source.startswith("https://") for m in session.scalars(select(BankMerger)))


def test_merger_codes_must_exist_in_the_ifsc_master(session):
    bad = [{"old_bank": "ZZZZ", "canonical_bank": "BARB", "source": "x"}]
    with pytest.raises(MasterDataError, match="ZZZZ"):
        import_banks(session, FIXTURES, bad)


def test_canonical_bank_follows_mergers_and_sublets(session):
    import_banks(session, FIXTURES, load_config("bank_mergers.yaml")["mergers"])
    # A Vijaya Bank or Dena Bank IFSC resolves to Bank of Baroda (RBI, 1 Apr 2019).
    assert canonical_bank(session, "VIJB0001234") == "BARB"
    assert canonical_bank(session, "BKDN0001234") == "BARB"
    assert canonical_bank(session, "SYNB0001234") == "CNRB"
    assert canonical_bank(session, "BARB0VJABCD") == "BARB"
    # A sublet IFSC belongs to the bank that uses it, not the prefix owner.
    assert canonical_bank(session, "HDFC0CAACOB") == "AACX"
    assert canonical_bank(session, "HDFC0000001") == "HDFC"


def test_reimport_keeps_values_the_source_does_not_provide(session):
    cfg = load_config("master_data.yaml")["aicte"]
    import_institutions(session, SNAPSHOT, cfg)
    inst = session.scalars(select(Institution).where(Institution.state == "Kerala")).one()
    inst.region = "set by hand"
    inst.contacts = inst.contacts | {"email": "office@example.org"}
    import_institutions(session, SNAPSHOT, cfg)
    assert inst.region == "set by hand"
    assert inst.contacts["email"] == "office@example.org"


def test_imports_are_audited(session):
    import_institutions(session, SNAPSHOT, load_config("master_data.yaml")["aicte"])
    import_banks(session, FIXTURES, load_config("bank_mergers.yaml")["mergers"])
    actions = [e.action for e in session.scalars(select(Event).order_by(Event.seq))]
    assert actions == ["masterdata.institutions_imported", "masterdata.banks_imported"]


def test_fetch_refuses_an_empty_all_india_list(tmp_path):
    cfg = load_config("master_data.yaml")["aicte"]
    with pytest.raises(SnapshotError, match="empty"):
        fetch_institutions(cfg, tmp_path, client=_dashboard([], {}))


def test_fetch_refuses_short_rows(tmp_path):
    cfg = load_config("master_data.yaml")["aicte"]
    short = [["1-0", "name only"]]
    with pytest.raises(SnapshotError, match="fewer than"):
        fetch_institutions(cfg, tmp_path, client=_dashboard(short, {cfg["states"][0]: short}))


def test_merger_chains_are_followed(session):
    mergers = [
        {"old_bank": "VIJB", "canonical_bank": "BKDN", "source": "test chain"},
        {"old_bank": "BKDN", "canonical_bank": "BARB", "source": "test chain"},
    ]
    import_banks(session, FIXTURES, mergers)
    assert canonical_bank(session, "VIJB0001234") == "BARB"


def test_merger_cycles_are_rejected(session):
    mergers = [
        {"old_bank": "VIJB", "canonical_bank": "BKDN", "source": "test cycle"},
        {"old_bank": "BKDN", "canonical_bank": "VIJB", "source": "test cycle"},
    ]
    with pytest.raises(MasterDataError, match="cycle"):
        import_banks(session, FIXTURES, mergers)
