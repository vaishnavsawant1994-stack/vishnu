from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from future_intelligence.engineering.api_contracts import ApiContractCase, ApiContractQualifier
from future_intelligence.engineering.canary import CanaryMetrics, CanaryThresholds, compare_canary
from future_intelligence.engineering.contracts import EngineeringSpec
from future_intelligence.engineering.database_qualification import SqliteMigrationSandbox
from future_intelligence.engineering.evidence import EngineeringEvidenceLedger
from future_intelligence.engineering.failure_intelligence import EngineeringFailureStore
from future_intelligence.engineering.portability import EngineeringArtifactClass, classify_engineering_artifact, portability_manifest
from future_intelligence.engineering.qualification import EngineeringQualification


def test_sqlite_migration_sandbox_qualifies_clone_without_touching_source(tmp_path: Path):
    source = tmp_path / "source.sqlite3"
    with sqlite3.connect(source) as con:
        con.execute("CREATE TABLE existing(id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
        con.execute("INSERT INTO existing(value) VALUES('owner-data')")
    before = source.read_bytes()

    def migrate(connection):
        connection.execute("CREATE TABLE candidate(id INTEGER PRIMARY KEY, existing_id INTEGER REFERENCES existing(id))")

    result = SqliteMigrationSandbox().qualify(source, migrate=migrate, required_tables=("existing", "candidate"))
    assert result.passed
    assert result.integrity_ok
    assert result.foreign_keys_ok
    assert result.schema_before_hash != result.schema_after_hash
    assert source.read_bytes() == before
    with sqlite3.connect(source) as con:
        assert con.execute("SELECT name FROM sqlite_master WHERE name='candidate'").fetchone() is None


def test_sqlite_migration_sandbox_rejects_symlink_source(tmp_path: Path):
    source = tmp_path / "source.sqlite3"
    with sqlite3.connect(source) as con:
        con.execute("CREATE TABLE existing(id INTEGER PRIMARY KEY)")
    link = tmp_path / "linked.sqlite3"
    try:
        os.symlink(source, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this platform")
    with pytest.raises(ValueError, match="non-symlink"):
        SqliteMigrationSandbox().qualify(link, migrate=lambda _connection: None)


def test_engineering_evidence_ledger_rejects_symlink_root(tmp_path: Path):
    real = tmp_path / "real-evidence"
    real.mkdir()
    link = tmp_path / "linked-evidence"
    try:
        os.symlink(real, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this platform")
    with pytest.raises(PermissionError, match="root cannot be a symlink"):
        EngineeringEvidenceLedger(link, work_order_id="work-1", attempt_id="attempt-1")


def test_api_contract_qualification_fails_closed_for_missing_or_forbidden_keys():
    case = ApiContractCase(
        "owner status",
        "GET",
        "/iphone/api/status",
        expected_statuses=(200,),
        required_json_keys=("ok", "model"),
        forbidden_json_keys=("api_key", "password"),
    )
    good = ApiContractQualifier.qualify(case, status_code=200, json_body={"ok": True, "model": {}})
    bad = ApiContractQualifier.qualify(case, status_code=200, json_body={"ok": True, "api_key": "should-never-appear"})
    assert good.passed
    assert not bad.passed
    assert bad.missing_keys == ("model",)
    assert bad.forbidden_keys_present == ("api_key",)


def test_failure_intelligence_redacts_secrets_requires_regression_test_and_never_suppresses(tmp_path: Path):
    store = EngineeringFailureStore(tmp_path / "failures.sqlite3")
    failure = store.record_failure("integration-test", "Authorization: Bearer secret-token-123456 error at request 123456")
    assert "secret-token" not in failure.normalized_excerpt
    requirement = store.regression_requirement(failure.fingerprint)
    assert requirement["permanent_regression_test_required"] is True
    assert requirement["automatic_gate_suppression"] is False
    for index, passed in enumerate((True, False, True, False), 1):
        store.record_test("tests/test_example.py::test_flow", candidate_revision=f"rev-{index}", passed=passed)
    assessment = store.assess_flaky("tests/test_example.py::test_flow")
    assert assessment.flaky
    assert assessment.pass_count == 2 and assessment.fail_count == 2


def test_canary_can_recommend_but_never_execute_rollback():
    baseline = CanaryMetrics(sample_count=100, error_rate=0.01, p95_latency_ms=100)
    candidate = CanaryMetrics(sample_count=100, error_rate=0.08, p95_latency_ms=180)
    result = compare_canary(baseline, candidate, thresholds=CanaryThresholds())
    assert result.recommended
    assert result.sufficient_evidence
    assert result.automatic_rollback_authority is False
    payload = result.to_dict()
    assert payload["automatic_rollback_authority"] is False


def test_engineering_portability_is_explicit_and_unknown_artifacts_fail_closed():
    assert classify_engineering_artifact("owner_engineering_policy").classification is EngineeringArtifactClass.PORTABLE
    assert classify_engineering_artifact("repository_graph").classification is EngineeringArtifactClass.REBUILDABLE
    assert classify_engineering_artifact("screenshot").classification is EngineeringArtifactClass.SENSITIVE_EVIDENCE
    assert classify_engineering_artifact("new-unclassified-thing").classification is EngineeringArtifactClass.SENSITIVE_EVIDENCE
    manifest = portability_manifest()
    assert manifest["portable"] and manifest["rebuildable"] and manifest["sensitive_evidence"]
    assert all(item["shared_learning_allowed_by_default"] is False for values in manifest.values() for item in values)


def test_owner_policy_metadata_creates_extended_pending_qualification_gates_for_ui_work():
    spec = EngineeringSpec(
        id="eng-extended",
        work_order_id="work-extended",
        attempt_id="attempt-extended",
        repository="owner/repo",
        base_revision="a" * 40,
        objective="qualify extended surfaces",
        allowed_paths=("src/",),
        ui_required=True,
        visual_review_required=True,
        metadata={
            "performance_required": True,
            "localization_required": True,
            "three_d_required": True,
            "physical_device_required": True,
            "preview_enabled": True,
        },
    )
    qualification = EngineeringQualification()
    required = qualification.required_gates(spec)
    for gate in ("performance", "localization", "three_d", "physical_device", "preview", "visual"):
        assert gate in required
    report = qualification.report(spec=spec, candidate_revision="b" * 40, observations=())
    assert not report.qualified
    statuses = {gate.gate: gate.status.value for gate in report.gates}
    assert all(statuses[gate] == "pending" for gate in ("performance", "localization", "three_d", "physical_device", "preview", "visual"))


def test_backend_work_does_not_require_ui_only_owner_gates():
    spec = EngineeringSpec(
        id="eng-backend",
        work_order_id="work-backend",
        attempt_id="attempt-backend",
        repository="owner/repo",
        base_revision="a" * 40,
        objective="qualify backend change",
        allowed_paths=("server/",),
        visual_review_required=True,
        metadata={
            "performance_required": True,
            "localization_required": True,
            "three_d_required": True,
            "physical_device_required": True,
            "preview_enabled": True,
        },
    )
    required = EngineeringQualification().required_gates(spec)
    assert "performance" in required
    assert "preview" in required
    assert "visual" in required
    assert "localization" not in required
    assert "three_d" not in required
    assert "physical_device" not in required
