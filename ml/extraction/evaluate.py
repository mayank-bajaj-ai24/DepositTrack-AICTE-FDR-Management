"""Measure field extraction (M3: RapidOCR + rules, pass A if on) on synthetic FDRs.

Run with the API's virtual environment (it holds the OCR engine and the rules):

    apps/api/.venv/Scripts/python -m fdrsynth --count 300 --out data/synthetic_fdr/eval --seed 2027
    apps/api/.venv/Scripts/python ml/extraction/evaluate.py --data data/synthetic_fdr/eval

Each page goes through the API's own entry point, `service.extract` (OCR, both passes, the
forgery score), and is scored on the value the API stores, so the time and accuracy follow
what the API does. Writes <data>/extraction_metrics.json.

Every number is a synthetic result: it shows how OCR and the rules read generated FDRs, whose
captions come from extraction.yaml. It is not a result on real FDRs, which still needs
labelled real scans.
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
from app.modules.extraction import service  # noqa: E402
from app.modules.extraction.ocr import run_ocr  # noqa: E402
from app.modules.extraction.rules import _normalize  # noqa: E402

FIELDS = list(service.FIELDS)
RULES = load_config("extraction.yaml")
# Generator value key per field, for the fields whose printed text is normalised as is.
PRINTED = {
    "fdr_no": "fdr_no",
    "bank": "bank",
    "branch": "branch",
    "ifsc": "ifsc",
    "amount_words": "amount_words",
    "depositor": "depositor",
    "beneficiary": "beneficiary",
    "lien_text": "lien_text",
}
AMOUNT_AND_DATES = ["amount", "issue_date", "maturity_date"]


def expected_fields(values: dict) -> dict[str, str]:
    """A generated FDR's values in the form extraction returns: text fields through the
    extractor's own normalisation, amount and dates from the generator's true values."""
    expected = {name: _normalize(name, values[key], RULES) for name, key in PRINTED.items()}
    expected["amount"] = str(values["amount"])
    expected["issue_date"] = values["deposit_date_iso"]
    expected["maturity_date"] = values["maturity_date_iso"]
    return expected


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
        # Nearest rank: the smallest time that at least 95% of pages do not exceed.
        "seconds_per_page_p95": round(seconds[-(-95 * len(seconds) // 100) - 1], 3)
        if seconds
        else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--show-misses", type=int, default=15)
    parser.add_argument(
        "--models-dir", type=Path, default=ROOT / "models", help="as the API's DT_MODELS_DIR"
    )
    args = parser.parse_args()

    records = sorted(args.data.glob("fdr_*.json"))[: args.limit]
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
        result = service.extract(image, RULES, str(args.models_dir))
        extracted = {k: f.value for k, f in result.fields.items() if f.value}
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
        "method": "service.extract: RapidOCR + extraction.yaml rules (pass B)"
        + ("; pass A on" if RULES.get("pass_a_enabled") else "; pass A off"),
        **summarise(pages),
        "examples_of_misses": misses,
    }
    (args.data / "extraction_metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
