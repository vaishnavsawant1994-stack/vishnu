from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from future_intelligence.capability_forge.oauth_lifecycle import CapabilityOAuthLifecycle
from future_intelligence.capability_forge.provenance import CapabilityPackageProvenance, CapabilityProvenanceError
from future_intelligence.capability_forge.canary_rollout import CapabilityCanaryRollout
from future_intelligence.capability_forge.production_canary import ProductionCapabilityCanaryRollout
from future_intelligence.capability_forge.provider_verification import CapabilityProviderVerifier
from future_intelligence.capability_forge.production_readiness import CapabilityForgeProductionReadiness
from future_intelligence.engineering.canary import CanaryMetrics, CanaryThresholds
from integrations.oauth import OAuthProvider
from tools.registry import Risk, VerificationResult


class Vault:
    def __init__(self): self.data = {}
    def get(self, key, default=None): return self.data.get(key, default)
    def set(self, key, value): self.data[key] = value
    def delete(self, key): self.data.pop(key, None)


class Catalog:
    def __init__(self):
        self.items = {"cap.a": {"id": "cap.a", "name": "A", "type": "openapi_operation"}}
        self.connections = {}
    def get(self, capability_id): return self.items.get(capability_id)
    def connect(self, capability_id, **kwargs): self.connections[capability_id] = {"status": "connected", **kwargs}
    def connection(self, capability_id, *, include_credential_ref=False):
        row = self.connections.get(capability_id)
        if not row: return None
        out = dict(row)
        if not include_credential_ref: out.pop("credential_ref", None)
        return out
    def revoke(self, capability_id):
        row = self.connections.get(capability_id)
        if not row or row.get("status") != "connected": return None
        row["status"] = "revoked"
        return row.pop("credential_ref", None)


class FakeOAuth:
    def __init__(self): self.providers = []; self.revoked = []
    def begin(self, provider, **kwargs):
        self.providers.append(provider)
        return {"state": "s" * 32, "url": "https://auth.example/authorize", "expires_in": 600}
    def complete(self, state, code, provider, **kwargs):
        self.providers.append(provider)
        return {"connected": True, "scopes": list(kwargs.get("scopes") or provider.scopes)}
    def token(self, provider): return f"secret-for:{provider.id}"
    def unlink(self, provider_id, **kwargs):
        self.revoked.append(provider_id)
        return {"revoked": True, "provider_revocation": "confirmed"}


def test_capability_oauth_is_namespaced_and_never_returns_token_from_public_lifecycle():
    oauth = FakeOAuth(); catalog = Catalog()
    provider = OAuthProvider("google", "https://auth.example/a", "https://auth.example/t", "cid", ["read", "write"])
    service = CapabilityOAuthLifecycle(oauth=oauth, catalog=catalog, providers={"google": provider})
    started = service.begin("cap.a", "google", scopes=["read"])
    assert started["capability_id"] == "cap.a" and "secret" not in json.dumps(started)
    scoped_id = oauth.providers[-1].id
    assert scoped_id == "capability:cap.a:google"
    binding = service.complete("cap.a", "google", state="s" * 32, code="code")
    assert binding.credential_ref == "oauth:capability:cap.a:google"
    assert catalog.connection("cap.a", include_credential_ref=True)["auth_type"] == "oauth2_pkce"
    assert service.token("cap.a", "google") == "secret-for:capability:cap.a:google"
    public_status = service.status("cap.a")
    assert "credential_ref" not in public_status and "secret" not in json.dumps(public_status)
    revoked = service.revoke("cap.a", "google")
    assert revoked["revoked"] is True and oauth.revoked == ["capability:cap.a:google"]


def test_capability_oauth_rejects_scope_expansion():
    service = CapabilityOAuthLifecycle(
        oauth=FakeOAuth(), catalog=Catalog(),
        providers={"p": OAuthProvider("p", "https://x/a", "https://x/t", "cid", ["read"])},
    )
    with pytest.raises(PermissionError, match="scope"):
        service.begin("cap.a", "p", scopes=["admin"])


