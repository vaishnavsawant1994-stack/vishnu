from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping

from .contracts import EngineeringAutonomyMode, EngineeringBudget, EngineeringSpec, SecurityClass


_BROWSER_DEPTHS = {"critical", "full", "release"}
_VISUAL_LEVELS = {"off", "diff", "semantic"}
_SECURITY_RANK = {
    SecurityClass.ORDINARY.value: 0,
    SecurityClass.SENSITIVE.value: 1,
    SecurityClass.AUTHORITY.value: 2,
}


@dataclass(frozen=True)
class EngineeringOwnerPolicy:
    mode: EngineeringAutonomyMode = EngineeringAutonomyMode.ANALYZE
    max_files: int = 24
    max_file_bytes: int = 500_000
    max_total_bytes: int = 2_000_000
    max_repair_cycles: int = 3
    browser_depth: str = "critical"
    visual_level: str = "diff"
    preview_enabled: bool = False
    security_level: SecurityClass = SecurityClass.ORDINARY
    evidence_retention_days: int = 30
    max_model_cost_per_work: float | None = None
    physical_device_required: bool = False
    physical_device_auto_dispatch: bool = False
    performance_required: bool = True
    localization_required: bool = True
    three_d_required: bool = True

    def __post_init__(self) -> None:
        EngineeringBudget(
            max_files=self.max_files,
            max_file_bytes=self.max_file_bytes,
            max_total_bytes=self.max_total_bytes,
            max_repair_cycles=self.max_repair_cycles,
        )
        if self.browser_depth not in _BROWSER_DEPTHS:
            raise ValueError("unsupported engineering browser depth")
        if self.visual_level not in _VISUAL_LEVELS:
            raise ValueError("unsupported engineering visual level")
        if not 1 <= int(self.evidence_retention_days) <= 3650:
            raise ValueError("engineering evidence retention must be between 1 and 3650 days")
        if self.max_model_cost_per_work is not None and not 0 < float(self.max_model_cost_per_work) <= 100_000:
            raise ValueError("engineering model budget is outside the supported range")

    def public(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "max_files": self.max_files,
            "max_file_bytes": self.max_file_bytes,
            "max_total_bytes": self.max_total_bytes,
            "max_repair_cycles": self.max_repair_cycles,
            "browser_depth": self.browser_depth,
            "visual_level": self.visual_level,
            "preview_enabled": self.preview_enabled,
            "security_level": self.security_level.value,
            "evidence_retention_days": self.evidence_retention_days,
            "max_model_cost_per_work": self.max_model_cost_per_work,
            "physical_device_required": self.physical_device_required,
            "physical_device_auto_dispatch": self.physical_device_auto_dispatch,
            "performance_required": self.performance_required,
            "localization_required": self.localization_required,
            "three_d_required": self.three_d_required,
            "remote_push_authority": False,
            "merge_authority": False,
            "deploy_authority": False,
            "body_activation_authority": False,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "EngineeringOwnerPolicy":
        raw = dict(data or {})
        return cls(
            mode=EngineeringAutonomyMode(str(raw.get("mode", EngineeringAutonomyMode.ANALYZE.value))),
            max_files=int(raw.get("max_files", 24)),
            max_file_bytes=int(raw.get("max_file_bytes", 500_000)),
            max_total_bytes=int(raw.get("max_total_bytes", 2_000_000)),
            max_repair_cycles=int(raw.get("max_repair_cycles", 3)),
            browser_depth=str(raw.get("browser_depth", "critical")),
            visual_level=str(raw.get("visual_level", "diff")),
            preview_enabled=bool(raw.get("preview_enabled", False)),
            security_level=SecurityClass(str(raw.get("security_level", SecurityClass.ORDINARY.value))),
            evidence_retention_days=int(raw.get("evidence_retention_days", 30)),
            max_model_cost_per_work=(None if raw.get("max_model_cost_per_work") in {None, ""} else float(raw["max_model_cost_per_work"])),
            physical_device_required=bool(raw.get("physical_device_required", False)),
            physical_device_auto_dispatch=bool(raw.get("physical_device_auto_dispatch", False)),
            performance_required=bool(raw.get("performance_required", True)),
            localization_required=bool(raw.get("localization_required", True)),
            three_d_required=bool(raw.get("three_d_required", True)),
        )

    def allows_workspace_mutation(self) -> bool:
        return self.mode in {
            EngineeringAutonomyMode.WORKSPACE,
            EngineeringAutonomyMode.AUTO_FIX,
            EngineeringAutonomyMode.REVIEW_CANDIDATE,
        }

    def allows_autonomous_execution(self) -> bool:
        return self.mode in {EngineeringAutonomyMode.AUTO_FIX, EngineeringAutonomyMode.REVIEW_CANDIDATE}

    def constrain_spec(self, spec: EngineeringSpec) -> EngineeringSpec:
        if _SECURITY_RANK[spec.security_class.value] > _SECURITY_RANK[self.security_level.value]:
            raise PermissionError("EngineeringSpec security class exceeds owner Engineering Autonomy policy")
        if spec.allow_authority_paths and self.security_level is not SecurityClass.AUTHORITY:
            raise PermissionError("authority-sensitive engineering exceeds owner Engineering Autonomy policy")
        requested = spec.budget
        budget = EngineeringBudget(
            max_files=min(requested.max_files, self.max_files),
            max_file_bytes=min(requested.max_file_bytes, self.max_file_bytes),
            max_total_bytes=min(requested.max_total_bytes, self.max_total_bytes),
            max_repair_cycles=min(requested.max_repair_cycles, self.max_repair_cycles),
            max_search_results=requested.max_search_results,
        )
        metadata = dict(spec.metadata)
        ui_change = bool(spec.ui_required or "ui" in {str(item).casefold() for item in spec.affected_surfaces})
        metadata.update({
            "owner_engineering_mode": self.mode.value,
            "owner_browser_depth": self.browser_depth,
            "owner_visual_level": self.visual_level,
            "preview_enabled": self.preview_enabled,
            "performance_required": self.performance_required,
            "physical_device_required": bool(self.physical_device_required and ui_change),
            "physical_device_auto_dispatch": bool(self.physical_device_auto_dispatch and self.physical_device_required and ui_change),
            "localization_required": bool(self.localization_required and ui_change),
            "three_d_required": bool(self.three_d_required and ui_change),
            "max_model_cost_per_work": self.max_model_cost_per_work,
            "specialist_consultation_enabled": True,
        })
        return replace(spec, budget=budget, metadata=metadata)


class EngineeringOwnerPolicyStore:
    """Small local owner-policy store; never carries model/tool/release authority itself."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._policy = self._load()

    def _load(self) -> EngineeringOwnerPolicy:
        if not self.path.exists():
            return EngineeringOwnerPolicy()
        if self.path.is_symlink() or not self.path.is_file():
            raise PermissionError("engineering owner policy path is unsafe")
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("engineering owner policy is unreadable") from exc
        if not isinstance(payload, dict) or int(payload.get("version", 0)) != 1:
            raise RuntimeError("unsupported engineering owner policy format")
        return EngineeringOwnerPolicy.from_dict(payload.get("policy"))

    def snapshot(self) -> EngineeringOwnerPolicy:
        with self._lock:
            return self._policy

    def update(self, **values: Any) -> EngineeringOwnerPolicy:
        allowed = set(EngineeringOwnerPolicy.__dataclass_fields__)
        unknown = set(values) - allowed
        if unknown:
            raise ValueError(f"unsupported engineering policy keys: {sorted(unknown)}")
        current = self.snapshot().public()
        for key in (
            "remote_push_authority", "merge_authority", "deploy_authority", "body_activation_authority"
        ):
            current.pop(key, None)
        current.update(values)
        candidate = EngineeringOwnerPolicy.from_dict(current)
        payload = {"version": 1, "policy": candidate.public()}
        for key in ("remote_push_authority", "merge_authority", "deploy_authority", "body_activation_authority"):
            payload["policy"].pop(key, None)
        raw = json.dumps(payload, sort_keys=True, indent=2)
        with self._lock:
            if self.path.exists() and self.path.is_symlink():
                raise PermissionError("engineering owner policy path became unsafe")
            temp = self.path.with_suffix(self.path.suffix + ".tmp")
            if temp.exists() or temp.is_symlink():
                raise PermissionError("engineering owner policy temporary path collision")
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(raw)
                    handle.flush()
                    os.fsync(handle.fileno())
                temp.replace(self.path)
                try:
                    os.chmod(self.path, 0o600)
                except OSError:
                    pass
            finally:
                if temp.exists():
                    temp.unlink(missing_ok=True)
            self._policy = candidate
        return candidate
