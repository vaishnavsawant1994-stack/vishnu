from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from hashlib import sha256
import hmac
import re
from typing import Any, Mapping


class ContributionMode(StrEnum):
    PRIVATE = "private"
    AGGREGATE = "aggregate"
    TRAINING_CONTRIBUTOR = "training_contributor"


class ContributionKind(StrEnum):
    AGENT_OUTCOME = "agent_outcome"
    TOOL_METRIC = "tool_metric"
    CORRECTION = "correction"
    CONVERSATION = "conversation"
    DOCUMENT = "document"


@dataclass(frozen=True)
class ContributionPreferences:
    mode: ContributionMode = ContributionMode.PRIVATE
    conversations: bool = False
    agent_outcomes: bool = True
    corrections: bool = False
    tool_metrics: bool = True
    documents: bool = False

    def permits(self, kind: ContributionKind) -> bool:
        if self.mode is ContributionMode.PRIVATE:
            return False
        return {
            ContributionKind.CONVERSATION: self.conversations,
            ContributionKind.AGENT_OUTCOME: self.agent_outcomes,
            ContributionKind.CORRECTION: self.corrections,
            ContributionKind.TOOL_METRIC: self.tool_metrics,
            ContributionKind.DOCUMENT: self.documents,
        }[kind]

    def public(self) -> dict[str, object]:
        return {
            "mode": self.mode.value,
            "conversations": self.conversations,
            "agent_outcomes": self.agent_outcomes,
            "corrections": self.corrections,
            "tool_metrics": self.tool_metrics,
            "documents": self.documents,
        }


@dataclass(frozen=True)
class ContributionDecision:
    accepted: bool
    reason: str
    kind: ContributionKind
    payload: dict[str, Any] = field(default_factory=dict)
    requires_training_governance: bool = False

    def public(self) -> dict[str, object]:
        return {
            "accepted": self.accepted,
            "reason": self.reason,
            "kind": self.kind.value,
            "payload": dict(self.payload),
            "requires_training_governance": self.requires_training_governance,
        }


_AGGREGATE_KEYS = frozenset(
    {
        "task_type",
        "strategy_id",
        "result",
        "tests_passed",
        "duration_bucket",
        "tool_family",
        "verifier_bucket",
        "failure_code",
        "retry_bucket",
        "cost_bucket",
        "latency_bucket",
    }
)
_FORBIDDEN_KEYS = frozenset(
    {
        "prompt",
        "response",
        "content",
        "raw_content",
        "document",
        "document_text",
        "chain_of_thought",
        "hidden_chain_of_thought",
        "api_key",
        "token",
        "password",
        "secret",
        "authorization",
        "cookie",
        "credentials",
    }
)
_SAFE_LABEL = re.compile(r"^[A-Za-z0-9._:/-]{1,64}$")


def _contains_forbidden_key(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).strip().lower()
            if normalized in _FORBIDDEN_KEYS:
                return True
            if _contains_forbidden_key(child):
                return True
    elif isinstance(value, (list, tuple, set, frozenset)):
        return any(_contains_forbidden_key(item) for item in value)
    return False


def _sanitize_aggregate(payload: Mapping[str, Any]) -> dict[str, Any]:
    unknown = set(map(str, payload)) - _AGGREGATE_KEYS
    if unknown:
        raise ValueError(f"aggregate contribution contains unsupported fields: {sorted(unknown)}")
    clean: dict[str, Any] = {}
    for key, value in payload.items():
        name = str(key)
        if value is None:
            continue
        if isinstance(value, bool):
            clean[name] = value
            continue
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            clean[name] = value
            continue
        label = str(value).strip()
        if not _SAFE_LABEL.fullmatch(label):
            raise ValueError(f"aggregate field {name} must be a bounded categorical label")
        clean[name] = label
    if not clean:
        raise ValueError("aggregate contribution payload is empty")
    return clean


