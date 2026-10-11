from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from .repository_intelligence import RepositoryGraph


@dataclass(frozen=True)
class ImpactReport:
    changed_paths: tuple[str, ...]
    dependent_paths: tuple[str, ...]
    relevant_tests: tuple[str, ...]
    surfaces: tuple[str, ...]
    risks: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "changed_paths": list(self.changed_paths),
            "dependent_paths": list(self.dependent_paths),
            "relevant_tests": list(self.relevant_tests),
            "surfaces": list(self.surfaces),
            "risks": list(self.risks),
        }


class EngineeringImpactAnalyzer:
    def analyze(self, graph: RepositoryGraph, changed_paths: tuple[str, ...]) -> ImpactReport:
        changed = tuple(dict.fromkeys(str(item) for item in changed_paths))
        changed_ids = {f"file:{path}" for path in changed}
        reverse: dict[str, set[str]] = {}
        node_path = {node.id: node.path for node in graph.nodes}
        for edge in graph.edges:
            if edge.kind == "imports":
                reverse.setdefault(edge.target, set()).add(edge.source)
        queue = list(changed_ids)
        dependent_ids: set[str] = set()
        while queue and len(dependent_ids) < 500:
            current = queue.pop(0)
            for dependent in reverse.get(current, ()):
                if dependent not in changed_ids and dependent not in dependent_ids:
                    dependent_ids.add(dependent)
                    queue.append(dependent)
        dependents = tuple(sorted({node_path[item] for item in dependent_ids if item in node_path}))
        tests = set()
        stems = {PurePosixPath(path).stem.replace("test_", "") for path in (*changed, *dependents)}
        for node in graph.nodes:
            if node.kind != "test":
                continue
            test_stem = PurePosixPath(node.path).stem.replace("test_", "")
            if any(stem and (stem in test_stem or test_stem in stem) for stem in stems):
                tests.add(node.path)
        surfaces: set[str] = set()
        risks: set[str] = set()
        for path in changed:
            lower = path.lower()
            if lower.startswith(("pwa/", "web-companion/")) or lower.endswith((".html", ".css", ".js", ".mjs", ".tsx", ".jsx")):
                surfaces.add("ui")
            if lower.startswith(("server/", "api/")) or "_api.py" in lower:
                surfaces.add("api")
            if "migration" in lower or "schema" in lower or lower.endswith(".sql"):
                surfaces.add("database"); risks.add("schema_change")
            if lower.startswith(("android", "ios")):
                surfaces.add("mobile")
            if lower.startswith(("security/", "identity/", "evolution/", "tools/", "capabilities/", "future_intelligence/work_orchestration/")):
                risks.add("authority_sensitive")
            if lower.startswith(".github/workflows/"):
                surfaces.add("ci"); risks.add("ci_change")
        if "ui" in surfaces:
            risks.add("responsive_regression")
        if "api" in surfaces:
            risks.add("contract_regression")
        return ImpactReport(changed, dependents, tuple(sorted(tests)), tuple(sorted(surfaces)), tuple(sorted(risks)))
