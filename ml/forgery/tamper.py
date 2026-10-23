"""Make tampered copies of synthetic FDRs for training the forgery signal.

Forgery types follow Gornale et al. (2022): copy-paste, insertion (re-typed text),
noise, blur and their combinations, applied to one field region of a page.
"""

import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

OPERATIONS = [
    "copy_paste",
    "insertion",
    "noise",
    "blur",
    "copy_blur",
    "insert_noise",
    "insert_blur",
]


def field_regions(record: dict) -> list[tuple[str, tuple[int, int, int, int]]]:
    """Union box of each labelled field's words, in reading order."""
    boxes: dict[str, list[list[int]]] = {}
    for word in record["words"]:
        if word["label"] != "O":
            boxes.setdefault(word["label"], []).append(word["box"])
    regions = []
    for label, items in boxes.items():
        xs0, ys0, xs1, ys1 = zip(*items, strict=True)
        regions.append((label, (min(xs0), min(ys0), max(xs1), max(ys1))))
    return sorted(regions, key=lambda r: (r[1][1], r[1][0]))


def _background(image: Image.Image, box) -> tuple[int, int, int]:
    x0, y0, x1, y1 = box
    strip = np.asarray(image.crop((x0, max(0, y0 - 6), x1, y0)).convert("RGB")).reshape(-1, 3)
    return tuple(int(v) for v in np.median(strip, axis=0)) if len(strip) else (250, 250, 246)


def _insertion(image, box, rng):
    x0, y0, x1, y1 = box
    draw = ImageDraw.Draw(image)
    draw.rectangle(box, fill=_background(image, box))
    digits = "".join(rng.choice("0123456789") for _ in range(max(3, (x1 - x0) // 14)))
    size = max(10, (y1 - y0) + rng.choice([-3, -2, 2, 3]))
    shade = rng.randint(0, 60)
    draw.text(
        (x0, y0),
        digits,
        fill=(shade, shade, shade + rng.randint(0, 30)),
        font=ImageFont.load_default(size=size),
    )


def _copy_paste(image, box, others, rng):
    if not others:
        return _insertion(image, box, rng)
    sx0, sy0, sx1, sy1 = rng.choice(others)[1]
    w, h = box[2] - box[0], box[3] - box[1]
    patch = image.crop((sx0, sy0, sx0 + w, sy0 + h))
    image.paste(patch, (box[0], box[1]))


def _noise(image, box, rng):
    region = np.asarray(image.crop(box), dtype=np.float32)
    noisy = np.clip(
        region
        + np.random.default_rng(rng.randint(0, 10**6)).normal(0, rng.uniform(8, 20), region.shape),
        0,
        255,
    )
    image.paste(Image.fromarray(noisy.astype(np.uint8)), box[:2])


def _blur(image, box, rng):
    image.paste(image.crop(box).filter(ImageFilter.GaussianBlur(rng.uniform(1.0, 2.2))), box[:2])


def tamper(
    image: Image.Image, regions, target: int, operation: str, rng: random.Random
) -> Image.Image:
    image = image.convert("RGB").copy()
    box = regions[target][1]
    others = [r for i, r in enumerate(regions) if i != target]
    steps = {
        "copy_paste": [lambda: _copy_paste(image, box, others, rng)],
        "insertion": [lambda: _insertion(image, box, rng)],
        "noise": [lambda: _noise(image, box, rng)],
        "blur": [lambda: _blur(image, box, rng)],
        "copy_blur": [lambda: _copy_paste(image, box, others, rng), lambda: _blur(image, box, rng)],
        "insert_noise": [lambda: _insertion(image, box, rng), lambda: _noise(image, box, rng)],
        "insert_blur": [lambda: _insertion(image, box, rng), lambda: _blur(image, box, rng)],
    }[operation]
    for step in steps:
        step()
    return image


def recompress(image: Image.Image, rng: random.Random) -> Image.Image:
    """Every page (genuine or not) is re-saved as JPEG, as a scan sent by email would be."""
    import io

    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=rng.randint(85, 95))
    buffer.seek(0)
    return Image.open(buffer).convert("RGB")
