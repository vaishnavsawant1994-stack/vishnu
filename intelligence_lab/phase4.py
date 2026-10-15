from __future__ import annotations

import time
from typing import Any, Callable, Mapping, Sequence

from .config import CapabilityLevel
from .phase4_qualification import (
    AdaptiveExperiment,
    EnduranceQualifier,
    FailureEngineering,
    FailureScenario,
    HardwareTuningQualifier,
    ModelConfiguration,
    ModelTask,
    ProductionReadiness,
    RealModelBenchmark,
    RealWorldEvaluation,
    RedTeamQualifier,
    TrustedDeviceQualification,
)


class IntelligenceLabPhase4:
    """Real-world qualification and adaptive optimization over Phase 3.

    Phase 4 owns no model credentials, ToolRegistry authority, DeviceGateway
    authority, approvals, or production deployment controls. Every live adapter
    is injected by the host and must already be governed by Vishnu Core.
    """

    def __init__(self, phase3: Any):
        self.phase3 = phase3
        self.lab = phase3.lab
        self.memory = self.lab.memory
        self.models = RealModelBenchmark(phase3, self.memory)
        self.devices = TrustedDeviceQualification(phase3, self.memory)
        self.failures = FailureEngineering(self.memory)
        self.endurance = EnduranceQualifier(self.memory)
        self.hardware = HardwareTuningQualifier(phase3, self.memory)
        self.red_team = RedTeamQualifier(self.memory)
        self.real_world = RealWorldEvaluation(self.memory)
        self.experiments = AdaptiveExperiment(phase3, self.memory)
        self.production = ProductionReadiness(self.memory)
        self.memory.audit(
            "phase4",
            "attached",
            {
                "new_cognitive_authority": False,
                "new_execution_authority": False,
                "automatic_core_mutation": False,
                "production_deployment_performed": False,
            },
        )

    def _require_think(self) -> None:
        self.lab.settings.require(CapabilityLevel.THINK)

    def status(self) -> dict[str, Any]:
        self._require_think()
        return {
            "name": "Vishnu Intelligence Lab Phase 4 — Real-World Qualification & Adaptive Optimization",
            "real_model_benchmarking": True,
            "trusted_device_live_qualification": True,
            "failure_engineering": True,
            "large_scale_endurance": True,
            "measured_hardware_tuning": True,
            "red_team_qualification": True,
            "cross_domain_real_world_evaluation": True,
            "adaptive_ab_optimization": True,
            "observability_snapshot": True,
            "production_readiness_evidence_gate": True,
            "new_cognitive_authority": False,
            "new_execution_authority": False,
            "automatic_core_mutation": False,
            "production_deployment_performed": False,
        }

    def benchmark_models(
        self,
        tasks: Sequence[ModelTask],
        configurations: Sequence[ModelConfiguration],
        runner: Callable[[ModelTask, ModelConfiguration], Mapping[str, Any]],
        *,
        scorer: Callable[[ModelTask, Mapping[str, Any]], float] | None = None,
        require_live: bool = False,
    ):
        self._require_think()
        return self.models.run(
            tasks,
            configurations,
            runner,
            scorer=scorer,
            require_live=require_live,
        )

    def qualify_trusted_devices(
        self,
        device_ids: Sequence[str],
        probe: Callable[[str, str], Mapping[str, Any]],
        *,
        cycles: int = 3,
        require_live: bool = True,
    ):
        self._require_think()
        return self.devices.qualify(
            device_ids,
            probe,
            cycles=cycles,
            require_live=require_live,
        )

    def run_failure_engineering(
        self,
        scenarios: Sequence[FailureScenario],
        operation: Callable[[FailureScenario], Mapping[str, Any]],
    ):
        self._require_think()
        return self.failures.run(scenarios, operation)

    def run_endurance(
        self,
        worker: Callable[[int], Mapping[str, Any]],
        *,
        iterations: int = 1000,
        concurrency: int = 8,
        minimum_success_rate: float = 0.995,
    ):
        self._require_think()
        return self.endurance.run(
            worker,
            iterations=iterations,
            concurrency=concurrency,
            minimum_success_rate=minimum_success_rate,
        )

    def qualify_hardware_tuning(
        self,
        platform: str,
        metadata: Mapping[str, Any],
        measurements: Sequence[Mapping[str, Any]],
        *,
        minimum_quality: float = 0.8,
    ) -> dict[str, Any]:
        self._require_think()
        return self.hardware.run(
            platform,
            metadata,
            measurements,
            minimum_quality=minimum_quality,
        )

    def run_red_team(self, evaluator, *, scenarios=None):
        self._require_think()
        return self.red_team.run(evaluator, scenarios=scenarios)

    def run_real_world_evaluation(self, evaluator, *, domains=None, require_live: bool = False):
        self._require_think()
        return self.real_world.run(
            evaluator,
            domains=domains,
            require_live=require_live,
        )

    def run_adaptive_experiment(
        self,
        task_class: str,
        configurations: Sequence[ModelConfiguration],
        runner,
        *,
        rounds: int = 5,
        minimum_quality: float = 0.8,
    ) -> dict[str, Any]:
        self._require_think()
        return self.experiments.run(
            task_class,
            configurations,
            runner,
            rounds=rounds,
            minimum_quality=minimum_quality,
        )

    def production_readiness(self, evidence: Mapping[str, Any]) -> dict[str, Any]:
        self._require_think()
        return self.production.assess(evidence)

    def observability(self) -> dict[str, Any]:
        self._require_think()
        recent_reports = {
            kind: self.memory.recent(kind, 10)
            for kind in (
                "phase4_model_benchmark",
                "phase4_device_qualification",
                "phase4_failure_engineering",
                "phase4_endurance",
                "phase4_hardware_tuning",
                "phase4_red_team",
                "phase4_real_world_evaluation",
                "phase4_adaptive_experiment",
                "phase4_production_readiness",
            )
        }
        performance = self.phase3.performance_summary()
        return {
            "generated_at": time.time(),
            "phase3": performance,
            "phase4": recent_reports,
            "governed_distributed_compute_available": self.phase3.status().get(
                "governed_distributed_compute_available", False
            ),
            "core_execution_authority_added": False,
            "automatic_core_mutation": False,
            "raw_prompts_in_dashboard": False,
            "credentials_in_dashboard": False,
        }

    def recommended_next_configuration(
        self,
        *,
        task_class: str = "general",
        minimum_quality: float = 0.8,
        maximum_cost: float | None = None,
    ) -> dict[str, Any]:
        self._require_think()
        recommendation = self.phase3.recommend_optimization(
            task_class=task_class,
            minimum_quality=minimum_quality,
            maximum_cost=maximum_cost,
        )
        return {
            **recommendation,
            "recommendation_only": True,
            "automatic_core_mutation": False,
            "promotion_requires_owner_and_release_governance": True,
        }
