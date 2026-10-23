"""Render an FDR receipt image with word-level annotations for LayoutLMv3 (M3).

Labels follow plan §8 M3: FDR_NO, BANK, BRANCH, IFSC, AMOUNT, AMOUNT_WORDS,
ISSUE_DATE, MATURITY_DATE, BENEFICIARY, DEPOSITOR, LIEN_TEXT. Words outside a field
are labelled O. Boxes are [x0, y0, x1, y1] in pixels.
"""

import math
import random
from dataclasses import dataclass, field

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from fdrsynth import WATERMARK
from fdrsynth.values import FDRValues

WIDTH, HEIGHT = 1240, 760
MARGIN = 60


@dataclass
class Word:
    text: str
    box: list[int]
    label: str


@dataclass
class Rendered:
    image: Image.Image
    words: list[Word] = field(default_factory=list)


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.load_default(size=size)


def _draw_words(
    draw: ImageDraw.ImageDraw, x: int, y: int, text: str, label: str, size: int, out: list[Word]
) -> int:
    """Draw text word by word, record each word's box, return the x after the last word."""
    font = _font(size)
    space = draw.textlength(" ", font=font)
    for token in text.split():
        x0, y0, x1, y1 = draw.textbbox((x, y), token, font=font)
        draw.text((x, y), token, fill=(20, 20, 30), font=font)
        out.append(Word(token, [int(x0), int(y0), int(x1), int(y1)], label))
        x = int(x1 + space)
    return x


def _row(draw, y, caption, value, label, out, value_x=420, size=24):
    _draw_words(draw, MARGIN, y, caption, "O", size, out)
    _draw_words(draw, value_x, y, value, label, size, out)


def _watermark(image: Image.Image) -> Image.Image:
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    font = _font(52)
    x0, y0, x1, y1 = ImageDraw.Draw(layer).textbbox((0, 0), WATERMARK, font=font)
    text_img = Image.new("RGBA", (int(x1 - x0) + 40, int(y1 - y0) + 40), (0, 0, 0, 0))
    ImageDraw.Draw(text_img).text((20 - x0, 20 - y0), WATERMARK, fill=(200, 30, 30, 70), font=font)
    rotated = text_img.rotate(math.degrees(math.atan2(HEIGHT, WIDTH)), expand=True)
    layer.paste(rotated, ((WIDTH - rotated.width) // 2, (HEIGHT - rotated.height) // 2), rotated)
    return Image.alpha_composite(image.convert("RGBA"), layer).convert("RGB")


def _scan_effects(image: Image.Image, rng: random.Random) -> Image.Image:
    """Light scan artefacts: slight blur and noise. Geometry is unchanged so boxes stay valid."""
    if rng.random() < 0.5:
        image = image.filter(ImageFilter.GaussianBlur(radius=rng.uniform(0.3, 0.9)))
    noise = Image.effect_noise(image.size, rng.uniform(4, 12)).convert("RGB")
    return Image.blend(image, noise, alpha=rng.uniform(0.03, 0.08))


def render(values: FDRValues, rng: random.Random, scan_effects: bool = True) -> Rendered:
    image = Image.new("RGB", (WIDTH, HEIGHT), (250, 250, 246))
    draw = ImageDraw.Draw(image)
    words: list[Word] = []

    draw.rectangle([20, 20, WIDTH - 20, HEIGHT - 20], outline=(60, 60, 90), width=3)
    _draw_words(draw, MARGIN, 45, values.bank, "BANK", 40, words)
    _draw_words(draw, MARGIN, 100, values.branch, "BRANCH", 24, words)
    x = _draw_words(draw, 760, 100, "IFSC:", "O", 24, words)
    _draw_words(draw, x, 100, values.ifsc, "IFSC", 24, words)
    _draw_words(draw, MARGIN, 150, "FIXED DEPOSIT RECEIPT", "O", 32, words)

    y = 215
    rows = [
        ("FDR No.", values.fdr_no, "FDR_NO"),
        ("Depositor", values.depositor, "DEPOSITOR"),
        ("Beneficiary", values.beneficiary, "BENEFICIARY"),
        ("Amount", values.amount_text, "AMOUNT"),
        ("Date of Deposit", values.deposit_date, "ISSUE_DATE"),
        ("Date of Maturity", values.maturity_date, "MATURITY_DATE"),
    ]
    for caption, value, label in rows:
        _row(draw, y, caption, value, label, words)
        y += 50

    _draw_words(draw, MARGIN, y + 10, "Amount in words:", "O", 22, words)
    _draw_words(draw, MARGIN, y + 45, values.amount_words, "AMOUNT_WORDS", 22, words)
    _draw_words(draw, MARGIN, y + 100, values.lien_text, "LIEN_TEXT", 22, words)
    _draw_words(draw, 860, HEIGHT - 80, "Authorised Signatory", "O", 22, words)

    image = _watermark(image)
    if scan_effects:
        image = _scan_effects(image, rng)
    return Rendered(image=image, words=words)
