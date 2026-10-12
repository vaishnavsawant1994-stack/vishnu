from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Protocol


CONTENT_INTELLIGENCE_V1_REQUIRED_GATES = (
    "production_ingestion_e2e",
    "stage16_grounded_understanding",
    "stage17_scope_isolation",
    "stage17_retry_recovery",
    "stage17_reprocessing",
    "stage18_multimodal_graph",
    "stage18_grounded_visual_qa",
    "unsupported_answer_rejection",
    "knowledge_integration",
    "projects_scope_isolation",
    "model_shadow_qualification",
    "owner_approval_gate",
    "release_controller_activation",
    "security_regression_suite",
    "backup_restore_recovery",
    "performance_budget",
    "windows_package",
    "macos_package",
    "ubuntu_package",
)


class RealWorldEvidenceAuthority(Protocol):
    def latest_qualified(self) -> dict[str, Any] | None: ...


@dataclass(frozen=True)
class ContentIntelligenceV1ReleaseReport:
    status: str
    implementation_qualified: bool
    production_hardening_qualified: bool
    real_world_corpus_qualified: bool
    v1_release_ready: bool
    completed_gates: tuple[str, ...]
    missing_gates: tuple[str, ...]
    blockers: tuple[str, ...]
    stage_floor: int
    stage_ceiling: int
    foundation_model: bool
    synthetic_evidence_can_qualify: bool
    evidence_sha256: str

    def public(self) -> dict[str, Any]:
        value = asdict(self)
        value["completed_gates"] = list(self.completed_gates)
        value["missing_gates"] = list(self.missing_gates)
        value["blockers"] = list(self.blockers)
        return value


class ContentIntelligenceV1ReleaseQualifier:
    """Final fail-closed release authority for the Stage 0-18 content stack.

    Repository/CI gates may establish implementation and production-hardening
    readiness. They can never substitute for genuine governed real-world corpus
    evidence. A V1 production-ready claim is allowed only when both authorities
    are satisfied.
    """

    required_gates = CONTENT_INTELLIGENCE_V1_REQUIRED_GATES

    @staticmethod
    def _real_world_qualified(authority: RealWorldEvidenceAuthority | None) -> bool:
        if authority is None:
            return False
        evidence = authority.latest_qualified()
        if not evidence:
            return False
        return (
            evidence.get("qualified") is True
            and evidence.get("real_world_corpus_qualified") is True
            and evidence.get("synthetic_evidence_can_qualify") is False
            and evidence.get("evidence_persisted") is True
            and int(evidence.get("records") or 0) > 0
            and int(evidence.get("source_groups") or 0) >= 6
        )

    @staticmethod
    def _digest(payload: Mapping[str, Any]) -> str:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def qualify(
        self,
        gates: Mapping[str, bool],
        *,
        real_world_authority: RealWorldEvidenceAuthority | None = None,
    ) -> ContentIntelligenceV1ReleaseReport:
        completed = tuple(sorted(name for name in self.required_gates if gates.get(name) is True))
        missing = tuple(sorted(name for name in self.required_gates if gates.get(name) is not True))
        implementation = not missing
        hardening_names = {
            "stage17_retry_recovery",
            "stage17_reprocessing",
            "security_regression_suite",
            "backup_restore_recovery",
            "performance_budget",
            "windows_package",
            "macos_package",
            "ubuntu_package",
        }
        hardening = all(gates.get(name) is True for name in hardening_names)
        real_world = self._real_world_qualified(real_world_authority)
        ready = implementation and hardening and real_world
        blockers: list[str] = []
        if missing:
            blockers.extend(f"missing_gate:{name}" for name in missing)
        if not real_world:
            blockers.append("genuine_real_world_corpus_evidence_required")
        if ready:
            status = "v1_release_qualified"
        elif implementation and hardening:
            status = "qualified_pending_real_world"
        else:
            status = "not_release_qualified"
        digest_payload = {
            "status": status,
            "implementation_qualified": implementation,
            "production_hardening_qualified": hardening,
            "real_world_corpus_qualified": real_world,
            "v1_release_ready": ready,
            "completed_gates": completed,
            "missing_gates": missing,
            "blockers": tuple(blockers),
            "stage_floor": 0,
            "stage_ceiling": 18,
            "foundation_model": False,
            "synthetic_evidence_can_qualify": False,
        }
        return ContentIntelligenceV1ReleaseReport(
            status=status,
            implementation_qualified=implementation,
            production_hardening_qualified=hardening,
            real_world_corpus_qualified=real_world,
            v1_release_ready=ready,
            completed_gates=completed,
            missing_gates=missing,
            blockers=tuple(blockers),
            stage_floor=0,
            stage_ceiling=18,
            foundation_model=False,
            synthetic_evidence_can_qualify=False,
            evidence_sha256=self._digest(digest_payload),
        )
