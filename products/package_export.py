from __future__ import annotations

import io
import json
import re
import zipfile
from datetime import datetime, timezone

from .signing import canonical_json, sha256_bytes, sign_payload


_SAFE_NAME = re.compile(r"[^a-zA-Z0-9._-]+")


def package_filename(name: str, version: str) -> str:
    stem = _SAFE_NAME.sub("-", str(name).strip()).strip("-._") or "vishnu-product"
    version_stem = _SAFE_NAME.sub("-", str(version).strip()).strip("-._") or "0.0.0"
    return f"{stem}-{version_stem}.vishnu-product"


def build_portable_package(manifest: dict, *, require_signature: bool = True) -> tuple[str, bytes, dict]:
    """Build a deterministic, secret-free Vishnu portable product package.

    A .vishnu-product file is a ZIP-compatible envelope containing only the
    canonical product contract and integrity/signature metadata. It intentionally
    does not copy the full Vishnu source tree, owner data, credentials, or other
    clients' state.
    """
    manifest_bytes = canonical_json(manifest)
    manifest_sha = sha256_bytes(manifest_bytes)
    signature = sign_payload(manifest_bytes, require_key=require_signature)
    created_at = datetime.now(timezone.utc).isoformat()
    metadata = {
        "schema": "vishnu.portable-product/v1",
        "product_id": manifest.get("product_id"),
        "name": manifest.get("name"),
        "version": manifest.get("version"),
        "created_at": created_at,
        "manifest_sha256": manifest_sha,
        "signed": signature is not None,
        "signature": signature.as_dict() if signature else None,
    }
    metadata_bytes = canonical_json(metadata)
    checksums = {
        "manifest.json": manifest_sha,
        "package.json": sha256_bytes(metadata_bytes),
    }
    checksums_bytes = canonical_json(checksums)

    output = io.BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        # Fixed ZIP timestamps keep the payload reproducible apart from package.json created_at.
        for filename, payload in (
            ("manifest.json", manifest_bytes),
            ("package.json", metadata_bytes),
            ("checksums.json", checksums_bytes),
        ):
            info = zipfile.ZipInfo(filename, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, payload)
    raw = output.getvalue()
    metadata["package_sha256"] = sha256_bytes(raw)
    metadata["size"] = len(raw)
    return package_filename(str(manifest.get("name") or "vishnu-product"), str(manifest.get("version") or "0.0.0")), raw, metadata


def inspect_portable_package(raw: bytes) -> dict:
    """Read and validate package checksums; signature verification is caller-controlled."""
    with zipfile.ZipFile(io.BytesIO(raw), mode="r") as archive:
        names = set(archive.namelist())
        expected = {"manifest.json", "package.json", "checksums.json"}
        if names != expected:
            raise ValueError("Portable product package contains unexpected files")
        manifest_bytes = archive.read("manifest.json")
        metadata_bytes = archive.read("package.json")
        checksums = json.loads(archive.read("checksums.json"))
        if checksums.get("manifest.json") != sha256_bytes(manifest_bytes):
            raise ValueError("Portable product manifest checksum mismatch")
        if checksums.get("package.json") != sha256_bytes(metadata_bytes):
            raise ValueError("Portable product metadata checksum mismatch")
        return {
            "manifest": json.loads(manifest_bytes),
            "package": json.loads(metadata_bytes),
            "checksums": checksums,
        }
