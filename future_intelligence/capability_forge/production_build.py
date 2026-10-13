from __future__ import annotations

from .build_service import CapabilityForgeBuildService


class ProductionReadyCapabilityForgeBuildService(CapabilityForgeBuildService):
    """V3 build service: qualified package -> provenance -> internal canary.

    It deliberately inherits the existing Engineering/Candidate qualification
    path and adds no build authority. Signing happens only after the base service
    has accepted an independently reviewed qualified candidate. A V3 build is
    kept activation-ineligible if provenance signing fails.
    """

    def __init__(self, *args, provenance, rollout=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.provenance = provenance
        self.rollout = rollout

    def _record_provenance_state(self, package, *, status: str, patch: dict) -> None:
        if self.lifecycle is None:
            return
        build = self.lifecycle.get_build(str(package.build_id))
        if not build:
            raise RuntimeError("Forge packaged build lineage disappeared before provenance recording")
        payload = {**dict(build.get("payload") or {}), **dict(patch or {})}
        self.lifecycle.record_build(
            build_id=str(build["id"]),
            spec_id=str(build["spec_id"]),
            plan_id=str(build["plan_id"]),
            work_order_id=str(build["work_order_id"]),
            attempt_id=str(build["attempt_id"]),
            candidate_revision=str(build["candidate_revision"]),
            status=str(status),
            payload=payload,
        )

    def execute_and_package(self, *args, **kwargs):
        candidate, package = super().execute_and_package(*args, **kwargs)
        if package is None:
            return candidate, None
        try:
            evidence = self.provenance.sign(
                package.package_path,
                expected_manifest_digest=package.manifest_digest,
            )
            self._record_provenance_state(
                package,
                status="packaged",
                patch={
                    "provenance_required": True,
                    "provenance_key_id": evidence.get("key_id"),
                    "provenance_file_count": evidence.get("file_count"),
                },
            )
        except Exception as exc:
            self._record_provenance_state(
                package,
                status="provenance_failed",
                patch={
                    "provenance_required": True,
                    "provenance_error_type": type(exc).__name__,
                },
            )
            if self.events is not None:
                self.events.emit(
                    "capability_forge.provenance_failed",
                    capability_id=package.capability_id,
                    version=package.version,
                    manifest_digest=package.manifest_digest,
                    error_type=type(exc).__name__,
                )
            raise
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
