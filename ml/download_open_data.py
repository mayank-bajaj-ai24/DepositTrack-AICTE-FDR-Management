"""Download an open dataset listed in ml/open_datasets.json with kagglehub.

    pip install -e "apps/api[data]"          # once, into the API's virtual environment
    apps/api/.venv/Scripts/python ml/download_open_data.py bpi-2017

Each catalog entry pins a dataset version (`owner/slug/versions/N`), so every run fetches the
same files. They are written to data/<name>/ in the repository (git-ignored), and the path is
printed. Entries whose licence is not confirmed are refused unless --accept-unconfirmed-licence
is given.

Kaggle is free but needs an account and an API token: create one under Settings > API on
kaggle.com and save it to ~/.kaggle/access_token (or set KAGGLE_API_TOKEN). Accept the
dataset's terms on its Kaggle page first if Kaggle asks.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = Path(__file__).resolve().parent / "open_datasets.json"
REQUIRED = ("kaggle", "licence", "licence_confirmed", "citation")
SETUP_HELP = (
    "Kaggle refused the download. Create a free API token under Settings > API on kaggle.com,\n"
    "save it to ~/.kaggle/access_token (or set KAGGLE_API_TOKEN), accept the dataset's terms on\n"
    "its Kaggle page if it asks, and run this again."
)


class CatalogError(ValueError):
    """The catalog file is malformed."""


def load_catalog(path: Path = CATALOG) -> dict[str, dict]:
    """Dataset entries by name; keys starting with "_" are comments."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    catalog = {k: v for k, v in raw.items() if not k.startswith("_")}
    for name, entry in catalog.items():
        if not name:
            raise CatalogError(f"{path.name}: dataset names must not be empty")
        if not isinstance(entry, dict):
            raise CatalogError(f"{path.name}: entry {name!r} must be an object")
        missing = [key for key in REQUIRED if key not in entry]
        if missing:
            raise CatalogError(f"{path.name}: entry {name!r} is missing {', '.join(missing)}")
        if not isinstance(entry["licence_confirmed"], bool):
            raise CatalogError(f"{path.name}: {name!r}.licence_confirmed must be true or false")
        if "/versions/" not in entry["kaggle"]:
            raise CatalogError(
                f"{path.name}: {name!r}.kaggle must pin a version (owner/slug/versions/N)"
            )
    return catalog


def target_dir(name: str, root: Path = ROOT) -> Path:
    return root / "data" / name


def download(name: str, entry: dict, out: Path, kagglehub=None) -> str:
    """Download one entry into `out` and return the local path; exits with setup help on auth."""
    if kagglehub is None:
        import kagglehub
    from kagglehub.exceptions import CredentialError, KaggleApiHTTPError, UnauthenticatedError

    out.mkdir(parents=True, exist_ok=True)
    try:
        return kagglehub.dataset_download(entry["kaggle"], output_dir=str(out))
    except (CredentialError, UnauthenticatedError) as exc:
        raise SystemExit(f"{name}: {exc}\n{SETUP_HELP}") from exc
    except KaggleApiHTTPError as exc:
        status = getattr(exc.response, "status_code", None)
        if status in (401, 403):
            raise SystemExit(f"{name}: HTTP {status}\n{SETUP_HELP}") from exc
        raise


def main(argv: list[str] | None = None) -> None:
    try:
        catalog = load_catalog()
    except CatalogError as exc:
        raise SystemExit(str(exc)) from exc
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("name", choices=sorted(catalog))
    parser.add_argument(
        "--accept-unconfirmed-licence",
        action="store_true",
        help="download an entry whose licence is not confirmed (you take responsibility)",
    )
    args = parser.parse_args(argv)

    entry = catalog[args.name]
    print(f"{args.name}: {entry['citation']}")
    print(f"licence: {entry['licence']}")
    if not entry["licence_confirmed"]:
        if not args.accept_unconfirmed_licence:
            raise SystemExit(
                f"{args.name}: licence not confirmed; refusing to download. Confirm the terms "
                "with the authors, or pass --accept-unconfirmed-licence to proceed anyway."
            )
        print(
            "WARNING: licence not confirmed; do not redistribute the data or derived models.",
            file=sys.stderr,
        )
    print(download(args.name, entry, target_dir(args.name)))


if __name__ == "__main__":
    main()
