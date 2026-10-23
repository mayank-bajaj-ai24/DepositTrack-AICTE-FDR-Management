"""CLI for the mock bank.

python -m mockbank seed --from ../../data/synthetic   load the bank's records from synthetic FDRs
python -m mockbank serve [--port 8090]                 run the HTTP API
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

from mockbank.ledger import Ledger
from mockbank.settings import get_settings


def _iso(value: str, fmt: str = "%d/%m/%Y") -> str:
    return datetime.strptime(value, fmt).date().isoformat()


def seed(source: Path) -> int:
    """Each synthetic FDR's true values become the bank's own record of it."""
    book = Ledger(get_settings().ledger_file)
    count = 0
    for path in sorted(source.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        values = record.get("values")
        if not values:
            continue
        book.upsert(
            {
                "fdr_no": values["fdr_no"],
                "ifsc": values["ifsc"],
                "amount": values["amount"],
                "issue_date": _iso(values["deposit_date"]),
                "maturity_date": _iso(values["maturity_date"]),
                "beneficiary": values["beneficiary"],
                "depositor": values["depositor"],
            }
        )
        count += 1
    return count


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="mockbank")
    sub = parser.add_subparsers(dest="command", required=True)
    seed_cmd = sub.add_parser("seed")
    seed_cmd.add_argument("--from", dest="source", type=Path, required=True)
    serve_cmd = sub.add_parser("serve")
    serve_cmd.add_argument("--host", default="127.0.0.1")
    serve_cmd.add_argument("--port", type=int, default=8090)
    args = parser.parse_args(argv)

    if args.command == "seed":
        print(f"Loaded {seed(args.source)} FDRs into the mock bank ledger")
    else:
        import uvicorn

        uvicorn.run("mockbank.app:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
