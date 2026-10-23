"""Per-region forgery features (M4, N6).

For each text region:
- the nine RGB-GLCM features of Gornale et al. (contrast, homogeneity and energy on the
  R, G and B channels);
- error-level analysis (ELA) mean/std and a noise residual;
- ink colour, ink ratio and sharpness (re-typed or blurred text differs from its page);
- copy-move similarity: the best correlation between this region and any other region
  of the same page (a pasted patch matches its source).
Each base feature is also compared with the median of the page's other regions, because
an edited field differs from its neighbours.
"""

import io

import numpy as np
from PIL import Image, ImageChops, ImageFilter

GLCM_LEVELS = 32
COPY_SIZE = (64, 16)
BASE_NAMES = [
    *(f"glcm_{prop}_{ch}" for ch in "rgb" for prop in ("contrast", "homogeneity", "energy")),
    "ela_mean",
    "ela_std",
    "noise_std",
    "ink_r",
    "ink_g",
    "ink_b",
    "ink_ratio",
    "sharpness",
]
FEATURE_NAMES = BASE_NAMES + [f"dev_{name}" for name in BASE_NAMES] + ["copy_similarity"]


def _glcm(channel: np.ndarray) -> tuple[float, float, float]:
    from skimage.feature import graycomatrix, graycoprops

    quantized = (channel.astype(np.uint16) * GLCM_LEVELS // 256).astype(np.uint8)
    matrix = graycomatrix(
        quantized,
        distances=[1],
        angles=[0, np.pi / 2],
        levels=GLCM_LEVELS,
        symmetric=True,
        normed=True,
    )
    return tuple(
        float(graycoprops(matrix, prop).mean()) for prop in ("contrast", "homogeneity", "energy")
    )


def _ela(region: Image.Image, quality: int = 90) -> tuple[float, float]:
    buffer = io.BytesIO()
    region.save(buffer, "JPEG", quality=quality)
    buffer.seek(0)
    resaved = Image.open(buffer).convert("RGB")
    diff = np.asarray(ImageChops.difference(region, resaved), dtype=np.float32)
    return float(diff.mean()), float(diff.std())


def _noise(gray: Image.Image) -> float:
    smooth = gray.filter(ImageFilter.MedianFilter(3))
    residual = np.asarray(gray, dtype=np.float32) - np.asarray(smooth, dtype=np.float32)
    return float(residual.std())


def _ink(arr: np.ndarray) -> tuple[float, float, float, float]:
    gray = arr.mean(axis=2)
    mask = gray < 128
    if not mask.any():
        return 255.0, 255.0, 255.0, 0.0
    ink = arr[mask]
    return (
        float(ink[:, 0].mean()),
        float(ink[:, 1].mean()),
        float(ink[:, 2].mean()),
        float(mask.mean()),
    )


def _sharpness(gray: Image.Image) -> float:
    edges = np.asarray(gray.filter(ImageFilter.FIND_EDGES), dtype=np.float32)
    return float(edges.var())


def _crop(image: Image.Image, box: tuple[int, int, int, int], pad: int) -> Image.Image:
    x0, y0, x1, y1 = box
    region = image.crop(
        (
            max(0, x0 - pad),
            max(0, y0 - pad),
            min(image.width, x1 + pad),
            min(image.height, y1 + pad),
        )
    )
    if region.width < 4 or region.height < 4:
        region = region.resize((max(4, region.width), max(4, region.height)))
    return region


def region_features(
    image: Image.Image, box: tuple[int, int, int, int], pad: int = 4
) -> list[float]:
    region = _crop(image, box, pad).convert("RGB")
    arr = np.asarray(region)
    gray = region.convert("L")
    feats: list[float] = []
    for c in range(3):
        feats.extend(_glcm(arr[:, :, c]))
    feats.extend(_ela(region))
    feats.append(_noise(gray))
    feats.extend(_ink(arr))
    feats.append(_sharpness(gray))
    return feats


def _copy_similarity(image: Image.Image, boxes: list[tuple[int, int, int, int]]) -> np.ndarray:
    """Best normalised cross-correlation of each region against every other region.

    A pasted region is compared with same-size windows of the other regions' left edges,
    which is where a copied patch is usually taken from.
    """
    gray = image.convert("L")
    patches = []
    for box in boxes:
        x0, y0, x1, y1 = box
        w, h = x1 - x0, y1 - y0
        patches.append((box, w, h))
    out = np.zeros(len(boxes))
    for i, (box, w, h) in enumerate(patches):
        if w < 8 or h < 8:
            continue
        target = np.asarray(gray.crop(box).resize(COPY_SIZE), dtype=np.float32)
        target = (target - target.mean()) / (target.std() + 1e-6)
        best = 0.0
        for j, (other, _, _) in enumerate(patches):
            if j == i:
                continue
            source = gray.crop((other[0], other[1], other[0] + w, other[1] + h))
            src = np.asarray(source.resize(COPY_SIZE), dtype=np.float32)
            src = (src - src.mean()) / (src.std() + 1e-6)
            best = max(best, float((target * src).mean()))
        out[i] = best
    return out


def page_features(image: Image.Image, boxes: list[tuple[int, int, int, int]]) -> np.ndarray:
    """Matrix (regions x FEATURE_NAMES)."""
    image = image.convert("RGB")
    if not boxes:
        return np.zeros((0, len(FEATURE_NAMES)))
    base = np.array([region_features(image, b) for b in boxes], dtype=np.float64)
    median = np.median(base, axis=0)
    scale = np.median(np.abs(base - median), axis=0) + 1e-6
    deviation = (base - median) / scale
    return np.hstack([base, deviation, _copy_similarity(image, boxes)[:, None]])
