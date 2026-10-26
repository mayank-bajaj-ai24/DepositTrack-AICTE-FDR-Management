"""Render a synthetic FDR receipt with word-level annotations for LayoutLMv3 (M3).

Each word has a field label, the extraction field in upper case (FDR_NO, BANK, BRANCH, IFSC,
AMOUNT, AMOUNT_WORDS, ISSUE_DATE, MATURITY_DATE, BENEFICIARY, DEPOSITOR, LIEN_TEXT) or O;
fdrsynth.labels turns these into the B-/I- tags the API's pass A expects. Each word also has
its line's box: at inference the API gives every token its whole OCR line's box, so a model
should be trained on `line_box`, while `box` (the word alone) is what tampering edits. Boxes
are [x0, y0, x1, y1] in pixels, inside the image.

Layouts imitate the common structure of an FDR (bank header, captioned rows, amount in
words, lien line, signatory) with no bank's logo or branding. Captions come from the caption
lists in apps/api/config/extraction.yaml (catalog.captions), so a result on these pages
measures OCR plus rules on known wording, not robustness to unseen wording.

The SYNTHETIC mark is printed three times: banners at the top and bottom, and a light
diagonal across the field rows, so that no crop keeps the fields without the mark. The
diagonal is not a labelled word.
"""

import math
import random
from dataclasses import dataclass, field
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from fdrsynth import WATERMARK
from fdrsynth.values import FDRValues

WIDTH, HEIGHT = 1400, 900
MARGIN = 70
INK = (20, 20, 30)
MARK = (190, 30, 30)
TITLES = ["FIXED DEPOSIT RECEIPT", "TERM DEPOSIT RECEIPT", "FIXED DEPOSIT ADVICE"]

# Value attribute of each captioned row, in the classic layout's order.
ROWS = {
    "FDR_NO": "fdr_no",
    "DEPOSITOR": "depositor",
    "BENEFICIARY": "beneficiary",
    "AMOUNT": "amount_text",
    "ISSUE_DATE": "deposit_date",
    "MATURITY_DATE": "maturity_date",
}
CLASSIC_VALUE_X = 440
BRANCH_ROOM = 760
SMALLEST = 14
# The narrowest value column of any layout (classic); a longer value is left out of the
# catalog rather than cut off at the page edge (see fits).
VALUE_ROOM = WIDTH - MARGIN - CLASSIC_VALUE_X


@dataclass
class Word:
    text: str
    box: list[int]
    label: str
    line_box: list[int] = field(default_factory=list)


@dataclass
class Rendered:
    image: Image.Image
    layout: str
    words: list[Word] = field(default_factory=list)


@lru_cache
def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.load_default(size=size)


_MEASURE = ImageDraw.Draw(Image.new("RGB", (1, 1)))


def text_width(text: str, size: int) -> float:
    return _MEASURE.textlength(text, font=_font(size))


def fits(text: str, room: float = VALUE_ROOM) -> bool:
    """True when `text` fits on one line in `room` pixels at the smallest size used."""
    return text_width(text, SMALLEST) <= room


