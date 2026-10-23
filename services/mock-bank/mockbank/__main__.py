"""CLI for the mock bank.

python -m mockbank register --ifsc ... --fdr-no ... --amount ... --issue-date YYYY-MM-DD
       --maturity-date YYYY-MM-DD --beneficiary ... --depositor ...
                                       record an FDR the bank issued in its own ledger
python -m mockbank serve [--port 8090] run the HTTP API

The ledger starts empty: the bank side records each FDR it issued (here, or with POST /fdrs),
the way a real bank's core system would hold it. Nothing is generated.
"""

import argparse

from pydantic import ValidationError

from mockbank.app import FdrRecord
from mockbank.ledger import Ledger
from mockbank.settings import get_settings


def register(record: FdrRecord) -> dict:
    book = Ledger(get_settings().ledger_file)
    if book.get(record.ifsc, record.fdr_no) is not None:
        raise SystemExit("This FDR is already on the bank's ledger")
    return book.upsert(record.model_dump(mode="json"))


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
        try:
            record = FdrRecord(
                fdr_no=args.fdr_no,
                ifsc=args.ifsc.upper(),
                amount=args.amount,
                issue_date=args.issue_date,
                maturity_date=args.maturity_date,
                beneficiary=args.beneficiary,
                depositor=args.depositor,
            )
        except ValidationError as exc:
            raise SystemExit(str(exc)) from exc
        entry = register(record)
        print(f"Recorded FDR {entry['fdr_no']} ({entry['ifsc']}) in the mock bank ledger")
    else:
        import uvicorn

        uvicorn.run("mockbank.app:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
