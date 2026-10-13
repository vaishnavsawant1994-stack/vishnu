from __future__ import annotations

from .build_service import CapabilityForgeBuildService


class ProductionReadyCapabilityForgeBuildService(CapabilityForgeBuildService):
    """V3 build service: qualified package -> provenance -> internal canary.

    It deliberately inherits the existing Engineering/Candidate qualification
    path and adds no build authority. Signing happens only after the base service
    has accepted an independently reviewed qualified candidate.
    """

    def __init__(self, *args, provenance, rollout=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.provenance = provenance
        self.rollout = rollout

    def execute_and_package(self, *args, **kwargs):
        candidate, package = super().execute_and_package(*args, **kwargs)
        if package is None:
            return candidate, None
        evidence = self.provenance.sign(
            package.package_path,
            expected_manifest_digest=package.manifest_digest,
        )
        if self.rollout is not None:
            self.rollout.start(
                capability_id=package.capability_id,
                version=package.version,
                manifest_digest=package.manifest_digest,
            )
        if self.events is not None:
            self.events.emit(
                "capability_forge.provenance_signed",
                capability_id=package.capability_id,
                version=package.version,
                manifest_digest=package.manifest_digest,
                key_id=evidence.get("key_id"),
                file_count=evidence.get("file_count"),
            )
            self.events.emit(
                "capability_forge.rollout_started",
                capability_id=package.capability_id,
                version=package.version,
                stage="internal",
            )
        return candidate, package
