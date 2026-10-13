from __future__ import annotations

from pathlib import Path
from typing import Any

from integrations.discovery.generated_catalog import register_generated_capability

from .governed_activation_v2 import GovernedCapabilityActivationServiceV2


class GovernedCapabilityActivationServiceV3(GovernedCapabilityActivationServiceV2):
    """V3 activation adds provenance and staged-rollout evidence.

    Legacy V1/V2 packages remain operable for compatibility. Any package built
    with a V3 provenance sidecar must pass signature verification and reach the
    broad_eligible canary stage before the existing exact activation approval can
    even be requested. Activation itself is still owned by the V2/canonical
    approval implementation.
    """

    def __init__(self, *args, provenance=None, rollout=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.provenance = provenance
        self.rollout = rollout

    @staticmethod
    def _has_provenance(package) -> bool:
        try:
            return (Path(package.package_path) / "provenance.json").is_file()
        except Exception:
            return False

    def _verify_v3_package(self, package, *, require_broad: bool) -> dict[str, Any] | None:
        if not self._has_provenance(package):
            # Backward-compatible internal operation for already-qualified V1/V2
            # packages. Production readiness reports these as not V3-provenanced.
            return None
        if self.provenance is None:
            raise RuntimeError("Capability Forge V3 provenance verifier is unavailable")
        evidence = self.provenance.verify(
            package.package_path,
            expected_manifest_digest=str(package.manifest_digest),
        )
        if require_broad:
            if self.rollout is None:
                raise RuntimeError("Capability Forge V3 canary rollout is unavailable")
            rollout = self.rollout.get(str(package.capability_id), str(package.version))
            if rollout.get("manifest_digest") != str(package.manifest_digest):
                raise PermissionError("Forge rollout package lineage does not match activation package")
            if rollout.get("stage") != "broad_eligible" or rollout.get("status") != "running":
                raise PermissionError("Forge package is not broad-eligible after staged canary qualification")
        return evidence

    def request_activation(self, package, *, owner_id="owner", device_id=None, session_id=None):
        self._verify_v3_package(package, require_broad=True)
        return super().request_activation(
            package,
            owner_id=owner_id,
            device_id=device_id,
            session_id=session_id,
        )

    def activate(self, package, *, ticket_id, owner_id="owner", device_id=None, session_id=None):
        provenance = self._verify_v3_package(package, require_broad=True)
        result = super().activate(
            package,
            ticket_id=ticket_id,
            owner_id=owner_id,
            device_id=device_id,
            session_id=session_id,
        )
        if provenance is not None:
            current = self.catalog.get(str(package.capability_id))
            if not current or current.get("type") != "generated_capability":
                raise RuntimeError("activated generated capability disappeared from catalog")
            enriched = {
                **current,
                "provenance_required": True,
                "provenance_key_id": provenance["key_id"],
                "provenance_file_count": provenance["file_count"],
                "rollout_stage": "broad_eligible",
            }
            register_generated_capability(self.catalog, enriched)
            result = {**result, "capability": enriched, "provenance_verified": True, "rollout_stage": "broad_eligible"}
            if self.events is not None:
                self.events.emit(
                    "capability_forge.v3_activated",
                    capability_id=str(package.capability_id),
                    version=str(package.version),
                    provenance_key_id=provenance["key_id"],
                    rollout_stage="broad_eligible",
                )
        return result

    def rollback(self, capability_id: str, *, ticket_id: str, target_activation_id: str,
                 owner_id="owner", device_id=None, session_id=None):
        if self.lifecycle is None:
            raise RuntimeError("Forge lifecycle store is required for rollback")
        target = self.lifecycle.get_activation(str(target_activation_id))
        if target:
            package_path = self.data_root / str(target.get("package_ref") or "")
            sidecar = package_path / "provenance.json"
            if sidecar.is_file():
                if self.provenance is None:
                    raise RuntimeError("Capability Forge V3 provenance verifier is unavailable")
                self.provenance.verify(
                    package_path,
                    expected_manifest_digest=str(target.get("manifest_digest") or ""),
                )
        result = super().rollback(
            capability_id,
            ticket_id=ticket_id,
            target_activation_id=target_activation_id,
            owner_id=owner_id,
            device_id=device_id,
            session_id=session_id,
        )
        if target and (self.data_root / str(target.get("package_ref") or "") / "provenance.json").is_file():
            current = self.catalog.get(str(capability_id))
            if current and current.get("type") == "generated_capability":
                evidence = self.provenance.verify(
                    self.data_root / str(target.get("package_ref") or ""),
                    expected_manifest_digest=str(target.get("manifest_digest") or ""),
                )
                enriched = {
                    **current,
                    "provenance_required": True,
                    "provenance_key_id": evidence["key_id"],
                    "provenance_file_count": evidence["file_count"],
                }
                register_generated_capability(self.catalog, enriched)
                result = {**result, "capability": enriched, "provenance_verified": True}
        return result
