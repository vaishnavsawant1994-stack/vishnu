from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
_SHA_RE = re.compile(r'^[0-9a-f]{40}$')
_DIGEST_RE = re.compile(r'^[0-9a-f]{64}$')
LOCK_FILES = (
    'requirements-bootstrap.lock',
    'requirements.lock',
    'requirements-tools.lock',
    'requirements-ml.lock',
    'requirements-training.lock',
    'package-lock.json',
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _qualification_statuses(results: dict[str, Any]) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for name, result in results.items():
        status = result.get('result') if isinstance(result, dict) else result
        if not isinstance(status, str):
            raise ValueError(f'qualification result for {name} is missing')
        statuses[name] = status
    if not statuses or any(status != 'success' for status in statuses.values()):
        raise ValueError('all recorded qualification results must be successful')
    return dict(sorted(statuses.items()))


def validate_evidence(evidence: object, *, expected_source_sha: str | None = None, expected_artifacts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    if not isinstance(evidence, dict) or evidence.get('schema') != 1:
        raise ValueError('reproducibility evidence schema 1 is required')
    source_sha = evidence.get('source_sha')
    if not isinstance(source_sha, str) or not _SHA_RE.fullmatch(source_sha):
        raise ValueError('reproducibility source SHA is invalid')
    if expected_source_sha and source_sha != expected_source_sha.lower():
        raise ValueError('reproducibility source SHA does not match release manifest')
    for field in ('workflow', 'workflow_ref', 'run_id', 'run_attempt'):
        if not isinstance(evidence.get(field), str) or not evidence[field]:
            raise ValueError(f'reproducibility {field} is required')
    for field in ('lockfiles', 'sbom_files'):
        files = evidence.get(field)
        if not isinstance(files, dict) or not files:
            raise ValueError(f'reproducibility {field} must be a non-empty mapping')
        for name, digest in files.items():
            if not isinstance(name, str) or not name or Path(name).name != name:
                raise ValueError(f'invalid {field} identity')
            if not isinstance(digest, str) or not _DIGEST_RE.fullmatch(digest):
                raise ValueError(f'invalid SHA-256 in {field}')
    if not set(LOCK_FILES).issubset(evidence['lockfiles']):
        raise ValueError('reproducibility evidence is missing a dependency lock identity')
    _qualification_statuses(evidence.get('qualification_results', {}))
    artifacts = evidence.get('artifacts')
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError('reproducibility evidence must contain package artifacts')
    seen: set[str] = set()
    for item in artifacts:
        if not isinstance(item, dict):
            raise ValueError('reproducibility package artifact is invalid')
        name, digest, size = item.get('name'), item.get('sha256'), item.get('size')
        if not isinstance(name, str) or not name or Path(name).name != name or name in seen:
            raise ValueError('reproducibility package artifact name is invalid')
        if not isinstance(digest, str) or not _DIGEST_RE.fullmatch(digest):
            raise ValueError(f'invalid package SHA-256 for {name}')
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise ValueError(f'invalid package size for {name}')
        seen.add(name)
    if expected_artifacts is not None:
        actual = {item['name']: (item['sha256'], item['size']) for item in artifacts}
        expected = {item['name']: (item['sha256'], item['size']) for item in expected_artifacts}
        if actual != expected:
            raise ValueError('provenance package identities do not match release manifest artifacts')
    return evidence


def build_evidence(*, source_sha: str, artifact_dir: Path, sbom_dir: Path, qualification_results: dict[str, Any], workflow: str, workflow_ref: str, run_id: str, run_attempt: str) -> dict[str, Any]:
    source_sha = source_sha.strip().lower()
    if not _SHA_RE.fullmatch(source_sha):
        raise ValueError('source SHA must be an exact 40-character Git SHA')
    artifacts = sorted(path for path in artifact_dir.rglob('*') if path.is_file() and path.suffix.lower() in {'.msi', '.dmg', '.deb'})
    if not artifacts:
        raise ValueError('no installer artifacts were found')
    artifact_entries = [{'name': path.name, 'sha256': sha256(path), 'size': path.stat().st_size} for path in artifacts]
    if len({item['name'] for item in artifact_entries}) != len(artifact_entries):
        raise ValueError('installer artifact filenames must be unique')
    lockfiles = {name: sha256(ROOT / name) for name in LOCK_FILES}
    sbom_paths = sorted(path for path in sbom_dir.glob('*.json') if path.is_file())
    if not sbom_paths or not (sbom_dir / 'manifest.json').is_file():
        raise ValueError('SBOM outputs and manifest are required')
    evidence = {
        'schema': 1,
        'source_sha': source_sha,
        'workflow': workflow,
        'workflow_ref': workflow_ref,
        'run_id': run_id,
        'run_attempt': run_attempt,
        'lockfiles': lockfiles,
        'sbom_files': {path.name: sha256(path) for path in sbom_paths},
        'qualification_results': _qualification_statuses(qualification_results),
        'artifacts': sorted(artifact_entries, key=lambda item: item['name']),
    }
    return validate_evidence(evidence, expected_source_sha=source_sha)


def main() -> int:
    parser = argparse.ArgumentParser(description='Bind release installers to source, locks, SBOMs, and qualification.')
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--artifact-dir', type=Path, required=True)
    parser.add_argument('--sbom-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    results = json.loads(os.environ.get('QUALIFICATION_RESULTS_JSON', '{}'))
    evidence = build_evidence(
        source_sha=args.source_sha,
        artifact_dir=args.artifact_dir.resolve(),
        sbom_dir=args.sbom_dir.resolve(),
        qualification_results=results,
        workflow=os.environ.get('GITHUB_WORKFLOW', ''),
        workflow_ref=os.environ.get('GITHUB_WORKFLOW_REF', ''),
        run_id=os.environ.get('GITHUB_RUN_ID', ''),
        run_attempt=os.environ.get('GITHUB_RUN_ATTEMPT', ''),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
