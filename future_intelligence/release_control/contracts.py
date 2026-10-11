from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import IntEnum, StrEnum
from typing import Any, Mapping
from urllib.parse import urlsplit
import re


_SHA_RE = re.compile(r"^[0-9a-fA-F]{7,64}$")


class ReleaseEnvironment(StrEnum):
    PREVIEW = "preview"
    STAGING = "staging"
    PRODUCTION = "production"


class ReleaseRiskClass(IntEnum):
    LOW = 10
    MEDIUM = 20
    HIGH = 30
    CRITICAL = 40

    @property
    def label(self) -> str:
        return self.name.lower()

    @classmethod
    def parse(cls, value: object) -> "ReleaseRiskClass":
        if isinstance(value, cls):
            return value
        if isinstance(value, int):
            return cls(value)
        text = str(value).strip().upper()
        try:
            return cls[text]
        except KeyError as exc:
            raise ValueError(f"unsupported release risk class: {value}") from exc


class ReleaseStatus(StrEnum):
    PLANNED = "planned"
    AWAITING_APPROVAL = "awaiting_approval"
    PREVIEWING = "previewing"
    PREVIEW_QUALIFYING = "preview_qualifying"
    PREVIEW_QUALIFIED = "preview_qualified"
    READY_FOR_PRODUCTION = "ready_for_production"
    PROMOTING = "promoting"
    PRODUCTION_QUALIFYING = "production_qualifying"
    MONITORING = "monitoring"
    SUCCEEDED = "succeeded"
    ROLLBACK_RECOMMENDED = "rollback_recommended"
    ROLLING_BACK = "rolling_back"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def terminal(self) -> bool:
        return self in {
            ReleaseStatus.SUCCEEDED,
            ReleaseStatus.ROLLED_BACK,
            ReleaseStatus.FAILED,
            ReleaseStatus.CANCELLED,
        }


@dataclass(frozen=True)
class ReleaseEvidence:
    kind: str
    summary: str
    reference: str = ""
    revision: str = ""
    trusted: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def __post_init__(self) -> None:
        if not self.kind.strip():
            raise ValueError("release evidence kind is required")
        if not self.summary.strip():
            raise ValueError("release evidence summary is required")
        if self.revision and not _SHA_RE.fullmatch(self.revision):
            raise ValueError("release evidence revision must be a commit-like hexadecimal revision")

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "summary": self.summary,
            "reference": self.reference,
            "revision": self.revision,
            "trusted": self.trusted,
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ReleaseEvidence":
        return cls(
            kind=str(data["kind"]),
            summary=str(data["summary"]),
            reference=str(data.get("reference", "")),
            revision=str(data.get("revision", "")),
            trusted=bool(data.get("trusted", False)),
            metadata=dict(data.get("metadata") or {}),
            created_at=str(data.get("created_at") or datetime.now(UTC).isoformat()),
        )


