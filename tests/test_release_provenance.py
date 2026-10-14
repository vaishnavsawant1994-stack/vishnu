from __future__ import annotations

import json
from pathlib import Path

import pytest

from updates.build_reproducibility_evidence import build_evidence, validate_evidence
from updates.release_sign import build_manifest
from updates.release_verify import validate_manifest


LOCKS = (
    'requirements-bootstrap.lock',
    'requirements.lock',
    'requirements-tools.lock',
    'requirements-ml.lock',
    'requirements-training.lock',
    'package-lock.json',
)


def _lockfiles(root: Path) -> None:
    for name in LOCKS:
        (root / name).write_text(name + '\n', encoding='utf-8')


def test_evidence_binds_packages_locks_sbom_and_qualification(tmp_path: Path, monkeypatch) -> None:
    _lockfiles(tmp_path)
    artifact_dir = tmp_path / 'artifacts'
    artifact_dir.mkdir()
    (artifact_dir / 'Vishnu-v1-linux-x64.deb').write_bytes(b'installer')
    sbom_dir = tmp_path / 'sbom'
    sbom_dir.mkdir()
    (sbom_dir / 'manifest.json').write_text(json.dumps({'source_sha': 'a' * 40}), encoding='utf-8')
    (sbom_dir / 'python-runtime.cdx.json').write_text('{"bomFormat":"CycloneDX"}', encoding='utf-8')
    monkeypatch.setattr('updates.build_reproducibility_evidence.ROOT', tmp_path)
    evidence = build_evidence(
        source_sha='a' * 40,
        artifact_dir=artifact_dir,
        sbom_dir=sbom_dir,
        qualification_results={'package': {'result': 'success'}},
        workflow='Package Validation',
        workflow_ref='owner/repo/.github/workflows/package.yml@refs/heads/main',
        run_id='42',
        run_attempt='1',
    )
    assert evidence['lockfiles']['requirements.lock']
    assert evidence['sbom_files']['python-runtime.cdx.json']
    assert evidence['qualification_results'] == {'package': 'success'}
    assert evidence['artifacts'][0]['sha256']


def test_evidence_rejects_failed_qualification(tmp_path: Path, monkeypatch) -> None:
    _lockfiles(tmp_path)
    artifacts = tmp_path / 'artifacts'
    artifacts.mkdir()
    (artifacts / 'app.deb').write_bytes(b'pkg')
    sbom = tmp_path / 'sbom'
    sbom.mkdir()
    (sbom / 'manifest.json').write_text('{}', encoding='utf-8')
    monkeypatch.setattr('updates.build_reproducibility_evidence.ROOT', tmp_path)
    with pytest.raises(ValueError, match='qualification'):
        build_evidence(
            source_sha='a' * 40,
            artifact_dir=artifacts,
            sbom_dir=sbom,
            qualification_results={'package': {'result': 'failure'}},
            workflow='test',
            workflow_ref='test',
            run_id='1',
            run_attempt='1',
        )


def test_signed_release_manifest_validates_provenance_against_assets(tmp_path: Path) -> None:
    package = tmp_path / 'Vishnu-v1-linux-x64.deb'
    package.write_bytes(b'installer')
    provenance = {
        'schema': 1,
        'source_sha': 'e' * 40,
        'workflow': 'Signed Release',
        'workflow_ref': 'release.yml@refs/tags/v1',
        'run_id': '7',
        'run_attempt': '1',
        'lockfiles': {name: 'a' * 64 for name in LOCKS},
        'sbom_files': {'manifest.json': 'b' * 64},
        'qualification_results': {'linux': 'success'},
        'artifacts': [{'name': package.name, 'sha256': 'd' * 64, 'size': package.stat().st_size}],
    }
    with pytest.raises(ValueError, match='package identities'):
        manifest = build_manifest(
            version='v1',
            source_commit='e' * 40,
            channel='stable',
            artifacts=[package],
            provenance=provenance,
        )
        validate_manifest(manifest)
