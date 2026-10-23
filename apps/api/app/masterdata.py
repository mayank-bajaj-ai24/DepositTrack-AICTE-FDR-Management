"""Fetch and import public master data (M12).

    python -m app.masterdata fetch-institutions   AICTE approved institutions -> data/open/aicte/
    python -m app.masterdata import-institutions  upsert them into the database
    python -m app.masterdata fetch-banks          RBI IFSC master -> data/open/ifsc/
    python -m app.masterdata import-banks         banks, sublet IFSCs and RBI-cited mergers

Sources and parameters are in config/master_data.yaml and config/bank_mergers.yaml.
"""

import argparse
from pathlib import Path

from app.core.configfiles import load_config

API_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = API_ROOT.parents[1] / "data" / "open"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="app.masterdata")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("fetch-institutions")
    imp = sub.add_parser("import-institutions")
    imp.add_argument("--snapshot", type=Path, default=None)
    sub.add_parser("fetch-banks")
    sub.add_parser("import-banks")
    args = parser.parse_args(argv)

    cfg = load_config("master_data.yaml")
    aicte_dir, ifsc_dir = args.data_dir / "aicte", args.data_dir / "ifsc"

    if args.command == "fetch-institutions":
        from app.modules.masterdata.aicte import fetch_institutions

        print(f"Saved {fetch_institutions(cfg['aicte'], aicte_dir)}")
        return
    if args.command == "fetch-banks":
        from app.modules.masterdata.banks import fetch_ifsc

        for path in fetch_ifsc(cfg["ifsc"], ifsc_dir):
            print(f"Saved {path}")
        return

    from sqlalchemy.orm import Session

    from app.db.session import get_engine

    with Session(get_engine()) as session:
        if args.command == "import-institutions":
            from app.modules.masterdata.aicte import import_institutions

            snapshot = args.snapshot or aicte_dir / (
                f"institutions_{cfg['aicte']['academic_year']}.json"
            )
            result = import_institutions(session, snapshot, cfg["aicte"])
        else:
            from app.modules.masterdata.banks import import_banks

            mergers = load_config("bank_mergers.yaml")["mergers"]
            result = import_banks(session, ifsc_dir, mergers)
        session.commit()
    print(result)


if __name__ == "__main__":
    main()
