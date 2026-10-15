from __future__ import annotations

import atexit
import os
import re
import subprocess
from pathlib import Path
from typing import Any, MutableMapping

from devices.registry import DeviceRegistry
from sensorium.sensor_permissions import SensorPermissionStore

from .runtime import TrustContinuityRuntime, build_trust_continuity_runtime


_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
_PROCESS_ID = "vishnu-runtime"


def _commit_sha(runtime: MutableMapping[str, Any]) -> str:
    """Resolve the running revision without trusting arbitrary short labels."""
    candidates = (
        runtime.get("running_git_revision"),
        os.environ.get("VISHNU_TRUSTED_RELEASE_REVISION"),
        os.environ.get("GITHUB_SHA"),
    )
    for candidate in candidates:
        value = str(candidate or "").strip()
        if _SHA_RE.fullmatch(value):
            return value.lower()
    try:
        project_root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
        value = result.stdout.strip()
        if _SHA_RE.fullmatch(value):
            return value.lower()
    except (OSError, subprocess.SubprocessError):
        pass
    # Deliberately cannot be production-ready until exact revision evidence is
    # available. ProductionReadinessManager will have no passing exact-head
    # software checks for this sentinel.
    return "unversioned"


def _data_dir(runtime: MutableMapping[str, Any]) -> Path:
    settings = runtime.get("settings")
    path = getattr(settings, "data_dir", None)
    if path is None:
        raise RuntimeError("canonical Vishnu data directory is unavailable")
    return Path(path)


