from __future__ import annotations

from types import SimpleNamespace

import pytest

from future_intelligence.capability_forge.governed_activation_v3 import GovernedCapabilityActivationServiceV3
from future_intelligence.capability_forge.provenance import CapabilityPackageProvenance, CapabilityProvenanceError


class Vault:
    def __init__(self): self.data = {}
    def get(self, key, default=None): return self.data.get(key, default)
    def set(self, key, value): self.data[key] = value
    def delete(self, key): self.data.pop(key, None)


class Lifecycle:
    def get_build(self, build_id):
        return {"id": build_id, "status": "packaged", "payload": {"provenance_required": True}}


def test_missing_sidecar_cannot_downgrade_v3_package_to_legacy(tmp_path):
    package_root = tmp_path / "package"
    package_root.mkdir()
    package = SimpleNamespace(
        package_path=package_root,
        build_id="build:v3",
        manifest_digest="0" * 64,
        capability_id="generated.v3",
        version="1.0.0",
    )
    service = GovernedCapabilityActivationServiceV3(
        catalog=SimpleNamespace(),
        approvals=SimpleNamespace(),
        tools=SimpleNamespace(),
        data_root=tmp_path,
        lifecycle=Lifecycle(),
        provenance=CapabilityPackageProvenance(Vault()),
        rollout=None,
    )
    with pytest.raises(CapabilityProvenanceError, match="missing"):
        service._verify_v3_package(package, require_broad=False)
