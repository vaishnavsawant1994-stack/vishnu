from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from future_intelligence.engineering.canary import CanaryMetrics, CanaryThresholds, compare_canary
from future_intelligence.engineering.contracts import EngineeringSpec, QualificationReport
from future_intelligence.engineering.production_feedback import ProductionRegressionWorkBridge
from future_intelligence.engineering.release_qualification import (
    PreviewQualificationProvider,
    ProductionRegression,
    ProductionSmokeProvider,
)

from .contracts import (
    ReleaseEnvironment,
    ReleaseEvidence,
    ReleasePlan,
    ReleaseRiskClass,
    ReleaseStatus,
)
from .policy import ReleaseOwnerPolicy
from .providers import ReleaseDeployment, ReleaseProvider
from .store import ReleaseStore


class ReleaseControlError(RuntimeError):
    pass


def _qualification_digest(report: QualificationReport) -> str:
    payload = json.dumps(report.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _release_id(spec: EngineeringSpec, report: QualificationReport, target: str) -> str:
    seed = "|".join((spec.work_order_id, spec.attempt_id, report.candidate_revision, target)).encode("utf-8")
    return f"release-{hashlib.sha256(seed).hexdigest()[:24]}"


class GovernedReleaseController:
    """Revision-bound release authority above the engineering subsystem.

    The controller never asks a model to deploy, never accepts a different
    revision from a provider, and never treats canary analysis as rollback
    authority. Provider credentials and infrastructure permissions remain in
    the configured ReleaseProvider implementation.
    """

    def __init__(
        self,
        *,
        store: ReleaseStore,
        policy: ReleaseOwnerPolicy,
        preview_qualifier: PreviewQualificationProvider | None = None,
        production_smoke: ProductionSmokeProvider | None = None,
        regression_bridge: ProductionRegressionWorkBridge | None = None,
    ) -> None:
        self.store = store
        self.policy = policy
        self.preview_qualifier = preview_qualifier
        self.production_smoke = production_smoke
        self.regression_bridge = regression_bridge

    def _save(self, plan: ReleasePlan) -> ReleasePlan:
        return self.store.save(plan)

    def require(self, release_id: str) -> ReleasePlan:
        plan = self.store.get(release_id)
        if plan is None:
            raise ReleaseControlError(f"unknown release: {release_id}")
        return plan

    @staticmethod
    def _provider_matches(plan: ReleasePlan, provider: ReleaseProvider) -> None:
        if str(provider.name) != plan.provider:
            raise ReleaseControlError("release provider does not match the bound plan")

    @staticmethod
    def _validate_deployment(plan: ReleasePlan, deployment: ReleaseDeployment, environment: ReleaseEnvironment) -> None:
        if deployment.revision != plan.candidate_revision:
            raise ReleaseControlError("provider returned a deployment for a different revision")
        if deployment.environment is not environment:
            raise ReleaseControlError("provider returned the wrong deployment environment")
        if deployment.provider != plan.provider or deployment.target != plan.target:
            raise ReleaseControlError("provider returned a deployment outside the bound target")
        if deployment.state.lower() not in {"ready", "healthy", "active", "succeeded"}:
            raise ReleaseControlError(f"deployment is not ready: {deployment.state}")

    @staticmethod
    def _has_trusted_evidence(plan: ReleasePlan, kind: str) -> bool:
        return any(
            item.kind == kind and item.trusted and item.revision == plan.candidate_revision
            for item in plan.evidence
        )

    def create_plan(
        self,
        *,
        spec: EngineeringSpec,
        report: QualificationReport,
        provider: str,
        target: str,
        risk_class: ReleaseRiskClass = ReleaseRiskClass.MEDIUM,
        requested_environment: ReleaseEnvironment = ReleaseEnvironment.PRODUCTION,
        metadata: dict[str, Any] | None = None,
    ) -> ReleasePlan:
        if not report.qualified:
            raise ReleaseControlError("engineering candidate is not qualified")
        if report.spec_id != spec.id:
            raise ReleaseControlError("qualification report is not bound to this EngineeringSpec")
        if report.base_revision != spec.base_revision:
            raise ReleaseControlError("qualification base revision does not match EngineeringSpec")
        if report.candidate_revision == report.base_revision:
            raise ReleaseControlError("qualification did not produce a distinct candidate revision")
        if not provider.strip() or not target.strip():
            raise ReleaseControlError("provider and target are required")

        digest = _qualification_digest(report)
        release_id = _release_id(spec, report, target)
        existing = self.store.get(release_id)
        if existing is not None:
            if (
                existing.candidate_revision != report.candidate_revision
                or existing.qualification_digest != digest
                or existing.repository != spec.repository
            ):
                raise ReleaseControlError("release id collision with different qualified evidence")
            return existing

        plan = ReleasePlan(
            id=release_id,
            work_order_id=spec.work_order_id,
            attempt_id=spec.attempt_id,
            engineering_spec_id=spec.id,
            repository=spec.repository,
            base_revision=spec.base_revision,
            candidate_revision=report.candidate_revision,
            qualification_digest=digest,
            provider=provider.strip(),
            target=target.strip(),
            risk_class=ReleaseRiskClass.parse(risk_class),
            requested_environment=requested_environment,
            affected_surfaces=tuple(spec.affected_surfaces),
            approval_required=True,
            metadata=dict(metadata or {}),
        )
        approval_required = self.policy.requires_owner_approval(plan)
        plan = plan.with_update(approval_required=approval_required)
        plan = plan.append_evidence(
            ReleaseEvidence(
                kind="engineering_qualification",
                summary="Exact engineering candidate passed trusted qualification and independent review.",
                reference=f"sha256:{digest}",
                revision=report.candidate_revision,
                trusted=True,
                metadata={
                    "spec_id": report.spec_id,
                    "reviewer": report.reviewer,
                    "review_decision": report.review_decision,
                    "gate_count": len(report.gates),
                },
            )
        )
        return self._save(plan)

    def approve(self, release_id: str, *, owner_identity: str) -> ReleasePlan:
        plan = self.require(release_id)
        if plan.status.terminal:
            raise ReleaseControlError("terminal release cannot be approved")
        if not owner_identity.strip():
            raise ReleaseControlError("owner identity is required")
        plan = plan.with_update(
            approved_by=owner_identity.strip(),
            approved_at=datetime.now(UTC).isoformat(),
        ).append_evidence(
            ReleaseEvidence(
                kind="owner_approval",
                summary="Owner approved production promotion for the exact bound candidate.",
                revision=plan.candidate_revision,
                trusted=True,
                metadata={"owner_identity": owner_identity.strip()},
            )
        )
        return self._save(plan)

    def create_and_qualify_preview(self, release_id: str, *, provider: ReleaseProvider) -> ReleasePlan:
        plan = self.require(release_id)
        self._provider_matches(plan, provider)
        if not self.policy.can_create_preview():
            raise ReleaseControlError("release policy does not permit previews")
        if plan.status.terminal:
            raise ReleaseControlError("terminal release cannot create a preview")
        if self.preview_qualifier is None:
            raise ReleaseControlError("preview qualification provider is required before deployment")

        plan = self._save(plan.with_update(status=ReleaseStatus.PREVIEWING))
        deployment = provider.create_preview(plan)
        self._validate_deployment(plan, deployment, ReleaseEnvironment.PREVIEW)
        plan = self._save(
            plan.with_update(
                status=ReleaseStatus.PREVIEW_QUALIFYING,
                preview_deployment_id=deployment.id,
                preview_url=deployment.url,
            ).append_evidence(
                ReleaseEvidence(
                    kind="preview_deployment",
                    summary="Provider created a preview for the exact candidate revision.",
                    reference=deployment.id,
                    revision=plan.candidate_revision,
                    trusted=True,
                    metadata=deployment.to_dict(),
                )
            )
        )
        result = self.preview_qualifier.qualify_preview(
            target=deployment.url,
            spec_id=plan.engineering_spec_id,
            candidate_revision=plan.candidate_revision,
        )
        evidence = ReleaseEvidence(
            kind="preview_qualification",
            summary=result.summary or ("Preview qualification passed." if result.passed else "Preview qualification failed."),
            reference=";".join(result.evidence),
            revision=plan.candidate_revision,
            trusted=True,
            metadata=result.to_dict(),
        )
        next_status = ReleaseStatus.PREVIEW_QUALIFIED if result.passed else ReleaseStatus.FAILED
        plan = plan.with_update(status=next_status).append_evidence(evidence)
        return self._save(plan)

    def promote(self, release_id: str, *, provider: ReleaseProvider) -> ReleasePlan:
        plan = self.require(release_id)
        self._provider_matches(plan, provider)
        if plan.status.terminal:
            raise ReleaseControlError("terminal release cannot be promoted")
        if self.policy.require_exact_revision_evidence and not self._has_trusted_evidence(plan, "engineering_qualification"):
            raise ReleaseControlError("exact-revision engineering qualification evidence is missing")
        if self.policy.require_preview and not self._has_trusted_evidence(plan, "preview_qualification"):
            raise ReleaseControlError("qualified preview evidence is required")
        if not self.policy.can_promote(plan):
            if self.policy.requires_owner_approval(plan) and not plan.approved_by:
                raise ReleaseControlError("owner approval is required for this production release")
            raise ReleaseControlError("release policy does not permit production promotion")
        if self.policy.require_production_smoke and self.production_smoke is None:
            raise ReleaseControlError("production smoke provider is required before promotion")

        plan = self._save(plan.with_update(status=ReleaseStatus.PROMOTING))
        deployment = provider.promote(plan)
        self._validate_deployment(plan, deployment, ReleaseEnvironment.PRODUCTION)
        plan = self._save(
            plan.with_update(
                status=ReleaseStatus.PRODUCTION_QUALIFYING,
                production_deployment_id=deployment.id,
                production_url=deployment.url,
            ).append_evidence(
                ReleaseEvidence(
                    kind="production_deployment",
                    summary="Provider promoted the exact qualified candidate revision.",
                    reference=deployment.id,
                    revision=plan.candidate_revision,
                    trusted=True,
                    metadata=deployment.to_dict(),
                )
            )
        )

        if self.policy.require_production_smoke:
            assert self.production_smoke is not None
            result = self.production_smoke.smoke_production(
                target=deployment.url,
                release_revision=plan.candidate_revision,
            )
            plan = plan.append_evidence(
                ReleaseEvidence(
                    kind="production_smoke",
                    summary=result.summary or ("Production smoke passed." if result.passed else "Production smoke failed."),
                    reference=";".join(result.evidence),
                    revision=plan.candidate_revision,
                    trusted=True,
                    metadata=result.to_dict(),
                )
            )
            if not result.passed:
                return self._save(plan.with_update(status=ReleaseStatus.ROLLBACK_RECOMMENDED))

        return self._save(
            plan.with_update(
                status=ReleaseStatus.MONITORING if self.policy.require_canary else ReleaseStatus.SUCCEEDED
            )
        )

    def record_canary(
        self,
        release_id: str,
        *,
        baseline: CanaryMetrics,
        candidate: CanaryMetrics,
        additional_checks: dict[str, bool] | None = None,
    ) -> ReleasePlan:
        plan = self.require(release_id)
        if plan.status is not ReleaseStatus.MONITORING:
            raise ReleaseControlError("release is not in canary monitoring")
        thresholds = CanaryThresholds(
            max_error_rate_absolute=0.05,
            max_error_rate_increase=self.policy.canary_max_error_rate_regression,
            max_p95_latency_ratio=self.policy.canary_max_latency_ratio,
            min_sample_count=self.policy.canary_min_requests,
        )
        recommendation = compare_canary(
            baseline,
            candidate,
            thresholds=thresholds,
            additional_checks=additional_checks,
        )
        plan = plan.append_evidence(
            ReleaseEvidence(
                kind="canary_observation",
                summary=(
                    "Canary recommends rollback."
                    if recommendation.recommended
                    else "Canary is healthy." if recommendation.sufficient_evidence else "Canary evidence is not yet sufficient."
                ),
                revision=plan.candidate_revision,
                trusted=True,
                metadata={
                    "baseline": baseline.__dict__,
                    "candidate": candidate.__dict__,
                    "thresholds": thresholds.__dict__,
                    "recommendation": recommendation.to_dict(),
                    "additional_checks": dict(additional_checks or {}),
                },
            )
        )
        if not recommendation.sufficient_evidence:
            return self._save(plan)
        if recommendation.recommended:
            plan = self._save(plan.with_update(status=ReleaseStatus.ROLLBACK_RECOMMENDED))
            self._create_regression_work(
                plan,
                signal="; ".join(recommendation.reasons) or "canary regression",
                evidence=("release-canary",),
                severity="high",
            )
            return plan
        return self._save(plan.with_update(status=ReleaseStatus.SUCCEEDED))

    def observe_regression(
        self,
        release_id: str,
        *,
        signal: str,
        evidence: tuple[str, ...] = (),
        severity: str = "warning",
    ) -> Any:
        plan = self.require(release_id)
        if not signal.strip():
            raise ReleaseControlError("production regression signal is required")
        plan = plan.append_evidence(
            ReleaseEvidence(
                kind="production_regression",
                summary=signal.strip(),
                revision=plan.candidate_revision,
                trusted=False,
                metadata={"evidence": list(evidence), "severity": severity},
            )
        )
        self._save(plan)
        return self._create_regression_work(plan, signal=signal, evidence=evidence, severity=severity)

    def _create_regression_work(
        self,
        plan: ReleasePlan,
        *,
        signal: str,
        evidence: tuple[str, ...],
        severity: str,
    ) -> Any:
        regression = ProductionRegression(
            release_revision=plan.candidate_revision,
            target=plan.production_url or plan.target,
            signal=signal,
            evidence=evidence,
            severity=severity,
        )
        if self.regression_bridge is None:
            return regression
        return self.regression_bridge.create(regression)

    def rollback(
        self,
        release_id: str,
        *,
        provider: ReleaseProvider,
        explicitly_approved: bool,
    ) -> ReleasePlan:
        plan = self.require(release_id)
        self._provider_matches(plan, provider)
        if plan.status is not ReleaseStatus.ROLLBACK_RECOMMENDED:
            raise ReleaseControlError("rollback requires an explicit rollback recommendation")
        if not plan.production_deployment_id or not plan.production_url:
            raise ReleaseControlError("production deployment evidence is missing")
        if not self.policy.can_execute_rollback(explicitly_approved=explicitly_approved):
            raise ReleaseControlError("release policy does not grant rollback execution authority")

        deployed = ReleaseDeployment(
            id=plan.production_deployment_id,
            provider=plan.provider,
            target=plan.target,
            revision=plan.candidate_revision,
            environment=ReleaseEnvironment.PRODUCTION,
            url=plan.production_url,
            state="ready",
        )
        plan = self._save(plan.with_update(status=ReleaseStatus.ROLLING_BACK))
        result = provider.rollback(plan, deployed)
        if result.revision != plan.base_revision or result.environment is not ReleaseEnvironment.PRODUCTION:
            raise ReleaseControlError("rollback provider did not restore the bound base revision")
        plan = plan.with_update(status=ReleaseStatus.ROLLED_BACK).append_evidence(
            ReleaseEvidence(
                kind="rollback_execution",
                summary="Explicitly approved rollback restored the bound base revision.",
                reference=result.id,
                revision=plan.candidate_revision,
                trusted=True,
                metadata={"restored_revision": result.revision, "deployment": result.to_dict()},
            )
        )
        return self._save(plan)

    def cancel(self, release_id: str, *, reason: str) -> ReleasePlan:
        plan = self.require(release_id)
        if plan.status.terminal:
            return plan
        if plan.status in {ReleaseStatus.PROMOTING, ReleaseStatus.ROLLING_BACK}:
            raise ReleaseControlError("cannot cancel while an authority-bearing provider action is in progress")
        plan = plan.with_update(status=ReleaseStatus.CANCELLED).append_evidence(
            ReleaseEvidence(
                kind="release_cancelled",
                summary=reason.strip() or "Release cancelled by owner/policy.",
                revision=plan.candidate_revision,
                trusted=True,
            )
        )
        return self._save(plan)
