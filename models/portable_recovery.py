from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
from typing import Any, Iterable, Mapping
from uuid import uuid4
import zipfile

from models.portable_intelligence import IntelligenceManifest


_BUNDLE_SCHEMA_VERSION = 1
_BUNDLE_MANIFEST_NAME = "bundle-manifest.json"
_PAYLOAD_PREFIX = "payload/"
_MAX_MANIFEST_BYTES = 4 * 1024 * 1024
_DEFAULT_MAX_FILES = 100_000
_DEFAULT_MAX_TOTAL_BYTES = 128 * 1024 * 1024 * 1024
_FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = sha256()
    size = 0
    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            size += len(block)
            digest.update(block)
    return digest.hexdigest(), size


def _safe_relative_name(value: str | Path) -> str:
    raw = str(value)
    if not raw or "\x00" in raw or "\\" in raw:
        raise ValueError("recovery paths must be non-empty POSIX-style relative paths")
    path = PurePosixPath(raw)
    if path.is_absolute() or raw.startswith("/"):
        raise ValueError("recovery paths must be relative")
    parts = path.parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("recovery path traversal is not allowed")
    if ":" in parts[0]:
        raise ValueError("drive-qualified recovery paths are not allowed")
    normalized = path.as_posix()
    if normalized in {".", ""}:
        raise ValueError("recovery path is required")
    return normalized


def _component_name(value: str) -> str:
    normalized = str(value).strip()
    if not normalized or len(normalized) > 128:
        raise ValueError("recovery component name is required and must be at most 128 characters")
    if any(ord(char) < 32 for char in normalized):
        raise ValueError("recovery component name cannot contain control characters")
    return normalized


def _regular_zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(filename=name, date_time=_FIXED_ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o600) << 16
    return info


def _reject_unsafe_zip_member(info: zipfile.ZipInfo) -> None:
    if info.flag_bits & 0x1:
        raise ValueError("encrypted recovery archive members are not supported")
    name = info.filename
    if name == _BUNDLE_MANIFEST_NAME:
        pass
    elif name.startswith(_PAYLOAD_PREFIX):
        _safe_relative_name(name[len(_PAYLOAD_PREFIX) :])
    else:
        raise ValueError(f"unexpected recovery archive member: {name}")
    mode = info.external_attr >> 16
    if mode and stat.S_ISLNK(mode):
        raise ValueError("recovery archive symlinks are not allowed")
    if mode and not stat.S_ISREG(mode):
        raise ValueError("recovery archive contains a non-regular member")
    if info.is_dir():
        raise ValueError("recovery archive directory entries are not allowed")


def _assert_no_symlink_chain(root: Path, relative_name: str) -> Path:
    current = root
    for part in PurePosixPath(relative_name).parts:
        current = current / part
        if current.exists() or current.is_symlink():
            if current.is_symlink():
                raise ValueError("recovery source or destination cannot traverse symlinks")
    return current


