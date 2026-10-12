from __future__ import annotations

import io
import shutil
from dataclasses import dataclass
from statistics import mean
from typing import Protocol

from .visual import build_preprocess_variants


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

    def extract(
        self,
        image_bytes: bytes,
        *,
        filename: str = "image.png",
        access_class: str = "owner",
    ) -> list[dict]: ...


def _confidence(item: dict) -> float:
    value = item.get("confidence")
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _result_score(items: list[dict]) -> float:
    usable = [item for item in items if str(item.get("text") or "").strip()]
    if not usable:
        return 0.0
    chars = sum(len(str(item.get("text") or "").strip()) for item in usable)
    confidences = [_confidence(item) for item in usable if item.get("confidence") is not None]
    average = mean(confidences) if confidences else 0.35
    return average * 100.0 + min(chars, 4000) / 400.0


class TesseractOcrProvider:
    """Local-only adaptive Tesseract OCR with orientation and multilingual language-pack support."""

    name = "tesseract-local/adaptive-v2"
    external = False

    def __init__(
        self,
        *,
        language: str = "eng",
        languages: tuple[str, ...] | list[str] | None = None,
        command: str | None = None,
        orientation: bool = True,
        psm: int = 6,
    ):
        self.language = str(language or "eng")
        self.languages = tuple(str(item).strip() for item in (languages or ()) if str(item).strip())
        self.command = command
        self.orientation = bool(orientation)
        self.psm = int(psm)

    def _runtime(self):
        try:
            import pytesseract
            from PIL import Image
        except ImportError as exc:
            raise OcrUnavailable("Local OCR requires Pillow and pytesseract") from exc
        executable = self.command or shutil.which("tesseract")
        if not executable:
            raise OcrUnavailable("Local OCR requires the tesseract executable")
        pytesseract.pytesseract.tesseract_cmd = executable
        return pytesseract, Image

    def available_languages(self) -> tuple[str, ...]:
        pytesseract, _ = self._runtime()
        try:
            return tuple(sorted(str(item) for item in pytesseract.get_languages(config="") if item))
        except Exception as exc:
            raise OcrUnavailable("Local OCR language packs could not be inspected") from exc

    def _resolved_language(self, pytesseract) -> str:
        requested = list(self.languages)
        if not requested and self.language.lower() != "auto":
            requested = [part for part in self.language.replace(",", "+").split("+") if part]
        try:
            available = set(pytesseract.get_languages(config=""))
        except Exception:
            available = set()
        if requested:
            usable = [item for item in requested if not available or item in available]
            if usable:
                return "+".join(usable)
        if self.language.lower() == "auto":
            preferred = ("eng", "deu", "fra", "spa", "ita", "por", "hin", "ara", "jpn", "kor", "chi_sim")
            usable = [item for item in preferred if item in available]
            if usable:
                return "+".join(usable[:4])
        if not available or "eng" in available:
            return "eng"
        if available:
            return sorted(available)[0]
        return self.language or "eng"

    def _orient(self, image, pytesseract):
        if not self.orientation:
            return image, 0
        try:
            osd = pytesseract.image_to_osd(image, output_type=pytesseract.Output.DICT)
            rotate = int(float(osd.get("rotate", 0) or 0)) % 360
        except Exception:
            rotate = 0
        if rotate:
            return image.rotate(-rotate, expand=True, fillcolor="white"), rotate
        return image, 0

    @staticmethod
    def _lines_from_data(data: dict, *, orientation_degrees: int, language: str, profile: str) -> list[dict]:
        texts = data.get("text") or []
        count = len(texts)
        lines: dict[tuple[int, int, int], list[dict]] = {}
        for index in range(count):
            text = str(texts[index] or "").strip()
            if not text:
                continue
            try:
                raw_conf = float((data.get("conf") or [])[index])
                confidence = None if raw_conf < 0 else max(0.0, min(1.0, raw_conf / 100.0))
            except (TypeError, ValueError, IndexError):
                confidence = None
            try:
                left = float((data.get("left") or [0] * count)[index])
                top = float((data.get("top") or [0] * count)[index])
                width = float((data.get("width") or [0] * count)[index])
                height = float((data.get("height") or [0] * count)[index])
            except (TypeError, ValueError, IndexError):
                left = top = width = height = 0.0

            def number(key: str) -> int:
                try:
                    return int((data.get(key) or [0] * count)[index])
                except (TypeError, ValueError, IndexError):
                    return 0

            key = (number("block_num"), number("par_num"), number("line_num"))
            lines.setdefault(key, []).append(
                {
                    "text": text,
                    "confidence": confidence,
                    "bbox": [left, top, left + width, top + height],
                    "word_num": number("word_num"),
                }
            )

        result: list[dict] = []
        for line_key, words in lines.items():
            words.sort(key=lambda item: (item["bbox"][0], item["word_num"]))
            line_text = " ".join(item["text"] for item in words).strip()
            if not line_text:
                continue
            x1 = min(item["bbox"][0] for item in words)
            y1 = min(item["bbox"][1] for item in words)
            x2 = max(item["bbox"][2] for item in words)
            y2 = max(item["bbox"][3] for item in words)
            confidences = [item["confidence"] for item in words if item["confidence"] is not None]
            result.append(
                {
                    "text": line_text,
                    "confidence": mean(confidences) if confidences else None,
                    "bbox": [x1, y1, x2, y2],
                    "metadata": {
                        "ocr_block": line_key[0],
                        "ocr_paragraph": line_key[1],
                        "ocr_line": line_key[2],
                        "word_count": len(words),
                        "orientation_degrees": orientation_degrees,
                        "language": language,
                        "preprocess_profile": profile,
                    },
                }
            )
        result.sort(key=lambda item: (item["bbox"][1], item["bbox"][0]))
        return result

    def extract(
        self,
        image_bytes: bytes,
        *,
        filename: str = "image.png",
        access_class: str = "owner",
    ) -> list[dict]:
        pytesseract, Image = self._runtime()
        language = self._resolved_language(pytesseract)
        best: list[dict] = []
        best_score = -1.0
        try:
            variants = build_preprocess_variants(image_bytes)
            for profile, payload in variants[:4]:
                with Image.open(io.BytesIO(payload)) as image:
                    image.load()
                    prepared, rotation = self._orient(image.convert("RGB"), pytesseract)
                    data = pytesseract.image_to_data(
                        prepared,
                        lang=language,
                        config=f"--psm {self.psm}",
                        output_type=pytesseract.Output.DICT,
                    )
                lines = self._lines_from_data(
                    data,
                    orientation_degrees=rotation,
                    language=language,
                    profile=profile,
                )
                score = _result_score(lines)
                if score > best_score:
                    best, best_score = lines, score
                confidences = [_confidence(item) for item in lines if item.get("confidence") is not None]
                if lines and confidences and mean(confidences) >= 0.82:
                    break
        except OcrUnavailable:
            raise
        except Exception as exc:
            raise OcrUnavailable("Local OCR failed safely") from exc
        for item in best:
            item.setdefault("metadata", {})["adaptive_score"] = round(best_score, 4)
        return best


