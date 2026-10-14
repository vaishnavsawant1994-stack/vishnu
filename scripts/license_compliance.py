from __future__ import annotations

import argparse
import importlib.metadata
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / 'config' / 'license-policy.json'
PYTHON_PROFILES = {
    'python-runtime.cdx.json': ('runtime', ROOT / 'requirements.txt', True),
    'python-tools.cdx.json': ('tools', ROOT / 'requirements-tools.in', True),
    'python-ml.cdx.json': ('ml', ROOT / 'requirements-ml.txt', False),
    'python-training.cdx.json': ('training', ROOT / 'requirements-training.txt', False),
}
NODE_SBOM = 'nodejs.cdx.json'
ALIASES = {
    'mit license': 'MIT',
    'apache license 2.0': 'Apache-2.0',
    'apache software license': 'Apache-2.0',
    'bsd 2-clause license': 'BSD-2-Clause',
    'bsd 3-clause license': 'BSD-3-Clause',
    'isc license': 'ISC',
    'python software foundation license': 'PSF-2.0',
    'zlib license': 'Zlib',
    'unlicense': 'Unlicense',
}


def normalize_package(name: str) -> str:
    return re.sub(r'[-_.]+', '-', name).lower()


def direct_requirements(source: Path) -> set[str]:
    direct: set[str] = set()
    visited: set[Path] = set()

    def visit(path: Path) -> None:
        path = path.resolve()
        if path in visited:
            return
        visited.add(path)
        for raw_line in path.read_text(encoding='utf-8').splitlines():
            line = raw_line.split('#', 1)[0].strip()
            if not line:
                continue
            include = re.match(r'^(?:-r|--requirement)(?:\s+|=)(.+)$', line)
            if include:
                visit(path.parent / include.group(1).strip())
                continue
            if line.startswith('-'):
                continue
            match = re.match(r'^([A-Za-z0-9][A-Za-z0-9_.-]*)', line)
            if match:
                direct.add(normalize_package(match.group(1)))

    visit(source)
    return direct


def classify_license(expression: str, policy: dict[str, Any]) -> tuple[str, str]:
    value = expression.strip()
    if not value or value.upper() in {'NOASSERTION', 'UNKNOWN'}:
        return 'review', 'No license identifier was found.'
    alias = ALIASES.get(value.casefold())
    tokens = [alias] if alias else re.findall(r'[A-Za-z0-9][A-Za-z0-9.+-]*', value)
    operators = {'AND', 'OR', 'WITH'}
    identifiers = [token for token in tokens if token.upper() not in operators]
    allowed = set(policy['allow_spdx_ids'])
    denied = set(policy['deny_spdx_ids'])
    if any(token in denied for token in identifiers):
        return 'deny', 'The license matches an explicit repository deny rule.'
    if identifiers and all(token in allowed for token in identifiers):
        return 'allow', 'Every license identifier is on the repository allow list.'
    return 'review', 'The license is outside the explicit allow and deny lists.'


def _metadata_license(name: str) -> tuple[str, str]:
    try:
        distribution = importlib.metadata.distribution(name)
    except importlib.metadata.PackageNotFoundError:
        return 'NOASSERTION', 'not-installed'
    metadata = distribution.metadata
    expression = metadata.get('License-Expression')
    if expression:
        return expression, 'installed-package License-Expression metadata'
    classifiers = metadata.get_all('Classifier') or []
    for classifier in classifiers:
        prefix = 'License :: OSI Approved :: '
        if classifier.startswith(prefix):
            return classifier[len(prefix):], 'installed-package OSI classifier'
    license_text = metadata.get('License')
    if license_text and len(license_text) < 200:
        return license_text, 'installed-package License metadata'
    return 'NOASSERTION', 'installed-package metadata has no usable license field'


