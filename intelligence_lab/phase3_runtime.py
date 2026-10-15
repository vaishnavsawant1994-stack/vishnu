from __future__ import annotations

from dataclasses import asdict
from typing import Any, Mapping

from devices.trusted_compute import CAPABILITY, sanitize_compute_request

from .adaptive_compute import AdaptiveReasoningScheduler, TrustedComputeScheduler
from .cache import CachePolicy, SafeSemanticCache
from .config import CapabilityLevel
from .dag_planner import DAGPlan, ParallelDAGPlanner
from .optimizer import AdaptivePerformanceOptimizer
from .performance import PerformanceBudget, PerformanceTelemetry
from .phase3_config import Phase3Settings
from .retrieval import AcceleratedLabRetriever, ContextCompressor
from .world_index import IndexedWorldGraph


class IntelligenceLabPhase3:
    """Performance/scale layer over an already-isolated Intelligence Lab.

    This object owns no tool, approval, secret, device or model authority.
    It optimizes selection, retrieval and planning, then returns real work to
    the existing Lab/Core bridge. Phase 3.1 can propose bounded remote compute,
    but actual dispatch is still re-planned by Core through AgentExecutor and
    ToolRegistry.
    """

    def __init__(
        self,
        lab: Any,
        *,
        core_runtime: Mapping[str, Any] | None = None,
        settings: Phase3Settings | None = None,
    ):
        self.lab = lab
        self.core_runtime = core_runtime
        self.settings = settings or Phase3Settings.from_environment()
        self.telemetry = PerformanceTelemetry(
            lab.memory, window=self.settings.telemetry_window
        )
        self.cache = SafeSemanticCache(
            lab.memory,
            policy=CachePolicy(
                ttl_seconds=self.settings.cache_ttl_seconds,
                semantic_threshold=self.settings.semantic_cache_threshold,
                maximum_entries=self.settings.cache_entries,
            ),
        )
        core_models = core_runtime.get("models") if core_runtime is not None else None
        embed = getattr(core_models, "embed", None)
        embedding_callback = None
        if callable(embed):
            def embedding_callback(text: str) -> list[float]:
                return list(embed(text, sensitivity="internal"))
        self.retriever = AcceleratedLabRetriever(
            lab.memory,
            index_limit=self.settings.retrieval_index_limit,
            hot_limit=self.settings.retrieval_hot_limit,
            embedding_callback=embedding_callback,
        )
        self.compressor = ContextCompressor(
            max_chars=self.settings.context_max_chars,
            max_chunks=self.settings.context_max_chunks,
        )
        self.world_index = IndexedWorldGraph(lab.temporal_world, lab.memory)
        self.reasoning = AdaptiveReasoningScheduler(
            lab.reasoner,
            lab.model_team,
            lab.memory,
            self.telemetry,
            self.cache,
            self.compressor,
            fast_confidence=self.settings.fast_confidence,
            smart_confidence=self.settings.smart_confidence,
        )
        self.dag = ParallelDAGPlanner(
            lab.memory,
            self.telemetry,
            max_workers=self.settings.dag_max_workers,
        )
        registry = (
            core_runtime.get("device_registry")
            if core_runtime is not None
            else None
        )
        self.compute = TrustedComputeScheduler(registry, lab.memory)
        self.optimizer = AdaptivePerformanceOptimizer(
            lab.memory,
            window=self.settings.optimization_window,
        )
        lab.memory.audit(
            "phase3",
            "attached",
            {
                "stable_core_authority_changed": False,
                "parallel_security_authority_added": False,
                "device_dispatch_bypass_added": False,
            },
        )

    def _require_think(self) -> None:
        self.lab.settings.require(CapabilityLevel.THINK)

    def _governed_compute_available(self) -> bool:
        if self.core_runtime is None:
            return False
        tools = self.core_runtime.get("tools")
        gateway = self.core_runtime.get("device_gateway")
        if tools is None or gateway is None or not callable(getattr(tools, "all", None)):
            return False
        return any(getattr(tool, "name", "") == "trusted_device_compute" for tool in tools.all())

    def status(self) -> dict[str, Any]:
        return {
            "name": "Vishnu Intelligence Lab Phase 3",
            "settings": self.settings.public_snapshot(),
            "adaptive_fast_smart_deep_routing": True,
            "exact_semantic_prefix_cache": True,
            "accelerated_hot_retrieval": True,
            "governed_vector_reranking": self.retriever.embedding_callback is not None,
            "persistent_world_indexes": True,
            "parallel_dag_planning": True,
            "adaptive_performance_learning": True,
            "trusted_device_placement": True,
            "governed_distributed_compute_available": self._governed_compute_available(),
            "core_execution_authority_added": False,
            "device_gateway_bypass_added": False,
            "raw_prompt_cache_persisted": False,
            "automatic_core_mutation": False,
        }

    def reason(
        self,
        goal: str,
        *,
        context: Mapping[str, Any] | None = None,
        domain: str = "general",
        sensitivity: str = "internal",
        scope: str = "shared",
        requested_depth: str | None = None,
    ):
        self._require_think()
        contradictions = len(self.lab.temporal_world.contradictions())
        return self.reasoning.run(
            goal,
            context=context,
            domain=domain,
            sensitivity=sensitivity,
            scope=scope,
            requested_depth=requested_depth,
            contradictions=contradictions,
        )

    def retrieve(self, query: str, *, kind: str | None = None, limit: int = 20):
        self._require_think()
        return self.retriever.search(query, kind=kind, limit=limit)

    def compress_context(self, query: str, chunks):
        self._require_think()
        return self.compressor.compress(query, chunks)

    def refresh_retrieval_index(self) -> int:
        self._require_think()
        return self.retriever.refresh()

    def build_dag(self, goal: str, *, plan=None) -> DAGPlan:
        self._require_think()
        plan = plan or self.lab.plan(goal)
        return self.dag.from_plan(plan)

    def run_dag(self, dag: DAGPlan, worker, *, stop_on_failure: bool = True):
        self._require_think()
        return self.dag.run(dag, worker, stop_on_failure=stop_on_failure)

    def compute_placement(
        self,
        *,
        sensitivity: str = "internal",
        local_device: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._require_think()
        if local_device is None:
            try:
                profile = self.compute.probe_local_hardware(
                    path=str(self.lab.settings.data_dir),
                    online=False,
                )
                local_device = {
                    **profile,
                    "memory_gb": profile.get("ram_gb", 0.0),
                    "gpu": profile.get("accelerator_name", ""),
                    "gpu_available": profile.get("accelerator") not in {"", "none", None},
                    "local": True,
                    "network": "local",
                }
            except Exception:
                local_device = None
        return self.compute.select(
            sensitivity=sensitivity,
            local_device=local_device,
        )

    def inference_acceleration_plan(
        self,
        *,
        platform: str,
        metadata: Mapping[str, Any],
    ) -> dict[str, Any]:
        self._require_think()
        return self.compute.acceleration_plan(platform, metadata)

    def _remote_compute_targets(self, sensitivity: str) -> list[Any]:
        if str(sensitivity).lower() not in {"public", "internal"}:
            raise PermissionError("remote distributed compute is disabled for private/sensitive/secret data")
        if self.core_runtime is None:
            return []
        gateway = self.core_runtime.get("device_gateway")
        registry = self.core_runtime.get("device_registry")
        if gateway is None or registry is None:
            return []
        capability_getter = getattr(gateway, "capabilities", None)
        authorize = getattr(registry, "authorize", None)
        if not callable(capability_getter) or not callable(authorize):
            return []
        candidates = self.compute.candidates(sensitivity=sensitivity, local_device=None)
        return [
            candidate
            for candidate in candidates
            if not candidate.local
            and authorize(candidate.id, "device:admin")
            and CAPABILITY in set(capability_getter(candidate.id))
        ]

    def _create_distributed_compute_proposal(
        self,
        goal: str,
        *,
        context: Mapping[str, Any] | None = None,
        mode: str = "smart",
        sensitivity: str = "internal",
        target_device_id: str | None = None,
        max_tokens: int = 2048,
        timeout_seconds: float = 45.0,
    ):
        self._require_think()
        self.lab.settings.require(CapabilityLevel.PROPOSE)
        if not self._governed_compute_available():
            raise RuntimeError("governed trusted-device compute capability is unavailable")
        targets = self._remote_compute_targets(sensitivity)
        if target_device_id is not None:
            targets = [item for item in targets if item.id == str(target_device_id)]
        if not targets:
            raise RuntimeError("no eligible online trusted compute device is available")
        selected = targets[0]
        parameters = {
            "device_id": selected.id,
            "destination": f"device:{selected.id}",
            "prompt": str(goal),
            "context": dict(context or {}),
            "mode": str(mode).lower(),
            "sensitivity": str(sensitivity).lower(),
            "max_tokens": int(max_tokens),
            "timeout_seconds": float(timeout_seconds),
        }
        clean = sanitize_compute_request(parameters)
        parameters.update(
            {
                "context": clean["context"],
                "mode": clean["mode"],
                "sensitivity": clean["sensitivity"],
                "max_tokens": clean["max_tokens"],
                "timeout_seconds": clean["timeout_seconds"],
            }
        )
        proposal = self.lab.propose(
            "trusted_device_compute",
            parameters,
            (
                "Run bounded reasoning on the selected trusted compute device. "
                "Core must independently re-plan, authorize, approve, dispatch and verify the registered tool."
            ),
            risk="external_side_effect",
        )
        self.lab.memory.audit(
            "compute",
            "distributed_compute_proposed",
            {
                "proposal_id": proposal.id,
                "device_id": selected.id,
                "dispatch_performed": False,
                "core_reapproval_required": True,
            },
        )
        return selected, proposal

    def distributed_compute_proposal(
        self,
        goal: str,
        *,
        context: Mapping[str, Any] | None = None,
        mode: str = "smart",
        sensitivity: str = "internal",
        target_device_id: str | None = None,
        max_tokens: int = 2048,
        timeout_seconds: float = 45.0,
    ) -> dict[str, Any]:
        selected, proposal = self._create_distributed_compute_proposal(
            goal,
            context=context,
            mode=mode,
            sensitivity=sensitivity,
            target_device_id=target_device_id,
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
        )
        return {
            "selected": asdict(selected),
            "proposal": proposal.public_dict(),
            "executed": False,
            "core_reapproval_required": True,
        }

    def execute_distributed_compute(
        self,
        goal: str,
        *,
        context: Mapping[str, Any] | None = None,
        mode: str = "smart",
        sensitivity: str = "internal",
        target_device_id: str | None = None,
        max_tokens: int = 2048,
        timeout_seconds: float = 45.0,
        **execution_context: Any,
    ) -> Any:
        """Request real remote compute through the existing Core bridge.

        This method is intentionally not exposed by the standalone Phase-3 API.
        Capability level 5+, normal ToolRegistry permission/approval, emergency
        stop, destination/data policy, worker response verification and audit all
        remain mandatory.
        """
        selected, proposal = self._create_distributed_compute_proposal(
            goal,
            context=context,
            mode=mode,
            sensitivity=sensitivity,
            target_device_id=target_device_id,
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
        )
        result = self.lab.execute(proposal, **execution_context)
        self.lab.memory.audit(
            "compute",
            "distributed_compute_returned_via_core",
            {
                "proposal_id": proposal.id,
                "device_id": selected.id,
                "direct_gateway_dispatch": False,
            },
        )
        return result

    def record_optimization_episode(self, **kwargs: Any):
        self._require_think()
        return self.optimizer.record(**kwargs)

    def recommend_optimization(self, **kwargs: Any):
        self._require_think()
        return self.optimizer.recommend(**kwargs)

    def performance_summary(self) -> dict[str, Any]:
        self._require_think()
        return {
            "operations": self.telemetry.snapshot(),
            "cache": self.cache.stats(),
            "retrieval": self.retriever.hot_stats(),
            "world_index": self.world_index.stats(),
            "memory": self.lab.memory.performance_pragmas(),
        }

    def performance_gate(
        self,
        operation: str,
        *,
        p95_latency_ms: float | None = None,
        p99_latency_ms: float | None = None,
        minimum_success_rate: float = 0.98,
        minimum_quality: float | None = None,
        maximum_mean_cost: float | None = None,
        minimum_cache_hit_rate: float | None = None,
    ) -> dict[str, Any]:
        self._require_think()
        return self.telemetry.gate(
            operation,
            PerformanceBudget(
                p95_latency_ms=p95_latency_ms,
                p99_latency_ms=p99_latency_ms,
                minimum_success_rate=minimum_success_rate,
                minimum_quality=minimum_quality,
                maximum_mean_cost=maximum_mean_cost,
                minimum_cache_hit_rate=minimum_cache_hit_rate,
            ),
        )

    def set_world_source_reliability(self, source: str, reliability: float) -> None:
        self._require_think()
        self.world_index.set_source_reliability(source, reliability)

    def indexed_world_prediction(self, effect: str) -> dict[str, Any]:
        self._require_think()
        return self.world_index.predict(effect)
