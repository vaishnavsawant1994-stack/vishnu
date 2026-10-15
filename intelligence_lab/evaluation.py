from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from .config import LabSettings
from .memory import LabMemory
from .models import EvaluationResult, Experiment, ExperimentStatus, PromotionRecord, PromotionStatus


class ExperimentManager:
    """Records safety-bounded experiments in the isolated Lab store."""

    def __init__(self, memory: LabMemory):
        self.memory = memory

    def create(self, name: str, hypothesis: str, inputs: Mapping[str, Any] | None = None) -> Experiment:
        experiment = Experiment(
            name=str(name).strip(),
            hypothesis=str(hypothesis).strip(),
            inputs=dict(inputs or {}),
        )
        if not experiment.name or not experiment.hypothesis:
            raise ValueError("experiment name and hypothesis are required")
        self.memory.put(experiment.id, "experiment", experiment.public_dict())
        self.memory.audit("experiment", "created", {"id": experiment.id, "name": experiment.name})
        return experiment

    def complete(self, experiment: Experiment, result: Mapping[str, Any], *, successful: bool) -> Experiment:
        status = ExperimentStatus.COMPLETED if successful else ExperimentStatus.FAILED
        completed = replace(experiment, status=status, result=dict(result))
        self.memory.put(completed.id, "experiment", completed.public_dict())
        self.memory.audit(
            "experiment",
            "completed" if successful else "failed",
            {"id": completed.id},
        )
        return completed


class AGIResearchEvaluator:
    """Capability evaluator, not an AGI declaration mechanism.

    It scores evidence across generality-relevant dimensions. Passing means only
    that the candidate met the configured Lab benchmark, never that AGI/ASI was
    achieved.
    """

    DIMENSIONS = (
        "novel_task_learning",
        "cross_domain_transfer",
        "reasoning",
        "long_horizon_planning",
        "tool_discovery",
        "self_correction",
        "uncertainty_calibration",
        "social_context_reasoning",
        "safety_compliance",
        "verification_discipline",
    )

    def __init__(self, memory: LabMemory, settings: LabSettings):
        self.memory = memory
        self.settings = settings

    def evaluate(
        self,
        subject_id: str,
        scores: Mapping[str, float],
        *,
        evidence: list[str] | tuple[str, ...],
    ) -> EvaluationResult:
        normalized: dict[str, float] = {}
        failures: list[str] = []
        for dimension in self.DIMENSIONS:
            raw = float(scores.get(dimension, 0.0))
            value = max(0.0, min(raw, 1.0))
            normalized[dimension] = value
            if value < self.settings.minimum_promotion_score:
                failures.append(f"{dimension} below threshold")
        if not evidence:
            failures.append("no qualification evidence supplied")
        result = EvaluationResult(
            subject_id=subject_id,
            scores=normalized,
            passed=not failures,
            evidence=tuple(str(item) for item in evidence),
            failures=tuple(failures),
        )
        self.memory.put(result.id, "evaluation", result.public_dict())
        self.memory.audit(
            "evaluation",
            "completed",
            {
                "id": result.id,
                "subject_id": subject_id,
                "passed": result.passed,
                "aggregate_score": result.aggregate_score,
                "agi_claim": False,
            },
        )
        return result


class PromotionGate:
    """Experiment -> evaluation -> verification -> owner approval -> eligibility.

    Eligibility is intentionally the final operation here. This class has no
    code path that mutates stable Vishnu code, memory, policy, permissions, or
    tool registration. Promotion into Core is a separate engineering/release act.
    """

    def __init__(self, memory: LabMemory, settings: LabSettings):
        self.memory = memory
        self.settings = settings

    def begin(self, subject_id: str) -> PromotionRecord:
        record = PromotionRecord(subject_id=subject_id)
        self._store(record)
        return record

    def attach_evaluation(self, record: PromotionRecord, evaluation: EvaluationResult) -> PromotionRecord:
        if evaluation.subject_id != record.subject_id:
            raise ValueError("evaluation does not belong to promotion subject")
        if not evaluation.passed or evaluation.aggregate_score < self.settings.minimum_promotion_score:
            rejected = replace(
                record,
                evaluation_id=evaluation.id,
                status=PromotionStatus.REJECTED,
                rejection_reason="qualification threshold not met",
            )
            self._store(rejected)
            return rejected
        updated = replace(record, evaluation_id=evaluation.id, status=PromotionStatus.EVALUATED)
        self._store(updated)
        return updated

    def verify(self, record: PromotionRecord, evidence: list[str] | tuple[str, ...]) -> PromotionRecord:
        if record.status is not PromotionStatus.EVALUATED:
            raise PermissionError("promotion must pass evaluation before verification")
        clean = tuple(str(item).strip() for item in evidence if str(item).strip())
        if not clean:
            raise ValueError("verification evidence is required")
        updated = replace(
            record,
            verification_evidence=clean,
            status=PromotionStatus.VERIFIED,
        )
        self._store(updated)
        return updated

    def owner_approve(self, record: PromotionRecord, *, approved: bool) -> PromotionRecord:
        if record.status is not PromotionStatus.VERIFIED:
            raise PermissionError("promotion must be verified before owner approval")
        if not approved:
            updated = replace(
                record,
                owner_approved=False,
                status=PromotionStatus.REJECTED,
                rejection_reason="owner did not approve promotion",
            )
        else:
            updated = replace(
                record,
                owner_approved=True,
                status=PromotionStatus.OWNER_APPROVED,
            )
        self._store(updated)
        return updated

    def mark_eligible(self, record: PromotionRecord) -> PromotionRecord:
        if record.status is not PromotionStatus.OWNER_APPROVED or not record.owner_approved:
            raise PermissionError("owner approval is required before promotion eligibility")
        if not record.evaluation_id or not record.verification_evidence:
            raise PermissionError("promotion evidence is incomplete")
        updated = replace(record, status=PromotionStatus.ELIGIBLE)
        self._store(updated)
        self.memory.audit(
            "promotion",
            "eligible_for_engineering_review",
            {
                "id": updated.id,
                "subject_id": updated.subject_id,
                "stable_core_mutated": False,
            },
        )
        return updated

    def _store(self, record: PromotionRecord) -> None:
        self.memory.put(record.id, "promotion", record.public_dict())
        self.memory.audit(
            "promotion",
            record.status.value,
            {"id": record.id, "subject_id": record.subject_id},
        )