class AdaptiveOcrProvider:
    """Local-first OCR quality layer for any installed OCR provider."""

    external = False

    def __init__(
        self,
        provider: OcrProvider | None = None,
        *,
        max_variants: int = 4,
        min_confidence: float = 0.72,
    ):
        self.provider = provider or TesseractOcrProvider(language="auto")
        self.external = bool(getattr(self.provider, "external", False))
        self.name = f"adaptive:{getattr(self.provider, 'name', self.provider.__class__.__name__)}"
        self.max_variants = max(1, min(int(max_variants), 8))
        self.min_confidence = max(0.0, min(1.0, float(min_confidence)))

    def extract(
        self,
        image_bytes: bytes,
        *,
        filename: str = "image.png",
        access_class: str = "owner",
    ) -> list[dict]:
        variants = build_preprocess_variants(image_bytes)[: self.max_variants]
        best: list[dict] = []
        best_score = -1.0
        errors: list[Exception] = []
        for profile, payload in variants:
            try:
                result = self.provider.extract(payload, filename=filename, access_class=access_class)
            except OcrUnavailable as exc:
                errors.append(exc)
                continue
            except Exception:
                errors.append(OcrUnavailable("Configured local OCR provider failed safely"))
                continue
            normalized = []
            for item in result if isinstance(result, list) else []:
                if not isinstance(item, dict):
                    continue
                copied = dict(item)
                metadata = dict(copied.get("metadata") or {})
                metadata["adaptive_profile"] = profile
                copied["metadata"] = metadata
                normalized.append(copied)
            score = _result_score(normalized)
            if score > best_score:
                best, best_score = normalized, score
            confidences = [_confidence(item) for item in normalized if item.get("confidence") is not None]
            if normalized and confidences and mean(confidences) >= self.min_confidence:
                break
        if best:
            for item in best:
                item.setdefault("metadata", {})["adaptive_score"] = round(best_score, 4)
            return best
        if errors:
            raise OcrUnavailable(str(errors[-1]))
        return []