def package(tmp_path: Path):
    root = tmp_path / "pkg"; root.mkdir()
    (root / "capability.py").write_text("def run(payload):\n    return payload\n", encoding="utf-8")
    manifest = {
        "type": "generated_capability", "id": "generated.test", "version": "1.0.0",
        "source_files": ["capability.py"],
        "forge": {"spec_id":"s","plan_id":"p","work_order_id":"w","attempt_id":"a",
                  "candidate_revision":"r","qualification_digest":"q","build_id":"b"},
    }
    raw = (json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()
    (root / "manifest.json").write_bytes(raw)
    import hashlib
    return root, hashlib.sha256(raw).hexdigest()


def test_package_provenance_binds_manifest_source_and_lineage(tmp_path):
    root, digest = package(tmp_path); signer = CapabilityPackageProvenance(Vault())
    signed = signer.sign(root, expected_manifest_digest=digest)
    assert signed["file_count"] == 1 and signed["key_id"]
    verified = signer.verify(root, expected_manifest_digest=digest)
    assert verified["verified"] is True and verified["lineage"]["work_order_id"] == "w"
    (root / "capability.py").write_text("def run(payload):\n    return {'tampered': True}\n", encoding="utf-8")
    with pytest.raises(CapabilityProvenanceError, match="changed"):
        signer.verify(root, expected_manifest_digest=digest)


def test_package_provenance_rejects_undeclared_files(tmp_path):
    root, digest = package(tmp_path); signer = CapabilityPackageProvenance(Vault())
    (root / "hidden.py").write_text("x=1", encoding="utf-8")
    with pytest.raises(CapabilityProvenanceError, match="undeclared"):
        signer.sign(root, expected_manifest_digest=digest)


class FakeApprovals:
    def __init__(self): self.records = {}; self.epoch = 1; self.counter = 0
    def current_security_epoch(self): return self.epoch
    def create(self, execution_id, tool_name, parameters, **kwargs):
        from security.approvals import parameter_hash
        self.counter += 1; tid = f"t{self.counter}"
        ticket = SimpleNamespace(id=tid, execution_id=execution_id, tool_name=tool_name,
            parameter_hash=parameter_hash(parameters), owner_id=kwargs.get("owner_id"),
            device_id=kwargs.get("device_id"), session_id=kwargs.get("session_id"),
            security_epoch=self.epoch, destination=kwargs.get("destination"),
            data_classification=kwargs.get("data_classification"))
        self.records[tid] = {"status":"pending", "ticket":ticket}
        return ticket
    def record(self, tid): return self.records.get(tid)
    def approve(self, tid): self.records[tid]["status"] = "approved"
    def begin_dispatch(self, tid, **kwargs): return {"dispatch": True, "status": "dispatching"}
    def complete_dispatch(self, tid, outcome): self.records[tid]["status"] = "consumed"
    def mark_recovery_required(self, tid, reason): self.records[tid]["status"] = "recovery_required"


class EmptyLifecycle:
    def _con(self): raise AssertionError("not used")


def test_canary_rollout_requires_evidence_and_canonical_approval(tmp_path):
    approvals = FakeApprovals()
    rollout = CapabilityCanaryRollout(
        path=tmp_path / "forge.sqlite3", lifecycle=EmptyLifecycle(), approvals=approvals,
        catalog=SimpleNamespace(), tools=SimpleNamespace(),
        thresholds=CanaryThresholds(min_sample_count=3, max_error_rate_absolute=.25),
    )
    rollout.start(capability_id="g", version="1", manifest_digest="d",
                  baseline=CanaryMetrics(3, 0.0, 10.0))
    rollout.record_sample("g", "1", ok=True, duration_ms=9)
    with pytest.raises(PermissionError, match="evidence"):
        rollout.request_promotion("g", "1", target_stage="limited")
    rollout.record_sample("g", "1", ok=True, duration_ms=10)
    rollout.record_sample("g", "1", ok=True, duration_ms=11)
    ticket = rollout.request_promotion("g", "1", target_stage="limited", device_id="d", session_id="s")
    with pytest.raises(PermissionError, match="approval"):
        rollout.promote("g", "1", target_stage="limited", ticket_id=ticket, device_id="d", session_id="s")
    approvals.approve(ticket)
    result = rollout.promote("g", "1", target_stage="limited", ticket_id=ticket, device_id="d", session_id="s")
    assert result["stage"] == "limited"


def test_v3_broad_rollout_requires_fresh_limited_stage_samples(tmp_path):
    approvals = FakeApprovals()
    rollout = ProductionCapabilityCanaryRollout(
        path=tmp_path / "forge.sqlite3", lifecycle=EmptyLifecycle(), approvals=approvals,
        catalog=SimpleNamespace(), tools=SimpleNamespace(),
        thresholds=CanaryThresholds(min_sample_count=3, max_error_rate_absolute=.25),
    )
    rollout.start(capability_id="g", version="1", manifest_digest="d",
                  baseline=CanaryMetrics(3, 0.0, 10.0))
    for latency in (8, 9, 10): rollout.record_sample("g", "1", ok=True, duration_ms=latency, source="internal")
    first = rollout.request_promotion("g", "1", target_stage="limited")
    approvals.approve(first)
    assert rollout.promote("g", "1", target_stage="limited", ticket_id=first)["stage"] == "limited"
    second = rollout.request_promotion("g", "1", target_stage="broad_eligible")
    approvals.approve(second)
    with pytest.raises(PermissionError, match="limited-stage evidence"):
        rollout.promote("g", "1", target_stage="broad_eligible", ticket_id=second)
    # A failed promotion never substitutes internal evidence for limited exposure.
    assert rollout.get("g", "1")["stage"] == "limited"
    for latency in (9, 10, 11): rollout.record_sample("g", "1", ok=True, duration_ms=latency, source="limited")
    third = rollout.request_promotion("g", "1", target_stage="broad_eligible")
    approvals.approve(third)
    broad = rollout.promote("g", "1", target_stage="broad_eligible", ticket_id=third)
    assert broad["stage"] == "broad_eligible"
    assert broad["baseline"]["sample_count"] == 3


class FakeToolRegistry:
    def __init__(self, risk=Risk.READ_ONLY):
        self.tool = SimpleNamespace(name="provider.read", risk=risk, verification_method="provider_probe")
    def get(self, name): return self.tool
    def authorize(self, tool, **kwargs): return SimpleNamespace(allowed=True, reason="allowed")
    def dispatch(self, tool, parameters): return {"ok": True, "token": "must-not-return"}
    def verify_result(self, tool, parameters, result): return VerificationResult(True, "verified", {"status": 200, "secret": "redacted"})


def test_provider_verification_uses_read_only_registry_and_redacts_result():
    verifier = CapabilityProviderVerifier(tools=FakeToolRegistry())
    result = verifier.verify("provider.read", {"id": "x"})
    assert result["verified"] is True and result["result_redacted"] is True
    assert "must-not-return" not in json.dumps(result) and set(result["evidence_keys"]) == {"secret", "status"}
    with pytest.raises(PermissionError, match="read-only"):
        CapabilityProviderVerifier(tools=FakeToolRegistry(Risk.REVERSIBLE)).verify("provider.write", {})


def test_production_readiness_is_fail_closed_without_real_associations():
    service = CapabilityForgeProductionReadiness()
    blocked = service.evaluate(
        public_base_url=None, oauth_redirect_uri=None, android_asset_links=[],
        apple_app_site_association={}, native_client_redirects={}, provenance_available=True,
        provider_verification_available=True, canary_available=True, external_oauth_available=True,
    )
    assert blocked.ready is False and blocked.blockers
    android = [{"relation":["delegate_permission/common.handle_all_urls"],"target":{
        "namespace":"android_app","package_name":"ai.vishnu.app",
        "sha256_cert_fingerprints":[":".join(["AA"]*32)]}}]
    apple = {"applinks":{"apps":[],"details":[{"appID":"TEAM.ai.vishnu.app","paths":["/iphone/native/*"]}]}}
    wrong_path = service.evaluate(
        public_base_url="https://vishnu.example.com",
        oauth_redirect_uri="https://vishnu.example.com/connector-oauth/callback",
        android_asset_links=android, apple_app_site_association=apple,
        native_client_redirects={"ios":{"vishnu://oauth/callback"}, "android":{"vishnu://oauth/callback"}},
        provenance_available=True, provider_verification_available=True,
        canary_available=True, external_oauth_available=True,
    )
    assert wrong_path.ready is False and wrong_path.checks["oauth_callback_path"] is False
    ready = service.evaluate(
        public_base_url="https://vishnu.example.com",
        oauth_redirect_uri="https://vishnu.example.com/iphone/capability-oauth/callback",
        android_asset_links=android, apple_app_site_association=apple,
        native_client_redirects={"ios":{"vishnu://oauth/callback"}, "android":{"vishnu://oauth/callback"}},
        provenance_available=True, provider_verification_available=True,
        canary_available=True, external_oauth_available=True,
    )
    assert ready.ready is True and not ready.blockers