@dataclass(frozen=True)
class RecoveryFile:
    path: str
    component: str
    size_bytes: int
    sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _safe_relative_name(self.path))
        object.__setattr__(self, "component", _component_name(self.component))
        if self.size_bytes < 0:
            raise ValueError("recovery file size cannot be negative")
        digest = self.sha256.strip().lower()
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError("recovery file sha256 must be a 64-character hexadecimal digest")
        object.__setattr__(self, "sha256", digest)

    def public(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "component": self.component,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class RecoveryBundleManifest:
    schema_version: int
    bundle_id: str
    fingerprint: str
    created_at: str
    owner_id: str
    intelligence_manifest: dict[str, Any]
    files: tuple[RecoveryFile, ...]

    @staticmethod
    def _files(values: Iterable[RecoveryFile]) -> tuple[RecoveryFile, ...]:
        files = tuple(sorted(tuple(values), key=lambda item: item.path))
        names = [item.path for item in files]
        if len(names) != len(set(names)):
            raise ValueError("recovery bundle file paths must be unique")
        return files

    @classmethod
    def create(
        cls,
        *,
        intelligence_manifest: IntelligenceManifest,
        files: Iterable[RecoveryFile],
        created_at: str | None = None,
    ) -> "RecoveryBundleManifest":
        intelligence_manifest.verify()
        normalized_files = cls._files(files)
        timestamp = str(created_at or _now())
        embedded = intelligence_manifest.public()
        unsigned = {
            "schema_version": _BUNDLE_SCHEMA_VERSION,
            "created_at": timestamp,
            "owner_id": intelligence_manifest.owner_id,
            "intelligence_manifest": embedded,
            "files": [item.public() for item in normalized_files],
        }
        fingerprint = sha256(_canonical_json(unsigned).encode("utf-8")).hexdigest()
        return cls(
            schema_version=_BUNDLE_SCHEMA_VERSION,
            bundle_id=f"vir-{fingerprint[:24]}",
            fingerprint=fingerprint,
            created_at=timestamp,
            owner_id=intelligence_manifest.owner_id,
            intelligence_manifest=embedded,
            files=normalized_files,
        )

    def unsigned(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "owner_id": self.owner_id,
            "intelligence_manifest": dict(self.intelligence_manifest),
            "files": [item.public() for item in self._files(self.files)],
        }

    def verify(self) -> IntelligenceManifest:
        if self.schema_version != _BUNDLE_SCHEMA_VERSION:
            raise ValueError("unsupported recovery bundle manifest schema")
        embedded = IntelligenceManifest.from_dict(self.intelligence_manifest)
        if embedded.owner_id != self.owner_id:
            raise RuntimeError("recovery bundle owner mismatch")
        expected = sha256(_canonical_json(self.unsigned()).encode("utf-8")).hexdigest()
        if expected != self.fingerprint:
            raise RuntimeError("recovery bundle fingerprint mismatch")
        if self.bundle_id != f"vir-{expected[:24]}":
            raise RuntimeError("recovery bundle id mismatch")
        return embedded

    def public(self) -> dict[str, Any]:
        self.verify()
        payload = self.unsigned()
        payload.update({"bundle_id": self.bundle_id, "fingerprint": self.fingerprint})
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RecoveryBundleManifest":
        if int(payload.get("schema_version", 0)) != _BUNDLE_SCHEMA_VERSION:
            raise ValueError("unsupported recovery bundle manifest schema")
        raw_files = payload.get("files") or ()
        if not isinstance(raw_files, (list, tuple)):
            raise ValueError("recovery bundle files must be a list")
        embedded = payload.get("intelligence_manifest")
        if not isinstance(embedded, Mapping):
            raise ValueError("recovery bundle intelligence_manifest must be an object")
        manifest = cls(
            schema_version=_BUNDLE_SCHEMA_VERSION,
            bundle_id=str(payload.get("bundle_id") or ""),
            fingerprint=str(payload.get("fingerprint") or ""),
            created_at=str(payload.get("created_at") or ""),
            owner_id=str(payload.get("owner_id") or ""),
            intelligence_manifest=dict(embedded),
            files=cls._files(RecoveryFile(**dict(item)) for item in raw_files),
        )
        if not manifest.created_at.strip() or not manifest.owner_id.strip():
            raise ValueError("recovery bundle created_at and owner_id are required")
        manifest.verify()
        return manifest


class PortableRecoveryBundle:
    """Verified transport for prepared Vishnu recovery snapshots.

    This layer never discovers or copies a live Vishnu data directory on its own.
    Callers must explicitly provide prepared snapshot paths grouped by component.
    That keeps transactionally-consistent SQLite snapshots, secret filtering and
    provider-specific model artifact export in their canonical subsystems.
    """

    @staticmethod
    def _collect_source_files(
        source_root: Path,
        components: Mapping[str, Iterable[str | Path]],
    ) -> tuple[tuple[RecoveryFile, Path], ...]:
        if source_root.is_symlink() or not source_root.is_dir():
            raise ValueError("recovery source_root must be a real directory")
        collected: dict[str, tuple[RecoveryFile, Path]] = {}
        for raw_component, requested_paths in components.items():
            component = _component_name(raw_component)
            for requested in requested_paths:
                relative_name = _safe_relative_name(requested)
                source = _assert_no_symlink_chain(source_root, relative_name)
                if not source.exists():
                    raise FileNotFoundError(relative_name)
                candidates: list[tuple[str, Path]] = []
                if source.is_file():
                    candidates.append((relative_name, source))
                elif source.is_dir():
                    for walk_root, dirnames, filenames in os.walk(source, followlinks=False):
                        walk_path = Path(walk_root)
                        for name in tuple(dirnames) + tuple(filenames):
                            entry = walk_path / name
                            if entry.is_symlink():
                                raise ValueError("recovery source cannot contain symlinks")
                        for filename in filenames:
                            entry = walk_path / filename
                            if not entry.is_file():
                                raise ValueError("recovery source can contain only regular files")
                            rel = entry.relative_to(source_root).as_posix()
                            candidates.append((_safe_relative_name(rel), entry))
                else:
                    raise ValueError("recovery source can contain only regular files and directories")

                for rel, file_path in candidates:
                    if rel in collected:
                        raise ValueError(f"recovery file is assigned more than once: {rel}")
                    digest, size = _sha256_file(file_path)
                    collected[rel] = (
                        RecoveryFile(path=rel, component=component, size_bytes=size, sha256=digest),
                        file_path,
                    )
        return tuple(collected[name] for name in sorted(collected))

    @classmethod
    def create(
        cls,
        *,
        source_root: str | Path,
        output_path: str | Path,
        intelligence_manifest: IntelligenceManifest,
        components: Mapping[str, Iterable[str | Path]],
        created_at: str | None = None,
        overwrite: bool = False,
    ) -> RecoveryBundleManifest:
        intelligence_manifest.verify()
        source = Path(source_root).expanduser()
        output = Path(output_path).expanduser()
        if output.exists() or output.is_symlink():
            if not overwrite:
                raise FileExistsError(output)
            if output.is_symlink() or not output.is_file():
                raise ValueError("existing recovery output must be a regular file")
        source_files = cls._collect_source_files(source, components)
        bundle_manifest = RecoveryBundleManifest.create(
            intelligence_manifest=intelligence_manifest,
            files=(item for item, _ in source_files),
            created_at=created_at,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        temp = output.with_name(f".{output.name}.{uuid4().hex}.tmp")
        try:
            with zipfile.ZipFile(temp, mode="w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
                manifest_bytes = (json.dumps(bundle_manifest.public(), sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
                archive.writestr(_regular_zip_info(_BUNDLE_MANIFEST_NAME), manifest_bytes)
                for recovery_file, file_path in source_files:
                    info = _regular_zip_info(f"{_PAYLOAD_PREFIX}{recovery_file.path}")
                    with file_path.open("rb") as source_handle, archive.open(info, mode="w") as archive_handle:
                        shutil.copyfileobj(source_handle, archive_handle, length=1024 * 1024)
            cls.verify(temp, expected_manifest=intelligence_manifest)
            temp.replace(output)
        finally:
            if temp.exists():
                temp.unlink()
        return bundle_manifest

    @staticmethod
    def _read_manifest(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> RecoveryBundleManifest:
        if info.file_size > _MAX_MANIFEST_BYTES:
            raise ValueError("recovery bundle manifest is too large")
        try:
            payload = json.loads(archive.read(info).decode("utf-8"))
        except Exception as exc:
            raise ValueError("recovery bundle manifest is unreadable") from exc
        if not isinstance(payload, dict):
            raise ValueError("recovery bundle manifest must be an object")
        return RecoveryBundleManifest.from_dict(payload)

    @classmethod
    def verify(
        cls,
        bundle_path: str | Path,
        *,
        expected_manifest: IntelligenceManifest | None = None,
        max_files: int = _DEFAULT_MAX_FILES,
        max_total_bytes: int = _DEFAULT_MAX_TOTAL_BYTES,
    ) -> RecoveryBundleManifest:
        path = Path(bundle_path).expanduser()
        if path.is_symlink() or not path.is_file():
            raise ValueError("recovery bundle must be a real file")
        if max_files <= 0 or max_total_bytes < 0:
            raise ValueError("recovery verification limits are invalid")
        try:
            with zipfile.ZipFile(path, mode="r") as archive:
                infos = archive.infolist()
                names = [info.filename for info in infos]
                if len(names) != len(set(names)):
                    raise ValueError("recovery archive contains duplicate members")
                for info in infos:
                    _reject_unsafe_zip_member(info)
                if _BUNDLE_MANIFEST_NAME not in names:
                    raise ValueError("recovery bundle manifest is missing")
                manifest_info = archive.getinfo(_BUNDLE_MANIFEST_NAME)
                manifest = cls._read_manifest(archive, manifest_info)
                embedded = manifest.verify()
                if expected_manifest is not None:
                    expected_manifest.verify()
                    if (
                        embedded.manifest_id != expected_manifest.manifest_id
                        or embedded.fingerprint != expected_manifest.fingerprint
                        or embedded.owner_id != expected_manifest.owner_id
                    ):
                        raise RuntimeError("recovery bundle intelligence manifest mismatch")

                if len(manifest.files) > max_files:
                    raise ValueError("recovery bundle exceeds file-count limit")
                expected_names = {_BUNDLE_MANIFEST_NAME}
                expected_names.update(f"{_PAYLOAD_PREFIX}{item.path}" for item in manifest.files)
                if set(names) != expected_names:
                    raise ValueError("recovery archive members do not match its manifest")

                total_size = sum(item.size_bytes for item in manifest.files)
                if total_size > max_total_bytes:
                    raise ValueError("recovery bundle exceeds uncompressed-size limit")

                for item in manifest.files:
                    info = archive.getinfo(f"{_PAYLOAD_PREFIX}{item.path}")
                    if info.file_size != item.size_bytes:
                        raise RuntimeError(f"recovery file size mismatch: {item.path}")
                    digest = sha256()
                    size = 0
                    with archive.open(info, mode="r") as handle:
                        while True:
                            block = handle.read(1024 * 1024)
                            if not block:
                                break
                            size += len(block)
                            digest.update(block)
                    if size != item.size_bytes or digest.hexdigest() != item.sha256:
                        raise RuntimeError(f"recovery file hash mismatch: {item.path}")
                return manifest
        except zipfile.BadZipFile as exc:
            raise ValueError("recovery bundle is not a valid ZIP archive") from exc

    @classmethod
    def restore(
        cls,
        bundle_path: str | Path,
        *,
        destination_root: str | Path,
        expected_manifest: IntelligenceManifest | None = None,
        overwrite: bool = False,
        max_files: int = _DEFAULT_MAX_FILES,
        max_total_bytes: int = _DEFAULT_MAX_TOTAL_BYTES,
    ) -> RecoveryBundleManifest:
        manifest = cls.verify(
            bundle_path,
            expected_manifest=expected_manifest,
            max_files=max_files,
            max_total_bytes=max_total_bytes,
        )
        destination = Path(destination_root).expanduser()
        if destination.is_symlink():
            raise ValueError("recovery destination cannot be a symlink")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and not destination.is_dir():
            raise ValueError("recovery destination must be a directory")

        targets: list[tuple[RecoveryFile, Path]] = []
        for item in manifest.files:
            target = _assert_no_symlink_chain(destination, item.path)
            if target.exists() or target.is_symlink():
                if target.is_symlink() or target.is_dir():
                    raise ValueError(f"recovery target is not a regular file: {item.path}")
                if not overwrite:
                    raise FileExistsError(target)
            targets.append((item, target))

        stage_parent = destination.parent
        with tempfile.TemporaryDirectory(prefix=f".{destination.name}.restore-", dir=stage_parent) as stage_name:
            stage = Path(stage_name)
            with zipfile.ZipFile(Path(bundle_path).expanduser(), mode="r") as archive:
                for item, _ in targets:
                    staged = stage / PurePosixPath(item.path)
                    staged.parent.mkdir(parents=True, exist_ok=True)
                    digest = sha256()
                    size = 0
                    with archive.open(f"{_PAYLOAD_PREFIX}{item.path}", mode="r") as source_handle, staged.open("wb") as target_handle:
                        while True:
                            block = source_handle.read(1024 * 1024)
                            if not block:
                                break
                            size += len(block)
                            digest.update(block)
                            target_handle.write(block)
                    if size != item.size_bytes or digest.hexdigest() != item.sha256:
                        raise RuntimeError(f"recovery file changed during restore: {item.path}")

            destination.mkdir(parents=True, exist_ok=True)
            for item, target in targets:
                _assert_no_symlink_chain(destination, item.path)
                target.parent.mkdir(parents=True, exist_ok=True)
                staged = stage / PurePosixPath(item.path)
                os.replace(staged, target)
        return manifest
