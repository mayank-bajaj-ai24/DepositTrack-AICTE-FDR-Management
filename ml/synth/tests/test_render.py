import json
import random

from fdrsynth import WATERMARK
from fdrsynth.__main__ import generate
from fdrsynth.render import HEIGHT, WIDTH, render
from fdrsynth.values import random_values

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


def test_render_labels_every_field():
    rendered = render(random_values(random.Random(3)), random.Random(3))
    labels = {w.label for w in rendered.words}
    assert FIELD_LABELS <= labels


def test_boxes_inside_image():
    rendered = render(random_values(random.Random(5)), random.Random(5))
    assert rendered.image.size == (WIDTH, HEIGHT)
    for word in rendered.words:
        x0, y0, x1, y1 = word.box
        assert 0 <= x0 < x1 <= WIDTH
        assert 0 <= y0 < y1 <= HEIGHT


def test_labelled_words_reassemble_the_value():
    values = random_values(random.Random(9))
    rendered = render(values, random.Random(9))
    ifsc = " ".join(w.text for w in rendered.words if w.label == "IFSC")
    words = " ".join(w.text for w in rendered.words if w.label == "AMOUNT_WORDS")
    assert ifsc == values.ifsc
    assert words == values.amount_words


def test_cli_writes_images_annotations_and_manifest(tmp_path):
    files = generate(3, tmp_path, seed=11, scan_effects=False)
    assert len(files) == 3
    assert len((tmp_path / "manifest.jsonl").read_text().splitlines()) == 3
    record = json.loads((tmp_path / "fdr_11_00000.json").read_text())
    assert record["synthetic"] is True
    assert record["watermark"] == WATERMARK
    assert record["words"]
