"""The ledger file and the `register` CLI: insert-only, and safe across threads and processes."""

import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from mockbank import __main__ as cli
from mockbank import files
from mockbank.ledger import AlreadyRecorded, Ledger
from mockbank.settings import Settings

PACKAGE_ROOT = Path(__file__).resolve().parents[1]

ENTRY = {
    "fdr_no": "XN1234567890",
    "ifsc": "XNBK0001234",
    "amount": 500000,
    "issue_date": "2025-01-10",
    "maturity_date": "2028-01-10",
    "beneficiary": "AICTE, New Delhi",
    "depositor": "Synthetic Institute of Technology",
}

ARGS = [
    "register",
    "--ifsc",
    "xnbk0001234",
    "--fdr-no",
    "XN1234567890",
    "--amount",
    "500000.50",
    "--issue-date",
    "2025-01-10",
    "--maturity-date",
    "2028-01-10",
    "--beneficiary",
    "AICTE, New Delhi",
    "--depositor",
    "Synthetic Institute of Technology",
]


def _arg(args: list[str], name: str, value: str) -> list[str]:
    out = list(args)
    out[out.index(name) + 1] = value
    return out


@pytest.fixture
def settings(tmp_path, monkeypatch):
    s = Settings(ledger_file=str(tmp_path / "ledger.json"), keys_dir=str(tmp_path / "keys"))
    monkeypatch.setattr(cli, "get_settings", lambda: s)
    return s


def test_insert_is_insert_only(tmp_path):
    book = Ledger(tmp_path / "ledger.json")
    first = book.insert(dict(ENTRY))
    assert (first["status"], first["lien_status"], first["status_index"]) == ("active", "MARKED", 1)
    with pytest.raises(AlreadyRecorded):
        book.insert(ENTRY | {"amount": 1, "fdr_no": ENTRY["fdr_no"].lower()})
    assert book.get(ENTRY["ifsc"], ENTRY["fdr_no"])["amount"] == 500000


def test_concurrent_inserts_of_one_fdr_record_it_once(tmp_path):
    book = Ledger(tmp_path / "ledger.json")

    def attempt(i: int) -> bool:
        try:
            book.insert(ENTRY | {"amount": 1000 + i})
            return True
        except AlreadyRecorded:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(16)))
    assert results.count(True) == 1
    assert len(book.entries()) == 1


def test_concurrent_inserts_lose_no_record(tmp_path):
    book = Ledger(tmp_path / "ledger.json")
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i: book.insert(ENTRY | {"fdr_no": f"T{i:04d}"}), range(40)))
    entries = book.entries()
    assert len(entries) == 40
    assert sorted(e["status_index"] for e in entries) == list(range(1, 41))


def test_register_processes_and_a_reader_share_the_ledger_safely(tmp_path):
    """Several `register` processes write while this process keeps reading the file."""
    ledger_file = tmp_path / "ledger.json"
    env = os.environ | {
        "MB_LEDGER_FILE": str(ledger_file),
        "MB_KEYS_DIR": str(tmp_path / "keys"),
        "MB_BANK_CODES": "",
    }
    reader_errors: list[Exception] = []
    done = threading.Event()

    def read_continuously() -> None:
        book = Ledger(ledger_file)
        while not done.is_set():
            try:
                book.entries()
            except Exception as exc:  # noqa: BLE001 - any failure is a partial read
                reader_errors.append(exc)
            time.sleep(0.002)

    reader = threading.Thread(target=read_continuously)
    reader.start()
    try:
        procs = [
            subprocess.Popen(  # noqa: S603 - fixed arguments, this interpreter
                [sys.executable, "-m", "mockbank", *_arg(ARGS, "--fdr-no", f"PROC{i:04d}")],
                cwd=PACKAGE_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            for i in range(6)
        ]
        outcomes = [p.communicate(timeout=120) for p in procs]
    finally:
        done.set()
        reader.join()
    assert [p.returncode for p in procs] == [0] * 6, outcomes
    assert sorted(e["fdr_no"] for e in Ledger(ledger_file).entries()) == [
        f"PROC{i:04d}" for i in range(6)
    ]
    assert reader_errors == []
    assert sorted(p.name for p in tmp_path.iterdir() if p.name.startswith("ledger")) == [
        "ledger.json"
    ]  # no temp file or lock file left behind


def test_a_stale_lock_from_a_crashed_process_is_cleared(tmp_path):
    book = Ledger(tmp_path / "ledger.json")
    lock = tmp_path / "ledger.json.lock"
    lock.write_text("12345", encoding="utf-8")
    old = time.time() - files.STALE_AFTER - 5
    os.utime(lock, (old, old))
    book.insert(dict(ENTRY))
    assert not lock.exists()


def test_a_held_lock_times_out(tmp_path, monkeypatch):
    monkeypatch.setattr(files, "LOCK_TIMEOUT", 0.05)
    book = Ledger(tmp_path / "ledger.json")
    with files.locked(book.path), pytest.raises(files.Busy):
        book.insert(dict(ENTRY))


def test_cli_register_records_the_fdr(settings, capsys):
    cli.main(ARGS)
    assert "Recorded FDR XN1234567890 (XNBK0001234)" in capsys.readouterr().out
    entry = Ledger(settings.ledger_file).get("XNBK0001234", "XN1234567890")
    assert entry["ifsc"] == "XNBK0001234"  # uppercased, as on the HTTP path
    assert entry["amount"] == 500000.5


def test_cli_register_trims_text(settings):
    args = _arg(_arg(ARGS, "--fdr-no", "  XN777 "), "--beneficiary", " AICTE ")
    cli.main(args)
    entry = Ledger(settings.ledger_file).get("XNBK0001234", "XN777")
    assert (entry["fdr_no"], entry["beneficiary"]) == ("XN777", "AICTE")


def test_cli_register_refuses_a_duplicate(settings):
    cli.main(ARGS)
    with pytest.raises(SystemExit, match="already on the bank's ledger"):
        cli.main(_arg(ARGS, "--amount", "1"))
    assert Ledger(settings.ledger_file).get("XNBK0001234", "XN1234567890")["amount"] == 500000.5


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("--ifsc", "bad", "ifsc"),
        ("--amount", "12.345", "decimal places"),
        ("--amount", "0", "greater than 0"),
        ("--maturity-date", "2025-01-10", "maturity_date must be after issue_date"),
        ("--beneficiary", "   ", "beneficiary"),
    ],
)
def test_cli_register_refuses_invalid_values(settings, name, value, message):
    with pytest.raises(SystemExit, match=message):
        cli.main(_arg(ARGS, name, value))
    assert Ledger(settings.ledger_file).entries() == []


def test_cli_register_refuses_a_bank_not_configured(tmp_path, monkeypatch):
    s = Settings(ledger_file=str(tmp_path / "ledger.json"), bank_codes="ZDFB")
    monkeypatch.setattr(cli, "get_settings", lambda: s)
    with pytest.raises(SystemExit, match="MB_BANK_CODES"):
        cli.main(ARGS)


def test_cli_refuses_equal_tokens(monkeypatch):
    monkeypatch.setenv("MB_API_TOKEN", "same-value")
    monkeypatch.setenv("MB_OPERATOR_TOKEN", "same-value")
    monkeypatch.setattr(cli, "get_settings", lambda: Settings(_env_file=None))
    with pytest.raises(SystemExit, match="must differ"):
        cli.main(ARGS)
    with pytest.raises(SystemExit, match="must differ"):
        cli.main(["serve", "--port", "1"])
