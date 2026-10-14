from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.generate_sbom import build_manifest


def test_manifest_binds_sboms_to_source_locks_and_audit_findings(tmp_path: Path) -> None:
    lock = tmp_path / 'requirements.lock'
    lock.write_text('example==1.2.3\n', encoding='utf-8')
    sbom = tmp_path / 'python-runtime.cdx.json'
    sbom.write_text(json.dumps({'bomFormat': 'CycloneDX', 'components': []}), encoding='utf-8')

    manifest = build_manifest(
        output_dir=tmp_path,
        source_sha='abc123',
        workflow='SBOM Evidence',
        workflow_ref='owner/repo/.github/workflows/sbom-evidence.yml@refs/heads/main',
        run_id='42',
        run_attempt='2',
        generators={'pip-audit': 'pip-audit 2.10.1'},
        input_paths={'requirements.lock': lock},
        vulnerability_findings={'python-ml.cdx.json': 11},
    )

    assert manifest['source_sha'] == 'abc123'
    assert manifest['workflow_ref'].endswith('@refs/heads/main')
    assert manifest['run_id'] == '42'
    assert manifest['run_attempt'] == '2'
    assert manifest['inputs']['requirements.lock']
    assert manifest['outputs']['python-runtime.cdx.json']
    assert manifest['vulnerability_findings']['python-ml.cdx.json'] == 11


def test_manifest_rejects_non_cyclonedx_output(tmp_path: Path) -> None:
    output = tmp_path / 'invalid.cdx.json'
    output.write_text('{"format":"other"}', encoding='utf-8')
    with pytest.raises(ValueError, match='not a CycloneDX'):
        build_manifest(
            output_dir=tmp_path,
            source_sha='abc123',
            workflow='test',
            workflow_ref='test',
            run_id='1',
            run_attempt='1',
            generators={},
            input_paths={},
            vulnerability_findings={},
        )
