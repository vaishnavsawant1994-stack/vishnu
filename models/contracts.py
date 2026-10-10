from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any
import time
import uuid


class PrivacyClass(str, Enum):
    PUBLIC = 'public'
    INTERNAL = 'internal'
    SENSITIVE = 'sensitive'
    PRIVATE_LOCAL = 'private_local'


class QualityClass(str, Enum):
    FAST = 'fast'
    BALANCED = 'balanced'
    BEST = 'best'


class FailureClass(str, Enum):
    TIMEOUT = 'timeout'
    RATE_LIMITED = 'rate_limited'
    QUOTA_EXHAUSTED = 'quota_exhausted'
    AUTHENTICATION = 'authentication_error'
    PROVIDER_UNAVAILABLE = 'provider_unavailable'
    MODEL_UNAVAILABLE = 'model_unavailable'
    INVALID_RESPONSE = 'malformed_response'
    CONTEXT_LIMIT = 'context_limit'
    TOOL_SCHEMA = 'tool_schema_failure'
    SAFETY_REFUSAL = 'safety_refusal'
    NETWORK = 'connection_error'
    SERVER = 'server_error'
    POLICY_DENIED = 'policy_denied'
    BUDGET_EXHAUSTED = 'budget_exhausted'
    UNKNOWN = 'unknown_failure'


@dataclass(frozen=True)
class CapabilityRequirement:
    name: str
    required: bool = True
    minimum: float = 0.0


@dataclass(frozen=True)
class ModelRequest:
    prompt: str = ''
    system: str = ''
    history: tuple[dict[str, Any], ...] = ()
    request_id: str = field(default_factory=lambda: f'req_{uuid.uuid4().hex}')
    execution_id: str | None = None
    task_id: str | None = None
    agent_id: str | None = None
    project_id: str | None = None
    capability: str = 'chat'
    routing_policy: str = 'fast_chat'
    required_capabilities: tuple[str, ...] = ()
    preferred_capabilities: tuple[str, ...] = ()
    sensitivity: str = PrivacyClass.INTERNAL.value
    quality: str = QualityClass.BALANCED.value
    max_tokens: int | None = None
    max_cost: float | None = None
    deadline_at: float | None = None
    preferred_provider: str | None = None
    preferred_model: str | None = None
    allowed_providers: tuple[str, ...] = ()
    blocked_providers: tuple[str, ...] = ()
    tools_allowed: tuple[str, ...] = ()
    structured_output_schema: dict[str, Any] | None = None
    # Private retrieved context is a separate field so the governed router can
    # inject it only into private/local providers. It must never be flattened
    # into a shared system/prompt string before provider selection.
    private_context: str = ''
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RoutingCandidate:
    provider_id: str
    model_id: str
    score: float
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class RoutingDecision:
    request_id: str
    provider_id: str
    model_id: str
    policy: str
    reason: str
    candidates: tuple[RoutingCandidate, ...] = ()
    decided_at: float = field(default_factory=time.time)
    fallback_index: int = 0

    def public(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class UsageRecord:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost: float = 0.0
    latency_ms: float | None = None


@dataclass(frozen=True)
class ModelResponse:
    request_id: str
    provider_id: str
    model_id: str
    content: str = ''
    tool_calls: tuple[dict[str, Any], ...] = ()
    structured_output: dict[str, Any] | None = None
    usage: UsageRecord = field(default_factory=UsageRecord)
    finish_reason: str | None = None
    retry_count: int = 0
    routing_decision_id: str | None = None


@dataclass(frozen=True)
class HandoffContext:
    execution_id: str
    agent_id: str
    task_id: str
    project_id: str | None
    goal: str
    current_plan: dict[str, Any]
    current_task: dict[str, Any]
    completed_tasks: tuple[str, ...] = ()
    failed_tasks: tuple[str, ...] = ()
    blocked_tasks: tuple[str, ...] = ()
    success_criteria: tuple[str, ...] = ()
    important_context: str = ''
    files_read: tuple[str, ...] = ()
    files_changed: tuple[str, ...] = ()
    tool_results: dict[str, Any] = field(default_factory=dict)
    decisions: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    project_instructions: str = ''
    relevant_memory: tuple[str, ...] = ()
    previous_model: str | None = None
    previous_provider: str | None = None
    next_model: str | None = None
    next_provider: str | None = None
    handoff_reason: str = ''
    token_budget_remaining: int | None = None
    cost_budget_remaining: float | None = None
    verification_state: dict[str, Any] = field(default_factory=dict)
    checkpoint_reference: str | None = None
