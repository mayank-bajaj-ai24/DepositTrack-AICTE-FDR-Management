"""M12 master data: AICTE institution import and RBI IFSC bank master / merger lineage.

Fixtures are small excerpts of the real public downloads (tests/fixtures/masterdata).
"""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from sqlalchemy import event, select

from app.core.configfiles import load_config
from app.models import Bank, BankMerger, Event, IfscLineage, Institution, Instrument
from app.modules.checks.canonical import canonical_bank
from app.modules.instruments.intake import duplicate_flags
from app.modules.lifecycle.states import InstrumentKind
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


def test_mergers_removed_from_the_config_are_removed_from_the_table(session):
    import_banks(session, FIXTURES, load_config("bank_mergers.yaml")["mergers"])
    kept = [{"old_bank": "VIJB", "canonical_bank": "BARB", "source": "test"}]
    result = import_banks(session, FIXTURES, kept)
    assert result["mergers_removed"] == len(load_config("bank_mergers.yaml")["mergers"]) - 1
    assert [m.old_bank for m in session.scalars(select(BankMerger))] == ["VIJB"]
    assert canonical_bank(session, "SYNB0001234") == "SYNB"


def test_a_reversed_merger_replaces_the_old_row_instead_of_forming_a_cycle(session):
    import_banks(session, FIXTURES, [{"old_bank": "VIJB", "canonical_bank": "BARB", "source": "x"}])
    import_banks(session, FIXTURES, [{"old_bank": "BARB", "canonical_bank": "VIJB", "source": "x"}])
    assert [(m.old_bank, m.canonical_bank) for m in session.scalars(select(BankMerger))] == [
        ("BARB", "VIJB")
    ]
    # One bank, one key: both prefixes resolve to the same canonical bank.
    assert canonical_bank(session, "VIJB0001234") == canonical_bank(session, "BARB0AAMBUR")


def test_a_bank_listed_twice_in_the_merger_config_is_rejected(session):
    twice = [
        {"old_bank": "VIJB", "canonical_bank": "BARB", "source": "x"},
        {"old_bank": "VIJB", "canonical_bank": "BKDN", "source": "x"},
    ]
    with pytest.raises(MasterDataError, match="more than once"):
        import_banks(session, FIXTURES, twice)


def test_bank_names_skip_sublet_ifscs(session):
    import_banks(session, FIXTURES, [])
    # In the real IFSC.csv, KNSB0000001 (let to KUNS, named after it) is the first KNSB row.
    assert session.get(Bank, "KNSB").name == "Kurla Nagarik Sahakari Bank"
    # A sublet row ahead of the prefix owner's own branch does not rename HDFC either.
    assert session.get(Bank, "HDFC").name == "HDFC Bank"
    # A bank with no IFSC of its own is named from the IFSCs let to it.
    assert session.get(Bank, "KUNS").name == "Kurmanchal Nagar Sahakari Bank"
    assert session.get(Bank, "AACX").name == "Akhand Anand Co.op Bank"


def _stored_instrument(session, ifsc: str, number: str = "123456") -> Instrument:
    """An instrument stored before the bank import: keyed by its IFSC prefix only."""
    inst = Institution(aicte_id=f"SYN-TEST-{number}", name="Synthetic Test Institute")
    session.add(inst)
    session.flush()
    fdr = Instrument(
        institution_id=inst.id,
        kind=InstrumentKind.FDR,
        bank_ifsc=ifsc,
        canonical_bank=ifsc[:4],
        instrument_no=number,
        instrument_no_norm=number,
    )
    session.add(fdr)
    session.flush()
    return fdr


def test_import_rekeys_instruments_stored_before_it(session):
    vijaya = _stored_instrument(session, "VIJB0009502")
    hdfc_sublet = _stored_instrument(session, "HDFC0CAACOB", "654321")
    result = import_banks(session, FIXTURES, load_config("bank_mergers.yaml")["mergers"])
    assert result["instruments_rekeyed"] == 2
    assert vijaya.canonical_bank == "BARB"
    assert hdfc_sublet.canonical_bank == "AACX"

    event = session.scalars(
        select(Event).where(Event.action == "masterdata.instruments_rekeyed")
    ).one()
    assert event.actor_id == "system"
    assert event.after["instruments"] == 2
    assert {(c["from"], c["to"], c["count"]) for c in event.after["changes"]} == {
        ("VIJB", "BARB", 1),
        ("HDFC", "AACX", 1),
    }


def test_rekeying_follows_a_merger_removed_from_the_config(session):
    vijaya = _stored_instrument(session, "VIJB0009502")
    import_banks(session, FIXTURES, load_config("bank_mergers.yaml")["mergers"])
    result = import_banks(session, FIXTURES, [])
    assert result["instruments_rekeyed"] == 1
    assert vijaya.canonical_bank == "VIJB"


def test_reimport_without_changes_rekeys_nothing_and_records_no_event(session):
    _stored_instrument(session, "VIJB0009502")
    mergers = load_config("bank_mergers.yaml")["mergers"]
    import_banks(session, FIXTURES, mergers)
    assert import_banks(session, FIXTURES, mergers)["instruments_rekeyed"] == 0
    events = session.scalars(select(Event).where(Event.action == "masterdata.instruments_rekeyed"))
    assert len(events.all()) == 1


def _submitted(session, ifsc: str, number: str, issued: date | None, amount: str | None):
    """An instrument keyed the way intake keys it, for a synthetic institution."""
    inst = Institution(aicte_id=f"SYN-DUP-{ifsc}-{number}-{issued}", name="Synthetic Institute")
    session.add(inst)
    session.flush()
    fdr = Instrument(
        institution_id=inst.id,
        kind=InstrumentKind.FDR,
        bank_ifsc=ifsc,
        canonical_bank=canonical_bank(session, ifsc),
        instrument_no=number,
        instrument_no_norm=number,
        issue_date=issued,
        amount=Decimal(amount) if amount else None,
    )
    session.add(fdr)
    session.flush()
    return fdr


