"""Download an open dataset listed in ml/open_datasets.json with kagglehub.

    apps/api/.venv/Scripts/python ml/download_open_data.py find-it-again

Needs a Kaggle account and API token (~/.kaggle/access_token or KAGGLE_API_TOKEN). Kaggle
is free; accept the dataset's terms on its page first if Kaggle asks. Prints the local path.
"""

import argparse
import json
from pathlib import Path

CATALOG = Path(__file__).resolve().parent / "open_datasets.json"


def main() -> None:
    catalog = {
        k: v for k, v in json.loads(CATALOG.read_text(encoding="utf-8")).items() if k[0] != "_"
    }
    parser = argparse.ArgumentParser()
    parser.add_argument("name", choices=sorted(catalog))
    args = parser.parse_args()

    import kagglehub

    entry = catalog[args.name]
    print(f"{args.name}: {entry['citation']} (licence: {entry['licence']})")
    print(kagglehub.dataset_download(entry["kaggle"]))


if __name__ == "__main__":
    main()
