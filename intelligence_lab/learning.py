from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
from typing import Any, Callable, Iterable, Mapping

from .memory import LabMemory
from .models import Thought, new_id


@dataclass(frozen=True)
class LearningEpisode:
    domain: str
    strategy: str
    successful: bool
    score: float
    evidence: tuple[str, ...]
    lesson: str
    id: str = field(default_factory=lambda: new_id("episode"))

    def public_dict(self) -> dict[str, Any]:
        return asdict(self)


class ContinualLearningEngine:
    """Lab-local adaptive strategy learning and reflection.

    It improves which reasoning strategy the Lab chooses and can produce
    owner-reviewable training candidates. It never fine-tunes or replaces a Core
    model, rewrites security policy, or changes trusted memory by itself.
    """

    DEFAULT_STRATEGIES = (
        "evidence_first",
        "skeptic",
        "counterfactual",
        "decompose",
        "verification_first",
    )

    def __init__(
        self,
        memory: LabMemory,
        *,
        model_callback: Callable[[str], str] | None = None,
        window: int = 200,
    ):
        self.memory = memory
        self.model_callback = model_callback
        self.window = max(20, min(int(window), 1000))

    def record_episode(
        self,
        *,
        domain: str,
        strategy: str,
        successful: bool,
        score: float,
        evidence: Iterable[str],
        lesson: str,
    ) -> LearningEpisode:
        clean_evidence = tuple(str(item).strip() for item in evidence if str(item).strip())
        if not clean_evidence:
            raise ValueError("learning episode requires evidence")
        score = max(0.0, min(float(score), 1.0))
        episode = LearningEpisode(
            domain=str(domain or "general")[:200],
            strategy=str(strategy or "evidence_first")[:200],
            successful=bool(successful),
            score=score,
            evidence=clean_evidence,
            lesson=str(lesson)[:4000],
        )
        self.memory.put(episode.id, "learning_episode", episode.public_dict())
        self.memory.audit(
            "learning",
            "episode_recorded",
            {
                "id": episode.id,
                "domain": episode.domain,
                "strategy": episode.strategy,
                "successful": episode.successful,
                "score": episode.score,
                "core_model_modified": False,
            },
        )
        return episode

    def strategy_statistics(self, *, domain: str | None = None) -> dict[str, dict[str, float]]:
        rows = self.memory.recent("learning_episode", self.window)
        stats: dict[str, dict[str, float]] = {}
        for row in rows:
            payload = row.get("payload", {})
            if domain is not None and str(payload.get("domain")) != str(domain):
                continue
            strategy = str(payload.get("strategy") or "unknown")
            item = stats.setdefault(strategy, {"count": 0.0, "successes": 0.0, "score_sum": 0.0})
            item["count"] += 1.0
            item["successes"] += 1.0 if payload.get("successful") else 0.0
            try:
                item["score_sum"] += float(payload.get("score", 0.0))
            except (TypeError, ValueError):
                pass
        for item in stats.values():
            count = max(1.0, item["count"])
            item["success_rate"] = item["successes"] / count
            item["mean_score"] = item["score_sum"] / count
            item["weight"] = (item["successes"] + 1.0) / (item["count"] + 2.0)
        return stats

    def recommend_strategy(
        self,
        *,
        domain: str = "general",
        choices: Iterable[str] | None = None,
    ) -> dict[str, Any]:
        choices = tuple(dict.fromkeys(str(item) for item in (choices or self.DEFAULT_STRATEGIES)))
        if not choices:
            raise ValueError("at least one reasoning strategy is required")
        stats = self.strategy_statistics(domain=domain)
        total = sum(item["count"] for item in stats.values())
        ranked = []
        for strategy in choices:
            item = stats.get(strategy, {"count": 0.0, "weight": 0.5, "mean_score": 0.5})
            count = float(item.get("count", 0.0))
            exploration = math.sqrt(math.log(total + 2.0) / (count + 1.0)) * 0.08
            score = min(1.0, float(item.get("weight", 0.5)) * 0.7 + float(item.get("mean_score", 0.5)) * 0.3 + exploration)
            ranked.append((score, strategy, count))
        ranked.sort(key=lambda row: (-row[0], row[1]))
        selected = ranked[0]
        return {
            "domain": domain,
            "strategy": selected[1],
            "score": selected[0],
            "observations": selected[2],
            "adaptive": bool(total),
            "core_policy_changed": False,
        }

    def adaptive_reason(
        self,
        reasoner: Any,
        goal: str,
        *,
        context: Mapping[str, Any] | None = None,
        domain: str = "general",
    ) -> Thought:
        decision = self.recommend_strategy(domain=domain)
        strategy = str(decision["strategy"])
        context = dict(context or {})
        if self.model_callback is None:
            baseline: Thought = reasoner.reason(goal, context=context)
            return Thought(
                goal=baseline.goal,
                summary=f"Adaptive strategy={strategy}. {baseline.summary}",
                assumptions=baseline.assumptions,
                unknowns=baseline.unknowns,
                confidence=min(0.9, max(0.2, baseline.confidence)),
                strategy=f"adaptive:{strategy}",
            )
        prompt = (
            "You are the Vishnu Intelligence Lab adaptive reasoner. Do not execute tools or claim authority. "
            f"Use the learned reasoning strategy '{strategy}'. Separate evidence, assumptions, unknowns, alternatives, "
            "and verification steps. Do not claim consciousness.\n"
            f"GOAL: {goal[:12000]}\nCONTEXT: {context!r}"
        )
        try:
            content = str(self.model_callback(prompt)).strip()
        except Exception:
            content = ""
        if not content:
            return self.adaptive_reason(reasoner, goal, context=context, domain=domain) if self.model_callback is None else reasoner.reason(goal, context=context)
        unknowns = tuple(key for key, value in context.items() if value in (None, "", "unknown"))
        thought = Thought(
            goal=str(goal),
            summary=content[:8000],
            assumptions=("Learned strategy performance is historical evidence, not a guarantee for this task.",),
            unknowns=unknowns,
            confidence=min(0.85, 0.55 + float(decision["score"]) * 0.25),
            strategy=f"adaptive:{strategy}",
        )
        self.memory.put(thought.id, "adaptive_thought", thought.public_dict())
        return thought

    def reflect(self, *, domain: str | None = None, limit: int = 50) -> dict[str, Any]:
        rows = self.memory.recent("learning_episode", max(1, min(int(limit), self.window)))
        episodes = [row.get("payload", {}) for row in rows if domain is None or str(row.get("payload", {}).get("domain")) == str(domain)]
        failures = [item for item in episodes if not item.get("successful")]
        stats = self.strategy_statistics(domain=domain)
        summary = (
            f"Reviewed {len(episodes)} Lab learning episodes; {len(failures)} were unsuccessful. "
            "Prefer strategies with stronger evidence while retaining exploration for under-tested strategies."
        )
        if self.model_callback is not None and episodes:
            prompt = (
                "Review these Vishnu Intelligence Lab learning episodes. Produce a concise, non-authoritative reflection: "
                "recurring failure patterns, transferable lessons, and what should be tested next. Never suggest bypassing "
                "security or owner approval.\nEPISODES=" + repr(episodes[:50])
            )
            try:
                candidate = str(self.model_callback(prompt)).strip()
            except Exception:
                candidate = ""
            if candidate:
                summary = candidate[:8000]
        record = {
            "domain": domain,
            "episodes_reviewed": len(episodes),
            "failures": len(failures),
            "strategy_statistics": stats,
            "summary": summary,
            "core_model_modified": False,
            "security_policy_modified": False,
        }
        record_id = new_id("reflection")
        self.memory.put(record_id, "learning_reflection", {"id": record_id, **record})
        self.memory.audit("learning", "reflection_completed", {"id": record_id, "episodes": len(episodes)})
        return {"id": record_id, **record}

    def training_candidates(self, *, minimum_score: float = 0.8, limit: int = 100) -> dict[str, Any]:
        threshold = max(0.0, min(float(minimum_score), 1.0))
        rows = self.memory.recent("learning_episode", max(1, min(int(limit), self.window)))
        examples = []
        for row in rows:
            item = row.get("payload", {})
            try:
                score = float(item.get("score", 0.0))
            except (TypeError, ValueError):
                score = 0.0
            if item.get("successful") and score >= threshold:
                examples.append(
                    {
                        "domain": item.get("domain"),
                        "strategy": item.get("strategy"),
                        "lesson": item.get("lesson"),
                        "evidence": list(item.get("evidence") or ()),
                        "score": score,
                    }
                )
        return {
            "examples": examples,
            "count": len(examples),
            "model_training_started": False,
            "requires_separate_owner_governed_training_pipeline": True,
        }
