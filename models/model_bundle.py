from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
from typing import Any, Mapping
from uuid import uuid4
import zipfile


_BUNDLE_SCHEMA_VERSION = 1
_BUNDLE_MANIFEST = "portable-model-bundle.json"
_ARTIFACT_MANIFEST = "artifact-manifest.json"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = sha256()
    size = 0
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


def checkpoint_inventory(root: str | Path) -> tuple[dict[str, Any], ...]:
    """Return the canonical file inventory used by Vishnu model artifacts.

    The store's own absolute-path manifest is excluded so a portable bundle never
    leaks the source host path and the inventory digest stays equal to the
    canonical ModelArtifactStore digest.
    """

    base = Path(root).expanduser().resolve()
    if not base.is_dir() or base.is_symlink():
        raise ValueError("checkpoint bundle source must be a real directory")
    files: list[dict[str, Any]] = []
    for item in sorted(base.rglob("*"), key=lambda value: value.as_posix()):
        if item.is_symlink():
            raise ValueError("symbolic links are not permitted in portable model bundles")
        if not item.is_file():
            continue
        relative = item.resolve().relative_to(base).as_posix()
        if not relative or relative.startswith("../") or "/.." in relative:
            raise ValueError("checkpoint file escaped bundle root")
        if relative == _ARTIFACT_MANIFEST:
            continue
        digest, size = _sha256_file(item)
        files.append({"path": relative, "size": size, "sha256": digest})
    if not files:
        raise ValueError("checkpoint bundle source contains no model files")
    return tuple(files)


def checkpoint_inventory_sha256(root: str | Path) -> str:
    inventory = checkpoint_inventory(root)
    return sha256(_canonical_json(list(inventory)).encode("utf-8")).hexdigest()


def _write_zip_entry(archive: zipfile.ZipFile, relative: str, source: Path) -> None:
    info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = 0o600 << 16
    with archive.open(info, "w", force_zip64=True) as destination, source.open("rb") as handle:
        shutil.copyfileobj(handle, destination, 1024 * 1024)


def _write_bytes_entry(archive: zipfile.ZipFile, relative: str, payload: bytes) -> None:
    info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = 0o600 << 16
    archive.writestr(info, payload)


@dataclass(frozen=True)
class PortableModelBundle:
    path: Path
    bundle_sha256: str
    size_bytes: int
    inventory_sha256: str
    files: tuple[dict[str, Any], ...]

    def public(self) -> dict[str, Any]:
        return {
            "bundle_sha256": self.bundle_sha256,
            "size_bytes": self.size_bytes,
            "inventory_sha256": self.inventory_sha256,
            "files": [dict(item) for item in self.files],
        }


def create_portable_model_bundle(
    checkpoint_root: str | Path,
    target: str | Path,
    *,
    model_id: str,
    expected_inventory_sha256: str | None = None,
) -> PortableModelBundle:
    """Create a deterministic single-file transport for a checkpoint directory."""

    source = Path(checkpoint_root).expanduser().resolve()
    inventory = checkpoint_inventory(source)
    inventory_sha = sha256(_canonical_json(list(inventory)).encode("utf-8")).hexdigest()
    expected = str(expected_inventory_sha256 or "").strip().lower()
    if expected and expected != inventory_sha:
        raise RuntimeError("checkpoint inventory does not match canonical model artifact digest")

    destination = Path(target).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": _BUNDLE_SCHEMA_VERSION,
        "model_id": str(model_id),
        "inventory_sha256": inventory_sha,
        "files": [dict(item) for item in inventory],
    }
    manifest_bytes = (_canonical_json(manifest) + "\n").encode("utf-8")

    if not destination.exists():
        temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
        try:
            with zipfile.ZipFile(temporary, mode="w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
                for entry in inventory:
                    _write_zip_entry(archive, str(entry["path"]), source / str(entry["path"]))
                _write_bytes_entry(archive, _BUNDLE_MANIFEST, manifest_bytes)
            try:
                os.chmod(temporary, 0o600)
            except OSError:
                pass
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)

    return verify_portable_model_bundle(
        destination,
        expected_model_id=str(model_id),
        expected_inventory_sha256=inventory_sha,
    )


def _safe_bundle_member(name: str) -> str:
    raw = str(name)
    path = Path(raw)
    if not raw or path.is_absolute() or ".." in path.parts or raw.startswith(("/", "\\")):
        raise ValueError("portable model bundle member path is unsafe")
    return path.as_posix()


def verify_portable_model_bundle(
    path: str | Path,
    *,
    expected_model_id: str | None = None,
    expected_inventory_sha256: str | None = None,
) -> PortableModelBundle:
    bundle = Path(path).expanduser().resolve()
    if not bundle.is_file() or bundle.is_symlink():
        raise ValueError("portable model bundle must be a real regular file")
    bundle_sha, bundle_size = _sha256_file(bundle)
    with zipfile.ZipFile(bundle, mode="r") as archive:
        infos = archive.infolist()
        names = [_safe_bundle_member(info.filename) for info in infos]
        if len(names) != len(set(names)):
            raise RuntimeError("portable model bundle contains duplicate members")
        if _BUNDLE_MANIFEST not in names:
            raise ValueError("portable model bundle manifest is missing")
        try:
            manifest = json.loads(archive.read(_BUNDLE_MANIFEST).decode("utf-8"))
        except Exception as exc:
            raise ValueError("portable model bundle manifest is unreadable") from exc
        if not isinstance(manifest, Mapping) or int(manifest.get("schema_version", 0)) != _BUNDLE_SCHEMA_VERSION:
            raise ValueError("unsupported portable model bundle schema")
        model_id = str(manifest.get("model_id") or "")
        if expected_model_id is not None and model_id != str(expected_model_id):
            raise RuntimeError("portable model bundle model id mismatch")
        raw_files = manifest.get("files") or ()
        if not isinstance(raw_files, list):
            raise ValueError("portable model bundle file inventory is invalid")
        recorded: list[dict[str, Any]] = []
        expected_names = {_BUNDLE_MANIFEST}
        for item in raw_files:
            if not isinstance(item, Mapping):
                raise ValueError("portable model bundle file record is invalid")
            relative = _safe_bundle_member(str(item.get("path") or ""))
            expected_names.add(relative)
            data = archive.read(relative)
            digest = sha256(data).hexdigest()
            size = len(data)
            if digest != str(item.get("sha256") or "") or size != int(item.get("size", -1)):
                raise RuntimeError(f"portable model bundle integrity failure: {relative}")
            recorded.append({"path": relative, "size": size, "sha256": digest})
        if set(names) != expected_names:
            raise RuntimeError("portable model bundle contains unexpected or missing members")
        inventory = tuple(recorded)
        inventory_sha = sha256(_canonical_json(list(inventory)).encode("utf-8")).hexdigest()
        if inventory_sha != str(manifest.get("inventory_sha256") or ""):
            raise RuntimeError("portable model bundle inventory digest mismatch")
        if expected_inventory_sha256 is not None and inventory_sha != str(expected_inventory_sha256).lower():
            raise RuntimeError("portable model bundle does not match expected model artifact")
    return PortableModelBundle(
        path=bundle,
        bundle_sha256=bundle_sha,
        size_bytes=bundle_size,
        inventory_sha256=inventory_sha,
        files=inventory,
    )
