from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping


class SecurityClass(StrEnum):
    ORDINARY = "ordinary"
    SENSITIVE = "sensitive"
    AUTHORITY = "authority"


class EngineeringAutonomyMode(StrEnum):
    OFF = "off"
    ANALYZE = "analyze"
    WORKSPACE = "workspace"
    AUTO_FIX = "auto_fix"
    REVIEW_CANDIDATE = "review_candidate"


class BrowserEngine(StrEnum):
    CHROMIUM = "chromium"
    WEBKIT = "webkit"
    FIREFOX = "firefox"


class QualificationGateStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    SKIPPED = "skipped"
    PENDING = "pending"


@dataclass(frozen=True)
class EngineeringBudget:
    max_files: int = 24
    max_file_bytes: int = 500_000
    max_total_bytes: int = 2_000_000
    max_repair_cycles: int = 3
    max_search_results: int = 100

    def __post_init__(self) -> None:
        if not 1 <= self.max_files <= 200:
            raise ValueError("max_files must be between 1 and 200")
        if not 1_000 <= self.max_file_bytes <= 5_000_000:
            raise ValueError("max_file_bytes is outside the supported range")
        if not self.max_file_bytes <= self.max_total_bytes <= 20_000_000:
            raise ValueError("max_total_bytes must be >= max_file_bytes and bounded")
        if not 0 <= self.max_repair_cycles <= 10:
            raise ValueError("max_repair_cycles must be between 0 and 10")
        if not 1 <= self.max_search_results <= 1_000:
            raise ValueError("max_search_results must be between 1 and 1000")

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_files": self.max_files,
            "max_file_bytes": self.max_file_bytes,
            "max_total_bytes": self.max_total_bytes,
            "max_repair_cycles": self.max_repair_cycles,
            "max_search_results": self.max_search_results,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "EngineeringBudget":
        data = data or {}
        return cls(**{key: int(data.get(key, field.default)) for key, field in cls.__dataclass_fields__.items()})


@dataclass(frozen=True)
class DeviceProfile:
    name: str
    width: int
    height: int
    device_scale_factor: float = 1.0
    mobile: bool = False
    touch: bool = False
    orientation: str = "portrait"

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("device profile name is required")
        if self.width < 240 or self.height < 240:
            raise ValueError("device profile dimensions are too small")
        if self.device_scale_factor <= 0:
            raise ValueError("device_scale_factor must be positive")
        if self.orientation not in {"portrait", "landscape"}:
            raise ValueError("orientation must be portrait or landscape")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "device_scale_factor": self.device_scale_factor,
            "mobile": self.mobile,
            "touch": self.touch,
            "orientation": self.orientation,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DeviceProfile":
        return cls(
            name=str(data["name"]),
            width=int(data["width"]),
            height=int(data["height"]),
            device_scale_factor=float(data.get("device_scale_factor", 1.0)),
            mobile=bool(data.get("mobile", False)),
            touch=bool(data.get("touch", False)),
            orientation=str(data.get("orientation", "portrait")),
        )