class Page:
    def __init__(self, rng: random.Random):
        paper = rng.randint(240, 252)
        self.image = Image.new("RGB", (WIDTH, HEIGHT), (paper, paper, paper - rng.randint(0, 8)))
        self.draw = ImageDraw.Draw(self.image)
        self.words: list[Word] = []

    def fit(self, text: str, size: int, room: float) -> int:
        """Largest size <= `size` at which `text` fits in `room` pixels (one OCR line)."""
        while size > SMALLEST and text_width(text, size) > room:
            size -= 1
        return size

    def text(self, x: float, y: float, text: str, label: str, size: int, fill=INK) -> int:
        """Draw text word by word, record each word's box, return the x after the last word."""
        font = _font(size)
        space = self.draw.textlength(" ", font=font)
        for token in text.split():
            x0, y0, x1, y1 = self.draw.textbbox((x, y), token, font=font)
            self.draw.text((x, y), token, fill=fill, font=font)
            self.words.append(Word(token, [int(x0), int(y0), int(x1), int(y1)], label))
            x = x1 + space
        return int(x)

    def mark(self) -> None:
        """Banners at the top and bottom of every page."""
        for y in (18, HEIGHT - 48):
            size = 26
            x = (WIDTH - text_width(WATERMARK, size)) / 2
            self.text(x, y, WATERMARK, "O", size, fill=MARK)

    def diagonal_mark(self, rng: random.Random) -> None:
        """A light, unlabelled mark across the field rows (y ~ 250-700)."""
        font = _font(64)
        left, top, right, bottom = self.draw.textbbox((0, 0), WATERMARK, font=font)
        stamp = Image.new("L", (right - left + 20, bottom - top + 20), 0)
        ImageDraw.Draw(stamp).text((10 - left, 10 - top), WATERMARK, fill=255, font=font)
        stamp = stamp.rotate(rng.uniform(14, 20), expand=True, resample=Image.BILINEAR)
        alpha = stamp.point(lambda v: v * 25 // 255)
        x = (WIDTH - stamp.width) // 2
        y = 470 - stamp.height // 2
        self.image.paste(Image.new("RGB", stamp.size, MARK), (x, y), alpha)

    def signatory(self, rng: random.Random) -> None:
        x, y = WIDTH - 380, HEIGHT - 150
        points = [(x + i * 12, y + rng.randint(-10, 10)) for i in range(18)]
        self.draw.line(points, fill=(30, 40, 110), width=2)
        self.text(x, y + 30, "Authorised Signatory", "O", 22)


def _caption(captions: dict, rng: random.Random, label: str) -> str:
    return rng.choice(captions[label])


def _header(page: Page, values: FDRValues, captions: dict, rng: random.Random) -> int:
    size = page.fit(values.bank, 40, WIDTH - 2 * MARGIN)
    page.text(MARGIN, 70, values.bank, "BANK", size)
    page.text(MARGIN, 125, values.branch, "BRANCH", page.fit(values.branch, 24, BRANCH_ROOM))
    x = page.text(WIDTH - 420, 125, f"{_caption(captions, rng, 'IFSC')}:", "O", 24)
    page.text(x, 125, values.ifsc, "IFSC", 24)
    page.draw.line([(MARGIN, 165), (WIDTH - MARGIN, 165)], fill=(90, 90, 110), width=2)
    page.text(MARGIN, 185, rng.choice(TITLES), "O", 32)
    return 250


def _footer(page: Page, values: FDRValues, y: int, rng: random.Random) -> None:
    page.text(MARGIN, y, "Amount in words:", "O", 22)
    words_size = page.fit(values.amount_words, 22, WIDTH - 2 * MARGIN)
    page.text(MARGIN, y + 35, values.amount_words, "AMOUNT_WORDS", words_size)
    page.text(MARGIN, y + 85, values.lien_text, "LIEN_TEXT", 22)
    page.signatory(rng)


def _rows(page, values, captions, rng, labels, y, inline: bool) -> int:
    """Captioned rows, one per label: the value in a column, or after "Caption:" (inline)."""
    for label in labels:
        value = getattr(values, ROWS[label])
        if inline:
            x = page.text(MARGIN, y, f"{_caption(captions, rng, label)}:", "O", 24)
        else:
            page.text(MARGIN, y, _caption(captions, rng, label), "O", 24)
            x = CLASSIC_VALUE_X
        page.text(x, y, value, label, page.fit(value, 24, WIDTH - MARGIN - x))
        y += 52
    return y


def _classic(page: Page, values: FDRValues, captions: dict, rng: random.Random) -> None:
    y = _header(page, values, captions, rng)
    y = _rows(page, values, captions, rng, list(ROWS), y, inline=False)
    _footer(page, values, y + 15, rng)


def _two_column(page: Page, values: FDRValues, captions: dict, rng: random.Random) -> None:
    y = _header(page, values, captions, rng)
    half = WIDTH // 2
    for left, right in (("FDR_NO", "ISSUE_DATE"), ("AMOUNT", "MATURITY_DATE")):
        page.text(MARGIN, y, _caption(captions, rng, left), "O", 24)
        page.text(MARGIN + 260, y, getattr(values, ROWS[left]), left, 24)
        page.text(half + 40, y, _caption(captions, rng, right), "O", 24)
        page.text(half + 300, y, getattr(values, ROWS[right]), right, 24)
        y += 56
    for label in ("DEPOSITOR", "BENEFICIARY"):
        page.text(MARGIN, y, _caption(captions, rng, label), "O", 24)
        value = getattr(values, ROWS[label])
        page.text(MARGIN + 260, y, value, label, page.fit(value, 24, WIDTH - 2 * MARGIN - 260))
        y += 56
    page.draw.rectangle([MARGIN - 15, 240, WIDTH - MARGIN + 15, y], outline=(90, 90, 110))
    _footer(page, values, y + 25, rng)


def _inline(page: Page, values: FDRValues, captions: dict, rng: random.Random) -> None:
    """Caption and value on one line ("Deposit No: 1234"); extraction strips the caption."""
    y = _header(page, values, captions, rng)
    order = ["FDR_NO", "AMOUNT", "ISSUE_DATE", "MATURITY_DATE", "DEPOSITOR", "BENEFICIARY"]
    y = _rows(page, values, captions, rng, order, y, inline=True)
    _footer(page, values, y + 15, rng)


LAYOUTS = {"classic": _classic, "two_column": _two_column, "inline": _inline}


def _line_boxes(words: list[Word]) -> None:
    """Give each word the box of its text line, the way an OCR engine groups words: the same
    row, and a gap to the previous word of less than about one word height."""
    line: list[Word] = []

    def close():
        if line:
            box = [
                min(w.box[0] for w in line),
                min(w.box[1] for w in line),
                max(w.box[2] for w in line),
                max(w.box[3] for w in line),
            ]
            for w in line:
                w.line_box = list(box)

    for word in words:
        if line:
            last = line[-1]
            height = last.box[3] - last.box[1]
            same_row = abs((word.box[1] + word.box[3]) - (last.box[1] + last.box[3])) < height
            if same_row and 0 <= word.box[0] - last.box[2] < 1.2 * height:
                line.append(word)
                continue
            close()
        line = [word]
    close()


def _rotate_box(box, angle_deg: float, centre) -> list[int]:
    cx, cy = centre
    a = math.radians(-angle_deg)  # PIL rotates counter-clockwise for positive angles
    corners = [(box[0], box[1]), (box[2], box[1]), (box[0], box[3]), (box[2], box[3])]
    xs, ys = [], []
    for x, y in corners:
        dx, dy = x - cx, y - cy
        xs.append(cx + dx * math.cos(a) - dy * math.sin(a))
        ys.append(cy + dx * math.sin(a) + dy * math.cos(a))
    return clamp([math.floor(min(xs)), math.floor(min(ys)), math.ceil(max(xs)), math.ceil(max(ys))])


def clamp(box) -> list[int]:
    """The box inside the image, at least one pixel wide and high."""
    x0 = min(max(0, int(box[0])), WIDTH - 1)
    y0 = min(max(0, int(box[1])), HEIGHT - 1)
    x1 = min(WIDTH, max(x0 + 1, int(box[2])))
    y1 = min(HEIGHT, max(y0 + 1, int(box[3])))
    return [x0, y0, x1, y1]


def _noise(size: tuple[int, int], sigma: float, rng: random.Random) -> Image.Image:
    """Grey noise around 128 from `rng`, so the same seed gives the same pixels everywhere
    (Pillow's effect_noise uses an unseeded C generator)."""
    frame = Image.frombytes("L", size, rng.randbytes(size[0] * size[1]))
    # Uniform 0-255 has a standard deviation of ~74; scale it to `sigma`.
    return frame.point(lambda v: round(128 + (v - 127.5) * sigma / 74)).convert("RGB")


def _scan_effects(rendered: Rendered, rng: random.Random) -> None:
    """Scan artefacts: a slight skew (boxes moved with it), blur and noise."""
    image = rendered.image
    angle = rng.uniform(-1.0, 1.0)
    fill = image.getpixel((5, 5))
    # BILINEAR: under a degree of skew it looks the same as BICUBIC after blur and noise.
    image = image.rotate(angle, resample=Image.BILINEAR, fillcolor=fill)
    for word in rendered.words:
        word.box = _rotate_box(word.box, angle, (WIDTH / 2, HEIGHT / 2))
        word.line_box = _rotate_box(word.line_box, angle, (WIDTH / 2, HEIGHT / 2))
    if rng.random() < 0.5:
        image = image.filter(ImageFilter.GaussianBlur(radius=rng.uniform(0.3, 0.8)))
    noise = _noise(image.size, rng.uniform(4, 12), rng)
    rendered.image = Image.blend(image, noise, alpha=rng.uniform(0.02, 0.06))


def render(
    values: FDRValues,
    rng: random.Random,
    captions: dict[str, tuple[str, ...]],
    scan_effects: bool = True,
    layout: str | None = None,
) -> Rendered:
    layout = layout or rng.choice(list(LAYOUTS))
    page = Page(rng)
    # The diagonal goes on first, so the text is drawn over it and keeps its full contrast.
    page.diagonal_mark(rng)
    page.mark()
    LAYOUTS[layout](page, values, captions, rng)
    page.draw.rectangle([10, 10, WIDTH - 10, HEIGHT - 10], outline=(60, 60, 90), width=3)
    for word in page.words:
        word.box = clamp(word.box)
    _line_boxes(page.words)
    rendered = Rendered(image=page.image, layout=layout, words=page.words)
    if scan_effects:
        _scan_effects(rendered, rng)
    return rendered
