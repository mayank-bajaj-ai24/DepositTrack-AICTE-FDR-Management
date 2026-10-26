"""CLI: python -m fdrsynth --count 20 [--out data/synthetic_fdr] [--seed 7] [--no-scan-effects]
                          [--overwrite] [--ifsc-dir data/open/ifsc]
                          [--institutions data/open/aicte/institutions_<year>.json]
                          [--api-config apps/api/config] [--placeholders path/to/placeholders.json]

Writes, per sample: <id>.png and <id>.json (values, layout, words with field label, B-/I-
tag, word box and line box), plus manifest.jsonl (one line per sample), mockbank.jsonl (each
FDR as the issuing bank records it, for the mock bank's POST /fdrs) and labels.json (the tag
list to train with). Every page carries the SYNTHETIC mark. Paths default to the DepositTrack
checkout: the output to the git-ignored data/synthetic_fdr/ at the repo root.

Each sample draws its values and its rendering from two random streams seeded by
(seed, sample index), so `--no-scan-effects` or a change to the rendering never changes the
values of an FDR with the same id.
"""

import argparse
import dataclasses
import json
import random
from pathlib import Path

from fdrsynth import WATERMARK
from fdrsynth.catalog import Catalog, load_catalog, repo_root
from fdrsynth.labels import bio_tags, label_list
from fdrsynth.render import BRANCH_ROOM, fits, render
from fdrsynth.values import branch_text, random_values

OUTPUTS = ("manifest.jsonl", "mockbank.jsonl", "labels.json")


def printable(catalog: Catalog) -> Catalog:
    """Leave out institutions and branches whose name cannot fit on one line of the page."""
    institutions = tuple(i for i in catalog.institutions if fits(i.name))
    branches = tuple(b for b in catalog.branches if fits(branch_text(b), BRANCH_ROOM))
    if not institutions or not branches:
        raise ValueError("no institution or branch name fits on the page")
    return dataclasses.replace(catalog, institutions=institutions, branches=branches)


def _clear(out: Path, overwrite: bool) -> None:
    """Refuse to mix two runs in one folder; with overwrite, remove the earlier run's files."""
    earlier = [p for p in out.glob("fdr_*") if p.suffix in (".png", ".json")]
    earlier += [out / name for name in OUTPUTS if (out / name).exists()]
    if not earlier:
        return
    if not overwrite:
        raise FileExistsError(
            f"{out} already holds generated FDRs: choose another --out or pass --overwrite"
        )
    for path in earlier:
        path.unlink()


def generate(
    count: int,
    out: Path | None = None,
    seed: int = 7,
    scan_effects: bool = True,
    ifsc_dir: Path | None = None,
    institutions: Path | None = None,
    placeholders: Path | None = None,
    api_config: Path | None = None,
    overwrite: bool = False,
) -> list[Path]:
    if count < 1:
        raise ValueError("count must be at least 1")
    out = out or repo_root() / "data" / "synthetic_fdr"
    catalog = printable(load_catalog(ifsc_dir, institutions, placeholders, api_config))
    out.mkdir(parents=True, exist_ok=True)
    _clear(out, overwrite)
    (out / "labels.json").write_text(json.dumps(label_list(catalog.fields)), encoding="utf-8")
    written: list[Path] = []
    with (
        open(out / "manifest.jsonl", "w", encoding="utf-8") as manifest,
        open(out / "mockbank.jsonl", "w", encoding="utf-8") as mockbank,
    ):
        for index in range(count):
            sample_id = f"fdr_{seed}_{index:05d}"
            values = random_values(random.Random(f"{seed}/{index}/values"), catalog)
            rendered = render(
                values,
                random.Random(f"{seed}/{index}/render"),
                catalog.captions,
                scan_effects=scan_effects,
            )
            image_path = out / f"{sample_id}.png"
            # Level 1: the scan noise barely compresses, and level 6 takes ~5x as long.
            rendered.image.save(image_path, compress_level=1)
            tags = bio_tags([w.label for w in rendered.words])
            record = {
                "id": sample_id,
                "synthetic": True,
                "watermark": WATERMARK,
                "image": image_path.name,
                "layout": rendered.layout,
                "width": rendered.image.width,
                "height": rendered.image.height,
                "values": values.as_dict(),
                "words": [
                    {**dataclasses.asdict(w), "tag": tag}
                    for w, tag in zip(rendered.words, tags, strict=True)
                ],
            }
            (out / f"{sample_id}.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
            manifest.write(
                json.dumps({"id": sample_id, "image": image_path.name, "layout": rendered.layout})
                + "\n"
            )
            mockbank.write(json.dumps({"id": sample_id, **values.mockbank_record()}) + "\n")
            written.append(image_path)
    return written


def _positive(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return value


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic FDR receipts.")
    parser.add_argument("--count", type=_positive, default=20)
    parser.add_argument("--out", type=Path, default=None, help="default: <repo>/data/synthetic_fdr")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--no-scan-effects", action="store_true")
    parser.add_argument("--overwrite", action="store_true", help="replace an earlier run in --out")
    parser.add_argument(
        "--ifsc-dir", type=Path, default=None, help="default: <repo>/data/open/ifsc"
    )
    parser.add_argument(
        "--institutions",
        type=Path,
        default=None,
        help="default: the AICTE snapshot for master_data.yaml's academic year",
    )
    parser.add_argument(
        "--api-config", type=Path, default=None, help="default: <repo>/apps/api/config"
    )
    parser.add_argument(
        "--placeholders",
        type=Path,
        default=None,
        help="value ranges and wording (default: fdrsynth/data/placeholders.json)",
    )
    args = parser.parse_args(argv)
    try:
        files = generate(
            args.count,
            args.out,
            args.seed,
            scan_effects=not args.no_scan_effects,
            ifsc_dir=args.ifsc_dir,
            institutions=args.institutions,
            placeholders=args.placeholders,
            api_config=args.api_config,
            overwrite=args.overwrite,
        )
    except (FileExistsError, FileNotFoundError, ValueError) as exc:
        parser.exit(2, f"fdrsynth: {exc}\n")
    print(f"Wrote {len(files)} synthetic FDRs to {files[0].parent}")


if __name__ == "__main__":
    main()
