from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

from .runtime import ProductRuntimeSpec


PACKAGE_EXTENSION = ".vishnu-product"


def _json_bytes(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def create_package(spec: ProductRuntimeSpec, output_path: str | Path) -> dict:
    """Create the portable intermediate product package consumed by target builders.

    This is not a native APK/EXE itself. It is the credential-free, deterministic
    package from which platform adapters build native artifacts. Only validated,
    explicitly declared product data is written.
    """
    path = Path(output_path)
    if path.suffix != PACKAGE_EXTENSION:
        path = path.with_suffix(PACKAGE_EXTENSION)
    path.parent.mkdir(parents=True, exist_ok=True)

    manifest_bytes = _json_bytes(spec.manifest)
    descriptor_bytes = _json_bytes(spec.export_descriptor())
    integrity = {
        "schema": "vishnu.package.integrity/v1",
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "descriptor_sha256": hashlib.sha256(descriptor_bytes).hexdigest(),
    }
    integrity_bytes = _json_bytes(integrity)

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", manifest_bytes)
        archive.writestr("runtime-descriptor.json", descriptor_bytes)
        archive.writestr("integrity.json", integrity_bytes)

    package_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "path": str(path),
        "sha256": package_sha,
        "manifest_sha256": integrity["manifest_sha256"],
        "product_id": spec.product_id,
        "version": spec.version,
    }


def inspect_package(path: str | Path) -> ProductRuntimeSpec:
    source = Path(path)
    with zipfile.ZipFile(source, "r") as archive:
        names = set(archive.namelist())
        required = {"manifest.json", "runtime-descriptor.json", "integrity.json"}
        if names != required:
            raise ValueError("Unexpected product package contents")
        manifest_bytes = archive.read("manifest.json")
        descriptor_bytes = archive.read("runtime-descriptor.json")
        integrity = json.loads(archive.read("integrity.json"))
    if hashlib.sha256(manifest_bytes).hexdigest() != integrity.get("manifest_sha256"):
        raise ValueError("Product manifest integrity check failed")
    if hashlib.sha256(descriptor_bytes).hexdigest() != integrity.get("descriptor_sha256"):
        raise ValueError("Product descriptor integrity check failed")
    manifest = json.loads(manifest_bytes)
    return ProductRuntimeSpec.load(manifest)
