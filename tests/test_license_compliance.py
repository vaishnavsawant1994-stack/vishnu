from __future__ import annotations

import json
from pathlib import Path

from scripts.license_compliance import build_report, classify_license, direct_requirements


POLICY = {
    'schema_version': 1,
    'allow_spdx_ids': ['Apache-2.0', 'BSD-3-Clause', 'MIT'],
    'deny_spdx_ids': ['AGPL-3.0-only'],
    'default_decision': 'review',
    'review_note': 'Review unknown license metadata.',
}


def test_license_policy_allows_denies_and_escalates_unknowns() -> None:
    assert classify_license('MIT', POLICY)[0] == 'allow'
    assert classify_license('MIT OR Apache-2.0', POLICY)[0] == 'allow'
    assert classify_license('AGPL-3.0-only', POLICY)[0] == 'deny'
    assert classify_license('Custom License', POLICY)[0] == 'review'
    assert classify_license('NOASSERTION', POLICY)[0] == 'review'


def test_direct_requirements_resolves_nested_inputs(tmp_path: Path) -> None:
    base = tmp_path / 'base.txt'
    base.write_text('FastAPI>=1\nhttpx[http2]==2.0\n', encoding='utf-8')
    tools = tmp_path / 'tools.in'
    tools.write_text('-r base.txt\nruff==0.1\n', encoding='utf-8')
    assert direct_requirements(tools) == {'fastapi', 'httpx', 'ruff'}


def test_report_marks_optional_profile_license_as_review(tmp_path: Path) -> None:
    for filename in ('python-runtime.cdx.json', 'python-tools.cdx.json', 'python-ml.cdx.json', 'python-training.cdx.json'):
        (tmp_path / filename).write_text(json.dumps({'bomFormat': 'CycloneDX', 'components': []}), encoding='utf-8')
    (tmp_path / 'nodejs.cdx.json').write_text(json.dumps({
        'bomFormat': 'CycloneDX',
        'metadata': {'component': {'bom-ref': 'root'}},
        'dependencies': [{'ref': 'root', 'dependsOn': ['npm-direct']}],
        'components': [
            {'bom-ref': 'npm-direct', 'name': 'direct', 'version': '1.0.0', 'licenses': [{'license': {'id': 'MIT'}}]},
            {'bom-ref': 'npm-transitive', 'name': 'transitive', 'version': '2.0.0', 'licenses': []},
        ],
    }), encoding='utf-8')
    (tmp_path / 'manifest.json').write_text(json.dumps({'source_sha': 'abc123'}), encoding='utf-8')
    policy_path = tmp_path / 'policy.json'
    policy_path.write_text(json.dumps(POLICY), encoding='utf-8')

    report = build_report(tmp_path, policy_path)

    node = {entry['name']: entry for entry in report['components'] if entry['ecosystem'] == 'npm'}
    assert node['direct']['directness'] == 'direct'
    assert node['direct']['decision'] == 'allow'
    assert node['transitive']['directness'] == 'transitive'
    assert node['transitive']['decision'] == 'review'
