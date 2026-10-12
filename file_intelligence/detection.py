from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .models import ContentKind


@dataclass(frozen=True, slots=True)
class Detection:
    kind: ContentKind
    mime: str
    extension: str


_SIGNATURES = (
    (b"%PDF-", Detection(ContentKind.PDF, "application/pdf", ".pdf")),
    (b"\x89PNG\r\n\x1a\n", Detection(ContentKind.IMAGE, "image/png", ".png")),
    (b"\xff\xd8\xff", Detection(ContentKind.IMAGE, "image/jpeg", ".jpg")),
    (b"GIF87a", Detection(ContentKind.IMAGE, "image/gif", ".gif")),
    (b"GIF89a", Detection(ContentKind.IMAGE, "image/gif", ".gif")),
    (b"II*\x00", Detection(ContentKind.IMAGE, "image/tiff", ".tiff")),
    (b"MM\x00*", Detection(ContentKind.IMAGE, "image/tiff", ".tiff")),
    (b"fLaC", Detection(ContentKind.AUDIO, "audio/flac", ".flac")),
    (b"OggS", Detection(ContentKind.AUDIO, "audio/ogg", ".ogg")),
    (b"ID3", Detection(ContentKind.AUDIO, "audio/mpeg", ".mp3")),
    (b"\x1aE\xdf\xa3", Detection(ContentKind.VIDEO, "video/x-matroska", ".mkv")),
)

_CODE_EXTENSIONS = {
    ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".java", ".kt", ".kts", ".swift",
    ".go", ".rs", ".c", ".h", ".cc", ".cpp", ".hpp", ".cs", ".php", ".rb", ".sh",
    ".bash", ".zsh", ".fish", ".ps1", ".sql", ".graphql", ".gql", ".vue", ".svelte",
}

