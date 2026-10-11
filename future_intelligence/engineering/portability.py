from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class EngineeringArtifactClass(StrEnum):
    PORTABLE = "portable"
    REBUILDABLE = "rebuildable"
    SENSITIVE_EVIDENCE = "sensitive_evidence"


@dataclass(frozen=True)
class EngineeringArtifactPolicy:
    artifact: str
    classification: EngineeringArtifactClass
    reason: str
    shared_learning_allowed_by_default: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "artifact": self.artifact,
            "classification": self.classification.value,
            "reason": self.reason,
            "shared_learning_allowed_by_default": self.shared_learning_allowed_by_default,
        }


_EXPLICIT = {
    "owner_engineering_policy": EngineeringArtifactPolicy(
        "owner_engineering_policy",
        EngineeringArtifactClass.PORTABLE,
        "Owner-approved autonomy limits and qualification preferences are user settings, not build caches.",
        False,
    ),
    "project_instructions": EngineeringArtifactPolicy(
        "project_instructions",
        EngineeringArtifactClass.PORTABLE,
        "Owner/project instructions should follow the project across fresh machines.",
        False,
    ),
    "approved_design_contracts": EngineeringArtifactPolicy(
        "approved_design_contracts",
        EngineeringArtifactClass.PORTABLE,
        "Owner-approved design intent is durable project context.",
        False,
    ),
    "verified_engineering_lessons": EngineeringArtifactPolicy(
        "verified_engineering_lessons",
        EngineeringArtifactClass.PORTABLE,
        "Only verified, non-secret lessons may be promoted into durable intelligence.",
        False,
    ),
    "repository_graph": EngineeringArtifactPolicy(
        "repository_graph",
        EngineeringArtifactClass.REBUILDABLE,
        "The graph is revision-bound and reconstructable from a checkout.",
        False,
    ),
    "dependency_index": EngineeringArtifactPolicy(
        "dependency_index",
        EngineeringArtifactClass.REBUILDABLE,
        "Dependency indexes are caches and must not become identity-critical.",
        False,
    ),
    "worktree": EngineeringArtifactPolicy(
        "worktree",
        EngineeringArtifactClass.REBUILDABLE,
        "Isolated worktrees are execution scratch space tied to a local repository checkout.",
        False,
    ),
    "browser_cache": EngineeringArtifactPolicy(
        "browser_cache",
        EngineeringArtifactClass.REBUILDABLE,
        "Browser cache data is temporary and reproducible.",
        False,
    ),
    "screenshot": EngineeringArtifactPolicy(
        "screenshot",
        EngineeringArtifactClass.SENSITIVE_EVIDENCE,
        "Screenshots may contain private UI/user data and require local-first sanitized retention.",
        False,
    ),
    "dom_snapshot": EngineeringArtifactPolicy(
        "dom_snapshot",
        EngineeringArtifactClass.SENSITIVE_EVIDENCE,
        "DOM snapshots may contain private content and must be treated as qualification evidence.",
        False,
    ),
    "network_payload": EngineeringArtifactPolicy(
        "network_payload",
        EngineeringArtifactClass.SENSITIVE_EVIDENCE,
        "Network payloads can carry private or secret values and are never shared by default.",
        False,
    ),
    "database_fixture": EngineeringArtifactPolicy(
        "database_fixture",
        EngineeringArtifactClass.SENSITIVE_EVIDENCE,
        "Database fixtures may contain owner/project data and require explicit sanitization/retention policy.",
        False,
    ),
}


def classify_engineering_artifact(artifact: str) -> EngineeringArtifactPolicy:
    key = str(artifact or "").strip().casefold().replace(" ", "_")
    if key not in _EXPLICIT:
        return EngineeringArtifactPolicy(
            key or "unknown",
            EngineeringArtifactClass.SENSITIVE_EVIDENCE,
            "Unknown engineering artifacts fail closed as sensitive evidence until explicitly classified.",
            False,
        )
    return _EXPLICIT[key]


def portability_manifest() -> dict[str, list[dict[str, object]]]:
    result = {item.value: [] for item in EngineeringArtifactClass}
    for policy in _EXPLICIT.values():
        result[policy.classification.value].append(policy.to_dict())
    for values in result.values():
        values.sort(key=lambda item: str(item["artifact"]))
    return result
