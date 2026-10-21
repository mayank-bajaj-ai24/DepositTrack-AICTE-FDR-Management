"""CLI: python -m fdrsynth --count 20 --out data/synthetic [--seed 7] [--no-scan-effects]

Writes, per sample: <id>.png, <id>.json (values + word boxes + labels), and a
manifest.jsonl index. All outputs are synthetic and watermarked.
"""

import argparse
import json
import random
from pathlib import Path

from fdrsynth import WATERMARK
from fdrsynth.render import render
from fdrsynth.values import random_values


def generate(count: int, out: Path, seed: int, scan_effects: bool = True) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    written: list[Path] = []
    with open(out / "manifest.jsonl", "w", encoding="utf-8") as manifest:
        for index in range(count):
            sample_id = f"fdr_{seed}_{index:05d}"
            values = random_values(rng)
            rendered = render(values, rng, scan_effects=scan_effects)
            image_path = out / f"{sample_id}.png"
            rendered.image.save(image_path)
            record = {
                "id": sample_id,
                "synthetic": True,
                "watermark": WATERMARK,
                "image": image_path.name,
                "width": rendered.image.width,
                "height": rendered.image.height,
                "values": values.as_dict(),
                "words": [w.__dict__ for w in rendered.words],
            }
            (out / f"{sample_id}.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
            manifest.write(json.dumps({"id": sample_id, "image": image_path.name}) + "\n")
            written.append(image_path)
    return written


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic FDR receipts.")
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--out", type=Path, default=Path("data/synthetic"))
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--no-scan-effects", action="store_true")
    args = parser.parse_args(argv)
    files = generate(args.count, args.out, args.seed, scan_effects=not args.no_scan_effects)
    print(f"Wrote {len(files)} synthetic FDRs to {args.out}")


if __name__ == "__main__":
    main()
