from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from .detection import Detection, detect_content
from .extended_readers import (
    read_eml,
    read_epub,
    read_gzip,
    read_pdf_form_fields,
    read_rtf,
    read_tar,
    read_yaml,
    read_zip,
)
from .layout import enrich_layout
from .media import (
    LocalMediaDecoder,
    MediaUnavailable,
    discover_local_speech_provider,
    read_audio,
    read_subtitles,
    read_video,
)
from .models import ContentKind, VishnuDocument
from .ocr import OcrUnavailable
from .readers import (
    ContentReadError,
    read_csv,
    read_docx,
    read_html,
    read_image,
    read_json,
    read_jsonl,
    read_pdf,
    read_pptx,
    read_text,
    read_xlsx,
    read_xml,
)


class UnsupportedContentError(ContentReadError):
    pass


class FileIntelligenceEngine:
    """Deterministic, local-first content extraction for Vishnu; no network calls."""

    MAX_FILE_BYTES = 50 * 1024 * 1024
    MAX_ARCHIVE_DEPTH = 2

    def __init__(
        self,
        *,
        ocr_provider=None,
        speech_provider=None,
        media_decoder=None,
        media_language: str | None = None,
        max_video_keyframes: int = 12,
        max_file_bytes: int | None = None,
        allow_external_ocr: bool = False,
        allow_external_speech: bool = False,
    ):
        if ocr_provider is not None and bool(getattr(ocr_provider, "external", False)) and not allow_external_ocr:
            raise OcrUnavailable("External OCR is disabled by default; configure it explicitly if policy permits")
        if speech_provider is None:
            speech_provider = discover_local_speech_provider()
        if speech_provider is not None and bool(getattr(speech_provider, "external", False)) and not allow_external_speech:
            raise MediaUnavailable("External speech-to-text is disabled by default; configure it explicitly if policy permits")
        self.ocr_provider = ocr_provider
        self.speech_provider = speech_provider
        self.media_decoder = media_decoder or LocalMediaDecoder()
        self.media_language = str(media_language).strip() if media_language else None
        self.max_video_keyframes = max(1, min(int(max_video_keyframes), 24))
        self.max_file_bytes = int(max_file_bytes or self.MAX_FILE_BYTES)
        self.allow_external_ocr = bool(allow_external_ocr)
        self.allow_external_speech = bool(allow_external_speech)

    def extract(
        self,
        *,
        filename: str,
        data: bytes,
        declared_mime: str = "application/octet-stream",
        _archive_depth: int = 0,
    ) -> VishnuDocument:
        safe_name = Path(str(filename or "")).name.strip()
        if not safe_name or safe_name in {".", ".."}:
            raise ContentReadError("A safe filename is required")
        if not data:
            raise ContentReadError("File is empty")
        if len(data) > self.max_file_bytes:
            raise ContentReadError("File exceeds the configured size limit")
        detection = detect_content(safe_name, data, declared_mime)
        document = VishnuDocument(
            document_id=str(uuid.uuid4()),
            filename=safe_name,
            content_kind=detection.kind,
            detected_mime=detection.mime,
            declared_mime=declared_mime or "application/octet-stream",
            extension=detection.extension,
            sha256=hashlib.sha256(data).hexdigest(),
            size_bytes=len(data),
        )
        blocks, warnings, ocr_version, media_version = self._read(
            detection,
            safe_name,
            data,
            archive_depth=_archive_depth,
        )
        document.blocks = enrich_layout(blocks)
        document.warnings.extend(warnings)
        document.ocr_version = ocr_version
        document.media_version = media_version
        document.metadata["block_counts"] = self._block_counts(document)
        if detection.kind in {ContentKind.AUDIO, ContentKind.VIDEO}:
            document.metadata["media"] = True
        if not document.blocks:
            raise ContentReadError("No readable content was found")
        return document

    @staticmethod
    def _block_counts(document: VishnuDocument) -> dict[str, int]:
        counts: dict[str, int] = {}
        for block in document.blocks:
            counts[block.kind] = counts.get(block.kind, 0) + 1
        return counts

    def _read(self, detection: Detection, filename: str, data: bytes, *, archive_depth: int):
        suffix = detection.extension.lower()
        if detection.kind == ContentKind.PDF:
            blocks, warnings, ocr_version = read_pdf(data, filename, self.ocr_provider)
            try:
                blocks.extend(read_pdf_form_fields(data))
            except ContentReadError as exc:
                warnings.append(f"Embedded PDF form fields were skipped: {exc}")
            return blocks, warnings, ocr_version, None
        if detection.kind == ContentKind.IMAGE:
            blocks, ocr_version = read_image(data, filename, self.ocr_provider)
            return blocks, [], ocr_version, None
        if detection.kind == ContentKind.AUDIO:
            blocks, warnings, media_version = read_audio(
                data,
                filename=filename,
                speech_provider=self.speech_provider,
                decoder=self.media_decoder,
                language=self.media_language,
            )
            return blocks, warnings, None, media_version
        if detection.kind == ContentKind.VIDEO:
            blocks, warnings, media_version, ocr_version = read_video(
                data,
                filename=filename,
                speech_provider=self.speech_provider,
                decoder=self.media_decoder,
                ocr_provider=self.ocr_provider,
                language=self.media_language,
                max_keyframes=self.max_video_keyframes,
            )
            return blocks, warnings, ocr_version, media_version
        if suffix in {".srt", ".vtt"}:
            return read_subtitles(data), [], None, "subtitle-native/1"
        if suffix == ".docx":
            return read_docx(data), [], None, None
        if suffix == ".xlsx":
            return read_xlsx(data), [], None, None
        if suffix == ".pptx":
            return read_pptx(data), [], None, None
        if suffix == ".json":
            return read_json(data), [], None, None
        if suffix == ".jsonl":
            return read_jsonl(data), [], None, None
        if suffix == ".csv":
            return read_csv(data), [], None, None
        if suffix == ".xml":
            return read_xml(data), [], None, None
        if suffix in {".html", ".htm"}:
            return read_html(data), [], None, None
        if suffix in {".yaml", ".yml"}:
            return read_yaml(data), [], None, None
        if suffix == ".eml":
            return read_eml(data), [], None, None
        if suffix == ".rtf":
            return read_rtf(data), [], None, None
        if suffix == ".epub":
            return read_epub(data), [], None, None
        if detection.kind == ContentKind.ARCHIVE:
            if archive_depth >= self.MAX_ARCHIVE_DEPTH:
                raise ContentReadError("Archive nesting exceeds the configured safety limit")
            child_reader = lambda child_name, child_data: self.extract(
                filename=child_name,
                data=child_data,
                _archive_depth=archive_depth + 1,
            )
            if suffix == ".zip":
                blocks, warnings = read_zip(data, child_reader=child_reader)
                return blocks, warnings, None, None
            if suffix == ".tar":
                blocks, warnings = read_tar(data, child_reader=child_reader)
                return blocks, warnings, None, None
            if suffix in {".gz", ".tgz", ".tar.gz"}:
                blocks, warnings = read_gzip(data, filename=filename, child_reader=child_reader)
                return blocks, warnings, None, None
        if detection.kind in {ContentKind.TEXT, ContentKind.CODE}:
            blocks = read_text(data)
            for block in blocks:
                if detection.kind == ContentKind.CODE:
                    block.kind = "code"
                    block.metadata["language_hint"] = suffix.lstrip(".")
            return blocks, [], None, None
        if suffix in {".toml", ".ini", ".ics", ".vcf"}:
            blocks = read_text(data)
            for block in blocks:
                block.kind = "structured"
            return blocks, [], None, None
        raise UnsupportedContentError(f"Unsupported file type: {suffix or detection.mime or 'unknown'}")
