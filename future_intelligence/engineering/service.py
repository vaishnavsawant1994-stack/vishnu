from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

from .contracts import EngineeringSpec, QualificationReport
from .evidence import EngineeringEvidenceLedger
from .impact import EngineeringImpactAnalyzer, ImpactReport
from .qualification import EngineeringQualification, VerificationObservation
from .repository_editor import GovernedRepositoryEditor
from .repository_intelligence import RepositoryGraph, RepositoryIntelligenceBuilder


@dataclass(frozen=True)
class EngineeringContext:
    spec: EngineeringSpec
    graph: RepositoryGraph
    impact: ImpactReport
    changed_paths: tuple[str, ...]


class EngineeringCandidateCoordinator:
    """Connect existing Work/workspaces to engineering evidence without new release authority.

    The coordinator can inspect an isolated workspace, build reconstructable source
    intelligence, expose the governed editor, and assemble a qualification report.
    It cannot create approvals, push, merge, deploy, or activate a candidate.
    """

    def __init__(
        self,
        *,
        repository_provider,
        session,
        spec: EngineeringSpec,
        evidence_root: str | Path,
        graph_builder: RepositoryIntelligenceBuilder | None = None,
        impact_analyzer: EngineeringImpactAnalyzer | None = None,
        qualification: EngineeringQualification | None = None,
    ) -> None:
        self.provider = repository_provider
        self.session = session
        self.spec = spec
        self.editor = GovernedRepositoryEditor(provider=repository_provider, session=session, spec=spec)
        self.graph_builder = graph_builder or RepositoryIntelligenceBuilder()
        self.impact_analyzer = impact_analyzer or EngineeringImpactAnalyzer()
        self.qualification = qualification or EngineeringQualification()
        self.evidence = EngineeringEvidenceLedger(evidence_root, work_order_id=spec.work_order_id, attempt_id=spec.attempt_id)

    @staticmethod
    def _dirty_paths(changes: Iterable[str]) -> tuple[str, ...]:
        """Best-effort extraction of safe paths from Git porcelain status lines.

        The authoritative mutation list remains the governed editor's evidence.
        This fallback exists so inspection still surfaces pre-existing dirty work
        without changing repository authority or invoking shell parsing.
        """
        paths: list[str] = []
        for raw in changes:
            value = str(raw or "")
            payload = value[3:].strip() if len(value) >= 4 else value.strip()
            candidates = payload.split(" -> ", 1) if " -> " in payload else (payload,)
            for candidate in candidates:
                path = candidate.strip().strip('"').replace("\\", "/")
                if path and path not in paths:
                    paths.append(path)
        return tuple(paths)

    def _workspace_changed_paths(self) -> tuple[str, ...]:
        status = self.provider.status(self.session)
        committed = self.provider.changed_paths(
            base_revision=self.session.base_revision,
            working_revision=status.revision,
        )
        dirty = self.editor.mutated_paths
        if status.dirty:
            dirty = tuple(dict.fromkeys((*dirty, *self._dirty_paths(status.changes))))
        return tuple(dict.fromkeys((*committed, *dirty)))

    def inspect(self, *, changed_paths: Iterable[str] | None = None) -> EngineeringContext:
        current_paths = tuple(changed_paths) if changed_paths is not None else self._workspace_changed_paths()
        graph = self.graph_builder.build(self.session.local_path, revision=self.spec.base_revision, include_paths=self.spec.allowed_paths)
        impact = self.impact_analyzer.analyze(graph, current_paths)
        context = EngineeringContext(self.spec, graph, impact, current_paths)
        self.evidence.append("engineering.inspect", {
            "spec_id": self.spec.id,
            "base_revision": self.spec.base_revision,
            "graph_fingerprint": graph.fingerprint,
            "changed_paths": list(current_paths),
            "impact": impact.to_dict(),
        })
        return context

    def record_mutations(self) -> None:
        for item in self.editor.mutation_evidence:
            self.evidence.append("engineering.mutation", item.to_dict())

    def finalize(
        self,
        *,
        candidate_revision: str,
        observations: Iterable[VerificationObservation],
        reviewer: str = "",
        review_decision: str = "pending",
        limitations: Iterable[str] = (),
        review_evidence: Mapping[str, object] | None = None,
    ) -> QualificationReport:
        report = self.qualification.report(
            spec=self.spec,
            candidate_revision=candidate_revision,
            observations=observations,
            reviewer=reviewer,
            review_decision=review_decision,
            limitations=limitations,
        )
        self.evidence.append("engineering.qualification", report.to_dict())
        if review_evidence:
            self.evidence.append("engineering.review", dict(review_evidence))
        return report

    def status(self) -> dict[str, object]:
        return {
            "spec_id": self.spec.id,
            "work_order_id": self.spec.work_order_id,
            "attempt_id": self.spec.attempt_id,
            "workspace": str(self.session.local_path),
            "mutated_paths": list(self.editor.mutated_paths),
            "max_repair_cycles": self.spec.budget.max_repair_cycles,
            "push_authority": False,
            "merge_authority": False,
            "deploy_authority": False,
            "activation_authority": False,
        }
