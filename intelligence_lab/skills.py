from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import re
from typing import Any, Callable, Iterable, Mapping

from .bridge import VishnuCoreBridge
from .memory import LabMemory
from .models import ActionProposal, new_id
from .safety import LabSafetyPolicy, SimulationEngine


_PLACEHOLDER = re.compile(r"^\$\{input\.([A-Za-z_][A-Za-z0-9_]*)\}$")


@dataclass(frozen=True)
class SkillStep:
    action: str
    parameters: dict[str, Any]
    rationale: str
    risk: str = "unknown"

    def public_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SkillBlueprint:
    name: str
    description: str
    input_schema: dict[str, str]
    steps: tuple[SkillStep, ...]
    version: int = 1
    id: str = field(default_factory=lambda: new_id("skill_blueprint"))

    def public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "input_schema": dict(self.input_schema),
            "steps": [step.public_dict() for step in self.steps],
            "version": self.version,
        }


@dataclass(frozen=True)
class SkillPackage:
    blueprint: SkillBlueprint
    evidence: tuple[str, ...]
    package_hash: str
    status: str = "verified"
    raw_code_present: bool = False
    id: str = field(default_factory=lambda: new_id("skill_package"))

    def public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "blueprint": self.blueprint.public_dict(),
            "evidence": list(self.evidence),
            "package_hash": self.package_hash,
            "status": self.status,
            "raw_code_present": self.raw_code_present,
        }


