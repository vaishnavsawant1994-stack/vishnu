from __future__ import annotations

import hashlib
import json

from future_intelligence.capability_forge.oauth_durable import DurableCapabilityOAuthLifecycle
from future_intelligence.capability_forge.production_canary import ProductionCapabilityCanaryRollout
from future_intelligence.capability_forge.provenance import CapabilityPackageProvenance
from integrations.discovery.catalog_store import CapabilityCatalogStore
from integrations.discovery.generated_catalog import register_generated_capability
from integrations.discovery.generated_runtime_v3 import rehydrate_generated_capabilities_v3
from integrations.oauth import OAuthProvider
from security.vault import SecretVault


class Registry:
    def __init__(self): self._tools = {}
    def register(self, tool):
        if tool.name in self._tools: raise ValueError("duplicate")
        self._tools[tool.name] = tool
    def get(self, name): return self._tools[name]


class FakeOAuth:
    def begin(self, provider, **kwargs):
        return {"state": "z" * 32, "url": "https://auth.example/authorize", "expires_in": 600}
    def complete(self, state, code, provider, **kwargs):
        return {"connected": True, "scopes": list(provider.scopes)}
    def token(self, provider): return f"token:{provider.id}"
    def unlink(self, provider_id, **kwargs): return {"revoked": True, "provider_revocation": "confirmed"}


