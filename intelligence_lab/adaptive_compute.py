from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import math
import re
import time
from typing import Any, Mapping

from .cache import SafeSemanticCache
from .memory import LabMemory
from .performance import PerformanceTelemetry
from .retrieval import ContextCompressor
from models.adaptive_strategy import AdaptiveStrategy, ExecutionPattern, StrategyRequest, TaskComplexity
from models.hardware_profile import HardwareProfiler
from models.intelligence_modes import IntelligenceMode, intelligence_profile


class ComputeDepth(str, Enum):
    FAST = "fast"
    SMART = "smart"
    DEEP = "deep"


@dataclass(frozen=True)
class ComplexityAssessment:
    depth: ComputeDepth
    score: float
    reasons: tuple[str, ...]
    risk: str
    ambiguity: float
    estimated_context_chars: int


class ComplexityClassifier:
    HARD_TERMS = re.compile(
        r"\b(architecture|security|migration|debug|root cause|compare|prove|research|"
        r"optimi[sz]e|strategy|long[- ]horizon|multi[- ]step|legal|medical|financial)\b",
        re.IGNORECASE,
    )
    CRITICAL_TERMS = re.compile(
        r"\b(delete|production|deploy|credential|secret|payment|irreversible|"
        r"permission|security policy|release|signing|private key)\b",
        re.IGNORECASE,
    )

    def assess(
        self,
        goal: str,
        context: Mapping[str, Any] | None = None,
        *,
        contradictions: int = 0,
        requested_depth: ComputeDepth | str | None = None,
    ) -> ComplexityAssessment:
        text = str(goal)
        context_chars = len(repr(dict(context or {})))
        score = 0.0
        reasons: list[str] = []
        if len(text) > 500:
            score += 0.12
            reasons.append("long_goal")
        if context_chars > 8000:
            score += 0.16
            reasons.append("large_context")
        hard = len(self.HARD_TERMS.findall(text))
        if hard:
            score += min(0.30, hard * 0.08)
            reasons.append("complex_domain")
        critical = len(self.CRITICAL_TERMS.findall(text))
        if critical:
            score += min(0.35, critical * 0.12)
            reasons.append("high_risk_terms")
        if contradictions:
            score += min(0.30, contradictions * 0.10)
            reasons.append("conflicting_evidence")
        ambiguity = min(
            1.0,
            (
                text.count("?")
                + text.lower().count("maybe")
                + text.lower().count("unknown")
                + text.lower().count("uncertain")
            )
            / 5.0,
        )
        score += ambiguity * 0.18
        risk = "high" if critical else ("medium" if hard else "low")
        score = max(0.0, min(score, 1.0))
        if requested_depth is not None:
            depth = requested_depth if isinstance(requested_depth, ComputeDepth) else ComputeDepth(str(requested_depth).lower())
            reasons.append("explicit_depth")
        elif score >= 0.55 or risk == "high":
            depth = ComputeDepth.DEEP
        elif score >= 0.22:
            depth = ComputeDepth.SMART
        else:
            depth = ComputeDepth.FAST
        return ComplexityAssessment(
            depth=depth,
            score=score,
            reasons=tuple(reasons or ("simple_task",)),
            risk=risk,
            ambiguity=ambiguity,
            estimated_context_chars=context_chars,
        )

    @staticmethod
    def core_complexity(assessment: ComplexityAssessment) -> TaskComplexity:
        if assessment.risk == "high" or assessment.score >= 0.75:
            return TaskComplexity.CRITICAL
        if assessment.score >= 0.55:
            return TaskComplexity.HIGH
        if assessment.score >= 0.28:
            return TaskComplexity.MEDIUM
        if assessment.score >= 0.10:
            return TaskComplexity.LOW
        return TaskComplexity.TRIVIAL


@dataclass(frozen=True)
class ReasoningRun:
    depth: ComputeDepth
    content: str
    confidence: float
    cache_mode: str
    escalated: bool
    models_used: int
    latency_ms: float
    quality_estimate: float
    reasons: tuple[str, ...]

    def public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["depth"] = self.depth.value
        return data