class GovernedSkillLab:
    """Synthesizes, qualifies and runs declarative skills under Core governance.

    Skills are data-only action graphs, never arbitrary Python/shell code. Every
    real step is converted back into an ActionProposal and re-submitted through
    VishnuCoreBridge, preserving Core approvals, policy and audit.
    """

    def __init__(
        self,
        memory: LabMemory,
        safety: LabSafetyPolicy,
        simulator: SimulationEngine,
        bridge: VishnuCoreBridge,
        *,
        json_model_callback: Callable[[str], Mapping[str, Any]] | None = None,
        max_steps: int = 12,
    ):
        self.memory = memory
        self.safety = safety
        self.simulator = simulator
        self.bridge = bridge
        self.json_model_callback = json_model_callback
        self.max_steps = max(1, min(int(max_steps), 32))

    def synthesize(
        self,
        goal: str,
        *,
        allowed_actions: Iterable[str],
        examples: Iterable[Mapping[str, Any]] = (),
    ) -> SkillBlueprint:
        goal = str(goal).strip()
        actions = tuple(dict.fromkeys(str(item).strip() for item in allowed_actions if str(item).strip()))
        if not goal:
            raise ValueError("skill goal is required")
        if not actions:
            raise ValueError("skill synthesis requires an explicit action allowlist")
        if self.json_model_callback is None:
            raise RuntimeError("governed JSON model callback is unavailable for skill synthesis")
        prompt = (
            "Design a declarative Vishnu Intelligence Lab skill. Return JSON only with keys name, description, "
            "input_schema (object of input-name to type string), and steps (array). Each step must contain action, "
            "parameters, rationale, risk. Actions MUST come from ALLOWED_ACTIONS. Parameter values may use only exact "
            "placeholders like ${input.name}. Do not emit code, shell commands, credentials, approval tokens, security "
            "bypasses, or self-modification. The skill is advisory until Vishnu Core governs every real action.\n"
            f"GOAL={goal[:8000]}\nALLOWED_ACTIONS={json.dumps(actions)}\nEXAMPLES={json.dumps(list(examples)[:10], default=str)}"
        )
        raw = self.json_model_callback(prompt)
        if not isinstance(raw, Mapping):
            raise ValueError("skill model output must be an object")
        blueprint = self._parse_blueprint(raw)
        self.validate(blueprint, allowed_actions=actions)
        self.memory.put(blueprint.id, "skill_blueprint", blueprint.public_dict())
        self.memory.audit(
            "skill_lab",
            "blueprint_synthesized",
            {"id": blueprint.id, "name": blueprint.name, "steps": len(blueprint.steps), "raw_code_present": False},
        )
        return blueprint

    def validate(self, blueprint: SkillBlueprint, *, allowed_actions: Iterable[str]) -> None:
        allowed = set(str(item).strip() for item in allowed_actions if str(item).strip())
        if not blueprint.name.strip() or not blueprint.description.strip():
            raise ValueError("skill name and description are required")
        if not blueprint.steps or len(blueprint.steps) > self.max_steps:
            raise ValueError(f"skill must contain between 1 and {self.max_steps} steps")
        if any(token in json.dumps(blueprint.public_dict(), default=str).lower() for token in ("```", "import os", "subprocess", "shell=true")):
            raise PermissionError("raw executable code is outside the declarative skill boundary")
        for key, type_name in blueprint.input_schema.items():
            if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", str(key)):
                raise ValueError("invalid skill input name")
            if str(type_name) not in {"string", "number", "integer", "boolean", "object", "array", "any"}:
                raise ValueError("unsupported skill input type")
        for step in blueprint.steps:
            if step.action not in allowed:
                raise PermissionError(f"skill action is not allowlisted: {step.action}")
            verdict = self.safety.evaluate_proposal(
                ActionProposal(step.action, dict(step.parameters), step.rationale, risk=step.risk)
            )
            if not verdict.allowed:
                raise PermissionError("; ".join(verdict.reasons))
            self._validate_templates(step.parameters, blueprint.input_schema)

    def qualify(
        self,
        blueprint: SkillBlueprint,
        *,
        allowed_actions: Iterable[str],
        test_cases: Iterable[Mapping[str, Any]],
        world: Mapping[str, Any] | None = None,
    ) -> SkillPackage:
        self.validate(blueprint, allowed_actions=allowed_actions)
        cases = tuple(dict(item) for item in test_cases)
        if not cases:
            raise ValueError("skill qualification requires at least one test case")
        evidence: list[str] = []
        for index, case in enumerate(cases):
            inputs = dict(case.get("inputs") or {})
            expected = list(case.get("expected_actions") or [step.action for step in blueprint.steps])
            resolved = self._resolve_steps(blueprint, inputs)
            actions = [step.action for step in resolved]
            if actions != expected:
                raise AssertionError(f"skill qualification case {index} action sequence mismatch")
            for step in resolved:
                proposal = ActionProposal(step.action, step.parameters, step.rationale, risk=step.risk)
                verdict = self.safety.evaluate_proposal(proposal)
                if not verdict.allowed:
                    raise PermissionError("; ".join(verdict.reasons))
                simulation = self.simulator.simulate(proposal, world=world or {})
                if simulation.executed:
                    raise AssertionError("skill qualification simulation must never execute")
                evidence.append(f"case:{index}:simulation:{simulation.id}")
        digest = self._hash(blueprint, evidence)
        package = SkillPackage(blueprint=blueprint, evidence=tuple(evidence), package_hash=digest)
        self.memory.put(package.id, "skill_package", package.public_dict())
        self.memory.upsert_skill(
            blueprint.name,
            blueprint.description,
            package.evidence,
            1.0,
            status="verified",
        )
        self.memory.audit(
            "skill_lab",
            "package_qualified",
            {
                "id": package.id,
                "blueprint_id": blueprint.id,
                "package_hash": digest,
                "test_cases": len(cases),
                "real_actions_executed": False,
            },
        )
        return package

    def run(
        self,
        package: SkillPackage,
        *,
        inputs: Mapping[str, Any],
        execute: bool = False,
        autonomous: bool = False,
        preauthorized: bool = False,
        owner_id: str = "owner",
        device_id: str | None = None,
        session_id: str | None = None,
        conversation_id: str | None = None,
        reauthenticated_at: float | None = None,
    ) -> dict[str, Any]:
        if package.status != "verified" or package.raw_code_present:
            raise PermissionError("only verified declarative skill packages can run")
        if package.package_hash != self._hash(package.blueprint, package.evidence):
            raise PermissionError("skill package integrity check failed")
        resolved = self._resolve_steps(package.blueprint, dict(inputs))
        results = []
        for step in resolved:
            proposal = self.bridge.propose(step.action, step.parameters, step.rationale, risk=step.risk)
            simulation = self.simulator.simulate(proposal, world={})
            item: dict[str, Any] = {
                "proposal": proposal.public_dict(),
                "simulation": simulation.public_dict(),
                "executed": False,
                "result": None,
            }
            if execute:
                item["result"] = self.bridge.execute(
                    proposal,
                    autonomous=autonomous,
                    preauthorized=preauthorized,
                    owner_id=owner_id,
                    device_id=device_id,
                    session_id=session_id,
                    conversation_id=conversation_id,
                    reauthenticated_at=reauthenticated_at,
                )
                item["executed"] = True
            results.append(item)
        self.memory.audit(
            "skill_lab",
            "package_run",
            {
                "package_id": package.id,
                "steps": len(results),
                "execute_requested": bool(execute),
                "core_governance_required": bool(execute),
            },
        )
        return {
            "package_id": package.id,
            "package_hash": package.package_hash,
            "steps": results,
            "executed": bool(execute),
        }

    def promotion_manifest(self, package: SkillPackage) -> dict[str, Any]:
        return {
            "subject_id": package.package_hash,
            "package_id": package.id,
            "blueprint_id": package.blueprint.id,
            "skill_name": package.blueprint.name,
            "evidence": list(package.evidence),
            "package_hash": package.package_hash,
            "raw_code_present": False,
            "stable_core_mutated": False,
            "next_step": "evaluation_then_verification_then_trusted_owner_approval_then_engineering_review",
        }

    def _parse_blueprint(self, raw: Mapping[str, Any]) -> SkillBlueprint:
        steps_raw = raw.get("steps")
        if not isinstance(steps_raw, list):
            raise ValueError("skill steps must be an array")
        steps = []
        for item in steps_raw:
            if not isinstance(item, Mapping):
                raise ValueError("each skill step must be an object")
            steps.append(
                SkillStep(
                    action=str(item.get("action") or "").strip(),
                    parameters=dict(item.get("parameters") or {}),
                    rationale=str(item.get("rationale") or "").strip(),
                    risk=str(item.get("risk") or "unknown").strip().lower(),
                )
            )
        schema = raw.get("input_schema") or {}
        if not isinstance(schema, Mapping):
            raise ValueError("skill input_schema must be an object")
        return SkillBlueprint(
            name=str(raw.get("name") or "").strip()[:200],
            description=str(raw.get("description") or "").strip()[:2000],
            input_schema={str(key): str(value) for key, value in schema.items()},
            steps=tuple(steps),
        )

    def _resolve_steps(self, blueprint: SkillBlueprint, inputs: Mapping[str, Any]) -> tuple[SkillStep, ...]:
        missing = [name for name in blueprint.input_schema if name not in inputs]
        if missing:
            raise ValueError(f"missing skill inputs: {missing}")
        return tuple(
            SkillStep(
                action=step.action,
                parameters=self._resolve_value(step.parameters, inputs),
                rationale=step.rationale,
                risk=step.risk,
            )
            for step in blueprint.steps
        )

    @classmethod
    def _resolve_value(cls, value: Any, inputs: Mapping[str, Any]) -> Any:
        if isinstance(value, str):
            match = _PLACEHOLDER.match(value)
            if match:
                return inputs[match.group(1)]
            return value
        if isinstance(value, Mapping):
            return {str(key): cls._resolve_value(nested, inputs) for key, nested in value.items()}
        if isinstance(value, list):
            return [cls._resolve_value(item, inputs) for item in value]
        if isinstance(value, tuple):
            return tuple(cls._resolve_value(item, inputs) for item in value)
        return value

    @classmethod
    def _validate_templates(cls, value: Any, schema: Mapping[str, str]) -> None:
        if isinstance(value, str):
            if "${" in value:
                match = _PLACEHOLDER.match(value)
                if not match or match.group(1) not in schema:
                    raise ValueError("skill parameter contains an invalid input placeholder")
            return
        if isinstance(value, Mapping):
            for nested in value.values():
                cls._validate_templates(nested, schema)
        elif isinstance(value, (list, tuple)):
            for nested in value:
                cls._validate_templates(nested, schema)

    @staticmethod
    def _hash(blueprint: SkillBlueprint, evidence: Iterable[str]) -> str:
        payload = {
            "blueprint": blueprint.public_dict(),
            "evidence": list(evidence),
            "raw_code_present": False,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()
