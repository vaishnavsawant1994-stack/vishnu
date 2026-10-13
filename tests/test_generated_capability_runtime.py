import hashlib
import json
from pathlib import Path

import pytest

from integrations.discovery.generated_runtime import (
    GeneratedCapabilitySecurityError,
    PurePythonGeneratedCapability,
    attach_approved_generated_capability,
)


def _write_package(root: Path, *, source: str, permissions=None, risk="read"):
    root.mkdir(parents=True, exist_ok=True)
    (root / "capability.py").write_text(source, encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "id": "generated.test.calc",
        "name": "Test calculator",
        "version": "1.0.0",
        "type": "generated_capability",
        "runtime": "pure_python_v1",
        "entrypoint": {"file": "capability.py", "function": "run"},
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
        "permissions": permissions or {
            "network_hosts": [],
            "filesystem_read": [],
            "filesystem_write": [],
            "secret_names": [],
            "connector_ids": [],
            "side_effects": [],
            "background_allowed": False,
            "ui_required": False,
        },
        "risk": risk,
        "source_files": ["capability.py"],
        "forge": {
            "qualified": True,
            "review_decision": "approved",
            "spec_id": "spec",
            "plan_id": "plan",
            "work_order_id": "work",
            "attempt_id": "attempt",
            "candidate_revision": "sha",
            "qualification_digest": "q",
            "build_id": "build:attempt",
        },
    }
    raw = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()
    (root / "manifest.json").write_bytes(raw)
    return manifest, hashlib.sha256(raw).hexdigest()


def test_pure_generated_runtime_executes_restricted_json_function(tmp_path):
    package = tmp_path / "pkg"
    _manifest, digest = _write_package(
        package,
        source="def run(payload):\n    values = payload.get('values', [])\n    return {'total': sum(values), 'count': len(values)}\n",
    )
    runtime = PurePythonGeneratedCapability(package, expected_digest=digest)
    assert runtime.invoke({"values": [2, 3, 5]}) == {"total": 10, "count": 3}


def test_pure_generated_runtime_rejects_imports_dunder_and_external_authority(tmp_path):
    package = tmp_path / "bad-import"
    _manifest, digest = _write_package(
        package,
        source="import os\ndef run(payload):\n    return {'cwd': os.getcwd()}\n",
    )
    with pytest.raises(GeneratedCapabilitySecurityError, match="Import"):
        PurePythonGeneratedCapability(package, expected_digest=digest)

    package2 = tmp_path / "network"
    permissions = {
        "network_hosts": ["example.com"],
        "filesystem_read": [],
        "filesystem_write": [],
        "secret_names": [],
        "connector_ids": [],
        "side_effects": [],
        "background_allowed": False,
        "ui_required": False,
    }
    _manifest, digest2 = _write_package(
        package2,
        source="def run(payload):\n    return {'ok': True}\n",
        permissions=permissions,
    )
    with pytest.raises(GeneratedCapabilitySecurityError, match="external authority"):
        PurePythonGeneratedCapability(package2, expected_digest=digest2)

    package3 = tmp_path / "dunder"
    _manifest, digest3 = _write_package(
        package3,
        source="def run(payload):\n    return {'type': payload.__class__.__name__}\n",
    )
    with pytest.raises(GeneratedCapabilitySecurityError, match="dunder"):
        PurePythonGeneratedCapability(package3, expected_digest=digest3)


class Registry:
    def __init__(self):
        self._tools = {}

    def register(self, tool):
        if tool.name in self._tools:
            raise ValueError("duplicate")
        self._tools[tool.name] = tool

    def get(self, name):
        return self._tools[name]


def test_attach_generated_capability_registers_read_only_contract_tool_and_supports_version_replace(tmp_path):
    data_root = tmp_path / "data"
    package = data_root / "generated-capabilities" / "calc" / "1.0.0"
    manifest, digest = _write_package(
        package,
        source="def run(payload):\n    return {'value': int(payload.get('value', 0)) + 1}\n",
    )
    capability = {
        "id": manifest["id"],
        "name": manifest["name"],
        "type": "generated_capability",
        "state": "active",
        "version": "1.0.0",
        "package_ref": package.relative_to(data_root).as_posix(),
        "manifest_digest": digest,
        "input_schema": manifest["input_schema"],
        "output_schema": manifest["output_schema"],
    }
    registry = Registry()
    tool = attach_approved_generated_capability(capability, tools=registry, data_root=data_root)
    assert tool.risk.name == "READ_ONLY"
    assert registry.get(capability["id"]).handler({"value": 4}) == {"value": 5}

    replacement = attach_approved_generated_capability(capability, tools=registry, data_root=data_root)
    assert replacement.name == capability["id"]
    assert len(registry._tools) == 1