class AdaptiveReasoningScheduler:
    """Fast/Smart/Deep scheduler with cache, compression and early exit."""

    def __init__(
        self,
        reasoner: Any,
        model_team: Any,
        memory: LabMemory,
        telemetry: PerformanceTelemetry,
        cache: SafeSemanticCache,
        compressor: ContextCompressor,
        *,
        fast_confidence: float = 0.72,
        smart_confidence: float = 0.82,
    ):
        self.reasoner = reasoner
        self.model_team = model_team
        self.memory = memory
        self.telemetry = telemetry
        self.cache = cache
        self.compressor = compressor
        self.classifier = ComplexityClassifier()
        self.core_strategy = AdaptiveStrategy()
        self.fast_confidence = max(0.5, min(float(fast_confidence), 0.95))
        self.smart_confidence = max(self.fast_confidence, min(float(smart_confidence), 0.98))

    @staticmethod
    def _context_chunks(context: Mapping[str, Any]) -> list[dict[str, Any]]:
        return [
            {"id": str(key), "text": f"{key}: {value}", "priority": 0.5}
            for key, value in context.items()
        ]

    def run(
        self,
        goal: str,
        *,
        context: Mapping[str, Any] | None = None,
        domain: str = "general",
        sensitivity: str = "internal",
        scope: str = "shared",
        requested_depth: ComputeDepth | str | None = None,
        contradictions: int = 0,
    ) -> ReasoningRun:
        raw_context = dict(context or {})
        assessment = self.classifier.assess(
            goal,
            raw_context,
            contradictions=contradictions,
            requested_depth=requested_depth,
        )
        mode_for_depth = {
            ComputeDepth.FAST: IntelligenceMode.STANDARD,
            ComputeDepth.SMART: IntelligenceMode.SMART,
            ComputeDepth.DEEP: IntelligenceMode.RESEARCH,
        }[assessment.depth]
        decision = self.core_strategy.decide(
            StrategyRequest(
                profile=intelligence_profile(mode_for_depth),
                task_domain=str(domain),
                complexity=self.classifier.core_complexity(assessment),
                sensitivity=str(sensitivity),
                evidence_required=bool(contradictions or assessment.risk != "low"),
            )
        )
        compressed = self.compressor.compress(goal, self._context_chunks(raw_context))
        cache_prompt = f"{goal}\n{compressed['text']}\npattern={decision.pattern.value}"
        cached, cache_mode = self.cache.get(
            cache_prompt,
            namespace=f"adaptive-reasoning:{domain}",
            version="phase3-v1",
            scope=scope,
            sensitivity=sensitivity,
        )
        if cached is not None and isinstance(cached, Mapping):
            result = ReasoningRun(
                depth=ComputeDepth(str(cached["depth"])),
                content=str(cached["content"]),
                confidence=float(cached["confidence"]),
                cache_mode=cache_mode,
                escalated=bool(cached.get("escalated", False)),
                models_used=int(cached.get("models_used", 1)),
                latency_ms=0.0,
                quality_estimate=float(cached.get("quality_estimate", cached["confidence"])),
                reasons=tuple(cached.get("reasons", assessment.reasons)),
            )
            self.telemetry.record(
                "adaptive_reasoning",
                0.0,
                success=True,
                quality=result.quality_estimate,
                cache_hit=True,
                metadata={"depth": result.depth.value, "domain": domain},
            )
            return result

        started = time.perf_counter()
        baseline = self.reasoner.reason(goal, context=raw_context)
        content = baseline.summary
        confidence = float(baseline.confidence)
        models_used = 1
        escalated = False
        depth = assessment.depth

        should_escalate_fast = (
            depth == ComputeDepth.FAST
            and (
                confidence < self.fast_confidence
                or bool(baseline.unknowns)
                or contradictions > 0
            )
        )
        if should_escalate_fast:
            depth = ComputeDepth.SMART
            escalated = True
            decision = self.core_strategy.decide(
                StrategyRequest(
                    profile=intelligence_profile(IntelligenceMode.SMART),
                    task_domain=str(domain),
                    complexity=max(
                        self.classifier.core_complexity(assessment),
                        TaskComplexity.MEDIUM,
                        key=lambda item: list(TaskComplexity).index(item),
                    ),
                    sensitivity=str(sensitivity),
                    evidence_required=True,
                )
            )

        if (
            decision.pattern is not ExecutionPattern.SINGLE
            and getattr(self.model_team, "available", False)
        ):
            team_mode = {
                ExecutionPattern.PRIMARY_PLUS_VERIFIER: "critic",
                ExecutionPattern.SPECIALIST_RACE: "parallel_compare",
                ExecutionPattern.DEEP_CONSENSUS: "consensus",
            }.get(decision.pattern, "critic")
            team = self.model_team.deliberate(
                goal,
                context={
                    "compressed_context": compressed["text"],
                    "baseline": baseline.public_dict(),
                    "strategy_pattern": decision.pattern.value,
                },
                mode=team_mode,
                sensitivity=sensitivity,
            )
            if team.final.get("content"):
                content = str(team.final["content"])
                models_used = max(1, len(team.candidates))
                team_confidence = min(
                    0.95,
                    0.68 + 0.06 * max(0, models_used - 1) - 0.08 * len(team.failures),
                )
                confidence = max(confidence, team_confidence)
            if (
                depth == ComputeDepth.SMART
                and confidence < self.smart_confidence
                and assessment.score >= 0.45
            ):
                deep_decision = self.core_strategy.decide(
                    StrategyRequest(
                        profile=intelligence_profile(IntelligenceMode.RESEARCH),
                        task_domain=str(domain),
                        complexity=TaskComplexity.HIGH,
                        sensitivity=str(sensitivity),
                        evidence_required=True,
                    )
                )
                deep = self.model_team.deliberate(
                    goal,
                    context={
                        "compressed_context": compressed["text"],
                        "prior": content,
                        "strategy_pattern": deep_decision.pattern.value,
                    },
                    mode="consensus",
                    sensitivity=sensitivity,
                )
                if deep.final.get("content"):
                    content = str(deep.final["content"])
                    models_used = max(models_used, len(deep.candidates))
                    confidence = max(confidence, 0.82)
                    depth = ComputeDepth.DEEP
                    escalated = True

        latency_ms = (time.perf_counter() - started) * 1000.0
        quality = max(0.0, min(confidence, 1.0))
        result = ReasoningRun(
            depth=depth,
            content=content,
            confidence=confidence,
            cache_mode="miss",
            escalated=escalated,
            models_used=models_used,
            latency_ms=latency_ms,
            quality_estimate=quality,
            reasons=assessment.reasons,
        )
        self.cache.put(
            cache_prompt,
            result.public_dict(),
            namespace=f"adaptive-reasoning:{domain}",
            version="phase3-v1",
            scope=scope,
            sensitivity=sensitivity,
        )
        self.telemetry.record(
            "adaptive_reasoning",
            latency_ms,
            success=True,
            quality=quality,
            cache_hit=False,
            metadata={
                "depth": depth.value,
                "models_used": models_used,
                "domain": str(domain)[:100],
                "compressed_chars": compressed["characters"],
                "strategy_pattern": decision.pattern.value,
            },
        )
        self.memory.audit(
            "performance",
            "adaptive_reasoning_completed",
            {
                "depth": depth.value,
                "escalated": escalated,
                "models_used": models_used,
                "raw_prompt_persisted": False,
            },
        )
        return result


