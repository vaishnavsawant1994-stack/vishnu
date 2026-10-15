from __future__ import annotations

from pathlib import Path

from intelligence_lab.bootstrap import build_intelligence_lab
from intelligence_lab.config import CapabilityLevel, LabSettings
from intelligence_lab.phase4_qualification import (
    FailureScenario,
    ModelConfiguration,
    ModelTask,
)
from intelligence_lab.phase4_service import create_phase4_app


def settings(tmp_path: Path) -> LabSettings:
    return LabSettings(
        enabled=True,
        level=CapabilityLevel.THINK,
        data_dir=tmp_path / "lab",
        max_models=3,
        benchmark_variants=1,
        learning_window=100,
    )


def test_phase4_attaches_without_new_authority(tmp_path):
    lab = build_intelligence_lab(settings=settings(tmp_path), use_core_model=False)
    status = lab.phase3.phase4.status()
    assert status["real_model_benchmarking"] is True
    assert status["trusted_device_live_qualification"] is True
    assert status["new_cognitive_authority"] is False
    assert status["new_execution_authority"] is False
    assert status["automatic_core_mutation"] is False


def test_real_model_benchmark_records_optimizer_evidence(tmp_path):
    lab = build_intelligence_lab(settings=settings(tmp_path), use_core_model=False)
    tasks = [
        ModelTask("t1", "summarize", task_class="research"),
        ModelTask("t2", "compare", task_class="research"),
    ]
    configs = [
        ModelConfiguration("fast", depth="fast", model_count=1, parallelism=1),
        ModelConfiguration("smart", depth="smart", model_count=2, parallelism=2),
    ]

    def runner(task, config):
        return {
            "success": True,
            "quality": 0.86 if config.name == "fast" else 0.94,
            "latency_ms": 20 if config.name == "fast" else 40,
            "cost": 0.01 if config.name == "fast" else 0.02,
            "tokens": 100,
            "live": True,
            "evidence": [f"{config.name}:{task.id}"],
        }

    report = lab.phase3.phase4.benchmark_models(
        tasks,
        configs,
        runner,
        require_live=True,
    )
    assert report.passed is True
    assert report.live_samples == 4
    recommendation = lab.phase3.phase4.recommended_next_configuration(
        task_class="research",
        minimum_quality=0.8,
    )
    assert recommendation["adaptive"] is True
    assert recommendation["automatic_core_mutation"] is False


def test_trusted_device_qualification_distinguishes_live_evidence(tmp_path):
    lab = build_intelligence_lab(settings=settings(tmp_path), use_core_model=False)

    def probe(device_id, operation):
        return {
            "success": True,
            "live": True,
            "quality": 1.0,
            "evidence": [f"{device_id}:{operation}:ok"],
        }

    report = lab.phase3.phase4.qualify_trusted_devices(
        ["desktop-a"],
        probe,
        cycles=3,
        require_live=True,
    )
    assert report.passed is True
    assert report.live_samples == 3


def test_failure_engineering_requires_safe_recovery(tmp_path):
    lab = build_intelligence_lab(settings=settings(tmp_path), use_core_model=False)
    scenarios = [
        FailureScenario("network-drop", "dispatch"),
        FailureScenario("worker-crash", "reasoning"),
        FailureScenario("db-retry", "checkpoint"),
    ]

    def operation(scenario):
        return {
            "safe": True,
            "recovered": True,
            "evidence": [f"{scenario.name}:recovered"],
        }

    report = lab.phase3.phase4.run_failure_engineering(scenarios, operation)
    assert report.passed is True
    assert report.success_rate == 1.0


def test_endurance_is_bounded_and_concurrent(tmp_path):
    lab = build_intelligence_lab(settings=settings(tmp_path), use_core_model=False)

    report = lab.phase3.phase4.run_endurance(
        lambda index: {"success": True, "quality": 0.99},
        iterations=250,
        concurrency=8,
        minimum_success_rate=0.99,
    )
    assert report.samples == 250
    assert report.passed is True


def test_red_team_suite_fails_closed(tmp_path):
    lab = build_intelligence_lab(settings=settings(tmp_path), use_core_model=False)

    def evaluator(scenario):
        return {
            "safe": True,
            "detected": True,
            "evidence": [scenario.expected],
        }

    report = lab.phase3.phase4.run_red_team(evaluator)
    assert report.passed is True
    assert report.samples >= 5


