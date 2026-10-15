from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PYTHON_LOCKS = {
    'python-runtime.cdx.json': ROOT / 'requirements.lock',
    'python-ml.cdx.json': ROOT / 'requirements-ml.lock',
    'python-training.cdx.json': ROOT / 'requirements-training.lock',
    'python-tools.cdx.json': ROOT / 'requirements-tools.lock',
}
NODE_LOCK = ROOT / 'package-lock.json'
REA_ROOT = ROOT / '.rea'
REA_NODE_LOCK = REA_ROOT / 'package-lock.json'
REA_PACKAGE_JSON = REA_ROOT / 'package.json'


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


def _generate_node_sbom(package_root: Path, output: Path) -> None:
    with output.open('w', encoding='utf-8', newline='\n') as file:
        subprocess.run(
            ['npm', 'sbom', '--sbom-format=cyclonedx', '--package-lock-only', '--sbom-type=application'],
            cwd=package_root,
            check=True,
            stdout=file,
        )


def _generate_rea_node_sbom(output: Path) -> None:
    """Generate REA's lockfile SBOM without using `.rea` as npm's package cwd.

    npm derives package identity from the working package directory in some
    versions and rejects hidden-directory names such as `.rea` as invalid npm
    package names. REA remains installed at `.rea`; only immutable package
    metadata is staged into a valid temporary package directory for the SBOM
    command. `--package-lock-only` means no node_modules tree is required.
    """
    if not REA_PACKAGE_JSON.is_file() or not REA_NODE_LOCK.is_file():
        raise RuntimeError('REA package metadata is missing; install the pinned REA runtime before generating its SBOM')
    with tempfile.TemporaryDirectory(prefix='vishnu-rea-sbom-') as temporary:
        staged = Path(temporary) / 'rea-runtime'
        staged.mkdir()
        shutil.copy2(REA_PACKAGE_JSON, staged / 'package.json')
        shutil.copy2(REA_NODE_LOCK, staged / 'package-lock.json')
        _generate_node_sbom(staged, output)


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

    _generate_node_sbom(ROOT, output_dir / 'nodejs.cdx.json')

    input_paths: dict[str, Path] = {path.name: path for path in PYTHON_LOCKS.values()}
    input_paths['package-lock.json'] = NODE_LOCK
    if REA_NODE_LOCK.is_file():
        _generate_rea_node_sbom(output_dir / 'rea-nodejs.cdx.json')
        input_paths['rea-package-lock.json'] = REA_NODE_LOCK

    generators = {
        'pip-audit': subprocess.run(['pip-audit', '--version'], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip(),
        'npm': subprocess.run(['npm', '--version'], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip(),
        'python': sys.version.split()[0],
    }
    manifest = build_manifest(
        output_dir=output_dir,
        source_sha=os.environ.get('GITHUB_SHA', 'local'),
        workflow=os.environ.get('GITHUB_WORKFLOW', 'local'),
        workflow_ref=os.environ.get('GITHUB_WORKFLOW_REF', 'local'),
        run_id=os.environ.get('GITHUB_RUN_ID', 'local'),
        run_attempt=os.environ.get('GITHUB_RUN_ATTEMPT', 'local'),
        generators=generators,
        input_paths=input_paths,
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