_EXTENSIONS = {
    ".txt": Detection(ContentKind.TEXT, "text/plain", ".txt"),
    ".md": Detection(ContentKind.TEXT, "text/markdown", ".md"),
    ".markdown": Detection(ContentKind.TEXT, "text/markdown", ".markdown"),
    ".log": Detection(ContentKind.TEXT, "text/plain", ".log"),
    ".ini": Detection(ContentKind.STRUCTURED, "text/plain", ".ini"),
    ".toml": Detection(ContentKind.STRUCTURED, "application/toml", ".toml"),
    ".yaml": Detection(ContentKind.STRUCTURED, "application/yaml", ".yaml"),
    ".yml": Detection(ContentKind.STRUCTURED, "application/yaml", ".yml"),
    ".csv": Detection(ContentKind.STRUCTURED, "text/csv", ".csv"),
    ".json": Detection(ContentKind.STRUCTURED, "application/json", ".json"),
    ".jsonl": Detection(ContentKind.STRUCTURED, "application/x-ndjson", ".jsonl"),
    ".xml": Detection(ContentKind.STRUCTURED, "application/xml", ".xml"),
    ".html": Detection(ContentKind.STRUCTURED, "text/html", ".html"),
    ".htm": Detection(ContentKind.STRUCTURED, "text/html", ".htm"),
    ".ics": Detection(ContentKind.STRUCTURED, "text/calendar", ".ics"),
    ".vcf": Detection(ContentKind.STRUCTURED, "text/vcard", ".vcf"),
    ".srt": Detection(ContentKind.STRUCTURED, "application/x-subrip", ".srt"),
    ".vtt": Detection(ContentKind.STRUCTURED, "text/vtt", ".vtt"),
    ".eml": Detection(ContentKind.EMAIL, "message/rfc822", ".eml"),
    ".rtf": Detection(ContentKind.DOCUMENT, "application/rtf", ".rtf"),
    ".epub": Detection(ContentKind.EBOOK, "application/epub+zip", ".epub"),
    ".zip": Detection(ContentKind.ARCHIVE, "application/zip", ".zip"),
    ".tar": Detection(ContentKind.ARCHIVE, "application/x-tar", ".tar"),
    ".gz": Detection(ContentKind.ARCHIVE, "application/gzip", ".gz"),
    ".tgz": Detection(ContentKind.ARCHIVE, "application/gzip", ".tgz"),
    ".docx": Detection(ContentKind.DOCUMENT, "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"),
    ".xlsx": Detection(ContentKind.SPREADSHEET, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"),
    ".pptx": Detection(ContentKind.PRESENTATION, "application/vnd.openxmlformats-officedocument.presentationml.presentation", ".pptx"),
    ".pdf": Detection(ContentKind.PDF, "application/pdf", ".pdf"),
    ".png": Detection(ContentKind.IMAGE, "image/png", ".png"),
    ".jpg": Detection(ContentKind.IMAGE, "image/jpeg", ".jpg"),
    ".jpeg": Detection(ContentKind.IMAGE, "image/jpeg", ".jpeg"),
    ".webp": Detection(ContentKind.IMAGE, "image/webp", ".webp"),
    ".tif": Detection(ContentKind.IMAGE, "image/tiff", ".tif"),
    ".tiff": Detection(ContentKind.IMAGE, "image/tiff", ".tiff"),
    ".wav": Detection(ContentKind.AUDIO, "audio/wav", ".wav"),
    ".flac": Detection(ContentKind.AUDIO, "audio/flac", ".flac"),
    ".mp3": Detection(ContentKind.AUDIO, "audio/mpeg", ".mp3"),
    ".m4a": Detection(ContentKind.AUDIO, "audio/mp4", ".m4a"),
    ".aac": Detection(ContentKind.AUDIO, "audio/aac", ".aac"),
    ".ogg": Detection(ContentKind.AUDIO, "audio/ogg", ".ogg"),
    ".opus": Detection(ContentKind.AUDIO, "audio/ogg", ".opus"),
    ".mp4": Detection(ContentKind.VIDEO, "video/mp4", ".mp4"),
    ".mov": Detection(ContentKind.VIDEO, "video/quicktime", ".mov"),
    ".mkv": Detection(ContentKind.VIDEO, "video/x-matroska", ".mkv"),
    ".webm": Detection(ContentKind.VIDEO, "video/webm", ".webm"),
    ".avi": Detection(ContentKind.VIDEO, "video/x-msvideo", ".avi"),
}
for _suffix in _CODE_EXTENSIONS:
    _EXTENSIONS[_suffix] = Detection(ContentKind.CODE, "text/plain", _suffix)


def _detect_zip(data: bytes) -> Detection | None:
    if not data.startswith(b"PK"):
        return None
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = set(archive.namelist())
            if "mimetype" in names:
                try:
                    if archive.read("mimetype")[:64].strip() == b"application/epub+zip":
                        return _EXTENSIONS[".epub"]
                except (KeyError, RuntimeError, OSError):
                    pass
    except (zipfile.BadZipFile, OSError):
        return None
    if "[Content_Types].xml" not in names:
        return _EXTENSIONS[".zip"]
    if any(name.startswith("word/") for name in names):
        return _EXTENSIONS[".docx"]
    if any(name.startswith("xl/") for name in names):
        return _EXTENSIONS[".xlsx"]
    if any(name.startswith("ppt/") for name in names):
        return _EXTENSIONS[".pptx"]
    return _EXTENSIONS[".zip"]


def _detect_iso_media(filename: str, data: bytes) -> Detection | None:
    if len(data) < 12 or data[4:8] != b"ftyp":
        return None
    suffix = Path(filename).suffix.lower()
    if suffix in {".m4a", ".aac"}:
        return _EXTENSIONS.get(suffix, _EXTENSIONS[".m4a"])
    if suffix == ".mov":
        return _EXTENSIONS[".mov"]
    return _EXTENSIONS[".mp4"]


def detect_content(filename: str, data: bytes, declared_mime: str = "application/octet-stream") -> Detection:
    lower_name = str(filename or "").lower()
    suffix = ".tar.gz" if lower_name.endswith(".tar.gz") else Path(filename).suffix.lower()
    if data.startswith(b"\x1f\x8b"):
        extension = ".tar.gz" if lower_name.endswith(".tar.gz") else ".tgz" if lower_name.endswith(".tgz") else ".gz"
        return Detection(ContentKind.ARCHIVE, "application/gzip", extension)
    if len(data) >= 265 and data[257:262] == b"ustar":
        return Detection(ContentKind.ARCHIVE, "application/x-tar", ".tar")
    if data.startswith(b"RIFF") and len(data) >= 12:
        if data[8:12] == b"WEBP":
            return Detection(ContentKind.IMAGE, "image/webp", ".webp")
        if data[8:12] == b"WAVE":
            return _EXTENSIONS[".wav"]
        if data[8:12] == b"AVI ":
            return _EXTENSIONS[".avi"]
    iso_media = _detect_iso_media(filename, data)
    if iso_media:
        return iso_media
    for signature, detected in _SIGNATURES:
        if data.startswith(signature):
            if signature == b"OggS" and suffix == ".opus":
                return _EXTENSIONS[".opus"]
            if signature == b"\x1aE\xdf\xa3" and suffix == ".webm":
                return _EXTENSIONS[".webm"]
            return detected
    if suffix == ".mp3" and len(data) >= 2 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0:
        return _EXTENSIONS[".mp3"]
    zipped = _detect_zip(data)
    if zipped:
        return zipped
    sample = data[:65536]
    try:
        text = sample.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = ""
    if text:
        controls = sum(1 for ch in text if ord(ch) < 32 and ch not in "\t\n\r\f\b")
        if "\x00" in text or controls > max(2, len(text) // 100):
            text = ""
    if text:
        stripped = text.lstrip()
        if stripped.startswith(("{", "[")):
            try:
                json.loads(data.decode("utf-8-sig"))
                return _EXTENSIONS[".json"]
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass
        if suffix in _EXTENSIONS:
            return _EXTENSIONS[suffix]
        return Detection(ContentKind.TEXT, declared_mime if declared_mime.startswith("text/") else "text/plain", suffix or ".txt")
    if suffix in _EXTENSIONS:
        return _EXTENSIONS[suffix]
    return Detection(ContentKind.UNKNOWN, declared_mime or "application/octet-stream", suffix)
