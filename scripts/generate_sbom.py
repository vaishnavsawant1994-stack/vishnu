from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PYTHON_LOCKS = {
    'python-runtime.cdx.json': ROOT / 'requirements.lock',
    'python-ml.cdx.json': ROOT / 'requirements-ml.lock',
    'python-training.cdx.json': ROOT / 'requirements-training.lock',
}
NODE_LOCK = ROOT / 'package-lock.json'


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as file:
        for block in iter(lambda: file.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def build_manifest(
    *,
    output_dir: Path,
    source_sha: str,
    workflow: str,
    workflow_ref: str,
    run_id: str,
    run_attempt: str,
    generators: dict[str, str],
    input_paths: dict[str, Path],
    vulnerability_findings: dict[str, int],
) -> dict[str, Any]:
    outputs = sorted(path for path in output_dir.glob('*.cdx.json') if path.is_file())
    if not outputs:
        raise ValueError('No CycloneDX SBOM outputs were generated')
    for output in outputs:
        document = json.loads(output.read_text(encoding='utf-8'))
        if document.get('bomFormat') != 'CycloneDX':
            raise ValueError(f'{output.name} is not a CycloneDX document')
    return {
        'schema_version': 1,
        'source_sha': source_sha,
        'workflow': workflow,
        'workflow_ref': workflow_ref,
        'run_id': run_id,
        'run_attempt': run_attempt,
        'generators': generators,
        'inputs': {name: sha256(path) for name, path in sorted(input_paths.items())},
        'outputs': {path.name: sha256(path) for path in outputs},
        'vulnerability_findings': dict(sorted(vulnerability_findings.items())),
    }


def generate(output_dir: Path) -> Path:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    vulnerability_findings: dict[str, int] = {}
    for name, lock in PYTHON_LOCKS.items():
        output = output_dir / name
        result = subprocess.run(
            ['pip-audit', '--requirement', str(lock), '--format', 'cyclonedx-json', '--output', str(output)],
            cwd=ROOT,
            check=False,
        )
        if not output.is_file():
            raise RuntimeError(f'pip-audit did not produce {name}')
        document = json.loads(output.read_text(encoding='utf-8'))
        if document.get('bomFormat') != 'CycloneDX':
            raise ValueError(f'{name} is not a CycloneDX document')
        finding_count = len(document.get('vulnerabilities', []))
        if result.returncode and not finding_count:
            raise subprocess.CalledProcessError(result.returncode, result.args)
        if finding_count:
            vulnerability_findings[name] = finding_count

    node_output = output_dir / 'nodejs.cdx.json'
    with node_output.open('w', encoding='utf-8', newline='\n') as file:
        subprocess.run(
            ['npm', 'sbom', '--sbom-format=cyclonedx', '--package-lock-only', '--sbom-type=application'],
            cwd=ROOT,
            check=True,
            stdout=file,
        )

    generators = {
        'pip-audit': subprocess.run(['pip-audit', '--version'], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip(),
        'npm': subprocess.run(['npm', '--version'], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip(),
        'python': sys.version.split()[0],
    }
    inputs = {path.name: path for path in (*PYTHON_LOCKS.values(), NODE_LOCK)}
    manifest = build_manifest(
        output_dir=output_dir,
        source_sha=os.environ.get('GITHUB_SHA', 'local'),
        workflow=os.environ.get('GITHUB_WORKFLOW', 'local'),
        workflow_ref=os.environ.get('GITHUB_WORKFLOW_REF', 'local'),
        run_id=os.environ.get('GITHUB_RUN_ID', 'local'),
        run_attempt=os.environ.get('GITHUB_RUN_ATTEMPT', 'local'),
        generators=generators,
        input_paths=inputs,
        vulnerability_findings=vulnerability_findings,
    )
    manifest_path = output_dir / 'manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return manifest_path


def main() -> int:
    parser = argparse.ArgumentParser(description='Generate dependency SBOMs and source/checksum evidence.')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'dist' / 'sbom')
    args = parser.parse_args()
    generate(args.output_dir)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
