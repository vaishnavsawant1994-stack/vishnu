from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from .store import TrustContinuityStore, utcnow


PRODUCTION_REQUIREMENTS = (
    "android_release_signing",
    "ios_distribution_signing",
    "ios_provisioning",
    "windows_authenticode",
    "macos_codesigning",
    "macos_notarization",
    "container_attestation",
    "deployment_worker_identity",
    "backup_restore_drill",
    "rollback_drill",
    "health_observability",
)

PHYSICAL_PLATFORMS = {"android", "ios", "windows", "macos", "linux", "watchos", "wearos"}
NON_PHYSICAL_PROVIDERS = {"emulator", "simulator", "hosted_vm", "virtual_simulation", "ci_runner"}


@dataclass(frozen=True)
class ReadinessResult:
    software_ready: bool
    externally_qualified: bool
    production_ready: bool
    pending: tuple[str, ...]
    commit_sha: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "software_ready": self.software_ready,
            "externally_qualified": self.externally_qualified,
            "production_ready": self.production_ready,
            "pending": list(self.pending),
            "commit_sha": self.commit_sha,
        }


class ProductionReadinessManager:
    """Fail-closed readiness/evidence registry.

    Secret material is never accepted. Records contain references, hashes and
    attestation metadata only. Real signing/notarization/provider evidence remains
    externally owned and cannot be manufactured by CI.
    """

    def __init__(self, store: TrustContinuityStore, *, commit_sha: str):
        if len(commit_sha) < 7:
            raise ValueError("an exact or abbreviated commit SHA is required")
        self.store = store
        self.commit_sha = commit_sha

    def declare_software_check(self, name: str, passed: bool, *, detail: str = "") -> dict[str, Any]:
        record = {
            "kind": "software_check",
            "name": name,
            "passed": bool(passed),
            "detail": detail[:2000],
            "commit_sha": self.commit_sha,
            "checked_at": utcnow(),
        }
        result = self.store.put("readiness_software", name, record, status="passed" if passed else "failed")
        self.store.audit("production", "software_check", subject=name, payload=record)
        return result

    def register_external_evidence(
        self,
        requirement: str,
        *,
        evidence_id: str,
        provider: str,
        artifact_digest: str,
        verified: bool,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if requirement not in PRODUCTION_REQUIREMENTS:
            raise ValueError("unknown production readiness requirement")
        if not evidence_id or not provider:
            raise ValueError("evidence_id and provider are required")
        digest = artifact_digest.lower().removeprefix("sha256:")
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise ValueError("artifact_digest must be a SHA-256 digest")
        safe_metadata = dict(metadata or {})
        forbidden = {"token", "password", "secret", "private_key", "credential"}
        if forbidden.intersection(key.lower() for key in safe_metadata):
            raise ValueError("secret material is forbidden in readiness evidence")
        payload = {
            "kind": "external_evidence",
            "requirement": requirement,
            "evidence_id": evidence_id[:200],
            "provider": provider[:200],
            "artifact_digest": digest,
            "verified": bool(verified),
            "commit_sha": self.commit_sha,
            "metadata": safe_metadata,
            "recorded_at": utcnow(),
        }
        result = self.store.put(
            "readiness_external",
            requirement,
            payload,
            status="verified" if verified else "unverified",
        )
        self.store.audit("production", "external_evidence", subject=requirement, payload=payload)
        return result

    def record_drill(
        self,
        drill: str,
        *,
        passed: bool,
        backup_digest: str | None = None,
        restore_verified: bool = False,
        rollback_verified: bool = False,
        recovery_seconds: float | None = None,
        detail: str = "",
    ) -> dict[str, Any]:
        if drill not in {"backup_restore_drill", "rollback_drill"}:
            raise ValueError("unsupported recovery drill")
        payload = {
            "drill": drill,
            "passed": bool(passed),
            "backup_digest": backup_digest,
            "restore_verified": bool(restore_verified),
            "rollback_verified": bool(rollback_verified),
            "recovery_seconds": recovery_seconds,
            "detail": detail[:4000],
            "commit_sha": self.commit_sha,
            "recorded_at": utcnow(),
        }
        result = self.store.put("recovery_drill", drill, payload, status="passed" if passed else "failed")
        self.store.audit("production", "recovery_drill", subject=drill, payload=payload)
        return result

    def readiness(self) -> ReadinessResult:
        software = self.store.list("readiness_software", limit=1000)
        software_ready = bool(software) and all(row["status"] == "passed" for row in software)
        evidence = {row["record_id"]: row for row in self.store.list("readiness_external", limit=1000)}
        drills = {row["record_id"]: row for row in self.store.list("recovery_drill", limit=100)}
        pending: list[str] = []
        for requirement in PRODUCTION_REQUIREMENTS:
            if requirement in {"backup_restore_drill", "rollback_drill"}:
                if drills.get(requirement, {}).get("status") != "passed":
                    pending.append(requirement)
            elif evidence.get(requirement, {}).get("status") != "verified":
                pending.append(requirement)
        externally_qualified = not pending
        return ReadinessResult(
            software_ready=software_ready,
            externally_qualified=externally_qualified,
            production_ready=software_ready and externally_qualified,
            pending=tuple(pending),
            commit_sha=self.commit_sha,
        )


class BackupRestoreVerifier:
    """Integrity verifier used by backup/restore and rollback drills."""

    @staticmethod
    def sha256_file(path: str | Path) -> str:
        digest = hashlib.sha256()
        with Path(path).open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @classmethod
    def verify_equal(cls, source: str | Path, restored: str | Path) -> dict[str, Any]:
        source_hash = cls.sha256_file(source)
        restored_hash = cls.sha256_file(restored)
        return {
            "source_sha256": source_hash,
            "restored_sha256": restored_hash,
            "verified": source_hash == restored_hash,
        }


class PhysicalL4Qualification:
    """Records physical-device evidence and refuses virtual providers as L4."""

    REQUIRED_METRICS = {
        "battery",
        "thermal",
        "background_restrictions",
        "permission_ui",
        "disconnect_reconnect",
    }

    def __init__(self, store: TrustContinuityStore, *, commit_sha: str):
        self.store = store
        self.commit_sha = commit_sha

    def record(
        self,
        *,
        device_id: str,
        platform: str,
        provider_class: str,
        hardware_fingerprint: str,
        scenarios: dict[str, bool],
        metrics: dict[str, Any],
        evidence_digest: str,
    ) -> dict[str, Any]:
        platform = platform.lower()
        provider_class = provider_class.lower()
        if platform not in PHYSICAL_PLATFORMS:
            raise ValueError("unsupported L4 platform")
        if provider_class in NON_PHYSICAL_PROVIDERS or provider_class != "physical_device":
            raise ValueError("L4 evidence must come from a physical device")
        if not hardware_fingerprint:
            raise ValueError("hardware fingerprint is required")
        missing_metrics = self.REQUIRED_METRICS - set(metrics)
        if missing_metrics:
            raise ValueError(f"missing L4 metrics: {sorted(missing_metrics)}")
        digest = evidence_digest.lower().removeprefix("sha256:")
        if len(digest) != 64:
            raise ValueError("evidence_digest must be SHA-256")
        passed = bool(scenarios) and all(bool(value) for value in scenarios.values())
        payload = {
            "device_id": device_id,
            "platform": platform,
            "provider_class": provider_class,
            "hardware_fingerprint_hash": hashlib.sha256(hardware_fingerprint.encode()).hexdigest(),
            "scenarios": scenarios,
            "metrics": metrics,
            "evidence_digest": digest,
            "commit_sha": self.commit_sha,
            "qualification_level": "L4" if passed else "L4_FAILED",
            "recorded_at": utcnow(),
        }
        result = self.store.put(
            "l4_evidence",
            f"{platform}:{device_id}",
            payload,
            status="passed" if passed else "failed",
            device_id=device_id,
        )
        self.store.audit("qualification", "l4_physical_evidence", actor=device_id, subject=platform, payload=payload)
        return result

    def platform_status(self) -> dict[str, str]:
        rows = self.store.list("l4_evidence", limit=1000)
        result = {platform: "pending" for platform in PHYSICAL_PLATFORMS}
        for row in rows:
            platform = row["payload"]["platform"]
            if row["status"] == "passed":
                result[platform] = "L4"
            elif result[platform] != "L4":
                result[platform] = "failed"
        return result


class DeploymentTransaction:
    """Crash/restart-safe release transaction metadata, not a deployment authority."""

    def __init__(self, store: TrustContinuityStore):
        self.store = store

    def begin(self, *, target: str, from_version: str, to_version: str, artifact_digest: str) -> str:
        tx_id = uuid4().hex
        payload = {
            "target": target,
            "from_version": from_version,
            "to_version": to_version,
            "artifact_digest": artifact_digest,
            "phase": "prepared",
            "verified": False,
            "rollback_available": True,
            "started_at": utcnow(),
        }
        self.store.put("deployment_tx", tx_id, payload, status="prepared")
        self.store.audit("deployment", "prepared", subject=tx_id, payload=payload)
        return tx_id

    def transition(self, tx_id: str, phase: str, *, verified: bool = False, detail: str = "") -> dict[str, Any]:
        if phase not in {"installing", "health_check", "committed", "rolling_back", "rolled_back", "failed"}:
            raise ValueError("invalid deployment phase")
        row = self.store.get("deployment_tx", tx_id)
        if row is None:
            raise KeyError(tx_id)
        payload = dict(row["payload"])
        payload.update({"phase": phase, "verified": bool(verified), "detail": detail[:4000], "updated_at": utcnow()})
        if phase == "committed" and not verified:
            raise ValueError("a deployment cannot commit without a verified health check")
        status = "complete" if phase in {"committed", "rolled_back"} else phase
        result = self.store.put("deployment_tx", tx_id, payload, status=status)
        self.store.audit("deployment", phase, subject=tx_id, payload={"verified": verified, "detail": detail[:1000]})
        return result
