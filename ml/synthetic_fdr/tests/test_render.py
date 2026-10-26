import hashlib
import json
import random

import pytest

from fdrsynth import WATERMARK
from fdrsynth.__main__ import generate, main, printable
from fdrsynth.catalog import Institution
from fdrsynth.labels import bio_tags, label_list
from fdrsynth.render import HEIGHT, LAYOUTS, WIDTH, fits, render
from fdrsynth.values import random_values
from tests.conftest import FIXTURES, INSTITUTIONS, RULES

FIELD_LABELS = {name.upper() for name in RULES["fields"]}


def _render(catalog, seed, **kw):
    values = random_values(random.Random(seed), catalog)
    return values, render(values, random.Random(seed), catalog.captions, **kw)


@pytest.mark.parametrize("layout", LAYOUTS)
def test_every_layout_labels_every_field(catalog, layout):
    _, rendered = _render(catalog, 3, layout=layout)
    assert FIELD_LABELS <= {w.label for w in rendered.words}


@pytest.mark.parametrize("layout", LAYOUTS)
def test_every_layout_carries_the_mark_in_both_banners(catalog, layout):
    _, rendered = _render(catalog, 4, layout=layout)
    text = " ".join(w.text for w in rendered.words)
    assert text.count(WATERMARK) == 2


def test_diagonal_mark_crosses_the_field_rows(catalog):
    values = random_values(random.Random(4), catalog)
    rendered = render(values, random.Random(4), catalog.captions, scan_effects=False)
    fields = [w.box for w in rendered.words if w.label != "O"]
    top = min(b[1] for b in fields if b[1] > 200)
    bottom = max(b[3] for b in fields if b[3] < 700)
    reddish = [
        y
        for y in range(top, bottom, 4)
        for x in range(100, WIDTH - 100, 8)
        if (lambda p: p[0] - p[2] > 20)(rendered.image.getpixel((x, y)))
    ]
    assert reddish and min(reddish) < (top + bottom) / 2 < max(reddish)


def test_captions_on_the_page_are_the_extractors(catalog):
    _, rendered = _render(catalog, 6, layout="classic", scan_effects=False)
    text = " ".join(w.text for w in rendered.words)
    for label in ("FDR_NO", "DEPOSITOR", "AMOUNT"):
        assert any(caption in text for caption in catalog.captions[label])


@pytest.mark.parametrize("scan_effects", [False, True])
def test_boxes_inside_image(catalog, scan_effects):
    for seed in range(6):
        _, rendered = _render(catalog, seed, scan_effects=scan_effects)
        assert rendered.image.size == (WIDTH, HEIGHT)
        for word in rendered.words:
            for x0, y0, x1, y1 in (word.box, word.line_box):
                assert 0 <= x0 < x1 <= WIDTH
                assert 0 <= y0 < y1 <= HEIGHT


def test_a_name_too_long_for_the_page_is_left_out(catalog):
    long_name = "JNAN VIKAS MANDALS " * 8
    assert not fits(long_name)
    wide = catalog.__class__(
        **{
            **catalog.__dict__,
            "institutions": (*catalog.institutions, Institution("1-x", long_name)),
        }
    )
    assert long_name not in {i.name for i in printable(wide).institutions}


def test_line_box_holds_the_word_and_its_neighbours(catalog):
    _, rendered = _render(catalog, 8, scan_effects=False)
    amount = [w for w in rendered.words if w.label == "AMOUNT_WORDS"]
    assert len({tuple(w.line_box) for w in amount}) == 1
    x0, y0, x1, y1 = amount[0].line_box
    assert all(x0 <= w.box[0] and w.box[2] <= x1 and y0 <= w.box[1] for w in amount)
    assert x1 - x0 > amount[0].box[2] - amount[0].box[0]


def test_labelled_words_reassemble_the_value(catalog):
    values, rendered = _render(catalog, 9)
    for label, expected in [
        ("IFSC", values.ifsc),
        ("AMOUNT_WORDS", values.amount_words),
        ("DEPOSITOR", values.depositor),
        ("MATURITY_DATE", values.maturity_date),
    ]:
        assert " ".join(w.text for w in rendered.words if w.label == label) == expected


def test_bio_tags_and_label_list():
    assert bio_tags(["O", "BANK", "BANK", "O", "IFSC"]) == ["O", "B-BANK", "I-BANK", "O", "B-IFSC"]
    assert label_list(["BANK", "IFSC"]) == ["O", "B-BANK", "I-BANK", "B-IFSC", "I-IFSC"]


def _run(tmp_path, name, **kw):
    out = tmp_path / name
    files = generate(3, out, seed=11, ifsc_dir=FIXTURES, institutions=INSTITUTIONS, **kw)
    return out, files


def test_cli_writes_images_annotations_manifest_mockbank_and_labels(tmp_path):
    out, files = _run(tmp_path, "a", scan_effects=False)
    assert len(files) == 3
    assert len((out / "manifest.jsonl").read_text().splitlines()) == 3
    record = json.loads((out / "fdr_11_00000.json").read_text())
    assert record["synthetic"] is True
    assert record["watermark"] == WATERMARK
    assert record["layout"] in LAYOUTS
    tags = [w["tag"] for w in record["words"]]
    assert set(tags) <= set(json.loads((out / "labels.json").read_text()))
    assert "B-FDR_NO" in tags
    bank = json.loads((out / "mockbank.jsonl").read_text().splitlines()[0])
    assert bank["id"] == "fdr_11_00000"
    assert bank["fdr_no"] == record["values"]["fdr_no"]
    assert bank["issue_date"] == record["values"]["deposit_date_iso"]


def _hashes(out):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir())}


def test_same_seed_gives_the_same_files(tmp_path):
    assert _hashes(_run(tmp_path, "a")[0]) == _hashes(_run(tmp_path, "b")[0])


def test_scan_effects_do_not_change_the_values(tmp_path):
    scanned, _ = _run(tmp_path, "a")
    clean, _ = _run(tmp_path, "b", scan_effects=False)
    assert (scanned / "mockbank.jsonl").read_text() == (clean / "mockbank.jsonl").read_text()


def test_a_second_run_into_the_same_folder_is_refused_or_replaces_it(tmp_path):
    out, _ = _run(tmp_path, "a")
    with pytest.raises(FileExistsError, match="--overwrite"):
        generate(1, out, seed=11, ifsc_dir=FIXTURES, institutions=INSTITUTIONS)
    generate(1, out, seed=11, ifsc_dir=FIXTURES, institutions=INSTITUTIONS, overwrite=True)
    assert sorted(p.name for p in out.glob("fdr_*.json")) == ["fdr_11_00000.json"]


def test_default_output_is_the_repo_root_data_folder(monkeypatch, tmp_path):
    import fdrsynth.__main__ as cli

    monkeypatch.setattr(cli, "repo_root", lambda: tmp_path)
    files = generate(1, seed=3, ifsc_dir=FIXTURES, institutions=INSTITUTIONS)
    assert files[0].parent == tmp_path / "data" / "synthetic_fdr"


@pytest.mark.parametrize("count", ["0", "-5"])
def test_count_must_be_positive(count, capsys):
    with pytest.raises(SystemExit):
        main(["--count", count])
    assert "at least 1" in capsys.readouterr().err