@dataclass(frozen=True)
class ComputeCandidate:
    id: str
    kind: str
    platform: str
    trusted: bool
    local: bool
    gpu: bool
    memory_gb: float
    battery_percent: float | None
    network: str
    score: float
    reasons: tuple[str, ...]


class TrustedComputeScheduler:
    """Advisory trusted-device placement; never dispatches work itself."""

    def __init__(self, device_registry: Any | None, memory: LabMemory):
        self.device_registry = device_registry
        self.memory = memory

    @staticmethod
    def probe_local_hardware(*, path: str = ".", online: bool = False) -> dict[str, Any]:
        profile = HardwareProfiler().probe(path, online=online)
        return profile.public()

    @staticmethod
    def acceleration_plan(platform: str, metadata: Mapping[str, Any]) -> dict[str, Any]:
        platform_text = str(platform).lower()
        gpu_text = str(metadata.get("gpu") or metadata.get("accelerator_name") or "").lower()
        accelerator = str(metadata.get("accelerator") or "").lower()
        if (
            "darwin" in platform_text
            or "mac" in platform_text
            or "apple" in gpu_text
            or accelerator == "apple-metal-shared"
        ):
            backend = "metal"
        elif "nvidia" in gpu_text or metadata.get("cuda") or accelerator == "nvidia-cuda":
            backend = "cuda"
        elif ("amd" in gpu_text and metadata.get("rocm")) or accelerator == "amd-rocm":
            backend = "rocm"
        else:
            backend = "cpu"
        memory_gb = float(metadata.get("memory_gb") or metadata.get("ram_gb") or 0.0)
        if 0 < memory_gb < 12:
            quantization = "4bit"
        elif 0 < memory_gb < 24:
            quantization = "8bit"
        else:
            quantization = "none"
        return {
            "backend": backend,
            "quantization": quantization,
            "kv_cache": True,
            "prefix_cache": True,
            "continuous_batching": bool(metadata.get("server_class", False)),
            "speculative_decoding": bool(metadata.get("speculative_decoding", False)),
            "embedding_batching": True,
            "authority_granted": False,
        }

    def candidates(
        self,
        *,
        sensitivity: str = "internal",
        local_device: Mapping[str, Any] | None = None,
    ) -> tuple[ComputeCandidate, ...]:
        rows: list[Mapping[str, Any]] = []
        if local_device is not None:
            rows.append({"id": "local", "name": "local", "platform": "local", "revoked": False, "metadata": dict(local_device), "permissions": ["ai:chat"]})
        if self.device_registry is not None and callable(getattr(self.device_registry, "list", None)):
            try:
                rows.extend(self.device_registry.list())
            except Exception:
                pass
        output: list[ComputeCandidate] = []
        sensitivity = str(sensitivity).lower()
        for row in rows:
            metadata = dict(row.get("metadata") or {})
            revoked = bool(row.get("revoked", False))
            permissions = set(row.get("permissions") or ())
            trusted = not revoked and ("ai:chat" in permissions or row.get("id") == "local")
            if not trusted:
                continue
            compute_enabled = str(metadata.get("compute_enabled", "true")).lower() not in {"0", "false", "no", "off"}
            if not compute_enabled:
                continue
            local = row.get("id") == "local" or str(metadata.get("local", "")).lower() in {"1", "true", "yes"}
            if sensitivity in {"private", "sensitive", "secret"} and not local:
                continue
            gpu = bool(metadata.get("gpu")) or str(metadata.get("gpu_available", "")).lower() in {"1", "true", "yes"}
            try:
                memory_gb = float(metadata.get("memory_gb") or metadata.get("ram_gb") or 0.0)
            except (TypeError, ValueError):
                memory_gb = 0.0
            try:
                battery = float(metadata["battery_percent"]) if "battery_percent" in metadata else None
            except (TypeError, ValueError):
                battery = None
            network = str(metadata.get("network") or "unknown")
            score = 0.35
            reasons = ["trusted_device"]
            if local:
                score += 0.20
                reasons.append("local_privacy")
            if gpu:
                score += 0.20
                reasons.append("gpu")
            score += min(0.15, memory_gb / 128.0)
            if battery is not None and battery < 20:
                score -= 0.20
                reasons.append("low_battery")
            if network.lower() in {"ethernet", "wifi", "lan"}:
                score += 0.08
                reasons.append("good_network")
            output.append(
                ComputeCandidate(
                    id=str(row.get("id") or "unknown"),
                    kind="device",
                    platform=str(row.get("platform") or "unknown"),
                    trusted=True,
                    local=local,
                    gpu=gpu,
                    memory_gb=max(0.0, memory_gb),
                    battery_percent=battery,
                    network=network,
                    score=max(0.0, min(score, 1.0)),
                    reasons=tuple(reasons),
                )
            )
        output.sort(key=lambda item: (-item.score, item.id))
        return tuple(output)

    def select(self, **kwargs: Any) -> dict[str, Any]:
        candidates = self.candidates(**kwargs)
        selected = candidates[0] if candidates else None
        result = {
            "selected": asdict(selected) if selected else None,
            "candidates": [asdict(item) for item in candidates],
            "dispatch_performed": False,
            "device_gateway_bypassed": False,
            "selection_is_advisory": True,
        }
        self.memory.audit(
            "compute",
            "placement_selected",
            {
                "candidate_count": len(candidates),
                "selected": selected.id if selected else None,
                "dispatch_performed": False,
            },
        )
        return result
