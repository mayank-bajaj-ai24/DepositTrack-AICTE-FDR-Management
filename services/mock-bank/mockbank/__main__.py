"""CLI for the mock bank.

python -m mockbank register --ifsc ... --fdr-no ... --amount ... --issue-date YYYY-MM-DD
       --maturity-date YYYY-MM-DD --beneficiary ... --depositor ...
                                       record an FDR the bank issued in its own ledger
python -m mockbank serve [--port 8090] run the HTTP API

The ledger starts empty: the bank side records each FDR it issued (here, or with POST /fdrs),
the way a real bank's core system would hold it. Nothing is generated. `register` is safe to
run while `serve` is running: both go through the same locked, insert-only ledger write.
"""

import argparse

from pydantic import ValidationError

from mockbank.files import Busy
from mockbank.ledger import AlreadyRecorded
from mockbank.records import FdrRecord, NotIssuedHere, record_issued_fdr
from mockbank.settings import get_settings


def register(args: argparse.Namespace) -> dict:
    try:
        record = FdrRecord(
            fdr_no=args.fdr_no,
            ifsc=args.ifsc,
            amount=args.amount,
            issue_date=args.issue_date,
            maturity_date=args.maturity_date,
            beneficiary=args.beneficiary,
            depositor=args.depositor,
        )
        return record_issued_fdr(record, get_settings())
    except (ValidationError, AlreadyRecorded, NotIssuedHere, Busy) as exc:
        raise SystemExit(f"Not recorded: {exc}") from exc


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="mockbank")
    sub = parser.add_subparsers(dest="command", required=True)
    reg = sub.add_parser("register")
    for name in ("ifsc", "fdr-no", "amount", "issue-date", "maturity-date", "beneficiary"):
        reg.add_argument(f"--{name}", required=True)
    reg.add_argument("--depositor", required=True)
    serve_cmd = sub.add_parser("serve")
    serve_cmd.add_argument("--host", default="127.0.0.1")
    serve_cmd.add_argument("--port", type=int, default=8090)
    args = parser.parse_args(argv)

    if args.command == "register":
        entry = register(args)
        print(f"Recorded FDR {entry['fdr_no']} ({entry['ifsc']}) in the mock bank ledger")
    else:
        import uvicorn

        try:
            get_settings()  # refuse to start on invalid settings, e.g. equal tokens
        except ValidationError as exc:
            raise SystemExit(f"Invalid mock bank settings: {exc}") from exc
        uvicorn.run("mockbank.app:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
