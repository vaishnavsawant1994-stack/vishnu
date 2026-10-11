from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Iterable, Mapping
from uuid import uuid4


_MANIFEST_SCHEMA_VERSION = 1


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _clean_mapping(value: Mapping[str, Any] | None) -> dict[str, Any]:
    return {str(key): item for key, item in dict(value or {}).items()}


@dataclass(frozen=True)
class IntelligenceReference:
    """Immutable reference to one versioned Vishnu intelligence component.

    References intentionally contain no credentials and no artifact payloads.
    Model bytes remain owned by the existing governed model-artifact pipeline;
    agent implementations remain owned by their canonical registries/code.
    """

    name: str
    ref_id: str
    version: str
    sha256: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("reference name is required")
        if not self.ref_id.strip():
            raise ValueError("reference ref_id is required")
        if not self.version.strip():
            raise ValueError("reference version is required")
        digest = self.sha256.strip().lower()
        if digest and (len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest)):
            raise ValueError("reference sha256 must be a 64-character hexadecimal digest")

    def public(self) -> dict[str, str]:
        return {
            "name": self.name,
            "ref_id": self.ref_id,
            "version": self.version,
            "sha256": self.sha256.lower(),
        }


@dataclass(frozen=True)
class IntelligenceManifest:
    """Tamper-evident reconstruction blueprint for one qualified Vishnu state.

    The manifest pins references and schema/registry versions. It is deliberately
    not a backup archive and never contains model weights, memories, documents,
    API keys, credentials, or private training examples.
    """

    schema_version: int
    manifest_id: str
    fingerprint: str
    created_at: str
    owner_id: str
    core_version: str
    models: tuple[IntelligenceReference, ...]
    agents: tuple[IntelligenceReference, ...]
    schemas: dict[str, str]
    registries: dict[str, str]
    runtime_policy: dict[str, Any]

    @staticmethod
    def _references(values: Iterable[IntelligenceReference]) -> tuple[IntelligenceReference, ...]:
        references = tuple(values)
        names = [item.name for item in references]
        if len(names) != len(set(names)):
            raise ValueError("intelligence reference names must be unique within a component kind")
        return tuple(sorted(references, key=lambda item: (item.name, item.version, item.ref_id)))

    @classmethod
    def create(
        cls,
        *,
        owner_id: str,
        core_version: str,
        models: Iterable[IntelligenceReference] = (),
        agents: Iterable[IntelligenceReference] = (),
        schemas: Mapping[str, str] | None = None,
        registries: Mapping[str, str] | None = None,
        runtime_policy: Mapping[str, Any] | None = None,
        created_at: str | None = None,
    ) -> "IntelligenceManifest":
        if not str(owner_id).strip():
            raise ValueError("owner_id is required")
        if not str(core_version).strip():
            raise ValueError("core_version is required")
        normalized_models = cls._references(models)
        normalized_agents = cls._references(agents)
        normalized_schemas = {str(key): str(value) for key, value in dict(schemas or {}).items()}
        normalized_registries = {str(key): str(value) for key, value in dict(registries or {}).items()}
        normalized_policy = _clean_mapping(runtime_policy)
        timestamp = str(created_at or _now())
        unsigned = {
            "schema_version": _MANIFEST_SCHEMA_VERSION,
            "created_at": timestamp,
            "owner_id": str(owner_id),
            "core_version": str(core_version),
            "models": [item.public() for item in normalized_models],
            "agents": [item.public() for item in normalized_agents],
            "schemas": normalized_schemas,
            "registries": normalized_registries,
            "runtime_policy": normalized_policy,
        }
        fingerprint = sha256(_canonical_json(unsigned).encode("utf-8")).hexdigest()
        return cls(
            schema_version=_MANIFEST_SCHEMA_VERSION,
            manifest_id=f"vim-{fingerprint[:24]}",
            fingerprint=fingerprint,
            created_at=timestamp,
            owner_id=str(owner_id),
            core_version=str(core_version),
            models=normalized_models,
            agents=normalized_agents,
            schemas=normalized_schemas,
            registries=normalized_registries,
            runtime_policy=normalized_policy,
        )

    def unsigned(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "owner_id": self.owner_id,
            "core_version": self.core_version,
            "models": [item.public() for item in self._references(self.models)],
            "agents": [item.public() for item in self._references(self.agents)],
            "schemas": dict(self.schemas),
            "registries": dict(self.registries),
            "runtime_policy": dict(self.runtime_policy),
        }

    def verify(self) -> None:
        if self.schema_version != _MANIFEST_SCHEMA_VERSION:
            raise ValueError("unsupported intelligence manifest schema")
        expected = sha256(_canonical_json(self.unsigned()).encode("utf-8")).hexdigest()
        if expected != self.fingerprint:
            raise RuntimeError("intelligence manifest fingerprint mismatch")
        if self.manifest_id != f"vim-{expected[:24]}":
            raise RuntimeError("intelligence manifest id mismatch")

    def public(self) -> dict[str, Any]:
        self.verify()
        payload = self.unsigned()
        payload.update({"manifest_id": self.manifest_id, "fingerprint": self.fingerprint})
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "IntelligenceManifest":
        if int(payload.get("schema_version", 0)) != _MANIFEST_SCHEMA_VERSION:
            raise ValueError("unsupported intelligence manifest schema")

        def references(key: str) -> tuple[IntelligenceReference, ...]:
            raw = payload.get(key) or ()
            if not isinstance(raw, (list, tuple)):
                raise ValueError(f"{key} must be a list")
            return tuple(IntelligenceReference(**dict(item)) for item in raw)

        manifest = cls(
            schema_version=_MANIFEST_SCHEMA_VERSION,
            manifest_id=str(payload.get("manifest_id") or ""),
            fingerprint=str(payload.get("fingerprint") or ""),
            created_at=str(payload.get("created_at") or ""),
            owner_id=str(payload.get("owner_id") or ""),
            core_version=str(payload.get("core_version") or ""),
            models=cls._references(references("models")),
            agents=cls._references(references("agents")),
            schemas={str(key): str(value) for key, value in dict(payload.get("schemas") or {}).items()},
            registries={str(key): str(value) for key, value in dict(payload.get("registries") or {}).items()},
            runtime_policy=_clean_mapping(payload.get("runtime_policy") if isinstance(payload.get("runtime_policy"), Mapping) else {}),
        )
        if not manifest.owner_id.strip() or not manifest.core_version.strip():
            raise ValueError("manifest owner_id and core_version are required")
        manifest.verify()
        return manifest


