"""Measure field extraction (M3 pass B: RapidOCR + config rules) on synthetic FDRs.

Run with the API's virtual environment (it holds the OCR engine and the rules):

    apps/api/.venv/Scripts/python -m fdrsynth --count 300 --out data/synthetic_fdr/eval --seed 2027
    apps/api/.venv/Scripts/python ml/extraction/evaluate.py --data data/synthetic_fdr/eval

Writes <data>/extraction_metrics.json. Every number is a synthetic result: it shows how OCR and
the rules read generated FDRs, whose captions come from extraction.yaml. It is not a result on
real FDRs, which still needs labelled real scans.
"""

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.core.configfiles import load_config  # noqa: E402
from app.modules.extraction.ocr import run_ocr  # noqa: E402
from app.modules.extraction.rules import extract_fields  # noqa: E402

FIELDS = [
    "fdr_no",
    "bank",
    "branch",
    "ifsc",
    "amount",
    "amount_words",
    "issue_date",
    "maturity_date",
    "depositor",
    "beneficiary",
    "lien_text",
]
AMOUNT_AND_DATES = ["amount", "issue_date", "maturity_date"]


def expected_fields(values: dict) -> dict[str, str]:
    """A generated FDR's values in the normalised form extraction returns."""
    return {
        "fdr_no": values["fdr_no"].replace(" ", "").upper(),
        "bank": " ".join(values["bank"].split()),
        "branch": " ".join(values["branch"].split()),
        "ifsc": values["ifsc"].upper(),
        "amount": str(values["amount"]),
        "amount_words": " ".join(values["amount_words"].split()),
        "issue_date": values["deposit_date_iso"],
        "maturity_date": values["maturity_date_iso"],
        "depositor": " ".join(values["depositor"].split()),
        "beneficiary": " ".join(values["beneficiary"].split()),
        "lien_text": " ".join(values["lien_text"].split()),
    }


def score_page(expected: dict[str, str], extracted: dict[str, str]) -> dict[str, bool]:
    """Exact match per field after normalisation; a missing field counts as wrong."""
    return {name: extracted.get(name) == expected[name] for name in FIELDS}


def rate(hits: list[bool]) -> float | None:
    return round(sum(hits) / len(hits), 4) if hits else None


def summarise(pages: list[dict]) -> dict:
    by_field = {name: rate([p["match"][name] for p in pages]) for name in FIELDS}
    by_layout: dict[str, list[bool]] = {}
    for page in pages:
        by_layout.setdefault(page["layout"], []).extend(page["match"].values())
    seconds = sorted(p["seconds"] for p in pages)
    return {
        "pages": len(pages),
        "exact_match_overall": rate([hit for p in pages for hit in p["match"].values()]),
        "exact_match_amount_and_dates": rate(
            [p["match"][name] for p in pages for name in AMOUNT_AND_DATES]
        ),
        "pages_all_fields_correct": rate([all(p["match"].values()) for p in pages]),
        "exact_match_by_field": by_field,
        "exact_match_by_layout": {k: rate(v) for k, v in sorted(by_layout.items())},
        "seconds_per_page_mean": round(statistics.fmean(seconds), 3) if seconds else None,
        "seconds_per_page_median": round(statistics.median(seconds), 3) if seconds else None,
        "seconds_per_page_p95": round(seconds[int(0.95 * (len(seconds) - 1))], 3)
        if seconds
        else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--show-misses", type=int, default=15)
    args = parser.parse_args()

    rules = load_config("extraction.yaml")
    records = sorted(p for p in args.data.glob("*.json") if p.name != "extraction_metrics.json")
    records = records[: args.limit] if args.limit else records
    if not records:
        raise SystemExit(f"No generated FDRs in {args.data}: run python -m fdrsynth first")
    # The first OCR call loads the models; keep it out of the per-page timing.
    run_ocr(Image.open(records[0].with_suffix(".png")).convert("RGB"))

    pages, misses = [], []
    for index, path in enumerate(records):
        record = json.loads(path.read_text(encoding="utf-8"))
        if not record.get("synthetic"):
            raise SystemExit(f"{path} is not marked synthetic; refusing to report it as such")
        image = Image.open(path.with_suffix(".png")).convert("RGB")
        start = time.perf_counter()
        extracted = {k: v.normalized for k, v in extract_fields(run_ocr(image), rules).items()}
        seconds = time.perf_counter() - start
        expected = expected_fields(record["values"])
        match = score_page(expected, extracted)
        pages.append({"layout": record["layout"], "match": match, "seconds": seconds})
        for name, ok in match.items():
            if not ok and len(misses) < args.show_misses:
                misses.append(
                    {
                        "id": record["id"],
                        "field": name,
                        "expected": expected[name],
                        "got": extracted.get(name),
                    }
                )
        if index % 50 == 0:
            print(f"  {index} pages", flush=True)

    metrics = {
        "data": "synthetic",
        "note": "Synthetic FDRs from ml/synthetic_fdr; captions from extraction.yaml. "
        "Not a result on real FDRs.",
        "method": "RapidOCR + extraction.yaml rules (pass B); pass A off",
        **summarise(pages),
        "examples_of_misses": misses,
    }
    (args.data / "extraction_metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
