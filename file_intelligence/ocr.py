from __future__ import annotations

import io
import shutil
from dataclasses import dataclass
from typing import Protocol

class OcrUnavailable(RuntimeError):
    pass

@dataclass(slots=True)
class OcrBlock:
    text: str
    confidence: float | None = None
    bbox: list[float] | None = None

class OcrProvider(Protocol):
    name: str
    external: bool
    def extract(self, image_bytes: bytes, *, filename: str = "image.png", access_class: str = "owner") -> list[dict]: ...

class TesseractOcrProvider:
    """Local-only OCR. It never sends image bytes over the network."""
    name = "tesseract-local"
    external = False

    def __init__(self, *, language: str = "eng", command: str | None = None):
        self.language = language
        self.command = command

    def extract(self, image_bytes: bytes, *, filename: str = "image.png", access_class: str = "owner") -> list[dict]:
        try:
            import pytesseract
            from PIL import Image
        except ImportError as exc:
            raise OcrUnavailable("Local OCR requires Pillow and pytesseract") from exc
        executable = self.command or shutil.which("tesseract")
        if not executable:
            raise OcrUnavailable("Local OCR requires the tesseract executable")
        pytesseract.pytesseract.tesseract_cmd = executable
        try:
            with Image.open(io.BytesIO(image_bytes)) as image:
                image.load()
                data = pytesseract.image_to_data(image.convert("RGB"), lang=self.language, output_type=pytesseract.Output.DICT)
        except Exception as exc:
            raise OcrUnavailable("Local OCR failed safely") from exc
        blocks: list[dict] = []
        count = len(data.get("text", []))
        for index in range(count):
            text = str(data["text"][index] or "").strip()
            if not text:
                continue
            try:
                raw_conf = float(data["conf"][index])
                confidence = None if raw_conf < 0 else max(0.0, min(1.0, raw_conf / 100.0))
            except (TypeError, ValueError, KeyError):
                confidence = None
            left = float(data.get("left", [0] * count)[index])
            top = float(data.get("top", [0] * count)[index])
            width = float(data.get("width", [0] * count)[index])
            height = float(data.get("height", [0] * count)[index])
            blocks.append({"text": text, "confidence": confidence, "bbox": [left, top, left + width, top + height]})
        return blocks
