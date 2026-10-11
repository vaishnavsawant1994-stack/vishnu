from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol


@dataclass(frozen=True)
class EnvironmentQualificationResult:
    environment: str
    target: str
    healthy: bool
    checks: Mapping[str, bool]
    evidence: tuple[str, ...] = ()
    summary: str = ""

    @property
    def passed(self) -> bool:
        return self.healthy and bool(self.checks) and all(bool(value) for value in self.checks.values())

    def to_dict(self) -> dict[str, object]:
        return {
            "environment": self.environment,
            "target": self.target,
            "healthy": self.healthy,
            "checks": dict(self.checks),
            "evidence": list(self.evidence),
            "summary": self.summary,
            "passed": self.passed,
        }


class PreviewQualificationProvider(Protocol):
    """Observe an already-created preview; this interface cannot deploy one."""
    def qualify_preview(
        self, *, target: str, spec_id: str, candidate_revision: str
    ) -> EnvironmentQualificationResult: ...


class ProductionSmokeProvider(Protocol):
    """Read-only/safe smoke checks against an already-approved deployment."""
    def smoke_production(self, *, target: str, release_revision: str) -> EnvironmentQualificationResult: ...


@dataclass(frozen=True)
class PreviewQualificationRequest:
    """Read-only handoff asking an external release system for a preview.

    This request describes what must be deployed by an existing release/preview
    authority. It is not itself a deployment command and intentionally carries
    no credential, push, merge or deployment authority.
    """

    work_order_id: str
    attempt_id: str
    spec_id: str
    repository: str
    candidate_revision: str

    def __post_init__(self) -> None:
        for name, value in (
            ("work_order_id", self.work_order_id),
            ("attempt_id", self.attempt_id),
            ("spec_id", self.spec_id),
            ("repository", self.repository),
            ("candidate_revision", self.candidate_revision),
        ):
            if not str(value).strip():
                raise ValueError(f"preview qualification request requires {name}")

    def to_dict(self) -> dict[str, object]:
        return {
            "work_order_id": self.work_order_id,
            "attempt_id": self.attempt_id,
            "spec_id": self.spec_id,
            "repository": self.repository,
            "candidate_revision": self.candidate_revision,
            "push_authority": False,
            "merge_authority": False,
            "deployment_authority": False,
            "activation_authority": False,
        }


@dataclass(frozen=True)
class ProductionRegression:
    release_revision: str
    target: str
    signal: str
    evidence: tuple[str, ...] = ()
    severity: str = "warning"

    def to_work_proposal(self) -> dict[str, object]:
        return {
            "title": f"Investigate production regression: {self.signal[:120]}",
            "objective": "Reproduce, diagnose and repair the observed production regression through canonical Work and governed engineering qualification.",
            "created_from": "production_regression_observation",
            "metadata": {
                "release_revision": self.release_revision,
                "target": self.target,
                "signal": self.signal,
                "evidence": list(self.evidence),
                "severity": self.severity,
                "automatic_mutation_authority": False,
                "automatic_deploy_authority": False,
            },
        }
