import hashlib
import json

from integrations.discovery.catalog_store import CapabilityCatalogStore
from integrations.discovery.generated_catalog import register_generated_capability
from integrations.discovery.generated_runtime import rehydrate_generated_capabilities


class Registry:
    def __init__(self):
        self._tools = {}

    def register(self, tool):
        if tool.name in self._tools:
            raise ValueError("duplicate")
        self._tools[tool.name] = tool

    def get(self, name):
        return self._tools[name]


def test_owner_approved_generated_capability_rehydrates_after_restart(tmp_path):
    data_root = tmp_path / "data"
    package = data_root / "generated-capabilities" / "calc" / "1.0.0"
    package.mkdir(parents=True)
    (package / "capability.py").write_text(
        "def run(payload):\n    return {'result': int(payload.get('value', 0)) * 2}\n",
        encoding="utf-8",
    )
    manifest = {
        "schema_version": 1,
        "id": "generated.restart.calc",
        "name": "Restart calculator",
        "version": "1.0.0",
        "type": "generated_capability",
        "runtime": "pure_python_v1",
        "entrypoint": {"file": "capability.py", "function": "run"},
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
        "permissions": {
            "network_hosts": [], "filesystem_read": [], "filesystem_write": [],
            "secret_names": [], "connector_ids": [], "side_effects": [],
            "background_allowed": False, "ui_required": False,
        },
        "risk": "read",
        "source_files": ["capability.py"],
        "forge": {
            "qualified": True, "review_decision": "approved", "spec_id": "spec",
            "plan_id": "plan", "work_order_id": "work", "attempt_id": "attempt",
            "candidate_revision": "candidate", "qualification_digest": "q",
            "build_id": "build:attempt",
        },
    }
    raw = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()
    (package / "manifest.json").write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    payload = {
        "id": manifest["id"], "category": "Generated", "name": manifest["name"],
        "type": "generated_capability", "version": manifest["version"],
        "runtime": manifest["runtime"], "entrypoint": manifest["entrypoint"],
        "input_schema": manifest["input_schema"], "output_schema": manifest["output_schema"],
        "permissions": manifest["permissions"], "risk": "read",
        "package_ref": package.relative_to(data_root).as_posix(),
        "manifest_digest": digest, "build_id": "build:attempt", "state": "active",
        "execution_supported": True, "forge": manifest["forge"],
    }
    catalog = CapabilityCatalogStore(data_root / "capability-catalog.sqlite3")
    register_generated_capability(catalog, payload)

    restarted_registry = Registry()
    restored = rehydrate_generated_capabilities(
        catalog,
        tools=restarted_registry,
        data_root=data_root,
    )

    assert restored == ["generated.restart.calc"]
    assert restarted_registry.get("generated.restart.calc").handler({"value": 9}) == {"result": 18}


def test_disabled_generated_capability_does_not_rehydrate(tmp_path):
    data_root = tmp_path / "data"
    catalog = CapabilityCatalogStore(data_root / "capability-catalog.sqlite3")
    register_generated_capability(catalog, {
        "id": "generated.disabled", "category": "Generated", "name": "Disabled",
        "type": "generated_capability", "version": "1.0.0", "runtime": "pure_python_v1",
        "entrypoint": {"file": "capability.py", "function": "run"},
        "input_schema": {}, "output_schema": {}, "permissions": {}, "risk": "read",
        "package_ref": "generated-capabilities/disabled/1.0.0", "manifest_digest": "missing",
        "build_id": "build", "state": "disabled", "execution_supported": True, "forge": {},
    })
    registry = Registry()
    assert rehydrate_generated_capabilities(catalog, tools=registry, data_root=data_root) == []
    assert registry._tools == {}