def evaluate_contribution(
    preferences: ContributionPreferences,
    kind: ContributionKind,
    payload: Mapping[str, Any],
    *,
    privacy_cleared: bool = False,
    secret_scan_passed: bool = False,
    provenance_present: bool = False,
) -> ContributionDecision:
    """Apply the boundary between private data, aggregate learning and training data.

    Aggregate mode never accepts free-form conversation/document content. Training
    contributor mode still does not make content automatically training-eligible;
    accepted raw contributions must enter Vishnu's existing governed candidate,
    privacy, provenance and approval pipeline before dataset inclusion.
    """

    kind = ContributionKind(kind)
    if preferences.mode is ContributionMode.PRIVATE:
        return ContributionDecision(False, "private_mode", kind)
    if not preferences.permits(kind):
        return ContributionDecision(False, "kind_not_opted_in", kind)
    if _contains_forbidden_key(payload):
        return ContributionDecision(False, "forbidden_or_secret_bearing_field", kind)

    if preferences.mode is ContributionMode.AGGREGATE:
        if kind not in {ContributionKind.AGENT_OUTCOME, ContributionKind.TOOL_METRIC}:
            return ContributionDecision(False, "aggregate_mode_allows_structured_signals_only", kind)
        try:
            clean = _sanitize_aggregate(payload)
        except ValueError as exc:
            return ContributionDecision(False, str(exc), kind)
        return ContributionDecision(True, "aggregate_signal_accepted", kind, clean, False)

    if kind in {ContributionKind.AGENT_OUTCOME, ContributionKind.TOOL_METRIC}:
        try:
            clean = _sanitize_aggregate(payload)
        except ValueError as exc:
            return ContributionDecision(False, str(exc), kind)
        return ContributionDecision(True, "aggregate_signal_accepted", kind, clean, False)

    if not privacy_cleared:
        return ContributionDecision(False, "privacy_clearance_required", kind)
    if not secret_scan_passed:
        return ContributionDecision(False, "secret_scan_required", kind)
    if not provenance_present:
        return ContributionDecision(False, "provenance_required", kind)

    return ContributionDecision(
        True,
        "training_candidate_handoff_required",
        kind,
        dict(payload),
        True,
    )


class ContributorPseudonymizer:
    """Create installation-scoped contributor pseudonyms without storing raw IDs.

    A pseudonym is not an anonymity guarantee. It is only a minimization tool;
    downstream aggregation still needs thresholding and privacy review.
    """

    def __init__(self, secret: bytes) -> None:
        if not isinstance(secret, (bytes, bytearray)) or len(secret) < 32:
            raise ValueError("pseudonymization secret must contain at least 32 bytes")
        self._secret = bytes(secret)

    def pseudonym(self, contributor_id: str) -> str:
        value = str(contributor_id or "").strip()
        if not value:
            raise ValueError("contributor_id is required")
        digest = hmac.new(self._secret, value.encode("utf-8"), sha256).hexdigest()
        return f"contrib-{digest[:32]}"


class StrategySignalAggregator:
    """Aggregate privacy-minimized agent/tool outcomes for federated agent learning.

    Reports are withheld until a strategy/task bucket reaches the configured
    distinct-contributor threshold. Raw contributor pseudonyms are never returned.
    """

    def __init__(self, *, minimum_contributors: int = 3) -> None:
        if int(minimum_contributors) < 2:
            raise ValueError("minimum_contributors must be at least 2")
        self.minimum_contributors = int(minimum_contributors)
        self._rows: dict[tuple[str, str], dict[str, Any]] = {}

    def add(self, contributor_pseudonym: str, decision: ContributionDecision) -> None:
        if not decision.accepted or decision.requires_training_governance:
            raise ValueError("only accepted aggregate signals may be aggregated")
        if decision.kind not in {ContributionKind.AGENT_OUTCOME, ContributionKind.TOOL_METRIC}:
            raise ValueError("unsupported aggregate contribution kind")
        contributor = str(contributor_pseudonym or "").strip()
        if not contributor.startswith("contrib-"):
            raise ValueError("pseudonymized contributor id is required")
        task_type = str(decision.payload.get("task_type") or "unspecified")
        strategy_id = str(decision.payload.get("strategy_id") or decision.payload.get("tool_family") or "unspecified")
        key = (task_type, strategy_id)
        row = self._rows.setdefault(
            key,
            {
                "task_type": task_type,
                "strategy_id": strategy_id,
                "contributors": set(),
                "samples": 0,
                "successes": 0,
                "failures": 0,
                "tests_passed": 0,
            },
        )
        row["contributors"].add(contributor)
        row["samples"] += 1
        result = str(decision.payload.get("result") or "").lower()
        if result in {"success", "passed", "pass", "ok"}:
            row["successes"] += 1
        elif result in {"failure", "failed", "fail", "error"}:
            row["failures"] += 1
        if decision.payload.get("tests_passed") is True:
            row["tests_passed"] += 1

    def report(self) -> tuple[dict[str, Any], ...]:
        visible: list[dict[str, Any]] = []
        for row in self._rows.values():
            contributor_count = len(row["contributors"])
            if contributor_count < self.minimum_contributors:
                continue
            samples = int(row["samples"])
            successes = int(row["successes"])
            visible.append(
                {
                    "task_type": row["task_type"],
                    "strategy_id": row["strategy_id"],
                    "contributors": contributor_count,
                    "samples": samples,
                    "successes": successes,
                    "failures": int(row["failures"]),
                    "tests_passed": int(row["tests_passed"]),
                    "success_rate": 0.0 if samples == 0 else round(successes / samples, 6),
                    "privacy_threshold": self.minimum_contributors,
                }
            )
        return tuple(sorted(visible, key=lambda item: (item["task_type"], item["strategy_id"])))