def make_signed_package(tmp_path):
    data_root = tmp_path / "data"
    package = data_root / "generated-capabilities" / "calc" / "1.0.0"
    package.mkdir(parents=True)
    (package / "capability.py").write_text(
        "def run(payload):\n    return {'result': int(payload.get('value', 0)) * 3}\n",
        encoding="utf-8",
    )
    manifest = {
        "schema_version": 2,
        "id": "generated.v3.restart.calc",
        "name": "V3 restart calculator",
        "version": "1.0.0",
        "type": "generated_capability",
        "runtime": "pure_python_v1",
        "entrypoint": {"file": "capability.py", "function": "run"},
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
        "permissions": {
            "network_hosts": [], "filesystem_read": [], "filesystem_write": [],
            "secret_names": [], "connector_ids": [], "side_effects": [], "allowed_tools": [],
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
    raw = (json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()
    (package / "manifest.json").write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    vault_path = data_root / "vault.json"
    signer = CapabilityPackageProvenance(SecretVault(vault_path, password="test-password"))
    evidence = signer.sign(package, expected_manifest_digest=digest)
    payload = {
        "id": manifest["id"], "category": "Generated", "name": manifest["name"],
        "type": "generated_capability", "version": manifest["version"],
        "runtime": manifest["runtime"], "entrypoint": manifest["entrypoint"],
        "input_schema": manifest["input_schema"], "output_schema": manifest["output_schema"],
        "permissions": manifest["permissions"], "risk": "read",
        "package_ref": package.relative_to(data_root).as_posix(),
        "manifest_digest": digest, "build_id": "build:attempt", "state": "active",
        "execution_supported": True, "forge": manifest["forge"],
        "provenance_required": True, "provenance_key_id": evidence["key_id"],
        "provenance_file_count": evidence["file_count"], "rollout_stage": "broad_eligible",
    }
    return data_root, package, vault_path, payload


def test_v3_signed_package_and_vault_key_survive_restart(tmp_path):
    data_root, _package, vault_path, payload = make_signed_package(tmp_path)
    catalog = CapabilityCatalogStore(data_root / "capability-catalog.sqlite3")
    register_generated_capability(catalog, payload)
    restarted_signer = CapabilityPackageProvenance(SecretVault(vault_path, password="test-password"))
    registry = Registry()
    restored = rehydrate_generated_capabilities_v3(
        catalog, tools=registry, data_root=data_root, action_service=object(), provenance=restarted_signer,
    )
    assert restored == [payload["id"]]
    assert registry.get(payload["id"]).handler({"value": 4}) == {"result": 12}
    assert catalog.get(payload["id"])["state"] == "active"


def test_v3_restart_quarantines_tampered_signed_package(tmp_path):
    data_root, package, vault_path, payload = make_signed_package(tmp_path)
    catalog = CapabilityCatalogStore(data_root / "capability-catalog.sqlite3")
    register_generated_capability(catalog, payload)
    (package / "capability.py").write_text("def run(payload):\n    return {'tampered': True}\n", encoding="utf-8")
    registry = Registry()
    restored = rehydrate_generated_capabilities_v3(
        catalog,
        tools=registry,
        data_root=data_root,
        action_service=object(),
        provenance=CapabilityPackageProvenance(SecretVault(vault_path, password="test-password")),
    )
    assert restored == []
    assert catalog.get(payload["id"])["state"] == "disabled"
    assert payload["id"] not in registry._tools


def test_capability_oauth_pending_route_survives_service_restart(tmp_path, monkeypatch):
    callback = "https://vishnu.example.com/iphone/capability-oauth/callback"
    monkeypatch.setenv("VISHNU_CAPABILITY_OAUTH_REDIRECT_URI", callback)
    catalog = CapabilityCatalogStore(tmp_path / "catalog.sqlite3")
    with __import__("sqlite3").connect(catalog.path) as db:
        db.execute(
            "INSERT INTO capability_catalog(id,category,name,payload) VALUES(?,?,?,?)",
            ("cap.oauth", "API", "OAuth capability", json.dumps({"id":"cap.oauth","category":"API","name":"OAuth capability","type":"openapi_operation"})),
        )
    provider = OAuthProvider("provider", "https://auth.example/authorize", "https://auth.example/token", "cid", ["read"])
    path = tmp_path / "forge.sqlite3"
    first = DurableCapabilityOAuthLifecycle(
        oauth=FakeOAuth(), catalog=catalog, providers={"provider": provider}, path=path,
    )
    started = first.begin("cap.oauth", "provider", scopes=["read"], device_id="device", session_id="session", security_epoch=4)
    assert first.pending(started["state"])["capability_id"] == "cap.oauth"
    try:
        first.begin("cap.oauth", "provider", scopes=["read"], redirect_uri="https://evil.example/callback")
        raise AssertionError("mismatched callback must fail closed")
    except PermissionError as exc:
        assert "configured V3 callback" in str(exc)
    restarted = DurableCapabilityOAuthLifecycle(
        oauth=FakeOAuth(), catalog=catalog, providers={"provider": provider}, path=path,
    )
    binding = restarted.complete_state(state=started["state"], code="code")
    assert binding.capability_id == "cap.oauth"
    assert restarted.pending(started["state"]) is None
    connection = catalog.connection("cap.oauth", include_credential_ref=True)
    assert connection["auth_type"] == "oauth2_pkce"
    assert connection["credential_ref"] == "oauth:capability:cap.oauth:provider"


class DummyApprovals:
    def current_security_epoch(self): return 1


class DummyLifecycle:
    pass


def test_v3_rollout_samples_survive_process_restart(tmp_path):
    path = tmp_path / "forge.sqlite3"
    first = ProductionCapabilityCanaryRollout(
        path=path, lifecycle=DummyLifecycle(), approvals=DummyApprovals(), catalog=object(), tools=object(),
    )
    first.start(capability_id="generated.persist", version="1.0.0", manifest_digest="digest")
    first.record_sample("generated.persist", "1.0.0", ok=True, duration_ms=7.5)
    second = ProductionCapabilityCanaryRollout(
        path=path, lifecycle=DummyLifecycle(), approvals=DummyApprovals(), catalog=object(), tools=object(),
    )
    state = second.get("generated.persist", "1.0.0")
    assert state["stage"] == "internal" and state["status"] == "running"
    assert second._candidate_metrics("generated.persist", "1.0.0").sample_count == 1
