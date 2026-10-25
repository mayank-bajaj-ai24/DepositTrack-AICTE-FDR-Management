"""Render a synthetic FDR receipt with word-level annotations for LayoutLMv3 (M3).

Labels are the extraction fields in upper case (apps/api/config/extraction.yaml): FDR_NO,
BANK, BRANCH, IFSC, AMOUNT, AMOUNT_WORDS, ISSUE_DATE, MATURITY_DATE, BENEFICIARY, DEPOSITOR,
LIEN_TEXT. Words outside a field are labelled O. Boxes are [x0, y0, x1, y1] in pixels.

Layouts imitate the common structure of an FDR (bank header, captioned rows, amount in
words, lien line, signatory) with no bank's logo or branding. Captions are drawn from the
caption lists in extraction.yaml, so a result on these pages measures OCR plus rules on known
wording, not robustness to unseen wording.
"""

import math
import random
from dataclasses import dataclass, field

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from fdrsynth import WATERMARK
from fdrsynth.values import FDRValues

WIDTH, HEIGHT = 1400, 900
MARGIN = 70
INK = (20, 20, 30)
MARK = (190, 30, 30)
LAYOUTS = ("classic", "two_column", "inline")

CAPTIONS = {
    "FDR_NO": ["FDR No.", "FDR Number", "Receipt No.", "Deposit No.", "TDR No."],
    "DEPOSITOR": ["Depositor", "Name of Depositor", "Depositor Name"],
    "BENEFICIARY": ["Beneficiary", "In favour of"],
    "AMOUNT": ["Amount", "Deposit Amount", "Principal"],
    "ISSUE_DATE": ["Date of Deposit", "Deposit Date", "Date of Issue", "Issue Date"],
    "MATURITY_DATE": ["Date of Maturity", "Maturity Date", "Due Date"],
}
TITLES = ["FIXED DEPOSIT RECEIPT", "TERM DEPOSIT RECEIPT", "FIXED DEPOSIT ADVICE"]


@dataclass
class Word:
    text: str
    box: list[int]
    label: str


@dataclass
class Rendered:
    image: Image.Image
    layout: str
    words: list[Word] = field(default_factory=list)


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.load_default(size=size)


class Page:
    def __init__(self, rng: random.Random):
        paper = rng.randint(240, 252)
        self.image = Image.new("RGB", (WIDTH, HEIGHT), (paper, paper, paper - rng.randint(0, 8)))
        self.draw = ImageDraw.Draw(self.image)
        self.words: list[Word] = []

    def width(self, text: str, size: int) -> float:
        return self.draw.textlength(text, font=_font(size))

    def fit(self, text: str, size: int, room: float, smallest: int = 14) -> int:
        """Largest size <= `size` at which `text` fits in `room` pixels (one OCR line)."""
        while size > smallest and self.width(text, size) > room:
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

    def row(self, y: int, caption: str, value: str, label: str, value_x: int, size: int) -> None:
        self.text(MARGIN, y, caption, "O", size)
        self.text(value_x, y, value, label, self.fit(value, size, WIDTH - MARGIN - value_x))

    def mark(self) -> None:
        """The SYNTHETIC mark: a banner across the top and bottom of every page."""
        for y in (18, HEIGHT - 48):
            size = 26
            x = (WIDTH - self.width(WATERMARK, size)) / 2
            self.text(x, y, WATERMARK, "O", size, fill=MARK)

    def signatory(self, rng: random.Random) -> None:
        x, y = WIDTH - 380, HEIGHT - 150
        points = [(x + i * 12, y + rng.randint(-10, 10)) for i in range(18)]
        self.draw.line(points, fill=(30, 40, 110), width=2)
        self.text(x, y + 30, "Authorised Signatory", "O", 22)


def _header(page: Page, values: FDRValues, rng: random.Random) -> int:
    size = page.fit(values.bank, 40, WIDTH - 2 * MARGIN)
    page.text(MARGIN, 70, values.bank, "BANK", size)
    page.text(MARGIN, 125, values.branch, "BRANCH", page.fit(values.branch, 24, 760))
    x = page.text(WIDTH - 420, 125, rng.choice(["IFSC:", "IFSC Code:"]), "O", 24)
    page.text(x, 125, values.ifsc, "IFSC", 24)
    page.draw.line([(MARGIN, 165), (WIDTH - MARGIN, 165)], fill=(90, 90, 110), width=2)
    page.text(MARGIN, 185, rng.choice(TITLES), "O", 32)
    return 250


def _caption(rng: random.Random, label: str) -> str:
    return rng.choice(CAPTIONS[label])


def _footer(page: Page, values: FDRValues, y: int, rng: random.Random) -> None:
    page.text(MARGIN, y, "Amount in words:", "O", 22)
    words_size = page.fit(values.amount_words, 22, WIDTH - 2 * MARGIN)
    page.text(MARGIN, y + 35, values.amount_words, "AMOUNT_WORDS", words_size)
    page.text(MARGIN, y + 85, values.lien_text, "LIEN_TEXT", 22)
    page.signatory(rng)


