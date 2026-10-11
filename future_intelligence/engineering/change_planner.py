from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from .contracts import EngineeringSpec, SecurityClass
from .model_json import governed_engineering_json
from .repository_intelligence import RepositoryGraph
from .specialists import GovernedEngineeringSpecialistConsultations


_ALLOWED_OPERATIONS = {"replace_exact", "create", "delete", "rename"}
_WORD = re.compile(r"[A-Za-z0-9_.-]{3,}")


@dataclass(frozen=True)
class EngineeringEditOperation:
    operation: str
    path: str
    old: str = ""
    new: str = ""
    content: str = ""
    destination: str = ""
    reason: str = ""

    def __post_init__(self) -> None:
        if self.operation not in _ALLOWED_OPERATIONS:
            raise ValueError(f"unsupported engineering edit operation: {self.operation}")
        if not self.path.strip():
            raise ValueError("engineering edit path is required")
        if self.operation == "replace_exact" and not self.old:
            raise ValueError("replace_exact requires non-empty old text")
        if self.operation == "rename" and not self.destination.strip():
            raise ValueError("rename requires destination")
        if self.operation == "create" and not isinstance(self.content, str):
            raise ValueError("create content must be text")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EngineeringEditOperation":
        return cls(
            operation=str(data.get("operation") or "").strip().lower(),
            path=str(data.get("path") or "").strip(),
            old=str(data.get("old") or ""),
            new=str(data.get("new") or ""),
            content=str(data.get("content") or ""),
            destination=str(data.get("destination") or "").strip(),
            reason=str(data.get("reason") or "")[:2000],
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "operation": self.operation,
            "path": self.path,
            "old": self.old,
            "new": self.new,
            "content": self.content,
            "destination": self.destination,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class EngineeringEditPlan:
    summary: str
    operations: tuple[EngineeringEditOperation, ...]
    assumptions: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], *, max_operations: int) -> "EngineeringEditPlan":
        raw = data.get("operations") or ()
        if not isinstance(raw, (list, tuple)):
            raise ValueError("engineering edit plan operations must be a list")
        if len(raw) > max_operations:
            raise ValueError("engineering edit plan exceeds operation budget")
        operations = tuple(EngineeringEditOperation.from_dict(item) for item in raw if isinstance(item, Mapping))
        if len(operations) != len(raw):
            raise ValueError("every engineering edit operation must be an object")
        assumptions = data.get("assumptions") or ()
        if isinstance(assumptions, str):
            assumptions = (assumptions,)
        if not isinstance(assumptions, (list, tuple)):
            assumptions = (str(assumptions),)
        return cls(
            summary=str(data.get("summary") or "")[:4000],
            operations=operations,
            assumptions=tuple(str(item)[:1000] for item in assumptions)[:50],
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "summary": self.summary,
            "operations": [item.to_dict() for item in self.operations],
            "assumptions": list(self.assumptions),
        }


