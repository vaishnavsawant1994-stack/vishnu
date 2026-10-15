from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from typing import Iterable

from PIL import Image, ImageFilter


MAX_PRIVACY_EDGE = 1280
MIN_PRIVACY_EDGE = 64


@dataclass(frozen=True)
class NormalizedRect:
    x: float
    y: float
    width: float
    height: float

    @classmethod
    def from_value(cls, value) -> "NormalizedRect":
        if isinstance(value, cls):
            return value
        if not isinstance(value, dict):
            raise ValueError("privacy region must be an object")
        try:
            rect = cls(
                float(value.get("x", 0)),
                float(value.get("y", 0)),
                float(value.get("width", 0)),
                float(value.get("height", 0)),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("privacy region contains invalid coordinates") from exc
        if not (
            0 <= rect.x <= 1
            and 0 <= rect.y <= 1
            and 0 < rect.width <= 1
            and 0 < rect.height <= 1
            and rect.x + rect.width <= 1.000001
            and rect.y + rect.height <= 1.000001
        ):
            raise ValueError("privacy region must fit inside the normalized frame")
        return rect

    def pixels(self, width: int, height: int) -> tuple[int, int, int, int]:
        left = max(0, min(width - 1, round(self.x * width)))
        top = max(0, min(height - 1, round(self.y * height)))
        right = max(left + 1, min(width, round((self.x + self.width) * width)))
        bottom = max(top + 1, min(height, round((self.y + self.height) * height)))
        return left, top, right, bottom


@dataclass(frozen=True)
class PrivacyOptions:
    max_edge: int = 1024
    crop: NormalizedRect | None = None
    redact_regions: tuple[NormalizedRect, ...] = ()
    faces_processed: bool = False
    require_face_redaction: bool = False

    @classmethod
    def from_value(cls, value) -> "PrivacyOptions":
        if value is None:
            return cls()
        if isinstance(value, cls):
            return value
        if not isinstance(value, dict):
            raise ValueError("privacy options must be an object")
        max_edge = int(value.get("max_edge", 1024))
        max_edge = max(MIN_PRIVACY_EDGE, min(max_edge, MAX_PRIVACY_EDGE))
        crop_raw = value.get("crop")
        crop = NormalizedRect.from_value(crop_raw) if crop_raw else None
        redactions = tuple(
            NormalizedRect.from_value(item)
            for item in list(value.get("redact_regions") or [])[:64]
        )
        return cls(
            max_edge=max_edge,
            crop=crop,
            redact_regions=redactions,
            faces_processed=bool(value.get("faces_processed", False)),
            require_face_redaction=bool(value.get("require_face_redaction", False)),
        )


def _load_image(raw: bytes) -> Image.Image:
    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
        return image.convert("RGB")
    except Exception as exc:
        raise ValueError("camera frame is not a decodable image") from exc


def _resize(image: Image.Image, max_edge: int) -> Image.Image:
    longest = max(image.size)
    if longest <= max_edge:
        return image
    scale = max_edge / float(longest)
    size = (
        max(1, round(image.width * scale)),
        max(1, round(image.height * scale)),
    )
    return image.resize(size, Image.Resampling.LANCZOS)


def _redact(image: Image.Image, boxes: Iterable[NormalizedRect]) -> Image.Image:
    output = image.copy()
    for rect in boxes:
        box = rect.pixels(output.width, output.height)
        region = output.crop(box)
        # Pixelation is intentionally strong and deterministic. It avoids
        # retaining readable text/face detail while remaining dependency-free.
        tiny = region.resize(
            (max(1, region.width // 18), max(1, region.height // 18)),
            Image.Resampling.BILINEAR,
        )
        obscured = tiny.resize(region.size, Image.Resampling.NEAREST).filter(ImageFilter.GaussianBlur(radius=2))
        output.paste(obscured, box)
    return output


def sanitize_image(raw: bytes, options: PrivacyOptions | dict | None = None) -> tuple[bytes, dict]:
    opts = PrivacyOptions.from_value(options)
    if opts.require_face_redaction and not opts.faces_processed:
        raise PermissionError(
            "face redaction was required but the capturing device did not confirm on-device face processing"
        )
    image = _load_image(raw)
    original = image.size
    if opts.crop is not None:
        image = image.crop(opts.crop.pixels(image.width, image.height))
    image = _resize(image, opts.max_edge)
    if opts.redact_regions:
        image = _redact(image, opts.redact_regions)
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=72, optimize=True)
    payload = out.getvalue()
    return payload, {
        "original_width": original[0],
        "original_height": original[1],
        "width": image.width,
        "height": image.height,
        "downsampled": image.size != original,
        "cropped": opts.crop is not None,
        "redacted_regions": len(opts.redact_regions),
        "faces_processed": opts.faces_processed,
        "require_face_redaction": opts.require_face_redaction,
    }


def data_url(raw: bytes, mime_type: str = "image/jpeg") -> str:
    return f"data:{mime_type};base64,{base64.b64encode(raw).decode('ascii')}"


def scene_fingerprint(raw: bytes, *, side: int = 16) -> tuple[int, ...]:
    image = _load_image(raw).convert("L").resize((side, side), Image.Resampling.BILINEAR)
    return tuple(int(value) for value in image.getdata())


def scene_delta(previous: tuple[int, ...] | None, current: tuple[int, ...]) -> float:
    if not previous or len(previous) != len(current):
        return 1.0
    return sum(abs(a - b) for a, b in zip(previous, current)) / (255.0 * len(current))