def _component_license(component: dict[str, Any]) -> str:
    choices = component.get('licenses') or []
    values: list[str] = []
    for choice in choices:
        license_value = choice.get('license') or {}
        value = license_value.get('id') or license_value.get('name')
        if value:
            values.append(str(value))
        expression = choice.get('expression')
        if expression:
            values.append(str(expression))
    return ' OR '.join(values) if values else 'NOASSERTION'


def _decision_record(
    *,
    ecosystem: str,
    profile: str,
    name: str,
    version: str,
    license_value: str,
    license_source: str,
    direct: bool,
    policy: dict[str, Any],
) -> dict[str, Any]:
    decision, reason = classify_license(license_value, policy)
    return {
        'ecosystem': ecosystem,
        'profile': profile,
        'name': name,
        'version': version,
        'directness': 'direct' if direct else 'transitive',
        'license': license_value,
        'license_source': license_source,
        'decision': decision,
        'policy_reason': reason,
        'redistribution_follow_up': (
            'Preserve the license and notice information supplied with the package.'
            if decision == 'allow'
            else 'Review the upstream license text, notice files, attribution, and redistribution conditions.'
        ),
    }


def build_report(sbom_dir: Path, policy_path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(policy_path.read_text(encoding='utf-8'))
    entries: list[dict[str, Any]] = []
    for filename, (profile, source, installed) in PYTHON_PROFILES.items():
        document = json.loads((sbom_dir / filename).read_text(encoding='utf-8'))
        direct_names = direct_requirements(source)
        for component in document.get('components', []):
            name = str(component.get('name', ''))
            version = str(component.get('version', ''))
            if not name or not version:
                continue
            if installed:
                license_value, license_source = _metadata_license(name)
            else:
                license_value, license_source = 'NOASSERTION', 'optional profile not installed for metadata inspection'
            entries.append(_decision_record(
                ecosystem='PyPI',
                profile=profile,
                name=name,
                version=version,
                license_value=license_value,
                license_source=license_source,
                direct=normalize_package(name) in direct_names,
                policy=policy,
            ))

    node_document = json.loads((sbom_dir / NODE_SBOM).read_text(encoding='utf-8'))
    root_ref = (node_document.get('metadata', {}).get('component') or {}).get('bom-ref')
    direct_refs: set[str] = set()
    for dependency in node_document.get('dependencies', []):
        if dependency.get('ref') == root_ref:
            direct_refs.update(dependency.get('dependsOn', []))
            break
    for component in node_document.get('components', []):
        entries.append(_decision_record(
            ecosystem='npm',
            profile='browser-qualification',
            name=str(component.get('name', '')),
            version=str(component.get('version', '')),
            license_value=_component_license(component),
            license_source='package-lock metadata',
            direct=str(component.get('bom-ref', '')) in direct_refs,
            policy=policy,
        ))

    totals = {decision: sum(entry['decision'] == decision for entry in entries) for decision in ('allow', 'deny', 'review')}
    manifest = json.loads((sbom_dir / 'manifest.json').read_text(encoding='utf-8'))
    return {
        'schema_version': 1,
        'policy_version': policy['schema_version'],
        'source_sha': manifest['source_sha'],
        'policy': {
            'allow_spdx_ids': policy['allow_spdx_ids'],
            'deny_spdx_ids': policy['deny_spdx_ids'],
            'default_decision': policy['default_decision'],
            'review_note': policy['review_note'],
        },
        'summary': {'total': len(entries), **totals},
        'components': sorted(entries, key=lambda entry: (entry['ecosystem'], entry['profile'], entry['name'].lower())),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Evaluate dependency license metadata against Vishnu policy.')
    parser.add_argument('--sbom-dir', type=Path, default=ROOT / 'dist' / 'sbom')
    parser.add_argument('--policy', type=Path, default=POLICY_PATH)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist' / 'sbom' / 'license-report.json')
    args = parser.parse_args()
    report = build_report(args.sbom_dir.resolve(), args.policy.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(report['summary'], sort_keys=True))
    return 1 if report['summary']['deny'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