@dataclass(frozen=True)
class ReleasePlan:
    id: str
    work_order_id: str
    attempt_id: str
    engineering_spec_id: str
    repository: str
    base_revision: str
    candidate_revision: str
    qualification_digest: str
    provider: str
    target: str
    risk_class: ReleaseRiskClass = ReleaseRiskClass.MEDIUM
    requested_environment: ReleaseEnvironment = ReleaseEnvironment.PRODUCTION
    status: ReleaseStatus = ReleaseStatus.PLANNED
    affected_surfaces: tuple[str, ...] = ()
    approval_required: bool = True
    approved_by: str = ""
    approved_at: str = ""
    preview_deployment_id: str = ""
    preview_url: str = ""
    production_deployment_id: str = ""
    production_url: str = ""
    evidence: tuple[ReleaseEvidence, ...] = ()
    rollback_of: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def __post_init__(self) -> None:
        for label, value in (
            ("id", self.id),
            ("work_order_id", self.work_order_id),
            ("attempt_id", self.attempt_id),
            ("engineering_spec_id", self.engineering_spec_id),
            ("repository", self.repository),
            ("provider", self.provider),
            ("target", self.target),
            ("qualification_digest", self.qualification_digest),
        ):
            if not str(value).strip():
                raise ValueError(f"{label} is required")
        for label, value in (("base_revision", self.base_revision), ("candidate_revision", self.candidate_revision)):
            if not _SHA_RE.fullmatch(str(value)):
                raise ValueError(f"{label} must be a commit-like hexadecimal revision")
        if self.base_revision == self.candidate_revision:
            raise ValueError("release candidate must differ from base revision")
        if self.status.terminal and self.status is ReleaseStatus.SUCCEEDED and not self.production_deployment_id:
            raise ValueError("successful release requires a production deployment id")
        for label, url in (("preview_url", self.preview_url), ("production_url", self.production_url)):
            if url:
                parsed = urlsplit(url)
                if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                    raise ValueError(f"{label} must be credential-free HTTPS")

    def with_update(self, **changes: Any) -> "ReleasePlan":
        changes.setdefault("updated_at", datetime.now(UTC).isoformat())
        return replace(self, **changes)

    def append_evidence(self, item: ReleaseEvidence) -> "ReleasePlan":
        if item.revision and item.revision != self.candidate_revision:
            raise ValueError("release evidence revision does not match the bound candidate")
        return self.with_update(evidence=(*self.evidence, item))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "work_order_id": self.work_order_id,
            "attempt_id": self.attempt_id,
            "engineering_spec_id": self.engineering_spec_id,
            "repository": self.repository,
            "base_revision": self.base_revision,
            "candidate_revision": self.candidate_revision,
            "qualification_digest": self.qualification_digest,
            "provider": self.provider,
            "target": self.target,
            "risk_class": self.risk_class.label,
            "requested_environment": self.requested_environment.value,
            "status": self.status.value,
            "affected_surfaces": list(self.affected_surfaces),
            "approval_required": self.approval_required,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
            "preview_deployment_id": self.preview_deployment_id,
            "preview_url": self.preview_url,
            "production_deployment_id": self.production_deployment_id,
            "production_url": self.production_url,
            "evidence": [item.to_dict() for item in self.evidence],
            "rollback_of": self.rollback_of,
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ReleasePlan":
        return cls(
            id=str(data["id"]),
            work_order_id=str(data["work_order_id"]),
            attempt_id=str(data["attempt_id"]),
            engineering_spec_id=str(data["engineering_spec_id"]),
            repository=str(data["repository"]),
            base_revision=str(data["base_revision"]),
            candidate_revision=str(data["candidate_revision"]),
            qualification_digest=str(data["qualification_digest"]),
            provider=str(data["provider"]),
            target=str(data["target"]),
            risk_class=ReleaseRiskClass.parse(data.get("risk_class", "medium")),
            requested_environment=ReleaseEnvironment(str(data.get("requested_environment", "production"))),
            status=ReleaseStatus(str(data.get("status", "planned"))),
            affected_surfaces=tuple(str(item) for item in data.get("affected_surfaces", ())),
            approval_required=bool(data.get("approval_required", True)),
            approved_by=str(data.get("approved_by", "")),
            approved_at=str(data.get("approved_at", "")),
            preview_deployment_id=str(data.get("preview_deployment_id", "")),
            preview_url=str(data.get("preview_url", "")),
            production_deployment_id=str(data.get("production_deployment_id", "")),
            production_url=str(data.get("production_url", "")),
            evidence=tuple(ReleaseEvidence.from_dict(item) for item in data.get("evidence", ())),
            rollback_of=str(data.get("rollback_of", "")),
            metadata=dict(data.get("metadata") or {}),
            created_at=str(data.get("created_at") or datetime.now(UTC).isoformat()),
            updated_at=str(data.get("updated_at") or datetime.now(UTC).isoformat()),
        )
