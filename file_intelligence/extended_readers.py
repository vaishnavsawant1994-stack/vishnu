from __future__ import annotations

import gzip
import io
import re
import stat
import tarfile
import zipfile
from email import policy
from email.parser import BytesParser

from .models import ExtractionMethod, SourceReference, VishnuBlock
from .readers import (
    ContentReadError,
    MAX_ARCHIVE_COMPRESSION_RATIO,
    MAX_ARCHIVE_EXPANDED_BYTES,
    MAX_ARCHIVE_MEMBER_BYTES,
    MAX_ARCHIVE_MEMBERS,
    read_html,
)


def _decode_text(data: bytes, label: str) -> str:
    for encoding in ("utf-8-sig", "utf-16", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ContentReadError(f"{label} could not be decoded safely")


def read_yaml(data: bytes) -> list[VishnuBlock]:
    text = _decode_text(data, "YAML")
    parsed = None
    try:
        import yaml
        parsed = yaml.safe_load(text)
    except ImportError:
        parsed = None
    except Exception as exc:
        raise ContentReadError("YAML file is malformed") from exc
    return [VishnuBlock("structured", text.strip(), data=parsed)] if text.strip() else []


def read_rtf(data: bytes) -> list[VishnuBlock]:
    text = _decode_text(data, "RTF")
    if not text.lstrip().startswith(r"{\rtf"):
        raise ContentReadError("RTF file is malformed")
    text = re.sub(r"\\'[0-9a-fA-F]{2}", " ", text)
    text = re.sub(r"\\[a-zA-Z]+-?\d* ?", " ", text)
    text = text.replace("{", " ").replace("}", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return [VishnuBlock("paragraph", text)] if text else []


def read_eml(data: bytes) -> list[VishnuBlock]:
    try:
        message = BytesParser(policy=policy.default).parsebytes(data)
    except Exception as exc:
        raise ContentReadError("Email file could not be parsed safely") from exc
    blocks: list[VishnuBlock] = []
    for header in ("subject", "from", "to", "cc", "date", "message-id"):
        value = str(message.get(header) or "").strip()
        if value:
            blocks.append(VishnuBlock(
                "key_value",
                f"{header.title()}: {value}",
                SourceReference(field=header),
                data={"key": header, "value": value},
            ))
    part_number = 0
    for part in message.walk():
        if part.is_multipart():
            continue
        part_number += 1
        disposition = str(part.get_content_disposition() or "")
        if disposition == "attachment":
            filename = str(part.get_filename() or f"attachment-{part_number}")
            blocks.append(VishnuBlock(
                "attachment",
                filename,
                SourceReference(email_part=str(part_number), member=filename),
                data={"filename": filename, "content_type": part.get_content_type()},
            ))
            continue
        if part.get_content_type() == "text/plain":
            try:
                text = part.get_content()
            except Exception:
                payload = part.get_payload(decode=True) or b""
                text = _decode_text(payload, "Email body")
            text = str(text or "").strip()
            if text:
                blocks.append(VishnuBlock("paragraph", text, SourceReference(email_part=str(part_number))))
        elif part.get_content_type() == "text/html":
            payload = part.get_payload(decode=True) or b""
            for child in read_html(payload):
                child.source.email_part = str(part_number)
                blocks.append(child)
    return blocks


def _safe_zip_members(data: bytes):
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, OSError) as exc:
        raise ContentReadError("Archive is malformed") from exc
    members = archive.infolist()
    if len(members) > MAX_ARCHIVE_MEMBERS:
        archive.close()
        raise ContentReadError("Archive contains too many members")
    expanded = 0
    for member in members:
        name = str(member.filename or "").replace("\\", "/")
        parts = [part for part in name.split("/") if part not in {"", "."}]
        mode = (int(member.external_attr) >> 16) & 0o170000
        if name.startswith("/") or ".." in parts or mode == stat.S_IFLNK:
            archive.close()
            raise ContentReadError("Archive contains an unsafe path")
        size, compressed = int(member.file_size or 0), int(member.compress_size or 0)
        if size > MAX_ARCHIVE_MEMBER_BYTES:
            archive.close()
            raise ContentReadError("Archive member exceeds the safety limit")
        expanded += size
        if expanded > MAX_ARCHIVE_EXPANDED_BYTES:
            archive.close()
            raise ContentReadError("Archive expanded size exceeds the safety limit")
        if compressed > 0 and size > 0 and size / compressed > MAX_ARCHIVE_COMPRESSION_RATIO:
            archive.close()
            raise ContentReadError("Archive compression ratio exceeds the safety limit")
    return archive, members


def read_epub(data: bytes) -> list[VishnuBlock]:
    archive, members = _safe_zip_members(data)
    blocks: list[VishnuBlock] = []
    try:
        for member in members:
            name = member.filename
            if member.is_dir() or not name.lower().endswith((".xhtml", ".html", ".htm")):
                continue
            raw = archive.read(member)
            for child in read_html(raw):
                child.source.member = name
                child.metadata = {**child.metadata, "epub_member": name}
                blocks.append(child)
    finally:
        archive.close()
    return blocks


def read_zip(
    data: bytes,
    *,
    child_reader,
    max_children: int = 128,
) -> tuple[list[VishnuBlock], list[str]]:
    archive, members = _safe_zip_members(data)
    blocks: list[VishnuBlock] = []
    warnings: list[str] = []
    processed = 0
    try:
        for member in members:
            if member.is_dir():
                continue
            if processed >= max_children:
                warnings.append(f"Archive member processing stopped after {max_children} files")
                break
            processed += 1
            name = member.filename
            if member.flag_bits & 0x1:
                warnings.append(f"Encrypted archive member skipped: {name}")
                continue
            try:
                raw = archive.read(member)
                child = child_reader(name, raw)
            except Exception as exc:
                warnings.append(f"Archive member skipped: {name}: {type(exc).__name__}")
                continue
            for child_block in child.blocks:
                source = SourceReference(**child_block.source.compact())
                source.member = name
                blocks.append(VishnuBlock(
                    child_block.kind,
                    child_block.text,
                    source,
                    child_block.extraction_method,
                    child_block.confidence,
                    data=child_block.data,
                    metadata={**child_block.metadata, "archive_member": name, "child_document_id": child.document_id},
                ))
    finally:
        archive.close()
    return blocks, warnings



def read_pdf_form_fields(data: bytes) -> list[VishnuBlock]:
    """Extract embedded AcroForm fields locally while keeping field-level provenance."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data), strict=False)
        fields = reader.get_fields() or {}
    except Exception as exc:
        raise ContentReadError("PDF form fields could not be read safely") from exc
    blocks: list[VishnuBlock] = []
    for raw_name, raw_field in fields.items():
        name = str(raw_name or "").strip()
        if not name or not isinstance(raw_field, dict):
            continue
        raw_value = raw_field.get("/V")
        value = "" if raw_value is None else str(raw_value)
        field_type = str(raw_field.get("/FT") or "").lstrip("/").lower() or "unknown"
        blocks.append(VishnuBlock(
            "form_field",
            f"{name}: {value}" if value else name,
            SourceReference(field=name),
            data={"key": name, "value": value, "field_type": field_type, "embedded_pdf_form": True},
            metadata={"layout": "form_field", "native_pdf_form": True},
        ))
    return blocks


def _safe_tar_members(data: bytes):
    try:
        archive = tarfile.open(fileobj=io.BytesIO(data), mode="r:*")
    except (tarfile.TarError, OSError) as exc:
        raise ContentReadError("TAR archive is malformed") from exc
    members = archive.getmembers()
    if len(members) > MAX_ARCHIVE_MEMBERS:
        archive.close()
        raise ContentReadError("Archive contains too many members")
    expanded = 0
    for member in members:
        name = str(member.name or "").replace("\\", "/")
        parts = [part for part in name.split("/") if part not in {"", "."}]
        if name.startswith("/") or ".." in parts or member.issym() or member.islnk():
            archive.close()
            raise ContentReadError("Archive contains an unsafe path")
        size = int(member.size or 0)
        if size > MAX_ARCHIVE_MEMBER_BYTES:
            archive.close()
            raise ContentReadError("Archive member exceeds the safety limit")
        expanded += size
        if expanded > MAX_ARCHIVE_EXPANDED_BYTES:
            archive.close()
            raise ContentReadError("Archive expanded size exceeds the safety limit")
    return archive, members


def read_tar(data: bytes, *, child_reader, max_children: int = 128) -> tuple[list[VishnuBlock], list[str]]:
    archive, members = _safe_tar_members(data)
    blocks: list[VishnuBlock] = []
    warnings: list[str] = []
    processed = 0
    try:
        for member in members:
            if not member.isfile():
                continue
            if processed >= max_children:
                warnings.append(f"Archive member processing stopped after {max_children} files")
                break
            processed += 1
            name = member.name
            try:
                extracted = archive.extractfile(member)
                if extracted is None:
                    warnings.append(f"Archive member skipped: {name}: unreadable")
                    continue
                raw = extracted.read(MAX_ARCHIVE_MEMBER_BYTES + 1)
                if len(raw) > MAX_ARCHIVE_MEMBER_BYTES:
                    raise ContentReadError("Archive member exceeds the safety limit")
                child = child_reader(name, raw)
            except Exception as exc:
                warnings.append(f"Archive member skipped: {name}: {type(exc).__name__}")
                continue
            for child_block in child.blocks:
                source = SourceReference(**child_block.source.compact())
                source.member = name
                blocks.append(VishnuBlock(
                    child_block.kind,
                    child_block.text,
                    source,
                    child_block.extraction_method,
                    child_block.confidence,
                    data=child_block.data,
                    metadata={**child_block.metadata, "archive_member": name, "archive_type": "tar", "child_document_id": child.document_id},
                ))
    finally:
        archive.close()
    return blocks, warnings


def read_gzip(data: bytes, *, filename: str, child_reader) -> tuple[list[VishnuBlock], list[str]]:
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(data), mode="rb") as stream:
            raw = stream.read(MAX_ARCHIVE_EXPANDED_BYTES + 1)
    except (OSError, EOFError) as exc:
        raise ContentReadError("GZIP archive is malformed") from exc
    if len(raw) > MAX_ARCHIVE_EXPANDED_BYTES:
        raise ContentReadError("GZIP expanded size exceeds the safety limit")
    lower = filename.lower()
    if lower.endswith(".tar.gz"):
        child_name = filename[:-3]
    elif lower.endswith(".tgz"):
        child_name = filename[:-4] + ".tar"
    elif lower.endswith(".gz"):
        child_name = filename[:-3] or "content"
    else:
        child_name = "content"
    try:
        child = child_reader(child_name, raw)
    except Exception as exc:
        raise ContentReadError(f"GZIP payload could not be read safely: {type(exc).__name__}") from exc
    blocks: list[VishnuBlock] = []
    for child_block in child.blocks:
        source = SourceReference(**child_block.source.compact())
        source.member = child_name
        blocks.append(VishnuBlock(
            child_block.kind,
            child_block.text,
            source,
            child_block.extraction_method,
            child_block.confidence,
            data=child_block.data,
            metadata={**child_block.metadata, "archive_member": child_name, "archive_type": "gzip", "child_document_id": child.document_id},
        ))
    return blocks, list(child.warnings)
