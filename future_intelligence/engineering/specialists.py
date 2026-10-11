from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from future_intelligence.workers.models import WorkerProfile

from .contracts import EngineeringSpec, SecurityClass
from .model_json import governed_engineering_json
from .repository_intelligence import RepositoryGraph


ENGINEERING_SPECIALISTS: tuple[WorkerProfile, ...] = (
    WorkerProfile(
        id="engineering-architect",
        description="Analyze architecture, dependency boundaries and minimum safe change scope; proposal only.",
        supported_capabilities=("architecture", "code", "repository", "review"),
        output_kinds=("analysis", "recommendation"), routing_policy="deep_reasoning",
        required_model_capabilities=("chat",), preferred_model_capabilities=("json",), parallelizable=True,
    ),
    WorkerProfile(
        id="engineering-frontend",
        description="Analyze frontend, responsive, browser and component implications; proposal only.",
        supported_capabilities=("frontend", "ui", "browser", "responsive", "code"),
        output_kinds=("analysis", "recommendation"), routing_policy="coding",
        required_model_capabilities=("chat",), preferred_model_capabilities=("json",), parallelizable=True,
    ),
    WorkerProfile(
        id="engineering-backend",
        description="Analyze backend, service and API implications; proposal only.",
        supported_capabilities=("backend", "api", "service", "code"),
        output_kinds=("analysis", "recommendation"), routing_policy="coding",
        required_model_capabilities=("chat",), preferred_model_capabilities=("json",), parallelizable=True,
    ),
    WorkerProfile(
        id="engineering-database",
        description="Analyze schema, migration and persistence implications; proposal only.",
        supported_capabilities=("database", "schema", "migration", "data"),
        output_kinds=("analysis", "recommendation"), routing_policy="deep_reasoning",
        required_model_capabilities=("chat",), preferred_model_capabilities=("json",), parallelizable=True,
    ),
    WorkerProfile(
        id="engineering-mobile",
        description="Analyze native/mobile, keyboard, safe-area and device implications; proposal only.",
        supported_capabilities=("mobile", "ios", "android", "device", "code"),
        output_kinds=("analysis", "recommendation"), routing_policy="coding",
        required_model_capabilities=("chat",), preferred_model_capabilities=("json",), parallelizable=True,
    ),
    WorkerProfile(
        id="engineering-ui-qa",
        description="Challenge UI state, content, geometry, browser and runtime coverage; proposal only.",
        supported_capabilities=("qa", "ui", "browser", "test", "responsive"),
        output_kinds=("review", "recommendation"), routing_policy="review",
        required_model_capabilities=("chat",), preferred_model_capabilities=("json",), parallelizable=True,
    ),
    WorkerProfile(
        id="engineering-visual-reviewer",
        description="Review visual-reference and source-correlation risks; proposal only.",
        supported_capabilities=("visual", "vision", "ui", "review"),
        output_kinds=("review", "recommendation"), routing_policy="review",
        required_model_capabilities=("chat",), preferred_model_capabilities=("json",), parallelizable=True,
    ),
    WorkerProfile(
        id="engineering-accessibility-reviewer",
        description="Review semantic, focus, keyboard, contrast and assistive-technology risks; proposal only.",
        supported_capabilities=("accessibility", "a11y", "ui", "review"),
        output_kinds=("review", "recommendation"), routing_policy="review",
        required_model_capabilities=("chat",), preferred_model_capabilities=("json",), parallelizable=True,
    ),
    WorkerProfile(
        id="engineering-security-reviewer",
        description="Review authority, secret, path, dependency and trust-boundary risks; proposal only.",
        supported_capabilities=("security", "authority", "review", "code"),
        output_kinds=("review", "recommendation"), routing_policy="review",
        required_model_capabilities=("chat",), preferred_model_capabilities=("json",), parallelizable=True,
    ),
    WorkerProfile(
        id="engineering-performance-reviewer",
        description="Review latency, resource, bundle and runtime performance risks; proposal only.",
        supported_capabilities=("performance", "profiling", "review", "code"),
        output_kinds=("review", "recommendation"), routing_policy="review",
        required_model_capabilities=("chat",), preferred_model_capabilities=("json",), parallelizable=True,
    ),
    WorkerProfile(
        id="engineering-code-reviewer",
        description="Adversarially review correctness and maintainability; never grants owner approval.",
        supported_capabilities=("code", "review", "quality"),
        output_kinds=("review", "critique"), routing_policy="review",
        required_model_capabilities=("chat",), preferred_model_capabilities=("json",), parallelizable=True,
    ),
    WorkerProfile(
        id="engineering-release-reviewer",
        description="Review qualification/release evidence and deployment risk; proposal only.",
        supported_capabilities=("release", "qualification", "review"),
        output_kinds=("review", "recommendation"), routing_policy="review",
        required_model_capabilities=("chat",), preferred_model_capabilities=("json",), parallelizable=True,
    ),
)

