from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True, slots=True)
class ImageQuality:
    width: int
    height: int
    dynamic_range: int
    entropy: float
    edge_density: float
    likely_surface: str

    def as_dict(self) -> dict:
        return {
            "width": self.width,
            "height": self.height,
            "dynamic_range": self.dynamic_range,
            "entropy": round(self.entropy, 4),
            "edge_density": round(self.edge_density, 4),
            "likely_surface": self.likely_surface,
        }


def _png(image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def inspect_image_quality(image_bytes: bytes) -> ImageQuality:
    try:
        from PIL import Image, ImageFilter, ImageOps, ImageStat
        with Image.open(io.BytesIO(image_bytes)) as image:
            image.load()
            image = ImageOps.exif_transpose(image).convert("RGB")
            width, height = image.size
            thumb = image.copy()
            thumb.thumbnail((768, 768))
            gray = ImageOps.grayscale(thumb)
            extrema = gray.getextrema()
            dynamic_range = max(0, int(extrema[1]) - int(extrema[0]))
            entropy = float(gray.entropy())
            edges = gray.filter(ImageFilter.FIND_EDGES)
            stat = ImageStat.Stat(edges)
            edge_mean = float(stat.mean[0] if stat.mean else 0.0)
            edge_density = max(0.0, min(1.0, edge_mean / 255.0))
    except Exception as exc:
        raise ValueError("Image quality could not be inspected safely") from exc

    aspect = width / max(height, 1)
    if dynamic_range < 35:
        surface = "low_contrast_document"
    elif edge_density > 0.12 and (aspect > 1.2 or width >= 1000):
        surface = "screenshot_or_diagram"
    elif entropy < 5.0 and edge_density > 0.06:
        surface = "document_or_form"
    else:
        surface = "photo_or_scan"
    return ImageQuality(width, height, dynamic_range, entropy, edge_density, surface)


def _projection_score(image) -> float:
    threshold = 180
    pixels = image.load()
    width, height = image.size
    if width <= 0 or height <= 0:
        return 0.0
    samples = []
    y_step = max(1, height // 200)
    x_step = max(1, width // 400)
    for y in range(0, height, y_step):
        dark = 0
        for x in range(0, width, x_step):
            if pixels[x, y] < threshold:
                dark += 1
        samples.append(dark)
    if not samples:
        return 0.0
    average = sum(samples) / len(samples)
    return sum((value - average) ** 2 for value in samples) / len(samples)


def deskew_image(image, *, max_angle: float = 5.0):
    from PIL import ImageOps
    gray = ImageOps.grayscale(image)
    probe = gray.copy()
    probe.thumbnail((900, 900))
    best_angle, best_score = 0.0, _projection_score(probe)
    for angle in (-max_angle, -3.0, -1.5, 1.5, 3.0, max_angle):
        candidate = probe.rotate(angle, expand=True, fillcolor=255)
        score = _projection_score(candidate)
        if score > best_score * 1.04:
            best_angle, best_score = float(angle), score
    if not best_angle:
        return image, 0.0
    return image.rotate(best_angle, expand=True, fillcolor="white"), best_angle


def build_preprocess_variants(image_bytes: bytes) -> list[tuple[str, bytes]]:
    """Create deterministic local OCR variants; no model or network call is involved."""
    try:
        from PIL import Image, ImageEnhance, ImageFilter, ImageOps
        with Image.open(io.BytesIO(image_bytes)) as image:
            image.load()
            base = ImageOps.exif_transpose(image).convert("RGB")
    except Exception as exc:
        raise ValueError("Image preprocessing failed safely") from exc

    variants: list[tuple[str, bytes]] = [("original", _png(base))]
    gray = ImageOps.grayscale(base)
    contrasted = ImageOps.autocontrast(gray, cutoff=1)
    if min(contrasted.size) < 1200:
        scale = min(2.5, max(1.25, 1200 / max(1, min(contrasted.size))))
        contrasted = contrasted.resize(
            (max(1, int(contrasted.width * scale)), max(1, int(contrasted.height * scale))),
            resample=Image.Resampling.LANCZOS,
        )
    sharpened = contrasted.filter(ImageFilter.MedianFilter(size=3)).filter(ImageFilter.SHARPEN)
    sharpened = ImageEnhance.Contrast(sharpened).enhance(1.35)
    variants.append(("autocontrast_sharpen", _png(sharpened)))

    deskewed, angle = deskew_image(sharpened.convert("RGB"))
    if angle:
        variants.append((f"deskew_{angle:+.1f}", _png(deskewed)))

    threshold = ImageOps.grayscale(deskewed).point(lambda value: 255 if value > 170 else 0, mode="1")
    variants.append(("binary_threshold", _png(threshold.convert("L"))))

    unique: list[tuple[str, bytes]] = []
    seen = set()
    for name, payload in variants:
        signature = (len(payload), payload[:128], payload[-128:])
        if signature in seen:
            continue
        seen.add(signature)
        unique.append((name, payload))
    return unique


def infer_spatial_layout(blocks: Iterable):
    """Attach deterministic OCR reading-order/column metadata from bounding boxes."""
    materialized = list(blocks)
    groups: dict[tuple, list] = {}
    for block in materialized:
        bbox = getattr(getattr(block, "source", None), "bbox", None)
        method = str(getattr(getattr(block, "extraction_method", None), "value", ""))
        if not bbox or len(bbox) != 4 or method != "ocr":
            continue
        source = block.source
        key = (source.page, source.image)
        groups.setdefault(key, []).append(block)

    for group in groups.values():
        if len(group) < 2:
            for order, block in enumerate(group, 1):
                block.metadata = {**block.metadata, "reading_order": order, "column": 1, "layout": "ocr_line"}
            continue
        page_width = max(float(block.source.bbox[2]) for block in group)
        starts = sorted(float(block.source.bbox[0]) for block in group)
        gaps = [(starts[index + 1] - starts[index], index) for index in range(len(starts) - 1)]
        split = None
        if gaps and page_width > 0:
            gap, index = max(gaps)
            if gap / page_width >= 0.20:
                split = (starts[index] + starts[index + 1]) / 2.0

        def column(block):
            if split is None:
                return 1
            center = (float(block.source.bbox[0]) + float(block.source.bbox[2])) / 2.0
            return 1 if center < split else 2

        ordered = sorted(
            group,
            key=lambda block: (column(block), float(block.source.bbox[1]), float(block.source.bbox[0])),
        )
        for order, block in enumerate(ordered, 1):
            text = str(block.text or "")
            visual_role = "text"
            if any(token in text for token in ("=", "∑", "√", "±", "≤", "≥")):
                visual_role = "equation_candidate"
            elif ":" in text and len(text.split(":", 1)[0]) <= 80:
                visual_role = "form_or_key_value"
            elif text.count("|") >= 2 or text.count("\t") >= 2:
                visual_role = "table_row_candidate"
            block.metadata = {
                **block.metadata,
                "layout": "ocr_line",
                "column": column(block),
                "reading_order": order,
                "visual_role": visual_role,
            }
    return materialized
