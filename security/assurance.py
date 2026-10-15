"""Exact-revision cybersecurity assurance gate for Vishnu.

This module validates the assurance program's machine-readable control catalog,
adversarial corpus, findings lifecycle, mandatory evidence paths, and candidate
revision. It is deliberately an evidence/release-qualification layer: it does
not own permissions, approvals, identity, tool execution, or deployment.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

SCHEMA = "vishnu.cybersecurity-assurance/v1"
FINDINGS_SCHEMA = "vishnu.cybersecurity-findings/v1"
ADVERSARIAL_SCHEMA = "vishnu.cybersecurity-adversarial-corpus/v1"

REQUIRED_DOMAINS = (
    "Application Security",
    "API Security",
    "AI/Agent Security",
    "Device Security",
    "Cloud/Infrastructure Security",
    "Supply Chain",
    "Identity & Access",
    "Data Protection",
    "Penetration Testing",
    "Red Teaming",
    "Recovery Testing",
)

REQUIRED_ADVERSARIAL_CATEGORIES = frozenset(
    {
        "direct_prompt_injection",
        "indirect_prompt_injection",
        "tool_result_poisoning",
        "policy_override",
        "secret_exfiltration",
        "unauthorized_tool_execution",
        "approval_bypass",
        "confused_deputy",
        "memory_poisoning",
        "cross_user_data_leakage",
        "malicious_content",
        "ssrf",
        "path_traversal",
        "injection",
        "replay",
        "rate_limit",
        "credential_theft",
        "audit_tampering",
        "backup_recovery",
        "key_rotation",
    }
)

SEVERITIES = frozenset({"Critical", "High", "Medium", "Low"})
RESOLVED_STATUSES = frozenset({"resolved", "closed", "fixed"})
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class AssuranceResult:
    candidate_sha: str
    head_sha: str
    controls: int
    adversarial_cases: int
    findings: int
    errors: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.errors


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"unable to load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _git_head(repo_root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip().lower()


def _safe_evidence_path(repo_root: Path, raw: str) -> Path | None:
    relative = Path(raw)
    if relative.is_absolute() or ".." in relative.parts:
        return None
    resolved = (repo_root / relative).resolve()
    try:
        resolved.relative_to(repo_root.resolve())
    except ValueError:
        return None
    return resolved


def _validate_controls(repo_root: Path, document: dict[str, Any]) -> tuple[list[str], int]:
    errors: list[str] = []
    if document.get("schema") != SCHEMA:
        errors.append(f"control catalog schema must be {SCHEMA}")

    declared_domains = document.get("domains")
    if declared_domains != list(REQUIRED_DOMAINS):
        errors.append("control catalog must declare the complete ordered domain baseline")

    controls = document.get("controls")
    if not isinstance(controls, list) or not controls:
        return errors + ["control catalog must contain controls"], 0

    seen_ids: set[str] = set()
    represented_domains: set[str] = set()
    for index, control in enumerate(controls):
        prefix = f"control[{index}]"
        if not isinstance(control, dict):
            errors.append(f"{prefix} must be an object")
            continue
        control_id = control.get("id")
        if not isinstance(control_id, str) or not control_id.strip():
            errors.append(f"{prefix} requires a non-empty id")
        elif control_id in seen_ids:
            errors.append(f"duplicate control id: {control_id}")
        else:
            seen_ids.add(control_id)

        domain = control.get("domain")
        if domain not in REQUIRED_DOMAINS:
            errors.append(f"{prefix} uses an unknown domain: {domain!r}")
        else:
            represented_domains.add(domain)

        if control.get("required") is not True:
            errors.append(f"{prefix} must remain required in v1")

        for field in ("title", "objective", "verification"):
            if not isinstance(control.get(field), str) or not control[field].strip():
                errors.append(f"{prefix} requires {field}")

        evidence_paths = control.get("evidence_paths")
        if not isinstance(evidence_paths, list) or not evidence_paths:
            errors.append(f"{prefix} requires at least one evidence path")
            continue
        for raw_path in evidence_paths:
            if not isinstance(raw_path, str) or not raw_path:
                errors.append(f"{prefix} has an invalid evidence path")
                continue
            path = _safe_evidence_path(repo_root, raw_path)
            if path is None:
                errors.append(f"{prefix} evidence path escapes repository: {raw_path}")
            elif not path.is_file():
                errors.append(f"{prefix} missing evidence path: {raw_path}")

    missing_domains = set(REQUIRED_DOMAINS) - represented_domains
    if missing_domains:
        errors.append("missing required control domains: " + ", ".join(sorted(missing_domains)))
    return errors, len(controls)


def _validate_adversarial(document: dict[str, Any]) -> tuple[list[str], int]:
    errors: list[str] = []
    if document.get("schema") != ADVERSARIAL_SCHEMA:
        errors.append(f"adversarial corpus schema must be {ADVERSARIAL_SCHEMA}")
    if document.get("scope") != "authorized-internal-simulation":
        errors.append("adversarial corpus must be explicitly scoped to authorized internal simulation")

    cases = document.get("cases")
    if not isinstance(cases, list) or not cases:
        return errors + ["adversarial corpus must contain cases"], 0

    seen_ids: set[str] = set()
    categories: set[str] = set()
    for index, case in enumerate(cases):
        prefix = f"adversarial_case[{index}]"
        if not isinstance(case, dict):
            errors.append(f"{prefix} must be an object")
            continue
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id.strip():
            errors.append(f"{prefix} requires an id")
        elif case_id in seen_ids:
            errors.append(f"duplicate adversarial case id: {case_id}")
        else:
            seen_ids.add(case_id)

        category = case.get("category")
        if not isinstance(category, str) or not category:
            errors.append(f"{prefix} requires a category")
        else:
            categories.add(category)

        if case.get("domain") not in REQUIRED_DOMAINS:
            errors.append(f"{prefix} has an unknown domain")
        for field in ("scenario", "expected_defense"):
            if not isinstance(case.get(field), str) or not case[field].strip():
                errors.append(f"{prefix} requires {field}")

    missing = REQUIRED_ADVERSARIAL_CATEGORIES - categories
    if missing:
        errors.append("missing adversarial categories: " + ", ".join(sorted(missing)))
    return errors, len(cases)


def _valid_acceptance(finding: dict[str, Any], today: date) -> bool:
    acceptance = finding.get("risk_acceptance")
    if not isinstance(acceptance, dict):
        return False
    if acceptance.get("owner_approved") is not True:
        return False
    rationale = acceptance.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        return False
    expires = acceptance.get("expires")
    if not isinstance(expires, str):
        return False
    try:
        expiry = date.fromisoformat(expires)
    except ValueError:
        return False
    return expiry > today


def _validate_findings(
    document: dict[str, Any],
    *,
    today: date,
) -> tuple[list[str], int]:
    errors: list[str] = []
    if document.get("schema") != FINDINGS_SCHEMA:
        errors.append(f"findings schema must be {FINDINGS_SCHEMA}")

    findings = document.get("findings")
    if not isinstance(findings, list):
        return errors + ["findings must be a list"], 0

    seen_ids: set[str] = set()
    for index, finding in enumerate(findings):
        prefix = f"finding[{index}]"
        if not isinstance(finding, dict):
            errors.append(f"{prefix} must be an object")
            continue
        finding_id = finding.get("id")
        if not isinstance(finding_id, str) or not finding_id.strip():
            errors.append(f"{prefix} requires an id")
            continue
        if finding_id in seen_ids:
            errors.append(f"duplicate finding id: {finding_id}")
            continue
        seen_ids.add(finding_id)

        severity = finding.get("severity")
        if severity not in SEVERITIES:
            errors.append(f"{finding_id} has invalid severity: {severity!r}")
            continue
        status = finding.get("status")
        if not isinstance(status, str) or not status:
            errors.append(f"{finding_id} requires status")
            continue
        if status.lower() in RESOLVED_STATUSES:
            continue

        if severity in {"Critical", "High"}:
            errors.append(f"{finding_id} is unresolved {severity} and blocks qualification")
            continue
        if not _valid_acceptance(finding, today):
            errors.append(
                f"{finding_id} is unresolved {severity} without valid owner-approved "
                "future-dated risk acceptance"
            )
    return errors, len(findings)


def evaluate(
    repo_root: Path,
    candidate_sha: str,
    *,
    today: date | None = None,
    head_sha: str | None = None,
) -> AssuranceResult:
    """Evaluate the exact revision and machine-readable assurance baseline."""
    root = repo_root.resolve()
    candidate = candidate_sha.strip().lower()
    actual_head = (head_sha or _git_head(root)).strip().lower()
    errors: list[str] = []

    if not SHA_RE.fullmatch(candidate):
        errors.append("candidate SHA must be exactly 40 lowercase hexadecimal characters")
    if not SHA_RE.fullmatch(actual_head):
        errors.append("checked-out HEAD is not a full 40-character Git SHA")
    if candidate != actual_head:
        errors.append(f"candidate SHA {candidate} does not match checked-out HEAD {actual_head}")

    try:
        controls_doc = _load_json(root / "security" / "assurance_controls.json")
        control_errors, control_count = _validate_controls(root, controls_doc)
        errors.extend(control_errors)
    except ValueError as exc:
        errors.append(str(exc))
        control_count = 0

    try:
        adversarial_doc = _load_json(root / "security" / "adversarial_cases.json")
        adversarial_errors, adversarial_count = _validate_adversarial(adversarial_doc)
        errors.extend(adversarial_errors)
    except ValueError as exc:
        errors.append(str(exc))
        adversarial_count = 0

    try:
        findings_doc = _load_json(root / "security" / "findings.json")
        findings_errors, finding_count = _validate_findings(
            findings_doc,
            today=today or datetime.now(UTC).date(),
        )
        errors.extend(findings_errors)
    except ValueError as exc:
        errors.append(str(exc))
        finding_count = 0

    return AssuranceResult(
        candidate_sha=candidate,
        head_sha=actual_head,
        controls=control_count,
        adversarial_cases=adversarial_count,
        findings=finding_count,
        errors=tuple(errors),
    )


def write_report(result: AssuranceResult, output_dir: Path) -> None:
    """Write JSON and Markdown evidence for one exact evaluated revision."""
    output_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(UTC).isoformat()
    payload = {
        "schema": "vishnu.cybersecurity-assurance-report/v1",
        "scope": "internal-cybersecurity-assurance",
        "independent_third_party_assessment": False,
        "candidate_sha": result.candidate_sha,
        "checked_out_head_sha": result.head_sha,
        "generated_at": generated_at,
        "result": "PASS" if result.passed else "FAIL",
        "required_domains": list(REQUIRED_DOMAINS),
        "control_count": result.controls,
        "adversarial_case_count": result.adversarial_cases,
        "finding_count": result.findings,
        "errors": list(result.errors),
    }
    (output_dir / "cybersecurity-assurance.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# Vishnu Cybersecurity Assurance Report",
        "",
        f"- Result: **{payload['result']}**",
        f"- Candidate SHA: `{result.candidate_sha}`",
        f"- Checked-out HEAD: `{result.head_sha}`",
        f"- Generated: {generated_at}",
        "- Scope: internal cybersecurity assurance",
        "- Independent third-party assessment: **No**",
        f"- Mandatory domains: {len(REQUIRED_DOMAINS)}",
        f"- Controls validated: {result.controls}",
        f"- Adversarial cases validated: {result.adversarial_cases}",
        f"- Findings registered: {result.findings}",
        "",
    ]
    if result.errors:
        lines.extend(["## Blocking errors", ""])
        lines.extend(f"- {error}" for error in result.errors)
        lines.append("")
    else:
        lines.extend(
            [
                "All repository-defined v1 assurance invariants passed for this exact revision.",
                "This result is not an independent penetration test and does not authorize deployment.",
                "",
            ]
        )
    (output_dir / "cybersecurity-assurance.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/cybersecurity-assurance"))
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = evaluate(args.repo_root, args.candidate_sha)
    output_dir = args.output_dir
    if not output_dir.is_absolute():
        output_dir = args.repo_root / output_dir
    write_report(result, output_dir)
    if result.passed:
        print(f"Cybersecurity assurance PASS for {result.candidate_sha}")
        return 0
    print(f"Cybersecurity assurance FAIL for {result.candidate_sha}")
    for error in result.errors:
        print(f"- {error}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
