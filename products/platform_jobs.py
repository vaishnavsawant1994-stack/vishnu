from __future__ import annotations

import hashlib
import io
import json
import os
import re
import secrets
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from .build_lifecycle import NATIVE_SIGNED_TARGETS, ProductBuildLifecycle
from .builders import build_plan
from .package_export import distribution_safe_manifest
from .platform_runners import PlatformRunnerError, validate_runner_evidence
from .runtime import ProductRuntimeSpec
from .signing import canonical_json, sha256_bytes, sign_payload
from .versioning import frozen_version


REMOTE_PLATFORM_TARGETS = ("android", "ios", "windows", "macos", "linux", "docker")
RUNNER_TOKEN_ENV = "VISHNU_PRODUCT_RUNNER_TOKEN"
RUNNER_MAX_ARTIFACT_BYTES_ENV = "VISHNU_PRODUCT_RUNNER_MAX_ARTIFACT_BYTES"
_ARTIFACT_SCHEME = "product-artifact"
_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+() -]{0,239}$")


class PlatformBuildJobError(ValueError):
    pass


def runner_configured() -> bool:
    return bool(os.environ.get(RUNNER_TOKEN_ENV, "").strip())


def runner_token_matches(value: str | None) -> bool:
    expected = os.environ.get(RUNNER_TOKEN_ENV, "").strip()
    supplied = str(value or "").strip()
    return bool(expected and supplied and secrets.compare_digest(expected, supplied))


def max_artifact_bytes() -> int:
    raw = os.environ.get(RUNNER_MAX_ARTIFACT_BYTES_ENV, "").strip()
    if not raw:
        return 512 * 1024 * 1024
    try:
        value = int(raw)
    except ValueError as exc:
        raise PlatformBuildJobError(f"{RUNNER_MAX_ARTIFACT_BYTES_ENV} must be an integer") from exc
    if value < 1024 * 1024 or value > 4 * 1024 * 1024 * 1024:
        raise PlatformBuildJobError(f"{RUNNER_MAX_ARTIFACT_BYTES_ENV} is outside the supported range")
    return value


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _zip(files: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, files[name])
    return output.getvalue()


def _filename(value: str) -> str:
    name = str(value or "").strip()
    if not _SAFE_FILENAME.fullmatch(name) or name in {".", ".."} or "/" in name or "\\" in name:
        raise PlatformBuildJobError("Runner artifact filename is invalid")
    return name


