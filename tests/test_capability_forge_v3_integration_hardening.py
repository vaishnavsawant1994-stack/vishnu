from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from future_intelligence.capability_forge.governed_activation_v3 import GovernedCapabilityActivationServiceV3
from future_intelligence.capability_forge.provenance import CapabilityPackageProvenance, CapabilityProvenanceError
from future_intelligence.capability_forge.runtime_v3 import install_capability_forge_v3
from server.capability_forge_v3_api import capability_forge_oauth_callback_router, capability_forge_v3_router
from server.capability_forge_v3_ui import capability_forge_v3_ui_router


class Vault:
    def __init__(self): self.data = {}
    def get(self, key, default=None): return self.data.get(key, default)
    def set(self, key, value): self.data[key] = value
    def delete(self, key): self.data.pop(key, None)


class Catalog:
    def __init__(self): self.items = []
    def all(self): return list(self.items)
    def get(self, capability_id):
        return next((item for item in self.items if item.get("id") == capability_id), None)


class Lifecycle:
    def __init__(self, build_payload=None): self.build_payload = dict(build_payload or {})
    def get_build(self, build_id):
        return {
            "id": str(build_id), "status": "packaged", "payload": dict(self.build_payload),
            "spec_id": "spec", "plan_id": "plan", "work_order_id": "work",
            "attempt_id": "attempt", "candidate_revision": "candidate",
        }
    def record_invocation(self, **kwargs): return None


class Tools:
    def __init__(self): self._tools = {}
    def register(self, tool): self._tools[tool.name] = tool


class Approvals:
    def current_security_epoch(self): return 1


def _package_without_sidecar(tmp_path: Path):
    root = tmp_path / "generated-capabilities" / "x" / "1.0.0"
    root.mkdir(parents=True)
    (root / "capability.py").write_text("def run(payload):\n    return payload\n", encoding="utf-8")
    manifest = {
        "type": "generated_capability", "id": "generated.x", "version": "1.0.0",
        "source_files": ["capability.py"],
        "forge": {"spec_id":"spec","plan_id":"plan","work_order_id":"work","attempt_id":"attempt",
                  "candidate_revision":"candidate","qualification_digest":"q","build_id":"build:attempt"},
    }
    raw = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()
    (root / "manifest.json").write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    package = SimpleNamespace(
        package_path=root, manifest_digest=digest, build_id="build:attempt",
        capability_id="generated.x", version="1.0.0", manifest=manifest,
    )
    return package


def test_v3_build_lineage_prevents_missing_provenance_downgrade(tmp_path):
    package = _package_without_sidecar(tmp_path)
    lifecycle = Lifecycle({
        "provenance_required": True,
        "capability_id": package.capability_id,
        "version": package.version,
        "manifest_digest": package.manifest_digest,
    })
    service = GovernedCapabilityActivationServiceV3(
        catalog=Catalog(), approvals=Approvals(), tools=Tools(), data_root=tmp_path,
        lifecycle=lifecycle, provenance=CapabilityPackageProvenance(Vault()), rollout=None,
    )
    with pytest.raises(CapabilityProvenanceError, match="missing"):
        service._verify_v3_package(package, require_broad=False)


def test_v3_runtime_install_is_idempotent(tmp_path):
    catalog = Catalog(); lifecycle = Lifecycle(); tools = Tools(); approvals = Approvals(); vault = Vault()
    program = SimpleNamespace(
        capability_catalog=catalog,
        capability_forge_lifecycle=lifecycle,
        capability_forge_actions=None,
        capability_forge_activation=SimpleNamespace(approvals=approvals),
        capability_forge_packages=object(),
        autonomy=SimpleNamespace(_work_bridge=None),
    )
    runtime = {"tools": tools, "vault": vault, "oauth": None, "oauth_providers": {}, "events": None}
    assert install_capability_forge_v3(program, runtime, data_root=tmp_path) is True
    first_activation = runtime["capability_forge_activation"]
    assert runtime["capability_forge_v3_installed"] is True
    assert install_capability_forge_v3(program, runtime, data_root=tmp_path) is True
    assert runtime["capability_forge_activation"] is first_activation


def test_native_and_v3_routers_define_each_v3_path_once():
    class Sessions:
        native_client_redirects = {}
    runtime = {
        "pwa_sessions": Sessions(),
        "device_registry": SimpleNamespace(),
    }
    routers = (
        capability_forge_v3_router(runtime),
        capability_forge_oauth_callback_router(runtime),
        capability_forge_v3_ui_router(),
    )
    paths = [
        path
        for router in routers
        for route in router.routes
        if (path := getattr(route, "path", None))
    ]
    readiness = "/iphone/api/owner/forge/v3/readiness"
    callback = "/iphone/capability-oauth/callback"
    assert paths.count(readiness) == 1
    assert paths.count(callback) == 1
