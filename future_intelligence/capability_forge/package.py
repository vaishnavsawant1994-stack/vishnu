from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import CapabilityPlan, CapabilityRisk, CapabilityRoute, CapabilitySpec


_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9._-]+)?$")
_SAFE_ID_RE = re.compile(r"[^a-z0-9._-]+")


def _canonical_json(data: dict[str, Any]) -> bytes:
    return (json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _safe_capability_id(spec: CapabilitySpec) -> str:
    explicit = str(dict(spec.metadata or {}).get("capability_id") or "").strip().lower()
    if explicit:
        candidate = _SAFE_ID_RE.sub("-", explicit).strip("-._")
    else:
        name = _SAFE_ID_RE.sub("-", spec.name.lower()).strip("-._") or "capability"
        digest = hashlib.sha256(spec.id.encode("utf-8")).hexdigest()[:12]
        candidate = f"generated.{name}.{digest}"
    if not candidate or len(candidate) > 160:
        raise ValueError("invalid generated capability id")
    return candidate


@dataclass(frozen=True)
class PackagedCapability:
    capability_id: str
    version: str
    package_path: Path
    manifest_path: Path
    manifest: dict[str, Any]
    manifest_digest: str
    build_id: str

    def catalog_payload(self, *, package_ref: str, state: str = "active") -> dict[str, Any]:
        return {
            "id": self.capability_id,
            "category": "Generated",
            "name": self.manifest["name"],
            "type": "generated_capability",
            "version": self.version,
            "runtime": self.manifest["runtime"],
            "entrypoint": self.manifest["entrypoint"],
            "input_schema": self.manifest["input_schema"],
            "output_schema": self.manifest["output_schema"],
            "permissions": self.manifest["permissions"],
            "risk": self.manifest["risk"],
            "package_ref": str(package_ref),
            "manifest_digest": self.manifest_digest,
            "build_id": self.build_id,
            "state": str(state),
            "execution_supported": True,
            "forge": dict(self.manifest["forge"]),
        }


class CapabilityPackageBuilder:
    """Create immutable versioned packages only from qualified Forge candidates."""

    MAX_FILES = 32
    MAX_FILE_BYTES = 500_000
    MAX_TOTAL_BYTES = 2_000_000

    @staticmethod
    def _inside(root: Path, path: Path) -> bool:
        root_resolved = root.resolve()
        path_resolved = path.resolve()
        return path_resolved == root_resolved or root_resolved in path_resolved.parents

    @staticmethod
    def _qualified(execution_result) -> bool:
        qualification = dict(getattr(execution_result, "qualification", {}) or {})
        review = dict(getattr(execution_result, "review", {}) or {})
        return (
            bool(getattr(execution_result, "qualified", False))
            or (
                str(getattr(execution_result, "status", "")) == "qualified"
                and bool(qualification.get("qualified"))
            )
        ) and str(review.get("decision", "approved")) == "approved"

    def build(
        self,
        *,
        spec: CapabilitySpec,
        plan: CapabilityPlan,
        execution_result,
        workspace_root: str | Path,
        source_root: str | Path,
        output_root: str | Path,
        version: str = "1.0.0",
        entrypoint: str | None = None,
    ) -> PackagedCapability:
        if plan.spec_id != spec.id:
            raise ValueError("Forge plan does not belong to the supplied capability specification")
        if plan.route is not CapabilityRoute.GENERATED:
            raise PermissionError("only generated capability routes can produce runtime packages")
        if not self._qualified(execution_result):
            raise PermissionError("only independently reviewed qualified candidates can be packaged")
        version = str(version or "").strip()
        if not _VERSION_RE.fullmatch(version):
            raise ValueError("version must be semantic x.y.z")
        workspace = Path(workspace_root).resolve()
        source = (workspace / Path(source_root)).resolve() if not Path(source_root).is_absolute() else Path(source_root).resolve()
        if not self._inside(workspace, source):
            raise PermissionError("capability source root escapes the engineering workspace")
        if not source.is_dir():
            raise FileNotFoundError(source)

        candidate_revision = str(getattr(execution_result, "candidate_revision", "") or "").strip()
        attempt_id = str(getattr(execution_result, "attempt_id", "") or "").strip()
        work_order_id = str(getattr(execution_result, "work_order_id", "") or "").strip()
        if not candidate_revision or not attempt_id or not work_order_id:
            raise ValueError("qualified execution result is missing candidate lineage")

        changed = tuple(str(item).replace("\\", "/") for item in getattr(execution_result, "changed_paths", ()) or ())
        source_relative = source.relative_to(workspace).as_posix().rstrip("/")
        files: list[tuple[str, Path, int]] = []
        total = 0
        for item in changed:
            rel = item.strip().lstrip("./")
            if not rel or rel == source_relative:
                continue
            prefix = source_relative + "/"
            if not rel.startswith(prefix):
                continue
            local_rel = rel[len(prefix):]
            src = (source / local_rel).resolve()
            if not self._inside(source, src) or not src.is_file() or src.is_symlink():
                continue
            size = src.stat().st_size
            if size > self.MAX_FILE_BYTES:
                raise ValueError(f"generated capability file exceeds size limit: {local_rel}")
            total += size
            if total > self.MAX_TOTAL_BYTES:
                raise ValueError("generated capability package exceeds total size limit")
            files.append((local_rel, src, size))
        if not files:
            raise ValueError("qualified candidate has no generated source files inside source_root")
        if len(files) > self.MAX_FILES:
            raise ValueError("generated capability package contains too many files")

        entry = str(entrypoint or dict(spec.metadata or {}).get("entrypoint") or "capability.py:run").strip()
        if ":" not in entry:
            raise ValueError("entrypoint must use relative_file.py:function syntax")
        entry_file, entry_function = entry.rsplit(":", 1)
        if not entry_file or not entry_function or entry_file.startswith("/") or ".." in Path(entry_file).parts:
            raise ValueError("invalid generated capability entrypoint")
        packaged_names = {name for name, _src, _size in files}
        if entry_file not in packaged_names:
            raise ValueError("entrypoint file is not part of the qualified generated candidate")

        risk = plan.risk.risk.value if plan.risk is not None else CapabilityRisk.WRITE.value
        qualification = dict(getattr(execution_result, "qualification", {}) or {})
        qualification_digest = hashlib.sha256(_canonical_json(qualification)).hexdigest()
        capability_id = _safe_capability_id(spec)
        build_id = f"build:{attempt_id}"
        manifest = {
            "schema_version": 1,
            "id": capability_id,
            "name": spec.name,
            "version": version,
            "type": "generated_capability",
            "runtime": "pure_python_v1",
            "entrypoint": {"file": entry_file, "function": entry_function},
            "input_schema": dict(spec.inputs or {}),
            "output_schema": dict(spec.outputs or {}),
            "permissions": {
                "network_hosts": list(spec.network_hosts),
                "filesystem_read": list(spec.filesystem_read),
                "filesystem_write": list(spec.filesystem_write),
                "secret_names": list(spec.secret_names),
                "connector_ids": list(spec.connector_ids),
                "side_effects": list(spec.side_effects),
                "background_allowed": bool(spec.background_allowed),
                "ui_required": bool(spec.ui_required),
            },
            "risk": risk,
            "source_files": [name for name, _src, _size in sorted(files)],
            "forge": {
                "spec_id": spec.id,
                "plan_id": plan.id,
                "work_order_id": work_order_id,
                "attempt_id": attempt_id,
                "candidate_revision": candidate_revision,
                "qualification_digest": qualification_digest,
                "qualified": True,
                "review_decision": "approved",
                "build_id": build_id,
            },
        }

        output = Path(output_root)
        output.mkdir(parents=True, exist_ok=True)
        target = output / capability_id / version
        manifest_bytes = _canonical_json(manifest)
        digest = hashlib.sha256(manifest_bytes).hexdigest()
        if target.exists():
            existing = target / "manifest.json"
            if existing.is_file() and hashlib.sha256(existing.read_bytes()).hexdigest() == digest:
                return PackagedCapability(capability_id, version, target, existing, manifest, digest, build_id)
            raise FileExistsError(f"generated capability version already exists with different contents: {target}")

        parent = target.parent
        parent.mkdir(parents=True, exist_ok=True)
        temp = Path(tempfile.mkdtemp(prefix=f".{version}-", dir=str(parent)))
        try:
            for rel, src, _size in files:
                dst = (temp / rel).resolve()
                if not self._inside(temp, dst):
                    raise PermissionError("generated package path escapes package root")
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dst)
                os.chmod(dst, 0o600)
            manifest_path = temp / "manifest.json"
            manifest_path.write_bytes(manifest_bytes)
            os.chmod(manifest_path, 0o600)
            os.replace(temp, target)
        except Exception:
            shutil.rmtree(temp, ignore_errors=True)
            raise
        return PackagedCapability(
            capability_id=capability_id,
            version=version,
            package_path=target,
            manifest_path=target / "manifest.json",
            manifest=manifest,
            manifest_digest=digest,
            build_id=build_id,
        )
