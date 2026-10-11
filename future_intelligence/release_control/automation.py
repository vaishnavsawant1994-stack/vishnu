from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

from future_intelligence.engineering.contracts import EngineeringSpec, QualificationReport, SecurityClass

from .contracts import ReleaseEnvironment, ReleaseEvidence, ReleasePlan, ReleaseRiskClass, ReleaseStatus
from .runtime import ReleaseControlRuntime


@dataclass(frozen=True)
class ReleaseHandoffResult:
    created: bool
    release_id: str = ""
    automatic_execution_started: bool = False
    reason: str = ""


class ReleaseAutomationService:
    """One-way handoff from final engineering qualification to release control.

    It can automatically create/qualify a preview and promote only when the
    immutable owner policy snapshot permits automatic production for that plan.
    Canary completion remains driven by production observations. Sensitive
    releases are created as approval-gated plans and are never auto-promoted.
    """

    def __init__(self, runtime: ReleaseControlRuntime, *, default_provider: str = "", default_target: str = "") -> None:
        self.runtime = runtime
        self.default_provider = default_provider.strip()
        self.default_target = default_target.strip()
        self._lock = threading.RLock()
        self._active: set[str] = set()

    @staticmethod
    def classify_risk(spec: EngineeringSpec) -> ReleaseRiskClass:
        if spec.security_class is SecurityClass.AUTHORITY:
            return ReleaseRiskClass.CRITICAL
        if spec.security_class is SecurityClass.SENSITIVE:
            return ReleaseRiskClass.HIGH
        surfaces = " ".join(spec.affected_surfaces).lower()
        sensitive = (
            "auth", "security", "permission", "billing", "payment", "database",
            "migration", "credential", "secret", "provider", "runtime", "body",
            "release", "deploy", "owner",
        )
        if any(item in surfaces for item in sensitive):
            return ReleaseRiskClass.HIGH
        return ReleaseRiskClass.LOW

    def _select_provider(self) -> str:
        if self.default_provider:
            return self.default_provider if self.default_provider in self.runtime.providers else ""
        if len(self.runtime.providers) == 1:
            return next(iter(self.runtime.providers))
        return ""

    def handoff(self, *, spec: EngineeringSpec, report: QualificationReport) -> ReleaseHandoffResult:
        if not report.qualified:
            return ReleaseHandoffResult(False, reason="engineering candidate is not qualified")
        provider_name = self._select_provider()
        if not provider_name:
            return ReleaseHandoffResult(False, reason="no unambiguous release provider is configured")
        target = self.default_target or spec.repository
        plan = self.runtime.controller.create_plan(
            spec=spec,
            report=report,
            provider=provider_name,
            target=target,
            risk_class=self.classify_risk(spec),
            requested_environment=ReleaseEnvironment.PRODUCTION,
            metadata={"created_from": "engineering.final_qualification"},
        )
        policy = self.runtime.policy()
        started = False
        if policy.allows_automatic_production(plan):
            started = self.start(plan.id)
        return ReleaseHandoffResult(True, plan.id, started, "qualified candidate handed to release control")

    def start(self, release_id: str) -> bool:
        plan = self.runtime.controller.require(release_id)
        policy = self.runtime.policy()
        if not policy.allows_automatic_production(plan):
            return False
        with self._lock:
            if release_id in self._active:
                return False
            self._active.add(release_id)
        thread = threading.Thread(
            target=self._run,
            args=(release_id,),
            name=f"vishnu-release-{release_id[-8:]}",
            daemon=True,
        )
        thread.start()
        return True

    def _fail(self, release_id: str, exc: Exception) -> None:
        try:
            plan = self.runtime.controller.require(release_id)
            if plan.status.terminal:
                return
            plan = plan.with_update(status=ReleaseStatus.FAILED).append_evidence(
                ReleaseEvidence(
                    kind="release_automation_failure",
                    summary=f"Release automation stopped safely: {type(exc).__name__}",
                    revision=plan.candidate_revision,
                    trusted=True,
                    metadata={"error_type": type(exc).__name__},
                )
            )
            self.runtime.controller.store.save(plan)
        except Exception:
            pass

    def _run(self, release_id: str) -> None:
        try:
            plan = self.runtime.controller.require(release_id)
            provider = self.runtime.provider(plan.provider)
            if not self.runtime.policy().allows_automatic_production(plan):
                return
            if not self.runtime.controller._has_trusted_evidence(plan, "preview_qualification"):
                plan = self.runtime.controller.create_and_qualify_preview(release_id, provider=provider)
            if plan.status is ReleaseStatus.PREVIEW_QUALIFIED:
                # Re-read policy immediately before the authority-bearing
                # production action so a concurrent owner OFF takes effect.
                if not self.runtime.policy().allows_automatic_production(plan):
                    return
                self.runtime.controller.policy = self.runtime.policy()
                self.runtime.controller.promote(release_id, provider=provider)
        except Exception as exc:
            self._fail(release_id, exc)
        finally:
            with self._lock:
                self._active.discard(release_id)

    def active_release_ids(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._active))
