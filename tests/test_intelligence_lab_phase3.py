from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from intelligence_lab.bootstrap import build_intelligence_lab
from intelligence_lab.cache import CachePolicy, SafeSemanticCache
from intelligence_lab.config import CapabilityLevel, LabSettings
from intelligence_lab.models import Plan, PlanStep
from intelligence_lab.performance import PerformanceBudget
from intelligence_lab.phase3_service import create_phase3_app
from intelligence_lab.retrieval import ContextCompressor


class FakeDevices:
    def list(self):
        return [
            {
                "id": "gpu-box",
                "name": "GPU Box",
                "platform": "linux",
                "created_at": "2026-01-01T00:00:00Z",
                "last_seen_at": "2026-01-01T00:00:00Z",
                "revoked": False,
                "permissions": ["ai:chat", "device:read"],
                "metadata": {
                    "compute_enabled": "true",
                    "local": "true",
                    "gpu": "NVIDIA RTX",
                    "memory_gb": "32",
                    "network": "ethernet",
                    "battery_percent": "100",
                },
            },
            {
                "id": "revoked",
                "name": "Revoked",
                "platform": "linux",
                "revoked": True,
                "permissions": ["ai:chat"],
                "metadata": {"compute_enabled": "true", "gpu": "NVIDIA"},
            },
        ]


def lab_settings(tmp_path: Path) -> LabSettings:
    return LabSettings(
        enabled=True,
        level=CapabilityLevel.THINK,
        data_dir=tmp_path / "lab",
        max_models=3,
        benchmark_variants=1,
        learning_window=100,
    )


def test_phase3_attaches_without_changing_core_authority(tmp_path):
    core = {
        "settings": SimpleNamespace(data_dir=tmp_path / "stable"),
        "device_registry": FakeDevices(),
    }
    lab = build_intelligence_lab(
        core_runtime=core,
        settings=lab_settings(tmp_path),
        use_core_model=False,
    )
    status = lab.phase3.status()
    assert status["adaptive_fast_smart_deep_routing"] is True
    assert status["core_execution_authority_added"] is False
    assert status["automatic_core_mutation"] is False
    assert "intelligence_lab" not in core


def test_safe_cache_exact_semantic_prefix_and_sensitive_scope(tmp_path):
    lab = build_intelligence_lab(settings=lab_settings(tmp_path), use_core_model=False)
    cache = SafeSemanticCache(
        lab.memory,
        policy=CachePolicy(semantic_threshold=0.8, maximum_entries=32),
    )
    cache.put(
        "alpha beta gamma",
        {"answer": 1},
        namespace="test",
        scope="owner-1",
        sensitivity="internal",
    )
    value, mode = cache.get(
        "alpha beta gamma",
        namespace="test",
        scope="owner-1",
        sensitivity="internal",
    )
    assert value == {"answer": 1}
    assert mode == "exact"
    value, mode = cache.get(
        "gamma alpha beta",
        namespace="test",
        scope="owner-1",
        sensitivity="internal",
    )
    assert value == {"answer": 1}
    assert mode == "semantic"
    cache.put_prefix("stable system context", {"prefix": True})
    assert cache.get_prefix("stable system context") == {"prefix": True}
    with pytest.raises(PermissionError, match="explicit owner/device scope"):
        cache.put("secret text", "x", sensitivity="sensitive", scope="shared")
    persisted = lab.memory.recent("semantic_cache_metadata", 10)
    assert persisted
    assert all(item["payload"]["raw_prompt_stored"] is False for item in persisted)
    assert all(item["payload"]["value_persisted"] is False for item in persisted)


def test_incremental_retrieval_hot_index_and_context_compression(tmp_path):
    lab = build_intelligence_lab(settings=lab_settings(tmp_path), use_core_model=False)
    lab.memory.put("r1", "note", {"text": "alpha architecture evidence"})
    found = lab.phase3.retrieve("architecture evidence", kind="note")
    assert found and found[0].id == "r1"

    lab.memory.put("r2", "note", {"text": "beta latency optimization"})
    found2 = lab.phase3.retrieve("latency optimization", kind="note")
    assert found2 and found2[0].id == "r2"

    compressed = lab.phase3.compress_context(
        "latency optimization",
        [
            {"id": "a", "text": "latency optimization details", "priority": 1.0},
            {"id": "dup", "text": "latency optimization details", "priority": 1.0},
            {"id": "b", "text": "unrelated weather text", "priority": 0.0},
        ],
    )
    assert compressed["selected_chunks"] >= 1
    assert compressed["deduplicated_chunks"] == 1
    assert "a" in compressed["provenance"]


