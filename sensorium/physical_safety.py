from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SafetyRule:
    rule_id: str
    triggers: tuple[str, ...]
    risk: str
    required_conditions: tuple[str, ...]
    stop_conditions: tuple[str, ...]
    escalation: str


DEFAULT_RULES = (
    SafetyRule(
        "mains-electricity",
        ("mains", "high voltage", "breaker", "live wire", "wall outlet"),
        "critical",
        ("power_isolated", "voltage_verified_absent"),
        ("unknown_live_state", "wet_environment", "damaged_insulation"),
        "Stop and use a qualified electrician when live-state isolation cannot be verified.",
    ),
    SafetyRule(
        "gas-flame",
        ("gas", "flame", "burner", "fuel line"),
        "critical",
        ("ventilation_adequate", "leak_absent"),
        ("gas_smell", "suspected_leak", "uncontrolled_flame"),
        "Stop, move to safety and use the relevant emergency/qualified service if a leak is suspected.",
    ),
    SafetyRule(
        "cutting-power-tool",
        ("saw", "drill", "grinder", "blade", "cutting"),
        "high",
        ("eye_protection", "workpiece_secured"),
        ("guard_missing", "unstable_workpiece", "bystander_in_zone"),
        "Do not continue until the tool/work area is safe.",
    ),
    SafetyRule(
        "heat-pressure",
        ("boiling", "pressure cooker", "steam", "hot surface"),
        "high",
        ("heat_protection",),
        ("pressure_unknown", "uncontrolled_steam"),
        "Stop and allow the system to reach a known safe state.",
    ),
)


class PhysicalSafetyEngine:
    """Independent proposal-safety assessment; it never approves execution."""

    RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}

    def __init__(self, *, events=None, rules: tuple[SafetyRule, ...] = DEFAULT_RULES) -> None:
        self.events = events
        self.rules = rules

    def evaluate(
        self,
        description: str,
        *,
        observed_conditions: dict[str, bool] | None = None,
        reversible: bool | None = None,
        requested_ppe: list[str] | None = None,
    ) -> dict[str, Any]:
        text = str(description or "").strip().lower()
        if not text:
            raise ValueError("safety evaluation description is required")
        conditions = {
            str(key): bool(value)
            for key, value in (observed_conditions or {}).items()
        }
        matched: list[dict[str, Any]] = []
        highest = "low"
        blocked = False
        for rule in self.rules:
            if not any(trigger in text for trigger in rule.triggers):
                continue
            missing = [
                condition for condition in rule.required_conditions
                if not conditions.get(condition, False)
            ]
            stops = [
                condition for condition in rule.stop_conditions
                if conditions.get(condition, False)
            ]
            rule_blocked = bool(missing or stops) and rule.risk in {"high", "critical"}
            blocked = blocked or rule_blocked
            if self.RISK_ORDER[rule.risk] > self.RISK_ORDER[highest]:
                highest = rule.risk
            matched.append(
                {
                    "rule_id": rule.rule_id,
                    "risk": rule.risk,
                    "missing_required_conditions": missing,
                    "active_stop_conditions": stops,
                    "escalation": rule.escalation,
                    "proposal_blocked": rule_blocked,
                }
            )
        if reversible is False and highest == "low":
            highest = "medium"
        result = {
            "risk": highest,
            "matched_rules": matched,
            "requested_ppe": list(requested_ppe or [])[:32],
            "proposal_blocked": blocked,
            "safe_to_propose": not blocked,
            "approval_granted": False,
            "execution_authority": False,
            "note": (
                "Sensorium safety can block or escalate a proposal; "
                "it cannot approve or execute an action."
            ),
        }
        if self.events is not None:
            self.events.emit(
                "sensorium.v3.safety.evaluated",
                risk=highest,
                proposal_blocked=blocked,
                approval_granted=False,
            )
        return result
