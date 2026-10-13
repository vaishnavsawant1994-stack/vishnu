from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

from core.permissions import PermissionDecision
from future_intelligence.capability_forge.action_runtime import GeneratedActionService
from future_intelligence.capability_forge.provenance import CapabilityPackageProvenance
from integrations.discovery.generated_runtime_v3 import rehydrate_generated_capabilities_v3
from security.approvals import ApprovalManager
from tools.registry import Risk, Tool, VerificationResult


class Vault:
    def __init__(self):
        self.data = {}
    def get(self, key, default=None):
        return self.data.get(key, default)
    def set(self, key, value):
        self.data[key] = value


class Catalog:
    def __init__(self, item):
        self.item = item
    def all(self):
        return [dict(self.item)]
    def get(self, capability_id):
        return dict(self.item) if capability_id == self.item["id"] else None


class Registry:
    def __init__(self, tool):
        self._tools = {tool.name: tool}
        self.dispatched = []
    def register(self, tool):
        self._tools[tool.name] = tool
    def get(self, name):
        return self._tools[name]
    def destination(self, parameters):
        return str(parameters.get("destination") or "")
    def effective_risk(self, tool, *, parameters=None, data_classification="internal"):
        return tool.minimum_risk if tool.minimum_risk is not None else tool.risk
    def authorize(self, tool, confirmed=False, *, parameters=None, data_classification="internal"):
        if tool.risk is Risk.READ_ONLY or confirmed:
            return PermissionDecision(True, False, "allowed")
        return PermissionDecision(False, True, "owner confirmation required")
    def dispatch(self, tool, parameters):
        self.dispatched.append((tool.name, dict(parameters)))
        return tool.handler(parameters)
    def verify_result(self, tool, parameters, result):
        return tool.verifier(parameters, result) if tool.verifier else VerificationResult(False, "missing verifier", {})


def _package(tmp_path):
    root = tmp_path / "generated-capabilities" / "generated.action.e2e" / "1.0.0"
    root.mkdir(parents=True)
    source = "def run(payload):\n    return {'calls': [{'tool': 'write.item', 'parameters': {'value': payload['value']}}]}\n"
    (root / "capability.py").write_text(source, encoding="utf-8")
    manifest = {
        "schema_version": 2,
        "id": "generated.action.e2e",
        "name": "Generated write E2E",
        "version": "1.0.0",
        "type": "generated_capability",
        "category": "Generated",
        "runtime": "governed_action_v2",
        "risk": "write",
        "source_files": ["capability.py"],
        "entrypoint": {"file": "capability.py", "function": "run"},
        "permissions": {
            "allowed_tools": ["write.item"],
            "network_hosts": [],
            "filesystem_read": [],
            "filesystem_write": [],
            "connector_ids": [],
            "secret_names": [],
            "side_effects": ["qualified write"],
        },
        "forge": {
            "qualified": True,
            "review_decision": "approved",
            "spec_id": "spec-e2e",
            "plan_id": "plan-e2e",
            "work_order_id": "work-e2e",
            "attempt_id": "attempt-e2e",
            "candidate_revision": "candidate-e2e",
            "qualification_digest": "qualification-e2e",
            "build_id": "build-e2e",
        },
        "action_policy": {
            "owner_approval_required": True,
            "automatic_commit": False,
            "critical_actions_enabled": False,
        },
    }
    raw = (json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
    (root / "manifest.json").write_bytes(raw)
    return root, manifest, hashlib.sha256(raw).hexdigest()


def test_v3_provenance_rehydration_preserves_stage_approve_commit_boundary(tmp_path):
    effects = []
    writer = Tool(
        name="write.item",
        description="verified reversible write",
        risk=Risk.REVERSIBLE,
        handler=lambda p: effects.append(p["value"]) or {"written": p["value"]},
        verifier=lambda p, r: VerificationResult(r.get("written") == p["value"], "verified", {}),
        verification_required=True,
        rollback=lambda p, _r: effects.remove(p["value"]),
    )
    registry = Registry(writer)
    approvals = ApprovalManager(path=tmp_path / "trusted-approvals.sqlite3")
    actions = GeneratedActionService(tmp_path / "capability-forge.sqlite3", tools=registry, approvals=approvals)
    package, manifest, digest = _package(tmp_path)
    provenance = CapabilityPackageProvenance(Vault())
    signed = provenance.sign(package, expected_manifest_digest=digest)
    item = {
        "id": manifest["id"],
        "name": manifest["name"],
        "version": manifest["version"],
        "type": "generated_capability",
        "category": "Generated",
        "state": "active",
        "package_ref": package.relative_to(tmp_path).as_posix(),
        "manifest_digest": digest,
        "provenance_required": True,
        "provenance_key_id": signed["key_id"],
        "input_schema": {},
    }
    attached = rehydrate_generated_capabilities_v3(
        Catalog(item), tools=registry, data_root=tmp_path, action_service=actions, provenance=provenance
    )
    assert attached == [manifest["id"]]

    generated = registry.get(manifest["id"])
    staged = registry.dispatch(generated, {"value": 7})
    assert staged["committed"] is False
    assert effects == []
    approval_id = staged["approval_ids"][0]
    actions.approve_ticket(approval_id, owner_id="owner", device_id=None, session_id=None)
    assert effects == []

    completed = actions.commit(
        staged["proposal_id"],
        manifest=manifest,
        manifest_digest=digest,
        owner_id="owner",
        device_id=None,
        session_id=None,
    )
    assert completed["state"] == "completed"
    assert effects == [7]
    assert approvals.record(approval_id)["status"] == "completed"


def test_v3_restart_rehydration_rejects_tampered_generated_write_package(tmp_path):
    writer = Tool(
        name="write.item", description="write", risk=Risk.REVERSIBLE,
        handler=lambda p: {"written": p["value"]},
        verifier=lambda p, r: VerificationResult(r.get("written") == p["value"], "verified", {}),
        verification_required=True, rollback=lambda _p, _r: None,
    )
    registry = Registry(writer)
    actions = GeneratedActionService(
        tmp_path / "capability-forge.sqlite3", tools=registry,
        approvals=ApprovalManager(path=tmp_path / "trusted-approvals.sqlite3"),
    )
    package, manifest, digest = _package(tmp_path)
    provenance = CapabilityPackageProvenance(Vault())
    signed = provenance.sign(package, expected_manifest_digest=digest)
    item = {
        "id": manifest["id"], "name": manifest["name"], "version": manifest["version"],
        "type": "generated_capability", "category": "Generated", "state": "active",
        "package_ref": package.relative_to(tmp_path).as_posix(), "manifest_digest": digest,
        "provenance_required": True, "provenance_key_id": signed["key_id"], "input_schema": {},
    }
    (package / "capability.py").write_text("def run(payload):\n    return {'calls': []}\n", encoding="utf-8")
    attached = rehydrate_generated_capabilities_v3(
        Catalog(item), tools=registry, data_root=tmp_path, action_service=actions, provenance=provenance
    )
    assert attached == []
    assert manifest["id"] not in registry._tools
