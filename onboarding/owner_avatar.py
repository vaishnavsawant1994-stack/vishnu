"""Local owner avatar persistence, scoped to the canonical Vishnu identity.

Never accept external URLs or untrusted SVG as user uploads. Re-encode decoded
raster pixels to a bounded local PNG so metadata and polyglot payloads do not
survive. Storage remains inside the private first-run data directory.
"""
from __future__ import annotations

import base64
import binascii
import io
import json
import os
import re
import secrets
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

PRESET_AVATARS = frozenset({"blue", "mountain", "forest", "horizon"})
MAX_UPLOAD_BYTES = 2 * 1024 * 1024
MAX_DIMENSION = 4096
OUTPUT_DIMENSION = 512
_OWNER_ID = re.compile(r"OWNER-[0-9A-F]{32}\Z")


def _directory(data_dir: Path) -> Path:
    folder = Path(data_dir) / "owner-profile"
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(folder, 0o700)
    return folder


def _atomic_bytes(path: Path, content: bytes) -> None:
    temp = path.with_name(path.name + "." + secrets.token_hex(8) + ".tmp")
    try:
        with temp.open("xb") as stream:
            os.chmod(temp, 0o600)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _safe_png(encoded: str) -> bytes:
    if not encoded or len(encoded) > ((MAX_UPLOAD_BYTES + 2) // 3 * 4):
        raise ValueError("Profile photo exceeds the allowed 2 MB size")
    try:
        original = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("Profile photo is not valid base64") from exc
    if not original or len(original) > MAX_UPLOAD_BYTES:
        raise ValueError("Profile photo exceeds the allowed 2 MB size")
    try:
        with Image.open(io.BytesIO(original)) as image:
            if image.format not in {"PNG", "JPEG", "WEBP"}:
                raise ValueError("Only PNG, JPEG and WebP photos are allowed")
            width, height = image.size
            if not (0 < width <= MAX_DIMENSION and 0 < height <= MAX_DIMENSION):
                raise ValueError("Photo dimensions exceed the allowed size")
            image.load()
            pixels = ImageOps.exif_transpose(image).convert("RGB")
            pixels.thumbnail((OUTPUT_DIMENSION, OUTPUT_DIMENSION), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            pixels.save(output, "PNG", optimize=True)
            return output.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("This photo could not be safely decoded") from exc


def store_owner_avatar(
    data_dir: Path, owner_id: str, *, source: str,
    preset_id: str = "", image_b64: str = "",
) -> dict:
    if not _OWNER_ID.fullmatch(str(owner_id)):
        raise ValueError("Invalid canonical owner identity")
    if source not in {"none", "preset", "upload"}:
        raise ValueError("Unknown profile photo source")
    if source == "preset":
        if preset_id not in PRESET_AVATARS or image_b64:
            raise ValueError("Invalid preset photo selection")
    elif source == "none":
        if preset_id or image_b64:
            raise ValueError("Photo removal cannot include image data")
    elif preset_id:
        raise ValueError("Uploaded photos cannot include a preset identifier")

    sanitized = _safe_png(image_b64) if source == "upload" else None
    folder = _directory(data_dir)
    photo = folder / "avatar.png"
    metadata = {"owner_id": owner_id, "source": source,
                "preset_id": preset_id if source == "preset" else ""}
    if sanitized is not None:
        _atomic_bytes(photo, sanitized)
    _atomic_bytes(folder / "avatar.json", json.dumps(metadata, sort_keys=True).encode("utf-8"))
    if sanitized is None:
        photo.unlink(missing_ok=True)
    return {"source": source, "preset_id": metadata["preset_id"], "saved": True}


def read_owner_avatar(data_dir: Path, owner_id: str) -> tuple[dict, bytes | None]:
    if not _OWNER_ID.fullmatch(str(owner_id)):
        raise ValueError("Invalid canonical owner identity")
    folder = Path(data_dir) / "owner-profile"
    metadata_file = folder / "avatar.json"
    if not metadata_file.exists():
        return {"source": "none", "preset_id": ""}, None
    try:
        metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("The saved profile photo metadata is unavailable") from exc
    if metadata.get("owner_id") != owner_id:
        raise ValueError("The saved profile photo belongs to another owner")
    source = metadata.get("source")
    if source not in {"none", "preset", "upload"}:
        raise ValueError("The saved profile photo source is invalid")
    preset = metadata.get("preset_id", "")
    if source == "preset" and preset not in PRESET_AVATARS:
        raise ValueError("The saved avatar preset is invalid")
    content = (folder / "avatar.png").read_bytes() if source == "upload" else None
    return {"source": source, "preset_id": preset if source == "preset" else ""}, content