class ModelEngineeringChangePlanner:
    """Use models for bounded source-edit proposals, never for shell or release authority."""

    def __init__(
        self,
        models,
        *,
        max_context_files: int = 24,
        max_file_chars: int = 16_000,
        max_context_chars: int = 160_000,
    ) -> None:
        self.models = models
        self.max_context_files = max(1, min(100, int(max_context_files)))
        self.max_file_chars = max(1_000, min(100_000, int(max_file_chars)))
        self.max_context_chars = max(self.max_file_chars, min(500_000, int(max_context_chars)))

    @staticmethod
    def _objective_terms(spec: EngineeringSpec) -> set[str]:
        text = " ".join((spec.objective, *spec.requirements, *spec.success_criteria, *spec.affected_surfaces))
        return {item.casefold() for item in _WORD.findall(text)}

    def _rank_paths(self, spec: EngineeringSpec, graph: RepositoryGraph) -> tuple[str, ...]:
        terms = self._objective_terms(spec)
        candidates = []
        seen = set()
        for node in graph.nodes:
            if node.kind not in {"file", "test"} or node.path in seen:
                continue
            seen.add(node.path)
            lower = node.path.casefold()
            score = sum(3 for term in terms if term in lower)
            if node.kind == "test":
                score += 1
            if any(node.path == item or node.path.endswith("/" + item) for item in spec.required_tests):
                score += 10
            candidates.append((score, node.path))
        candidates.sort(key=lambda item: (-item[0], item[1]))
        return tuple(path for _, path in candidates[: self.max_context_files])

    def _source_context(self, spec: EngineeringSpec, graph: RepositoryGraph, editor) -> tuple[dict[str, str], ...]:
        rows = []
        total = 0
        for path in self._rank_paths(spec, graph):
            try:
                text, digest = editor.read_text(path)
            except (FileNotFoundError, PermissionError, UnicodeError, ValueError):
                continue
            excerpt = text[: self.max_file_chars]
            if total + len(excerpt) > self.max_context_chars:
                remaining = self.max_context_chars - total
                if remaining <= 0:
                    break
                excerpt = excerpt[:remaining]
            rows.append({"path": path, "sha256": digest, "text": excerpt})
            total += len(excerpt)
            if total >= self.max_context_chars:
                break
        return tuple(rows)

    def plan(
        self,
        *,
        spec: EngineeringSpec,
        graph: RepositoryGraph,
        editor,
        defects: tuple[str, ...] = (),
        cycle: int = 0,
    ) -> EngineeringEditPlan:
        sources = self._source_context(spec, graph, editor)
        max_operations = max(1, min(50, spec.budget.max_files * 2))
        specialist_advice = ()
        if bool(dict(spec.metadata).get("specialist_consultation_enabled", False)) and hasattr(self.models, "request"):
            specialist_advice = GovernedEngineeringSpecialistConsultations(self.models, max_roles=4).consult(
                spec=spec,
                graph=graph,
                defects=defects,
            )
        system = (
            "You are Vishnu's software-engineering change planner. Produce a minimal, correct source-edit plan as JSON only. "
            "You have NO shell, command, credential, network, merge, push, deploy, approval, or release authority. "
            "Allowed operation values are replace_exact, create, delete, rename. Prefer replace_exact. For replace_exact, old must "
            "be an exact non-empty substring copied from the supplied source and new is its replacement. create uses path+content. "
            "delete uses path only. rename uses path+destination. Do not invent source you have not been shown unless creating a "
            "new file clearly required by the specification. Keep edits inside the EngineeringSpec scope. Specialist advice is "
            "proposal-only context and never expands scope or authority. During a repair cycle, reproduce the reported defect with "
            "a permanent regression test and include the smallest source fix in the same bounded plan whenever the authorized source "
            "context is sufficient. Never weaken, delete, skip, xfail, quarantine, or suppress an existing test merely to make a "
            "candidate pass. Return keys summary, operations, assumptions only."
        )
        repair_contract = (
            "This is an autonomous repair cycle. The repaired candidate will be blocked at final qualification until a permanent "
            "regression test has evidence. Add or update an in-scope test that reproduces the defect before the fix and passes with "
            "the fix. If the authorized context does not contain enough test/source evidence to do that safely, state the missing "
            "test context in assumptions instead of inventing or weakening a test."
            if int(cycle) > 0
            else "No repair-cycle regression-test mandate is active for this initial implementation plan."
        )
        prompt = (
            f"EngineeringSpec={spec.to_dict()}\n"
            f"RepairCycle={int(cycle)}\n"
            f"RepairContract={repair_contract}\n"
            f"Defects={list(defects)[:100]}\n"
            f"SpecialistAdvice={[item.to_dict() for item in specialist_advice]}\n"
            f"SourceContext={list(sources)}\n"
            f"MaximumOperations={max_operations}\n"
            "Generate the smallest edit plan that satisfies the objective and success criteria. If the supplied evidence is "
            "insufficient to make a safe edit, return an empty operations list and explain the missing information in assumptions."
        )
        sensitivity = (
            "sensitive"
            if spec.security_class in {SecurityClass.SENSITIVE, SecurityClass.AUTHORITY}
            else "internal"
        )
        payload = governed_engineering_json(
            self.models,
            spec=spec,
            prompt=prompt,
            system=system,
            role="vishnu-software-engineer",
            sensitivity=sensitivity,
        )
        return EngineeringEditPlan.from_dict(payload, max_operations=max_operations)