def attach_trust_continuity_runtime(
    runtime: MutableMapping[str, Any],
) -> TrustContinuityRuntime:
    """Bind the campaign to canonical Vishnu security/device authorities.

    This function is intentionally idempotent. It constructs no replacement
    DeviceRegistry, OwnerAccessStore, SecretVault, OAuth, approval or ToolRegistry
    authority. If a canonical dependency is absent the corresponding sensitive
    function stays unavailable/fail-closed.
    """
    existing = runtime.get("trust_continuity")
    if isinstance(existing, TrustContinuityRuntime):
        return existing

    registry = runtime.get("device_registry")
    owner_access = runtime.get("owner_access")
    tools = runtime.get("tools")
    oauth = runtime.get("oauth")
    if registry is None or owner_access is None or tools is None:
        raise RuntimeError("canonical Vishnu trust authorities are unavailable")

    identity = owner_access.identity()
    owner_id = str((identity or {}).get("owner_id") or "").strip()
    if not owner_id:
        # The product can run in onboarding/reduced state, but Trust/Continuity
        # must not invent an owner identity before the canonical ceremony.
        owner_id = "uninitialized-owner"

    data_dir = _data_dir(runtime)
    events = runtime.get("events")
    sensor_permissions = runtime.get("sensor_permissions")
    if sensor_permissions is None:
        sensor_permissions = SensorPermissionStore(
            data_dir / "sensor-permissions.sqlite3",
            events=events,
        )
        runtime["sensor_permissions"] = sensor_permissions

    def owner_authenticator(candidate_owner: str, method: str, proof: str) -> bool:
        if not identity or candidate_owner != owner_id:
            return False
        if method == "recovery_code":
            return bool(owner_access.consume_recovery_code(proof))
        # Passkeys and encrypted disaster-recovery packages already have
        # dedicated canonical WebAuthn/onboarding ceremonies. A generic string
        # proof here would be a security downgrade, so those methods fail closed.
        return False

    def register_restored_device(candidate_owner: str, metadata: dict[str, Any]) -> dict[str, str]:
        if not identity or candidate_owner != owner_id:
            raise PermissionError("stable owner identity is unavailable")
        platform = str(metadata.get("platform") or metadata.get("device_platform") or "unknown")[:40]
        name = str(metadata.get("name") or metadata.get("device_name") or f"Restored {platform}")[:120]
        device, credential = registry.enroll(name, platform)
        registry.set_permissions(device["id"], DeviceRegistry.OWNER_SCOPES)
        registry.set_metadata(device["id"], "owner_id", owner_id)
        registry.set_metadata(device["id"], "restored", "true")
        return {"device_id": str(device["id"]), "device_credential": str(credential)}

    def revoke_device(device_id: str) -> None:
        if not registry.revoke(device_id):
            raise KeyError("active device not found")
        try:
            sensor_permissions.revoke_all(device_id)
        except Exception:
            # Device credential revocation is authoritative. Sensor cleanup is
            # best effort after that fail-closed boundary.
            pass

    def stop_sensing() -> None:
        for device in registry.list():
            if not bool(device.get("revoked")):
                sensor_permissions.revoke_all(str(device["id"]))

    def stop_actions() -> None:
        tools.set_emergency_stop(True)

    def emergency_stop(enabled: bool) -> None:
        tools.set_emergency_stop(bool(enabled))

    oauth_providers = runtime.get("oauth_providers") or {}

    def disconnect_provider(connection_id: str) -> None:
        if oauth is None:
            raise RuntimeError("canonical OAuth authority is unavailable")
        provider = oauth_providers.get(connection_id) if isinstance(oauth_providers, dict) else None
        oauth.unlink(
            str(connection_id),
            provider=provider,
            connector_id=str(connection_id),
            owner_id=owner_id,
            attempt_provider_revocation=True,
        )

    def device_snapshot() -> dict[str, Any]:
        devices = registry.list()
        return {
            "count": len(devices),
            "active": sum(1 for item in devices if not bool(item.get("revoked"))),
            "devices": [
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "platform": item.get("platform"),
                    "revoked": bool(item.get("revoked")),
                    "last_seen_at": item.get("last_seen_at"),
                    "permissions": list(item.get("permissions") or []),
                }
                for item in devices
            ],
        }

    def integration_snapshot() -> dict[str, Any]:
        manager = runtime.get("integrations")
        if manager is None:
            return {"available": False, "connections": []}
        try:
            connections = manager.list()
        except Exception:
            return {"available": False, "connections": []}
        # Canonical integration list is expected to be metadata-only. Defensively
        # project only non-secret status fields here.
        safe = []
        for item in connections if isinstance(connections, list) else []:
            if not isinstance(item, dict):
                continue
            safe.append(
                {
                    key: item.get(key)
                    for key in ("id", "provider", "name", "status", "health", "scopes")
                    if key in item
                }
            )
        return {"available": True, "connections": safe}

    tc = build_trust_continuity_runtime(
        data_dir=data_dir,
        commit_sha=_commit_sha(runtime),
        owner_id=owner_id,
        is_trusted_device=registry.is_active,
        # Work/future layers may plan and pause, but cannot self-authorize a
        # consequential action. Existing ToolRegistry/ApprovalManager remain the
        # only execution path.
        approval_check=lambda _job_id, _step: False,
        proposal_approval_check=lambda _proposal_id: False,
        oauth_manager=oauth,
        owner_authenticator=owner_authenticator if identity else None,
        register_device=register_restored_device if identity else None,
        revoke_device=revoke_device,
        stop_sensing=stop_sensing,
        stop_actions=stop_actions,
        disconnect_provider=disconnect_provider,
        emergency_stop=emergency_stop,
        snapshot_sources={
            "devices": device_snapshot,
            "integrations": integration_snapshot,
            "memory": lambda: {
                "retention": "owner-policy",
                "authority": "canonical-memory-plus-trust-metadata",
            },
            "actions": lambda: {
                "emergency_stop": bool(getattr(tools, "emergency_stop", False)),
                "execution_authority": "ToolRegistry/ApprovalManager",
            },
        },
    )

    tc.health.register_probe("device_registry", lambda: {"healthy": True, "detail": f"{len(registry.list())} devices"})
    tc.health.register_probe("tool_registry", lambda: {"healthy": tools is not None, "detail": "canonical"})
    tc.health.register_probe("owner_identity", lambda: {"healthy": bool(owner_access.identity()), "detail": "initialized" if owner_access.identity() else "onboarding"})
    tc.health.register_probe("oauth", lambda: {"healthy": oauth is not None, "detail": "canonical" if oauth is not None else "unavailable"})

    previous = tc.store.get("process_state", _PROCESS_ID)
    clean_previous = previous is None or previous["status"] == "stopped" or not bool(previous["payload"].get("running"))
    tc.health.mark_process_start(_PROCESS_ID, clean_previous_shutdown=clean_previous)

    def _clean_shutdown() -> None:
        try:
            current = tc.store.get("process_state", _PROCESS_ID)
            if current is not None and current["status"] == "running":
                tc.health.mark_shutdown(_PROCESS_ID)
        except Exception:
            pass

    atexit.register(_clean_shutdown)
    runtime["trust_continuity"] = tc
    runtime["trust_continuity_owner_id"] = owner_id
    runtime["trust_continuity_revision"] = tc.readiness.commit_sha
    return tc
