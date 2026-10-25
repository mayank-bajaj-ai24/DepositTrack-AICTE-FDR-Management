import json
import random

import pytest

from fdrsynth import WATERMARK
from fdrsynth.__main__ import generate
from fdrsynth.render import HEIGHT, LAYOUTS, WIDTH, render
from fdrsynth.values import random_values
from tests.conftest import FIXTURES, INSTITUTIONS

FIELD_LABELS = {
    "FDR_NO",
    "BANK",
    "BRANCH",
    "IFSC",
    "AMOUNT",
    "AMOUNT_WORDS",
    "ISSUE_DATE",
    "MATURITY_DATE",
    "BENEFICIARY",
    "DEPOSITOR",
    "LIEN_TEXT",
}


@pytest.mark.parametrize("layout", LAYOUTS)
def test_every_layout_labels_every_field(catalog, layout):
    rendered = render(random_values(random.Random(3), catalog), random.Random(3), layout=layout)
    assert FIELD_LABELS <= {w.label for w in rendered.words}


@pytest.mark.parametrize("layout", LAYOUTS)
def test_every_layout_carries_the_mark_twice(catalog, layout):
    rendered = render(random_values(random.Random(4), catalog), random.Random(4), layout=layout)
    text = " ".join(w.text for w in rendered.words)
    assert text.count(WATERMARK) == 2


@pytest.mark.parametrize("scan_effects", [False, True])
def test_boxes_inside_image(catalog, scan_effects):
    for seed in range(6):
        values = random_values(random.Random(seed), catalog)
        rendered = render(values, random.Random(seed), scan_effects=scan_effects)
        assert rendered.image.size == (WIDTH, HEIGHT)
        for word in rendered.words:
            x0, y0, x1, y1 = word.box
            assert 0 <= x0 < x1 <= WIDTH
            assert 0 <= y0 < y1 <= HEIGHT


def test_labelled_words_reassemble_the_value(catalog):
    values = random_values(random.Random(9), catalog)
    rendered = render(values, random.Random(9))
    for label, expected in [
        ("IFSC", values.ifsc),
        ("AMOUNT_WORDS", values.amount_words),
        ("DEPOSITOR", values.depositor),
        ("MATURITY_DATE", values.maturity_date),
    ]:
        assert " ".join(w.text for w in rendered.words if w.label == label) == expected


def test_cli_writes_images_annotations_manifest_and_mockbank_file(tmp_path):
    files = generate(3, tmp_path, seed=11, scan_effects=False, ifsc_dir=FIXTURES,
                     institutions=INSTITUTIONS)  # fmt: skip
    assert len(files) == 3
    assert len((tmp_path / "manifest.jsonl").read_text().splitlines()) == 3
    record = json.loads((tmp_path / "fdr_11_00000.json").read_text())
    assert record["synthetic"] is True
    assert record["watermark"] == WATERMARK
    assert record["layout"] in LAYOUTS
    assert record["words"]
    bank = json.loads((tmp_path / "mockbank.jsonl").read_text().splitlines()[0])
    assert bank["id"] == "fdr_11_00000"
    assert bank["fdr_no"] == record["values"]["fdr_no"]
    assert bank["issue_date"] == record["values"]["deposit_date_iso"]
