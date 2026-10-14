from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _python_files(directory: Path):
    return sorted(path for path in directory.rglob('*.py') if path.is_file())


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding='utf-8'), filename=str(path))


def _imported_symbols(tree: ast.Module):
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                yield node.module or '', alias.name, alias.asname
        elif isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, '', alias.asname


def test_intelligence_modules_do_not_construct_or_import_tool_registry():
    violations = []
    roots = (ROOT / 'future_intelligence', ROOT / 'models')
    for directory in roots:
        for path in _python_files(directory):
            tree = _tree(path)
            for module, symbol, alias in _imported_symbols(tree):
                if module == 'tools.registry' and symbol == 'ToolRegistry':
                    violations.append(f'{path.relative_to(ROOT)} imports ToolRegistry')
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    if node.func.id == 'ToolRegistry':
                        violations.append(f'{path.relative_to(ROOT)} constructs ToolRegistry')
    assert violations == []


def test_root_key_store_construction_stays_in_existing_authority_integrations():
    allowed = {
        'security/vault.py',
        'recovery/backup.py',
        'continuity/importer.py',
        'continuity/authority.py',
    }
    users = set()
    production_files = (
        path for path in ROOT.rglob('*.py')
        if 'tests' not in path.relative_to(ROOT).parts and '.venv' not in path.parts
    )
    for path in production_files:
        tree = _tree(path)
        imported = any(
            module == 'security.keychain' and symbol == 'RootKeyStore'
            for module, symbol, _ in _imported_symbols(tree)
        )
        constructed = any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == 'RootKeyStore'
            for node in ast.walk(tree)
        )
        if imported or constructed:
            users.add(path.relative_to(ROOT).as_posix())
    assert users <= allowed
    assert users == allowed


def test_memory_package_does_not_import_knowledge_internals():
    violations = []
    for path in _python_files(ROOT / 'memory'):
        for module, _, _ in _imported_symbols(_tree(path)):
            if module == 'knowledge' or module.startswith('knowledge.'):
                violations.append(f'{path.relative_to(ROOT)} imports {module}')
    assert violations == []


def test_device_authority_types_have_single_canonical_definitions():
    definitions = {'DeviceRegistry': [], 'DeviceGateway': []}
    production_files = (
        path for path in ROOT.rglob('*.py')
        if 'tests' not in path.relative_to(ROOT).parts and '.venv' not in path.parts
    )
    for path in production_files:
        for node in ast.walk(_tree(path)):
            if isinstance(node, ast.ClassDef) and node.name in definitions:
                definitions[node.name].append(path.relative_to(ROOT).as_posix())
    assert definitions == {
        'DeviceRegistry': ['devices/registry.py'],
        'DeviceGateway': ['devices/gateway.py'],
    }
