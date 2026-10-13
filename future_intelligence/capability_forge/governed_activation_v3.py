from __future__ import annotations

from pathlib import Path
from typing import Any

from integrations.discovery.generated_catalog import register_generated_capability

from .governed_activation_v2 import GovernedCapabilityActivationServiceV2


class GovernedCapabilityActivationServiceV3(GovernedCapabilityActivationServiceV2):
    """V3 activation adds provenance and staged-rollout evidence.

    Legacy V1/V2 packages remain operable for compatibility. V3 provenance is
    bound into durable build lineage, so deleting a provenance sidecar cannot
    downgrade a V3 package into the legacy compatibility path.
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

    def _build_provenance(self, build_id: str) -> dict[str, Any]:
        if self.lifecycle is None:
            return {}
        build = self.lifecycle.get_build(str(build_id))
        if not build:
            return {}
        return dict(build.get("payload") or {})

    def _verify_v3_package(self, package, *, require_broad: bool) -> dict[str, Any] | None:
        build_payload = self._build_provenance(str(package.build_id))
        required = bool(build_payload.get("provenance_required")) or self._has_provenance(package)
        if not required:
            # Backward-compatible internal operation for already-qualified V1/V2
            # packages that predate durable V3 provenance lineage.
            return None
        if self.provenance is None:
            raise RuntimeError("Capability Forge V3 provenance verifier is unavailable")
        evidence = self.provenance.verify(
            package.package_path,
            expected_manifest_digest=str(package.manifest_digest),
        )
        expected_key = str(build_payload.get("provenance_key_id") or "")
        if expected_key and evidence.get("key_id") != expected_key:
            raise PermissionError("Forge package provenance key does not match durable build lineage")
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
        target_provenance = None
        if target:
            package_path = self.data_root / str(target.get("package_ref") or "")
            build_payload = self._build_provenance(str(target.get("build_id") or ""))
            required = bool(build_payload.get("provenance_required")) or (package_path / "provenance.json").is_file()
            if required:
                if self.provenance is None:
                    raise RuntimeError("Capability Forge V3 provenance verifier is unavailable")
                target_provenance = self.provenance.verify(
                    package_path,
                    expected_manifest_digest=str(target.get("manifest_digest") or ""),
                )
                expected_key = str(build_payload.get("provenance_key_id") or "")
                if expected_key and target_provenance.get("key_id") != expected_key:
                    raise PermissionError("rollback package provenance key does not match durable build lineage")
        result = super().rollback(
            capability_id,
            ticket_id=ticket_id,
            target_activation_id=target_activation_id,
            owner_id=owner_id,
            device_id=device_id,
            session_id=session_id,
        )
        if target and target_provenance is not None:
            current = self.catalog.get(str(capability_id))
            if current and current.get("type") == "generated_capability":
                enriched = {
                    **current,
                    "provenance_required": True,
                    "provenance_key_id": target_provenance["key_id"],
                    "provenance_file_count": target_provenance["file_count"],
                }
                register_generated_capability(self.catalog, enriched)
                result = {**result, "capability": enriched, "provenance_verified": True}
        return result
