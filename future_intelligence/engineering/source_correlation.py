from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Mapping

from .contracts import VisualDefect
from .repository_intelligence import RepositoryGraph


@dataclass(frozen=True)
class SourceCandidate:
    path: str
    score: float
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {"path": self.path, "score": self.score, "reasons": list(self.reasons)}


class VisualSourceCorrelator:
    """Deterministically rank source files before asking a model to diagnose a visual defect."""

    _UI_SUFFIXES = {".css", ".html", ".js", ".mjs", ".jsx", ".ts", ".tsx"}

    def correlate(self, graph: RepositoryGraph, defect: VisualDefect, *, dom_evidence: Mapping[str, object] | None = None, limit: int = 12) -> tuple[SourceCandidate, ...]:
        dom = dict(dom_evidence or {})
        needles = [
            defect.screen, defect.route, defect.suspected_component, defect.suspected_element,
            str(dom.get("component") or ""), str(dom.get("source_hint") or ""),
            str(dom.get("id") or ""), str(dom.get("class") or ""),
        ]
        tokens = {token.lower().strip("#./[]() ") for value in needles for token in str(value).replace("/", " ").replace("-", " ").replace("_", " ").split() if len(token.strip()) >= 3}
        ranked: list[SourceCandidate] = []
        for node in graph.nodes:
            if node.kind not in {"file", "test"}:
                continue
            suffix = PurePosixPath(node.path).suffix.lower()
            if suffix not in self._UI_SUFFIXES:
                continue
            haystack = f"{node.path} {node.name} {' '.join(str(item) for item in node.metadata.get('routes', ()))}".lower()
            score = 0.0
            reasons: list[str] = []
            for token in tokens:
                if token and token in haystack:
                    score += 1.0
                    reasons.append(f"matched:{token}")
            if suffix == ".css" and any(word in defect.actual.lower() for word in ("layout", "spacing", "position", "overflow", "size", "color", "font")):
                score += 0.75; reasons.append("visual-style-surface")
            if defect.route and defect.route in tuple(node.metadata.get("routes", ())):
                score += 2.0; reasons.append("route-match")
            if score > 0:
                ranked.append(SourceCandidate(node.path, score, tuple(dict.fromkeys(reasons))))
        ranked.sort(key=lambda item: (-item.score, item.path))
        return tuple(ranked[:max(1, min(50, int(limit)))])