def test_real_world_cross_domain_evaluation(tmp_path):
    lab = build_intelligence_lab(settings=settings(tmp_path), use_core_model=False)

    def evaluator(domain):
        return {
            "success": True,
            "quality": 0.9,
            "live": True,
            "evidence": [f"{domain}:evidence"],
        }

    report = lab.phase3.phase4.run_real_world_evaluation(
        evaluator,
        require_live=True,
    )
    assert report.passed is True
    assert report.live_samples == report.samples


def test_adaptive_experiment_recommends_but_never_mutates_core(tmp_path):
    lab = build_intelligence_lab(settings=settings(tmp_path), use_core_model=False)
    configs = [
        ModelConfiguration("fast", depth="fast", model_count=1, parallelism=1),
        ModelConfiguration("deep", depth="deep", model_count=3, parallelism=1),
    ]

    def runner(config):
        if config.name == "fast":
            return {"success": True, "quality": 0.9, "latency_ms": 25, "cost": 0.01}
        return {"success": True, "quality": 0.91, "latency_ms": 400, "cost": 0.2}

    outcome = lab.phase3.phase4.run_adaptive_experiment(
        "coding",
        configs,
        runner,
        rounds=4,
        minimum_quality=0.85,
    )
    assert outcome["recommendation"]["configuration"]["depth"] == "fast"
    assert outcome["automatic_core_mutation"] is False
    assert outcome["promotion_requires_owner_and_release_governance"] is True


def test_measured_hardware_tuning_is_recommendation_only(tmp_path):
    lab = build_intelligence_lab(settings=settings(tmp_path), use_core_model=False)
    result = lab.phase3.phase4.qualify_hardware_tuning(
        "linux",
        {
            "gpu": "NVIDIA RTX",
            "cuda": True,
            "memory_gb": 32,
            "server_class": True,
        },
        [
            {
                "name": "fp16",
                "success": True,
                "quality": 0.95,
                "latency_ms": 100,
                "tokens_per_second": 200,
                "memory_gb": 16,
            },
            {
                "name": "q4",
                "success": True,
                "quality": 0.91,
                "latency_ms": 60,
                "tokens_per_second": 350,
                "memory_gb": 8,
            },
        ],
        minimum_quality=0.9,
    )
    assert result["qualified_candidates"] == 2
    assert result["recommended_measurement"] is not None
    assert result["runtime_configuration_mutated"] is False


def test_production_readiness_does_not_overclaim(tmp_path):
    lab = build_intelligence_lab(settings=settings(tmp_path), use_core_model=False)
    evidence = {
        "real_model_evidence": True,
        "real_device_evidence": True,
        "failure_recovery_evidence": True,
        "endurance_evidence": True,
        "red_team_evidence": True,
        "cross_domain_evidence": True,
        "package_reproducibility_evidence": True,
        "provider_acceptance": False,
        "native_signing": False,
        "production_backup_restore": False,
    }
    result = lab.phase3.phase4.production_readiness(evidence)
    assert result["ready"] is False
    assert result["release_claim_allowed"] is False
    assert result["production_deployment_performed"] is False
    assert "native_signing" in result["missing"]


def test_observability_dashboard_is_read_only(tmp_path):
    lab = build_intelligence_lab(settings=settings(tmp_path), use_core_model=False)
    snapshot = lab.phase3.phase4.observability()
    assert snapshot["core_execution_authority_added"] is False
    assert snapshot["raw_prompts_in_dashboard"] is False
    assert snapshot["credentials_in_dashboard"] is False

    app = create_phase4_app(lab)
    paths = {route.path for route in app.routes}
    assert "/phase4/status" in paths
    assert "/phase4/observability" in paths
    assert "/phase4/dashboard" in paths
    assert "/phase4/execute" not in paths
    assert "/phase4/tool-dispatch" not in paths
    assert "/phase4/credentials" not in paths


def test_live_requirement_rejects_simulated_model_evidence(tmp_path):
    lab = build_intelligence_lab(settings=settings(tmp_path), use_core_model=False)
    report = lab.phase3.phase4.benchmark_models(
        [ModelTask("t", "test")],
        [ModelConfiguration("smart")],
        lambda task, config: {
            "success": True,
            "quality": 1.0,
            "latency_ms": 1,
            "live": False,
        },
        require_live=True,
    )
    assert report.passed is False
