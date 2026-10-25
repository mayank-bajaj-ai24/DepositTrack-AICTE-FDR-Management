"""CLI: python -m fdrsynth --count 20 --out data/synthetic_fdr [--seed 7] [--no-scan-effects]
                          [--ifsc-dir data/open/ifsc] [--institutions data/open/aicte/...json]
                          [--placeholders path/to/placeholders.json]

Writes, per sample: <id>.png and <id>.json (values, layout, word boxes and labels), plus
manifest.jsonl (one line per sample) and mockbank.jsonl (each FDR as the issuing bank
records it, for the mock bank's POST /fdrs). Every page carries the SYNTHETIC mark.
"""

import argparse
import json
import random
from pathlib import Path

from fdrsynth import WATERMARK
from fdrsynth.catalog import DEFAULT_IFSC_DIR, DEFAULT_INSTITUTIONS, load_catalog
from fdrsynth.render import render
from fdrsynth.values import random_values


def generate(
    count: int,
    out: Path,
    seed: int,
    scan_effects: bool = True,
    ifsc_dir: Path = DEFAULT_IFSC_DIR,
    institutions: Path = DEFAULT_INSTITUTIONS,
    placeholders: Path | None = None,
) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    catalog = load_catalog(ifsc_dir, institutions, placeholders)
    rng = random.Random(seed)
    written: list[Path] = []
    with (
        open(out / "manifest.jsonl", "w", encoding="utf-8") as manifest,
        open(out / "mockbank.jsonl", "w", encoding="utf-8") as mockbank,
    ):
        for index in range(count):
            sample_id = f"fdr_{seed}_{index:05d}"
            values = random_values(rng, catalog)
            rendered = render(values, rng, scan_effects=scan_effects)
            image_path = out / f"{sample_id}.png"
            rendered.image.save(image_path)
            record = {
                "id": sample_id,
                "synthetic": True,
                "watermark": WATERMARK,
                "image": image_path.name,
                "layout": rendered.layout,
                "width": rendered.image.width,
                "height": rendered.image.height,
                "values": values.as_dict(),
                "words": [w.__dict__ for w in rendered.words],
            }
            (out / f"{sample_id}.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
            manifest.write(
                json.dumps({"id": sample_id, "image": image_path.name, "layout": rendered.layout})
                + "\n"
            )
            mockbank.write(json.dumps({"id": sample_id, **values.mockbank_record()}) + "\n")
            written.append(image_path)
    return written


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic FDR receipts.")
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--out", type=Path, default=Path("data/synthetic_fdr"))
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--no-scan-effects", action="store_true")
    parser.add_argument("--ifsc-dir", type=Path, default=DEFAULT_IFSC_DIR)
    parser.add_argument("--institutions", type=Path, default=DEFAULT_INSTITUTIONS)
    parser.add_argument(
        "--placeholders",
        type=Path,
        default=None,
        help="value ranges and wording (default: fdrsynth/data/placeholders.json)",
    )
    args = parser.parse_args(argv)
    files = generate(
        args.count,
        args.out,
        args.seed,
        scan_effects=not args.no_scan_effects,
        ifsc_dir=args.ifsc_dir,
        institutions=args.institutions,
        placeholders=args.placeholders,
    )
    print(f"Wrote {len(files)} synthetic FDRs to {args.out}")


if __name__ == "__main__":
    main()