@pytest.fixture
def merged(session):
    import_banks(session, FIXTURES, load_config("bank_mergers.yaml")["mergers"])
    return session


def test_same_deposit_pledged_across_a_merger_is_a_critical_duplicate(merged):
    # A Vijaya Bank FDR pledged, then pledged again quoting the Bank of Baroda IFSC.
    _submitted(merged, "VIJB0009502", "123456", date(2018, 6, 1), "500000")
    again = _submitted(merged, "BARB0AAMBUR", "123456", date(2018, 6, 1), "500000.00")
    [(_, spec)] = duplicate_flags(merged, again)
    assert spec.flag_type == "duplicate_pledge"
    assert spec.severity == "critical"
    assert spec.fact["issuing_banks"] == ["BARB", "VIJB"]


def test_same_number_in_two_banks_series_joined_by_a_merger_is_not_a_duplicate(merged):
    # Vijaya Bank FDR 123456 and an unrelated Bank of Baroda FDR 123456, both pre-merger.
    _submitted(merged, "VIJB0009502", "123456", date(2017, 3, 1), "500000")
    other = _submitted(merged, "BARB0AAMBUR", "123456", date(2018, 9, 15), "750000")
    assert duplicate_flags(merged, other) == []


def test_near_number_in_a_merged_banks_series_is_not_a_near_duplicate(merged):
    _submitted(merged, "VIJB0009502", "123456", date(2017, 3, 1), "500000")
    other = _submitted(merged, "BARB0AAMBUR", "123457", date(2018, 9, 15), "750000")
    assert duplicate_flags(merged, other) == []


def test_same_bank_duplicate_does_not_need_matching_dates_or_amounts(merged):
    _submitted(merged, "BARB0AAMBUR", "123456", date(2017, 3, 1), "500000")
    again = _submitted(merged, "BARB0AAMBUR", "123456", date(2018, 9, 15), "750000")
    [(_, spec)] = duplicate_flags(merged, again)
    assert spec.flag_type == "duplicate_pledge"
    assert "issuing_banks" not in spec.fact


def test_cross_merger_duplicate_is_not_ruled_out_by_a_missing_field(merged):
    _submitted(merged, "VIJB0009502", "123456", date(2018, 6, 1), "500000")
    again = _submitted(merged, "BARB0AAMBUR", "123456", date(2018, 6, 1), None)
    [(_, spec)] = duplicate_flags(merged, again)
    assert spec.flag_type == "duplicate_pledge"


def _by_state(rows: list[dict]) -> dict:
    by_state: dict = {}
    for r in rows:
        by_state.setdefault(r["state"], []).append(r["row"])
    return by_state


def test_fetch_refuses_an_institution_listed_under_two_states(tmp_path):
    rows = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["rows"]
    by_state = _by_state(rows)
    by_state[rows[1]["state"]].append(rows[0]["row"])  # Kerala row also under Maharashtra
    cfg = load_config("master_data.yaml")["aicte"]
    client = _dashboard([r["row"] for r in rows], by_state)
    with pytest.raises(SnapshotError, match="more than once"):
        fetch_institutions(cfg, tmp_path, client=client)


def test_fetch_refuses_an_institution_repeated_within_a_state(tmp_path):
    rows = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["rows"]
    by_state = _by_state(rows)
    by_state[rows[0]["state"]].append(rows[0]["row"])
    cfg = load_config("master_data.yaml")["aicte"]
    client = _dashboard([r["row"] for r in rows], by_state)
    with pytest.raises(SnapshotError, match="more than once"):
        fetch_institutions(cfg, tmp_path, client=client)


def test_fetch_refuses_a_state_row_missing_from_the_all_india_list(tmp_path):
    rows = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["rows"]
    all_india = [r["row"] for r in rows[1:]]  # the all-India list lacks the Kerala row
    cfg = load_config("master_data.yaml")["aicte"]
    with pytest.raises(SnapshotError, match="not in the all-India list"):
        fetch_institutions(cfg, tmp_path, client=_dashboard(all_india, _by_state(rows)))


def test_import_refuses_a_snapshot_that_repeats_an_institution(session, tmp_path):
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    snapshot["rows"].append(snapshot["rows"][0] | {"state": snapshot["rows"][1]["state"]})
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    with pytest.raises(SnapshotError, match="repeats"):
        import_institutions(session, path, load_config("master_data.yaml")["aicte"])


def test_import_refuses_a_snapshot_that_does_not_match_the_all_india_count(session, tmp_path):
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    snapshot["rows"] = snapshot["rows"][1:]
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    with pytest.raises(SnapshotError, match="all-India list had 3"):
        import_institutions(session, path, load_config("master_data.yaml")["aicte"])


def test_bank_import_does_not_query_once_per_row(session):
    mergers = load_config("bank_mergers.yaml")["mergers"]
    rows = sum(
        len(json.loads((FIXTURES / name).read_text(encoding="utf-8")))
        for name in ("banks.json", "sublet.json")
    ) + len(mergers)
    statements: list[str] = []

    def count(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    engine = session.get_bind()
    event.listen(engine, "before_cursor_execute", count)
    try:
        for _ in range(2):  # first import inserts, the second one updates
            statements.clear()
            import_banks(session, FIXTURES, mergers)
            assert len(statements) < rows / 2, statements
    finally:
        event.remove(engine, "before_cursor_execute", count)