@dataclass(frozen=True)
class EngineeringSpec:
    id: str
    work_order_id: str
    attempt_id: str
    repository: str
    base_revision: str
    objective: str
    requirements: tuple[str, ...] = ()
    non_requirements: tuple[str, ...] = ()
    allowed_paths: tuple[str, ...] = ()
    prohibited_paths: tuple[str, ...] = ()
    affected_surfaces: tuple[str, ...] = ()
    api_impacts: tuple[str, ...] = ()
    schema_impacts: tuple[str, ...] = ()
    success_criteria: tuple[str, ...] = ()
    required_tests: tuple[str, ...] = ()
    required_states: tuple[str, ...] = ()
    reference_designs: tuple[str, ...] = ()
    browsers: tuple[BrowserEngine, ...] = (BrowserEngine.CHROMIUM,)
    devices: tuple[DeviceProfile, ...] = ()
    security_class: SecurityClass = SecurityClass.ORDINARY
    ui_required: bool = False
    accessibility_required: bool = False
    visual_review_required: bool = False
    review_required: bool = True
    allow_authority_paths: bool = False
    budget: EngineeringBudget = field(default_factory=EngineeringBudget)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        required = {
            "id": self.id,
            "work_order_id": self.work_order_id,
            "attempt_id": self.attempt_id,
            "repository": self.repository,
            "base_revision": self.base_revision,
            "objective": self.objective,
        }
        for label, value in required.items():
            if not str(value).strip():
                raise ValueError(f"{label} is required")
        if self.security_class is SecurityClass.AUTHORITY and not self.allow_authority_paths:
            raise ValueError("authority-class engineering requires explicit allow_authority_paths")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "work_order_id": self.work_order_id,
            "attempt_id": self.attempt_id,
            "repository": self.repository,
            "base_revision": self.base_revision,
            "objective": self.objective,
            "requirements": list(self.requirements),
            "non_requirements": list(self.non_requirements),
            "allowed_paths": list(self.allowed_paths),
            "prohibited_paths": list(self.prohibited_paths),
            "affected_surfaces": list(self.affected_surfaces),
            "api_impacts": list(self.api_impacts),
            "schema_impacts": list(self.schema_impacts),
            "success_criteria": list(self.success_criteria),
            "required_tests": list(self.required_tests),
            "required_states": list(self.required_states),
            "reference_designs": list(self.reference_designs),
            "browsers": [item.value for item in self.browsers],
            "devices": [item.to_dict() for item in self.devices],
            "security_class": self.security_class.value,
            "ui_required": self.ui_required,
            "accessibility_required": self.accessibility_required,
            "visual_review_required": self.visual_review_required,
            "review_required": self.review_required,
            "allow_authority_paths": self.allow_authority_paths,
            "budget": self.budget.to_dict(),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EngineeringSpec":
        tuple_fields = (
            "requirements", "non_requirements", "allowed_paths", "prohibited_paths",
            "affected_surfaces", "api_impacts", "schema_impacts", "success_criteria",
            "required_tests", "required_states", "reference_designs",
        )
        kwargs = {name: tuple(data.get(name, ())) for name in tuple_fields}
        return cls(
            id=str(data["id"]), work_order_id=str(data["work_order_id"]),
            attempt_id=str(data["attempt_id"]), repository=str(data["repository"]),
            base_revision=str(data["base_revision"]), objective=str(data["objective"]),
            browsers=tuple(BrowserEngine(str(item)) for item in data.get("browsers", [BrowserEngine.CHROMIUM.value])),
            devices=tuple(DeviceProfile.from_dict(item) for item in data.get("devices", ())),
            security_class=SecurityClass(str(data.get("security_class", SecurityClass.ORDINARY.value))),
            ui_required=bool(data.get("ui_required", False)),
            accessibility_required=bool(data.get("accessibility_required", False)),
            visual_review_required=bool(data.get("visual_review_required", False)),
            review_required=bool(data.get("review_required", True)),
            allow_authority_paths=bool(data.get("allow_authority_paths", False)),
            budget=EngineeringBudget.from_dict(data.get("budget")),
            metadata=dict(data.get("metadata") or {}), **kwargs,
        )


@dataclass(frozen=True)
class VisualDefect:
    screen: str
    route: str
    viewport: str
    browser: str
    state: str
    severity: str
    expected: str
    actual: str
    region: Mapping[str, float] = field(default_factory=dict)
    suspected_element: str = ""
    suspected_component: str = ""
    screenshot_evidence: str = ""
    baseline_evidence: str = ""
    confidence: float = 0.0
    recommended_action: str = ""

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")

    def to_dict(self) -> dict[str, Any]:
        result = dict(self.__dict__)
        result["region"] = dict(self.region)
        return result


@dataclass(frozen=True)
class QualificationGateResult:
    gate: str
    status: QualificationGateStatus
    summary: str = ""
    evidence: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def blocking(self) -> bool:
        return self.status in {QualificationGateStatus.FAIL, QualificationGateStatus.PENDING}

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate": self.gate,
            "status": self.status.value,
            "summary": self.summary,
            "evidence": list(self.evidence),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class QualificationReport:
    spec_id: str
    base_revision: str
    candidate_revision: str
    gates: tuple[QualificationGateResult, ...]
    reviewer: str = ""
    review_decision: str = "pending"
    limitations: tuple[str, ...] = ()

    @property
    def qualified(self) -> bool:
        return bool(self.gates) and all(not gate.blocking for gate in self.gates) and self.review_decision == "approved"

    def to_dict(self) -> dict[str, Any]:
        return {
            "spec_id": self.spec_id,
            "base_revision": self.base_revision,
            "candidate_revision": self.candidate_revision,
            "gates": [gate.to_dict() for gate in self.gates],
            "reviewer": self.reviewer,
            "review_decision": self.review_decision,
            "limitations": list(self.limitations),
            "qualified": self.qualified,
        }