def test_memory_reuses_connection_supports_batch_and_wal(tmp_path):
    lab = build_intelligence_lab(settings=lab_settings(tmp_path), use_core_model=False)
    assert lab.memory.put_many(
        [
            ("b1", "batch", {"value": 1}),
            ("b2", "batch", {"value": 2}),
            ("b3", "batch", {"value": 3}),
        ]
    ) == 3
    rows = lab.memory.recent("batch", 10)
    assert len(rows) == 3
    pragmas = lab.memory.performance_pragmas()
    assert str(pragmas["journal_mode"]).lower() == "wal"
    assert pragmas["thread_local_connection_reuse"] is True
    assert pragmas["batched_writes"] is True


def test_persistent_world_index_auto_refreshes_after_phase2_writes(tmp_path):
    lab = build_intelligence_lab(settings=lab_settings(tmp_path), use_core_model=False)
    lab.assert_world_fact(
        "cpu.load",
        0.9,
        confidence=0.9,
        source="trusted-probe",
        evidence=["probe-1"],
    )
    lab.relate_world_facts(
        "cpu.load",
        "latency.high",
        strength=0.9,
        evidence=["incident-1"],
        source="trusted-probe",
    )
    lab.phase3.set_world_source_reliability("trusted-probe", 0.95)
    prediction = lab.phase3.indexed_world_prediction("latency.high")
    assert prediction["indexed"] is True
    assert prediction["contributors"]
    stats = lab.phase3.world_index.stats()
    assert stats["facts_indexed"] >= 1
    assert stats["edges_indexed"] >= 1
    path = lab.phase3.world_index.causal_path("cpu.load", "latency.high", minimum_strength=0.5)
    assert len(path) == 1


def test_parallel_dag_builds_dependency_waves_without_new_execution_authority(tmp_path):
    lab = build_intelligence_lab(settings=lab_settings(tmp_path), use_core_model=False)
    plan = Plan(
        id="plan-parallel",
        goal="analyze and verify",
        horizon="long",
        created_at=1.0,
        steps=(
            PlanStep(
                index=0,
                objective="analyze A",
                kind="analysis",
                depends_on=(),
                reversible=True,
            ),
            PlanStep(
                index=1,
                objective="analyze B",
                kind="analysis",
                depends_on=(),
                reversible=True,
            ),
            PlanStep(
                index=2,
                objective="verify",
                kind="verify",
                depends_on=(0, 1),
                reversible=True,
            ),
        ),
    )
    dag = lab.phase3.dag.from_plan(plan)
    assert len(dag.waves[0]) == 2
    assert len(dag.waves[1]) == 1
    run = lab.phase3.run_dag(dag, lambda node: {"node": node.id})
    assert run["completed"] == 3
    assert run["failures"] == {}
    assert run["parallel_execution_authority"] is False
    assert run["worker_must_use_core_for_real_actions"] is True


def test_adaptive_reasoning_uses_fast_path_then_cache(tmp_path):
    lab = build_intelligence_lab(settings=lab_settings(tmp_path), use_core_model=False)
    first = lab.phase3.reason(
        "Summarize the known status",
        context={"status": "healthy"},
        domain="ops",
    )
    second = lab.phase3.reason(
        "Summarize the known status",
        context={"status": "healthy"},
        domain="ops",
    )
    assert first.content
    assert second.content == first.content
    assert second.cache_mode in {"exact", "semantic"}
    assert second.latency_ms == 0.0
    summary = lab.phase3.performance_summary()
    assert summary["cache"]["hits"] >= 1