class FilesystemIntelligenceManifestStore:
    """Content-addressed manifest history plus an atomic active pointer."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.manifests_root = self.root / "intelligence" / "manifests"
        self.manifests_root.mkdir(parents=True, exist_ok=True)
        self.active_path = self.root / "intelligence" / "active-manifest.json"

    def _path(self, manifest_id: str) -> Path:
        if not manifest_id.startswith("vim-") or any(char not in "0123456789abcdef" for char in manifest_id[4:]):
            raise ValueError("invalid intelligence manifest id")
        return self.manifests_root / f"{manifest_id}.json"

    def save(self, manifest: IntelligenceManifest) -> IntelligenceManifest:
        manifest.verify()
        path = self._path(manifest.manifest_id)
        content = json.dumps(manifest.public(), sort_keys=True, indent=2, ensure_ascii=False) + "\n"
        if path.exists():
            existing = self.load(manifest.manifest_id)
            if existing.fingerprint != manifest.fingerprint:
                raise RuntimeError("immutable intelligence manifest conflict")
            return existing
        temp = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        temp.write_text(content, encoding="utf-8")
        temp.replace(path)
        return self.load(manifest.manifest_id)

    def load(self, manifest_id: str) -> IntelligenceManifest:
        path = self._path(manifest_id)
        if not path.is_file() or path.is_symlink():
            raise FileNotFoundError(manifest_id)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError("intelligence manifest is unreadable") from exc
        if not isinstance(payload, dict):
            raise ValueError("intelligence manifest must be an object")
        return IntelligenceManifest.from_dict(payload)

    def activate(self, manifest: IntelligenceManifest) -> IntelligenceManifest:
        saved = self.save(manifest)
        pointer = {
            "schema_version": 1,
            "manifest_id": saved.manifest_id,
            "fingerprint": saved.fingerprint,
        }
        self.active_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.active_path.with_name(f".{self.active_path.name}.{uuid4().hex}.tmp")
        temp.write_text(json.dumps(pointer, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        temp.replace(self.active_path)
        return saved

    def active(self) -> IntelligenceManifest | None:
        if not self.active_path.exists():
            return None
        if not self.active_path.is_file() or self.active_path.is_symlink():
            raise ValueError("active intelligence manifest pointer is invalid")
        try:
            pointer = json.loads(self.active_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError("active intelligence manifest pointer is unreadable") from exc
        manifest = self.load(str(pointer.get("manifest_id") or ""))
        if str(pointer.get("fingerprint") or "") != manifest.fingerprint:
            raise RuntimeError("active intelligence manifest pointer fingerprint mismatch")
        return manifest


class ModelTier(str, Enum):
    MOBILE = "mobile"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


_TIER_RANK = {
    ModelTier.MOBILE: 0,
    ModelTier.SMALL: 1,
    ModelTier.MEDIUM: 2,
    ModelTier.LARGE: 3,
}


class ExecutionTarget(str, Enum):
    LOCAL = "local"
    REMOTE = "remote"


@dataclass(frozen=True)
class DeviceCapabilities:
    ram_gb: float
    gpu_vram_gb: float = 0.0
    online: bool = True
    accelerator: str = "none"
    platform: str = "unknown"

    def __post_init__(self) -> None:
        if self.ram_gb <= 0:
            raise ValueError("ram_gb must be positive")
        if self.gpu_vram_gb < 0:
            raise ValueError("gpu_vram_gb cannot be negative")


@dataclass(frozen=True)
class RuntimeCandidate:
    runtime_id: str
    model_ref: str
    tier: ModelTier
    target: ExecutionTarget
    minimum_ram_gb: float = 0.0
    minimum_vram_gb: float = 0.0
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.runtime_id.strip() or not self.model_ref.strip():
            raise ValueError("runtime_id and model_ref are required")
        if self.minimum_ram_gb < 0 or self.minimum_vram_gb < 0:
            raise ValueError("runtime resource requirements cannot be negative")
        if self.target is ExecutionTarget.REMOTE and self.minimum_vram_gb:
            raise ValueError("remote runtime candidates cannot require local VRAM")


@dataclass(frozen=True)
class RuntimeSelection:
    candidate: RuntimeCandidate
    reason_codes: tuple[str, ...]


def _local_feasible(candidate: RuntimeCandidate, device: DeviceCapabilities) -> bool:
    return (
        candidate.target is ExecutionTarget.LOCAL
        and candidate.minimum_ram_gb <= device.ram_gb
        and candidate.minimum_vram_gb <= device.gpu_vram_gb
    )


def select_runtime(
    candidates: Iterable[RuntimeCandidate],
    device: DeviceCapabilities,
    *,
    local_only: bool = False,
    maximum_tier: ModelTier | None = None,
) -> RuntimeSelection:
    """Select the strongest feasible registered runtime without bypassing policy.

    This function is intentionally a feasibility selector, not a provider router.
    The canonical governed model router remains responsible for permissions,
    privacy, provider eligibility, credentials, budgets and execution.
    """

    eligible: list[RuntimeCandidate] = []
    for candidate in candidates:
        if not candidate.enabled:
            continue
        if maximum_tier is not None and _TIER_RANK[candidate.tier] > _TIER_RANK[maximum_tier]:
            continue
        if candidate.target is ExecutionTarget.LOCAL:
            if _local_feasible(candidate, device):
                eligible.append(candidate)
            continue
        if not local_only and device.online:
            eligible.append(candidate)

    if not eligible:
        reason = "no feasible local runtime" if local_only or not device.online else "no feasible runtime"
        raise RuntimeError(reason)

    # Strongest tier wins. For equivalent intelligence tiers, prefer local
    # execution to reduce data movement and preserve offline continuity.
    chosen = max(
        eligible,
        key=lambda item: (
            _TIER_RANK[item.tier],
            1 if item.target is ExecutionTarget.LOCAL else 0,
            -item.minimum_vram_gb,
            -item.minimum_ram_gb,
            item.runtime_id,
        ),
    )
    reasons = [f"tier:{chosen.tier.value}", f"target:{chosen.target.value}"]
    if local_only:
        reasons.append("local_only_enforced")
    if not device.online:
        reasons.append("offline")
    if chosen.target is ExecutionTarget.LOCAL and chosen.minimum_vram_gb:
        reasons.append("gpu_capable")
    elif chosen.target is ExecutionTarget.LOCAL:
        reasons.append("cpu_or_shared_memory_capable")
    return RuntimeSelection(candidate=chosen, reason_codes=tuple(reasons))
