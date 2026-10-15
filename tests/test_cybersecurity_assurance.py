from __future__ import annotations

import copy
import json
from datetime import date
from pathlib import Path

from security import assurance


REPO_ROOT = Path(__file__).resolve().parents[1]
GOOD_SHA = "a" * 40


def _json(path: str) -> dict:
    return json.loads((REPO_ROOT / path).read_text(encoding="utf-8"))


def test_baseline_assurance_passes_for_exact_sha() -> None:
    result = assurance.evaluate(REPO_ROOT, GOOD_SHA, head_sha=GOOD_SHA, today=date(2026, 10, 15))
    assert result.passed, result.errors
    assert result.controls == 22
    assert result.adversarial_cases == 20


def test_candidate_must_match_exact_head() -> None:
    result = assurance.evaluate(REPO_ROOT, GOOD_SHA, head_sha="b" * 40)
    assert not result.passed
    assert any("does not match checked-out HEAD" in error for error in result.errors)


def test_candidate_must_be_full_sha() -> None:
    result = assurance.evaluate(REPO_ROOT, "abc123", head_sha=GOOD_SHA)
    assert not result.passed
    assert any("candidate SHA must be exactly 40" in error for error in result.errors)


def test_control_catalog_rejects_missing_domain() -> None:
    document = copy.deepcopy(_json("security/assurance_controls.json"))
    missing = "Red Teaming"
    document["domains"].remove(missing)
    document["controls"] = [item for item in document["controls"] if item["domain"] != missing]
    errors, _ = assurance._validate_controls(REPO_ROOT, document)
    assert errors
    assert any("domain baseline" in error or "missing required control domains" in error for error in errors)


def test_control_catalog_rejects_duplicate_ids() -> None:
    document = copy.deepcopy(_json("security/assurance_controls.json"))
    document["controls"][1]["id"] = document["controls"][0]["id"]
    errors, _ = assurance._validate_controls(REPO_ROOT, document)
    assert any("duplicate control id" in error for error in errors)


def test_control_catalog_rejects_missing_evidence() -> None:
    document = copy.deepcopy(_json("security/assurance_controls.json"))
    document["controls"][0]["evidence_paths"] = ["does/not/exist.security-evidence"]
    errors, _ = assurance._validate_controls(REPO_ROOT, document)
    assert any("missing evidence path" in error for error in errors)


def test_adversarial_corpus_requires_every_attack_category() -> None:
    document = copy.deepcopy(_json("security/adversarial_cases.json"))
    document["cases"] = [
        case for case in document["cases"] if case["category"] != "indirect_prompt_injection"
    ]
    errors, _ = assurance._validate_adversarial(document)
    assert any("missing adversarial categories" in error for error in errors)


def test_adversarial_corpus_must_remain_internal_scope() -> None:
    document = copy.deepcopy(_json("security/adversarial_cases.json"))
    document["scope"] = "independent-third-party"
    errors, _ = assurance._validate_adversarial(document)
    assert any("authorized internal simulation" in error for error in errors)


def test_unresolved_high_blocks_even_with_acceptance() -> None:
    document = {
        "schema": assurance.FINDINGS_SCHEMA,
        "findings": [
            {
                "id": "SEC-001",
                "severity": "High",
                "status": "open",
                "risk_acceptance": {
                    "owner_approved": True,
                    "rationale": "Temporary",
                    "expires": "2099-01-01",
                },
            }
        ],
    }
    errors, _ = assurance._validate_findings(document, today=date(2026, 10, 15))
    assert any("unresolved High" in error for error in errors)


def test_medium_requires_owner_approved_future_acceptance() -> None:
    document = {
        "schema": assurance.FINDINGS_SCHEMA,
        "findings": [{"id": "SEC-002", "severity": "Medium", "status": "open"}],
    }
    errors, _ = assurance._validate_findings(document, today=date(2026, 10, 15))
    assert any("without valid owner-approved" in error for error in errors)


def test_medium_can_have_bounded_owner_acceptance() -> None:
    document = {
        "schema": assurance.FINDINGS_SCHEMA,
        "findings": [
            {
                "id": "SEC-003",
                "severity": "Medium",
                "status": "open",
                "risk_acceptance": {
                    "owner_approved": True,
                    "rationale": "Bounded remediation window",
                    "expires": "2026-10-31",
                },
            }
        ],
    }
    errors, _ = assurance._validate_findings(document, today=date(2026, 10, 15))
    assert errors == []


def test_expired_acceptance_blocks() -> None:
    document = {
        "schema": assurance.FINDINGS_SCHEMA,
        "findings": [
            {
                "id": "SEC-004",
                "severity": "Low",
                "status": "open",
                "risk_acceptance": {
                    "owner_approved": True,
                    "rationale": "Expired",
                    "expires": "2026-10-14",
                },
            }
        ],
    }
    errors, _ = assurance._validate_findings(document, today=date(2026, 10, 15))
    assert errors


def test_resolved_high_does_not_block() -> None:
    document = {
        "schema": assurance.FINDINGS_SCHEMA,
        "findings": [{"id": "SEC-005", "severity": "High", "status": "resolved"}],
    }
    errors, _ = assurance._validate_findings(document, today=date(2026, 10, 15))
    assert errors == []


def test_report_cannot_claim_independent_assessment(tmp_path: Path) -> None:
    result = assurance.AssuranceResult(
        candidate_sha=GOOD_SHA,
        head_sha=GOOD_SHA,
        controls=22,
        adversarial_cases=20,
        findings=0,
        errors=(),
    )
    assurance.write_report(result, tmp_path)
    payload = json.loads((tmp_path / "cybersecurity-assurance.json").read_text(encoding="utf-8"))
    assert payload["result"] == "PASS"
    assert payload["independent_third_party_assessment"] is False
    assert payload["candidate_sha"] == GOOD_SHA