_PROFILE = {item.id: item for item in ENGINEERING_SPECIALISTS}


@dataclass(frozen=True)
class EngineeringSpecialistAdvice:
    role: str
    summary: str
    findings: tuple[str, ...] = ()
    suspected_files: tuple[str, ...] = ()
    required_tests: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "role": self.role,
            "summary": self.summary,
            "findings": list(self.findings),
            "suspected_files": list(self.suspected_files),
            "required_tests": list(self.required_tests),
            "risks": list(self.risks),
            "authority": "proposal_only",
        }


class EngineeringSpecialistSelector:
    """Select existing workforce-style specialist profiles without execution authority."""

    def select(self, spec: EngineeringSpec, *, max_roles: int = 4) -> tuple[WorkerProfile, ...]:
        surfaces = {str(item).casefold() for item in spec.affected_surfaces}
        roles = ["engineering-architect"]
        if spec.ui_required or "ui" in surfaces or "frontend" in surfaces:
            roles.extend(("engineering-frontend", "engineering-ui-qa"))
        if "api" in surfaces or "backend" in surfaces:
            roles.append("engineering-backend")
        if "database" in surfaces or spec.schema_impacts:
            roles.append("engineering-database")
        if "mobile" in surfaces or {"ios", "android"} & surfaces:
            roles.append("engineering-mobile")
        if spec.visual_review_required:
            roles.append("engineering-visual-reviewer")
        if spec.accessibility_required:
            roles.append("engineering-accessibility-reviewer")
        if spec.security_class in {SecurityClass.SENSITIVE, SecurityClass.AUTHORITY}:
            roles.append("engineering-security-reviewer")
        if bool(dict(spec.metadata).get("performance_required", False)):
            roles.append("engineering-performance-reviewer")
        unique = tuple(dict.fromkeys(roles))
        return tuple(_PROFILE[role] for role in unique[: max(1, min(int(max_roles), 8))])


class GovernedEngineeringSpecialistConsultations:
    """Bounded proposal-only model consultations through the existing model fabric."""

    def __init__(self, models, *, max_roles: int = 4) -> None:
        self.models = models
        self.max_roles = max(1, min(int(max_roles), 8))
        self.selector = EngineeringSpecialistSelector()

    @staticmethod
    def _tuple_strings(value, *, limit: int, chars: int) -> tuple[str, ...]:
        if isinstance(value, str):
            value = (value,)
        if not isinstance(value, (list, tuple)):
            return ()
        return tuple(str(item)[:chars] for item in value if str(item).strip())[:limit]

    def consult(
        self,
        *,
        spec: EngineeringSpec,
        graph: RepositoryGraph,
        defects: Iterable[str] = (),
    ) -> tuple[EngineeringSpecialistAdvice, ...]:
        if not hasattr(self.models, "request"):
            return ()
        profiles = self.selector.select(spec, max_roles=self.max_roles)
        paths = tuple(node.path for node in graph.nodes if node.kind in {"file", "test"})[:200]
        sensitivity = "sensitive" if spec.security_class in {SecurityClass.SENSITIVE, SecurityClass.AUTHORITY} else "internal"
        advice: list[EngineeringSpecialistAdvice] = []
        for profile in profiles:
            system = (
                f"You are Vishnu's {profile.id} specialist. You are proposal-only. "
                "You may identify risks, likely files and verification needs, but you have no tool, filesystem, shell, Git, "
                "approval, merge, deployment, rollback or activation authority. Return JSON with summary, findings, "
                "suspected_files, required_tests and risks only."
            )
            prompt = (
                f"EngineeringSpec={spec.to_dict()}\n"
                f"RepositoryPaths={list(paths)}\n"
                f"KnownDefects={list(defects)[:50]}\n"
                "Give concise specialist advice for the smallest safe implementation."
            )
            try:
                payload = governed_engineering_json(
                    self.models,
                    spec=spec,
                    prompt=prompt,
                    system=system,
                    role=profile.id,
                    sensitivity=sensitivity,
                )
            except Exception:
                # Consultations are advisory. The authoritative planner and
                # qualification gates remain fail-closed independently.
                continue
            advice.append(EngineeringSpecialistAdvice(
                role=profile.id,
                summary=str(payload.get("summary") or "")[:2000],
                findings=self._tuple_strings(payload.get("findings"), limit=20, chars=1000),
                suspected_files=self._tuple_strings(payload.get("suspected_files"), limit=30, chars=500),
                required_tests=self._tuple_strings(payload.get("required_tests"), limit=30, chars=500),
                risks=self._tuple_strings(payload.get("risks"), limit=20, chars=1000),
            ))
        return tuple(advice)