def test_performance_telemetry_and_regression_gate(tmp_path):
    lab = build_intelligence_lab(settings=lab_settings(tmp_path), use_core_model=False)
    telemetry = lab.phase3.telemetry
    telemetry.record("unit", 10, quality=0.95, cache_hit=True)
    telemetry.record("unit", 20, quality=0.90, cache_hit=True)
    telemetry.record("unit", 30, quality=0.92, cache_hit=False)
    passed = telemetry.gate(
        "unit",
        PerformanceBudget(
            p95_latency_ms=35,
            minimum_success_rate=1.0,
            minimum_quality=0.9,
            minimum_cache_hit_rate=0.5,
        ),
    )
    assert passed["passed"] is True
    failed = telemetry.gate(
        "unit",
        PerformanceBudget(p95_latency_ms=5, minimum_success_rate=1.0),
    )
    assert failed["passed"] is False
    assert "p95_latency" in failed["failures"]


def test_optimizer_learns_fast_high_quality_configuration(tmp_path):
    lab = build_intelligence_lab(settings=lab_settings(tmp_path), use_core_model=False)
    for latency in (100, 110, 90, 105):
        lab.phase3.record_optimization_episode(
            task_class="coding",
            depth="smart",
            model_count=2,
            cache_enabled=True,
            parallelism=4,
            latency_ms=latency,
            cost=0.01,
            quality=0.94,
            successful=True,
        )
    for latency in (500, 520, 480):
        lab.phase3.record_optimization_episode(
            task_class="coding",
            depth="deep",
            model_count=4,
            cache_enabled=False,
            parallelism=1,
            latency_ms=latency,
            cost=0.20,
            quality=0.95,
            successful=True,
        )
    recommendation = lab.phase3.recommend_optimization(
        task_class="coding",
        minimum_quality=0.9,
    )
    assert recommendation["adaptive"] is True
    assert recommendation["configuration"]["depth"] == "smart"
    assert recommendation["core_configuration_mutated"] is False


def test_trusted_device_placement_respects_privacy_and_never_dispatches(tmp_path):
    core = {
        "settings": SimpleNamespace(data_dir=tmp_path / "stable"),
        "device_registry": FakeDevices(),
    }
    lab = build_intelligence_lab(
        core_runtime=core,
        settings=lab_settings(tmp_path),
        use_core_model=False,
    )
    placement = lab.phase3.compute_placement(
        sensitivity="sensitive",
        local_device={
            "memory_gb": 4,
            "local": True,
            "network": "local",
            "compute_enabled": True,
        },
    )
    assert placement["selected"]["id"] == "gpu-box"
    assert placement["dispatch_performed"] is False
    assert placement["device_gateway_bypassed"] is False
    acceleration = lab.phase3.inference_acceleration_plan(
        platform="linux",
        metadata={
            "gpu": "NVIDIA RTX",
            "cuda": True,
            "memory_gb": 32,
            "server_class": True,
            "speculative_decoding": True,
        },
    )
    assert acceleration["backend"] == "cuda"
    assert acceleration["kv_cache"] is True
    assert acceleration["prefix_cache"] is True
    assert acceleration["continuous_batching"] is True
    assert acceleration["speculative_decoding"] is True
    assert acceleration["authority_granted"] is False


def test_phase3_scale_retrieval_and_batching_remain_bounded(tmp_path):
    lab = build_intelligence_lab(settings=lab_settings(tmp_path), use_core_model=False)
    rows = [
        (f"scale-{index}", "scale", {"text": f"record {index} optimization shard {index % 17}"})
        for index in range(1000)
    ]
    assert lab.memory.put_many(rows) == 1000
    assert lab.phase3.refresh_retrieval_index() >= 1000
    result = lab.phase3.retrieve("optimization shard 7", kind="scale", limit=25)
    assert 1 <= len(result) <= 25
    stats = lab.phase3.retriever.hot_stats()
    assert stats["indexed_records"] <= lab.phase3.settings.retrieval_index_limit
    assert stats["hot_records"] <= lab.phase3.settings.retrieval_hot_limit


def test_phase3_api_exposes_optimization_but_no_execution_authority(tmp_path):
    lab = build_intelligence_lab(settings=lab_settings(tmp_path), use_core_model=False)
    app = create_phase3_app(lab)
    paths = {route.path for route in app.routes}
    assert "/phase3/status" in paths
    assert "/phase3/reason" in paths
    assert "/phase3/performance" in paths
    assert "/phase3/compute/place" in paths
    assert "/phase3/execute" not in paths
    assert "/phase3/tool-dispatch" not in paths
    assert "/phase3/security-policy" not in paths
