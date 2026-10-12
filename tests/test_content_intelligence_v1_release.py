from __future__ import annotations

from pathlib import Path

import pytest

from file_intelligence import ContentWorker, Stage18ContentWorker, Stage18ProductionMultimodalRuntime
from qualification.content_intelligence_v1 import (
    CONTENT_INTELLIGENCE_V1_REQUIRED_GATES,
    ContentIntelligenceV1ReleaseQualifier,
)
from training.content_models import ContentModelTask
from training.stage18_real_world_evidence import Stage18RealWorldEvidenceStore


def _all_gates() -> dict[str, bool]:
    return {name: True for name in CONTENT_INTELLIGENCE_V1_REQUIRED_GATES}


class _NoEvidence:
    def latest_qualified(self):
        return None


class _PersistedQualifiedEvidence:
    def latest_qualified(self):
        return {
            "qualified": True,
            "real_world_corpus_qualified": True,
            "synthetic_evidence_can_qualify": False,
            "evidence_persisted": True,
            "records": 80,
            "source_groups": 8,
        }


def test_stage18_is_canonical_worker_and_has_separate_model_lane():
    assert ContentWorker is Stage18ContentWorker
    assert Stage18ProductionMultimodalRuntime is not None
    assert ContentModelTask.MULTIMODAL_VISUAL.value == "multimodal_visual"
    assert ContentModelTask.MULTIMODAL_VISUAL is not ContentModelTask.DOCUMENT_CLASSIFICATION


def test_release_authority_closes_internal_work_but_refuses_fake_real_world_claim():
    report = ContentIntelligenceV1ReleaseQualifier().qualify(_all_gates(), real_world_authority=_NoEvidence())
    assert report.implementation_qualified is True
    assert report.production_hardening_qualified is True
    assert report.real_world_corpus_qualified is False
    assert report.v1_release_ready is False
    assert report.status == "qualified_pending_real_world"
    assert report.blockers == ("genuine_real_world_corpus_evidence_required",)
    assert report.stage_floor == 0
    assert report.stage_ceiling == 18
    assert report.foundation_model is False
    assert report.synthetic_evidence_can_qualify is False
    assert len(report.evidence_sha256) == 64


def test_missing_release_gate_fails_closed_even_if_real_world_authority_exists():
    gates = _all_gates()
    gates["projects_scope_isolation"] = False
    report = ContentIntelligenceV1ReleaseQualifier().qualify(gates, real_world_authority=_PersistedQualifiedEvidence())
    assert report.real_world_corpus_qualified is True
    assert report.v1_release_ready is False
    assert report.status == "not_release_qualified"
    assert "projects_scope_isolation" in report.missing_gates
    assert "missing_gate:projects_scope_isolation" in report.blockers


def test_persisted_governed_real_world_authority_is_required_for_v1_ready():
    report = ContentIntelligenceV1ReleaseQualifier().qualify(
        _all_gates(), real_world_authority=_PersistedQualifiedEvidence()
    )
    assert report.status == "v1_release_qualified"
    assert report.v1_release_ready is True
    assert report.real_world_corpus_qualified is True
    assert report.blockers == ()


def test_stage18_evidence_store_rejects_synthetic_qualification_claim(tmp_path: Path):
    store = Stage18RealWorldEvidenceStore(tmp_path / "evidence.sqlite3")
    with pytest.raises(ValueError, match="explicitly forbid synthetic qualification"):
        store.record(
            {
                "qualified": True,
                "real_world_corpus_qualified": True,
                "synthetic_evidence_can_qualify": True,
                "evidence_sha256": "a" * 64,
                "created_at": "2026-10-12T00:00:00Z",
                "records": 100,
                "source_groups": 8,
            }
        )


def test_stage18_evidence_store_is_immutable_for_same_digest(tmp_path: Path):
    store = Stage18RealWorldEvidenceStore(tmp_path / "evidence.sqlite3")
    first = {
        "qualified": False,
        "real_world_corpus_qualified": False,
        "synthetic_evidence_can_qualify": False,
        "evidence_sha256": "b" * 64,
        "created_at": "2026-10-12T00:00:00Z",
        "records": 12,
        "source_groups": 4,
    }
    store.record(first)
    changed = {**first, "records": 13}
    with pytest.raises(RuntimeError, match="immutable Stage 18 evidence digest collision"):
        store.record(changed)


def test_release_evidence_digest_is_deterministic():
    qualifier = ContentIntelligenceV1ReleaseQualifier()
    one = qualifier.qualify(_all_gates(), real_world_authority=_NoEvidence())
    two = qualifier.qualify(dict(reversed(list(_all_gates().items()))), real_world_authority=_NoEvidence())
    assert one.evidence_sha256 == two.evidence_sha256