def _classic(page: Page, values: FDRValues, rng: random.Random) -> None:
    y = _header(page, values, rng)
    rows = [
        ("FDR_NO", values.fdr_no),
        ("DEPOSITOR", values.depositor),
        ("BENEFICIARY", values.beneficiary),
        ("AMOUNT", values.amount_text),
        ("ISSUE_DATE", values.deposit_date),
        ("MATURITY_DATE", values.maturity_date),
    ]
    for label, value in rows:
        page.row(y, _caption(rng, label), value, label, 440, 24)
        y += 52
    _footer(page, values, y + 15, rng)


def _two_column(page: Page, values: FDRValues, rng: random.Random) -> None:
    y = _header(page, values, rng)
    half = WIDTH // 2
    pairs = [
        (("FDR_NO", values.fdr_no), ("ISSUE_DATE", values.deposit_date)),
        (("AMOUNT", values.amount_text), ("MATURITY_DATE", values.maturity_date)),
    ]
    for (left_label, left), (right_label, right) in pairs:
        page.text(MARGIN, y, _caption(rng, left_label), "O", 24)
        page.text(MARGIN + 260, y, left, left_label, 24)
        page.text(half + 40, y, _caption(rng, right_label), "O", 24)
        page.text(half + 300, y, right, right_label, 24)
        y += 56
    for label, value in (("DEPOSITOR", values.depositor), ("BENEFICIARY", values.beneficiary)):
        page.row(y, _caption(rng, label), value, label, MARGIN + 260, 24)
        y += 56
    page.draw.rectangle([MARGIN - 15, 240, WIDTH - MARGIN + 15, y], outline=(90, 90, 110))
    _footer(page, values, y + 25, rng)


def _inline(page: Page, values: FDRValues, rng: random.Random) -> None:
    """Caption and value on one line ("Deposit No.: 1234"); extraction strips the caption."""
    y = _header(page, values, rng)
    rows = [
        ("FDR_NO", values.fdr_no),
        ("AMOUNT", values.amount_text),
        ("ISSUE_DATE", values.deposit_date),
        ("MATURITY_DATE", values.maturity_date),
        ("DEPOSITOR", values.depositor),
        ("BENEFICIARY", values.beneficiary),
    ]
    for label, value in rows:
        caption = f"{_caption(rng, label)}:"
        x = page.text(MARGIN, y, caption, "O", 24)
        page.text(x, y, value, label, page.fit(value, 24, WIDTH - MARGIN - x))
        y += 52
    _footer(page, values, y + 15, rng)


def _rotate_box(box, angle_deg: float, centre) -> list[int]:
    cx, cy = centre
    a = math.radians(-angle_deg)  # PIL rotates counter-clockwise for positive angles
    corners = [(box[0], box[1]), (box[2], box[1]), (box[0], box[3]), (box[2], box[3])]
    xs, ys = [], []
    for x, y in corners:
        dx, dy = x - cx, y - cy
        xs.append(cx + dx * math.cos(a) - dy * math.sin(a))
        ys.append(cy + dx * math.sin(a) + dy * math.cos(a))
    x0, y0 = max(0, math.floor(min(xs))), max(0, math.floor(min(ys)))
    x1, y1 = min(WIDTH, math.ceil(max(xs))), min(HEIGHT, math.ceil(max(ys)))
    return [x0, y0, max(x0 + 1, x1), max(y0 + 1, y1)]


def _scan_effects(rendered: Rendered, rng: random.Random) -> None:
    """Scan artefacts: a slight skew (boxes moved with it), blur and noise."""
    image = rendered.image
    angle = rng.uniform(-1.0, 1.0)
    fill = image.getpixel((5, 5))
    image = image.rotate(angle, resample=Image.BICUBIC, fillcolor=fill)
    for word in rendered.words:
        word.box = _rotate_box(word.box, angle, (WIDTH / 2, HEIGHT / 2))
    if rng.random() < 0.5:
        image = image.filter(ImageFilter.GaussianBlur(radius=rng.uniform(0.3, 0.8)))
    noise = Image.effect_noise(image.size, rng.uniform(4, 12)).convert("RGB")
    rendered.image = Image.blend(image, noise, alpha=rng.uniform(0.02, 0.06))


def render(
    values: FDRValues, rng: random.Random, scan_effects: bool = True, layout: str | None = None
) -> Rendered:
    layout = layout or rng.choice(LAYOUTS)
    page = Page(rng)
    page.mark()
    {"classic": _classic, "two_column": _two_column, "inline": _inline}[layout](page, values, rng)
    page.draw.rectangle([10, 10, WIDTH - 10, HEIGHT - 10], outline=(60, 60, 90), width=3)
    rendered = Rendered(image=page.image, layout=layout, words=page.words)
    if scan_effects:
        _scan_effects(rendered, rng)
    return rendered
