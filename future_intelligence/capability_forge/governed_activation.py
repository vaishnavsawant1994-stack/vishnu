from __future__ import annotations

from .activation import CapabilityActivationService


class GovernedCapabilityActivationService(CapabilityActivationService):
    """Activation service that requires server-recorded qualified package lineage."""

    def _require_packaged_lineage(self, package) -> dict:
        if self.lifecycle is None:
            raise PermissionError("Forge lifecycle evidence is required before activation")
        build = self.lifecycle.get_build(str(package.build_id))
        if not build or str(build.get("status")) != "packaged":
            raise PermissionError("generated capability has no server-recorded packaged build")
        payload = dict(build.get("payload") or {})
        checks = {
            "capability_id": str(package.capability_id),
            "version": str(package.version),
            "manifest_digest": str(package.manifest_digest),
        }
        for key, expected in checks.items():
            if str(payload.get(key) or "") != expected:
                raise PermissionError(f"Forge packaged build {key} lineage mismatch")
        if str(build.get("spec_id") or "") != str(dict(package.manifest.get("forge") or {}).get("spec_id") or ""):
            raise PermissionError("Forge packaged build specification lineage mismatch")
        if str(build.get("plan_id") or "") != str(dict(package.manifest.get("forge") or {}).get("plan_id") or ""):
            raise PermissionError("Forge packaged build plan lineage mismatch")
        return build

    def request_activation(self, package, **kwargs):
        self._require_packaged_lineage(package)
        return super().request_activation(package, **kwargs)

    def activate(self, package, **kwargs):
        self._require_packaged_lineage(package)
        return super().activate(package, **kwargs)