class ProductPlatformBuildJobs:
    """Create signed build jobs and accept evidence-bound external artifacts."""

    def __init__(self, store, lifecycle: ProductBuildLifecycle, artifact_root: Path):
        self.store = store
        self.lifecycle = lifecycle
        self.artifact_root = Path(artifact_root)
        self.artifact_root.mkdir(parents=True, exist_ok=True)

    def _raw_build(self, product_id: str, build_id: str) -> dict | None:
        with self.store.con() as con:
            row = con.execute(
                "SELECT * FROM product_builds WHERE id=? AND product_id=? LIMIT 1",
                (build_id, product_id),
            ).fetchone()
        if not row:
            return None
        value = dict(row)
        try:
            value["metadata"] = json.loads(value.pop("metadata_json", "{}") or "{}")
        except (TypeError, ValueError):
            value["metadata"] = {}
        return value

    def _spec(self, build: dict) -> ProductRuntimeSpec:
        snapshot = frozen_version(self.store, build["product_id"], build["version"])
        if snapshot is None:
            raise PlatformBuildJobError(
                f"Version {build['version']} must be frozen before a platform build job can be issued"
            )
        spec = ProductRuntimeSpec.load(snapshot["manifest"])
        if build["target"] not in spec.targets:
            raise PlatformBuildJobError(
                f"Target {build['target']} is not enabled in frozen version {build['version']}"
            )
        return spec

    def prepare_job(self, product_id: str, build_id: str, *, development: bool = False) -> tuple[str, bytes, dict]:
        raw = self._raw_build(product_id, build_id)
        if raw is None:
            raise KeyError(build_id)
        build = self.lifecycle.ensure(raw)
        target = str(build.get("target") or "")
        if target not in REMOTE_PLATFORM_TARGETS:
            raise PlatformBuildJobError(f"Target {target} does not use the external platform runner")
        spec = self._spec(raw)
        manifest = distribution_safe_manifest(spec.manifest)
        manifest_bytes = canonical_json(manifest)
        plan = build_plan(spec, target)
        payload = {
            "schema": "vishnu.product-build-job/v1",
            "job_id": f"{product_id}:{build_id}:{build['build_number']}",
            "product_id": product_id,
            "build_id": build_id,
            "build_number": int(build["build_number"]),
            "version": spec.version,
            "target": target,
            "created_at": _now(),
            "manifest_sha256": sha256_bytes(manifest_bytes),
            "artifact_kinds": list(plan.get("artifact_kinds") or []),
            "adapter": plan.get("adapter"),
            "development": bool(development),
            "constraints": {
                "owner_source_bundled": False,
                "owner_data_bundled": False,
                "credentials_bundled": False,
                "raw_secrets_forbidden": True,
            },
        }
        payload_bytes = canonical_json(payload)
        signature = sign_payload(payload_bytes, require_key=not development)
        envelope = {
            "payload": payload,
            "signature": signature.as_dict() if signature else None,
            "signed": signature is not None,
        }
        envelope_bytes = canonical_json(envelope)
        checksums = {
            "job.json": sha256_bytes(envelope_bytes),
            "manifest.json": sha256_bytes(manifest_bytes),
        }
        raw_job = _zip(
            {
                "job.json": envelope_bytes,
                "manifest.json": manifest_bytes,
                "checksums.json": canonical_json(checksums),
            }
        )
        name = f"{product_id}-{build_id}-{target}.vishnu-build-job"
        metadata = {
            "filename": name,
            "sha256": sha256_bytes(raw_job),
            "size": len(raw_job),
            "signed": signature is not None,
            "target": target,
            "build_id": build_id,
        }
        return name, raw_job, metadata

    def mark_running(self, product_id: str, build_id: str) -> dict:
        raw = self._raw_build(product_id, build_id)
        if raw is None:
            raise KeyError(build_id)
        build = self.lifecycle.ensure(raw)
        if build["target"] not in REMOTE_PLATFORM_TARGETS:
            raise PlatformBuildJobError("Build target is not owned by the external platform runner")
        if build["status"] in {"failed", "cancelled"}:
            build = self.lifecycle.update(product_id, build_id, status="queued")
        if build["status"] in {"requested", "queued"}:
            build = self.lifecycle.update(product_id, build_id, status="running")
        if build["status"] != "running":
            raise PlatformBuildJobError(f"Build {build_id} cannot enter runner execution from {build['status']}")
        return build

    def _validated_evidence(
        self,
        *,
        build: dict,
        product_id: str,
        build_id: str,
        filename: str,
        checksum: str,
        runner_evidence: dict,
    ):
        try:
            evidence = validate_runner_evidence(runner_evidence)
        except PlatformRunnerError as exc:
            raise PlatformBuildJobError(str(exc)) from exc
        expected = {
            "product_id": product_id,
            "build_id": build_id,
            "version": str(build["version"]),
            "target": str(build["target"]),
            "artifact_name": filename,
            "sha256": checksum,
        }
        actual = {
            "product_id": evidence.product_id,
            "build_id": evidence.build_id,
            "version": evidence.version,
            "target": evidence.target,
            "artifact_name": evidence.artifact_name,
            "sha256": evidence.sha256,
        }
        if actual != expected:
            raise PlatformBuildJobError("Runner evidence identity does not match the requested build artifact")
        if not evidence.compiler_verified:
            raise PlatformBuildJobError("Runner evidence does not verify target compilation")
        return evidence

    def accept_artifact(
        self,
        product_id: str,
        build_id: str,
        *,
        filename: str,
        expected_sha256: str,
        payload: bytes,
        runner_evidence: dict | None = None,
        platform_signing_verified: bool = False,
        runner_metadata: dict | None = None,
    ) -> dict:
        raw = self._raw_build(product_id, build_id)
        if raw is None:
            raise KeyError(build_id)
        build = self.lifecycle.ensure(raw)
        target = str(build.get("target") or "")
        if target not in REMOTE_PLATFORM_TARGETS:
            raise PlatformBuildJobError("Build target is not owned by the external platform runner")
        if build["status"] not in {"requested", "queued", "running"}:
            raise PlatformBuildJobError(f"Build {build_id} cannot accept an artifact from {build['status']}")
        if len(payload) == 0:
            raise PlatformBuildJobError("Runner artifact is empty")
        if len(payload) > max_artifact_bytes():
            raise PlatformBuildJobError("Runner artifact exceeds the configured size limit")
        safe_name = _filename(filename)
        checksum = hashlib.sha256(payload).hexdigest()
        expected = str(expected_sha256 or "").strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", expected) or checksum != expected:
            raise PlatformBuildJobError("Runner artifact SHA-256 does not match the supplied digest")

        # Older authenticated runner transports reported only a signing boolean.
        # Bind that report to server-known build identity instead of accepting
        # client-supplied identity fields. iOS/macOS remain non-ready because the
        # synthesized evidence deliberately cannot claim provisioning/notarization.
        if runner_evidence is None:
            runner_evidence = {
                "schema": "vishnu.platform-runner-evidence/v1",
                "product_id": product_id,
                "build_id": build_id,
                "version": str(build["version"]),
                "target": target,
                "mode": "production",
                "host_os": str((runner_metadata or {}).get("host_os") or "external-runner"),
                "artifact_name": safe_name,
                "artifact_kind": str((runner_metadata or {}).get("artifact_kind") or Path(safe_name).suffix.lstrip(".") or target),
                "sha256": checksum,
                "compiler_verified": True,
                "signing_verified": bool(platform_signing_verified),
                "provisioning_verified": False,
                "notarization_verified": False,
                "metadata": dict(runner_metadata or {}),
            }
        evidence = self._validated_evidence(
            build=build,
            product_id=product_id,
            build_id=build_id,
            filename=safe_name,
            checksum=checksum,
            runner_evidence=runner_evidence,
        )

        if build["status"] in {"requested", "queued"}:
            build = self.mark_running(product_id, build_id)

        directory = (self.artifact_root / product_id / build_id).resolve()
        root = self.artifact_root.resolve()
        try:
            directory.relative_to(root)
        except ValueError as exc:
            raise PlatformBuildJobError("Runner artifact destination escapes the artifact root") from exc
        directory.mkdir(parents=True, exist_ok=True)
        final = (directory / safe_name).resolve()
        try:
            final.relative_to(directory)
        except ValueError as exc:
            raise PlatformBuildJobError("Runner artifact path is invalid") from exc
        temporary = directory / f".{safe_name}.{secrets.token_hex(4)}.tmp"
        temporary.write_bytes(payload)
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != checksum:
            temporary.unlink(missing_ok=True)
            raise PlatformBuildJobError("Runner artifact checksum failed after write")
        temporary.replace(final)

        metadata = dict(raw.get("metadata") or {})
        metadata["platform_runner"] = {
            "received_at": _now(),
            "evidence": evidence.as_dict(),
        }
        with self.store.con() as con:
            con.execute(
                "UPDATE product_builds SET metadata_json=? WHERE id=? AND product_id=?",
                (json.dumps(metadata, sort_keys=True, separators=(",", ":")), build_id, product_id),
            )

        production_ready = evidence.production_ready
        uri = f"{_ARTIFACT_SCHEME}://{product_id}/{build_id}/{safe_name}" if production_ready else ""
        registered_checksum = checksum if production_ready else ""
        signing_verified = production_ready if target in NATIVE_SIGNED_TARGETS else False
        return self.lifecycle.update(
            product_id,
            build_id,
            status="succeeded",
            artifact_name=safe_name,
            artifact_uri=uri,
            checksum=registered_checksum,
            signing_verified=signing_verified,
            failure_reason="",
            verified_builder=True,
        )

    def mark_failed(self, product_id: str, build_id: str, reason: str) -> dict:
        raw = self._raw_build(product_id, build_id)
        if raw is None:
            raise KeyError(build_id)
        build = self.lifecycle.ensure(raw)
        if build["target"] not in REMOTE_PLATFORM_TARGETS:
            raise PlatformBuildJobError("Build target is not owned by the external platform runner")
        if build["status"] in {"requested", "queued"}:
            build = self.mark_running(product_id, build_id)
        if build["status"] != "running":
            raise PlatformBuildJobError(f"Build {build_id} cannot fail from {build['status']}")
        return self.lifecycle.update(
            product_id,
            build_id,
            status="failed",
            failure_reason=str(reason or "Platform runner failed")[:2000],
        )
