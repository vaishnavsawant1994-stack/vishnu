from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from uuid import uuid4

from .store import TrustContinuityStore, utcnow


DATA_POLICIES = {"device_only", "progress_only", "sync_everywhere", "on_demand"}


@dataclass(frozen=True)
class RecoveryResult:
    owner_id: str
    restored_device_id: str
    revoked_device_id: str | None
    recovery_method: str
    # Returned once to the caller when the canonical device authority issues a
    # new credential. It is deliberately never persisted in TrustContinuityStore.
    device_credential: str | None = None


class UniversalOwnerRecovery:
    """Orchestrates owner restore without introducing a master-device dependency.

    Authentication and device credential issuance are delegated to existing
    identity/device authorities supplied by the runtime. Restore challenges are
    short-lived and atomically single-consumption; recovery proofs and issued
    device credentials are never stored in this metadata database.
    """

    def __init__(
        self,
        store: TrustContinuityStore,
        *,
        owner_authenticator: Callable[[str, str, str], bool],
        register_device: Callable[[str, dict[str, Any]], str | dict[str, Any]],
        revoke_device: Callable[[str], None],
    ):
        self.store = store
        self.owner_authenticator = owner_authenticator
        self.register_device = register_device
        self.revoke_device = revoke_device

    def begin_restore(
        self,
        owner_id: str,
        *,
        method: str,
        destination_platform: str,
        ttl_seconds: int = 600,
    ) -> str:
        if method not in {"recovery_code", "recovery_package", "passkey"}:
            raise ValueError("unsupported recovery method")
        ttl = max(60, min(int(ttl_seconds), 1800))
        restore_id = uuid4().hex
        challenge = secrets.token_urlsafe(32)
        payload = {
            "owner_id": owner_id,
            "method": method,
            "destination_platform": destination_platform[:80],
            "challenge_hash": hashlib.sha256(challenge.encode()).hexdigest(),
            "phase": "challenge_issued",
            "created_at": utcnow(),
            "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=ttl)).isoformat(),
        }
        self.store.put("owner_restore", restore_id, payload, status="pending", owner_id=owner_id)
        self.store.audit(
            "identity",
            "restore_started",
            actor=owner_id,
            subject=restore_id,
            payload={"method": method, "expires_at": payload["expires_at"]},
        )
        return f"{restore_id}.{challenge}"

    def complete_restore(
        self,
        restore_token: str,
        *,
        owner_proof: str,
        device_metadata: dict[str, Any],
        lost_device_id: str | None = None,
    ) -> RecoveryResult:
        try:
            restore_id, challenge = restore_token.split(".", 1)
        except ValueError as exc:
            raise ValueError("invalid restore token") from exc
        row = self.store.get("owner_restore", restore_id)
        if row is None or row["status"] != "pending":
            raise PermissionError("restore is not active")
        payload = dict(row["payload"])
        expires_at = datetime.fromisoformat(str(payload["expires_at"]).replace("Z", "+00:00"))
        if datetime.now(timezone.utc) >= expires_at.astimezone(timezone.utc):
            self.store.put(
                "owner_restore",
                restore_id,
                {**payload, "phase": "expired", "expired_at": utcnow()},
                status="expired",
                owner_id=payload["owner_id"],
            )
            self.store.audit("identity", "restore_expired", actor=payload["owner_id"], subject=restore_id)
            raise PermissionError("restore challenge expired")
        actual_hash = hashlib.sha256(challenge.encode()).hexdigest()
        if not hmac.compare_digest(actual_hash, payload["challenge_hash"]):
            raise PermissionError("restore challenge mismatch")

        # Claim before verifying the proof so parallel calls and brute-force
        # retries cannot reuse a valid challenge. A denied proof requires a new
        # short-lived owner ceremony.
        claimed = self.store.claim_status(
            "owner_restore",
            restore_id,
            expected_status="pending",
            claimed_status="consuming",
        )
        if claimed is None:
            raise PermissionError("restore was already consumed")

        owner_id = payload["owner_id"]
        method = str(payload["method"])
        try:
            authenticated = bool(self.owner_authenticator(owner_id, method, owner_proof))
        except Exception:
            authenticated = False
        if not authenticated:
            self.store.put(
                "owner_restore",
                restore_id,
                {**payload, "phase": "denied", "denied_at": utcnow()},
                status="denied",
                owner_id=owner_id,
            )
            self.store.audit("identity", "restore_denied", actor=owner_id, subject=restore_id)
            raise PermissionError("owner recovery proof rejected")

        registration = self.register_device(owner_id, dict(device_metadata))
        credential = None
        if isinstance(registration, dict):
            restored_device_id = str(
                registration.get("device_id") or registration.get("id") or ""
            ).strip()
            credential_value = registration.get("device_credential") or registration.get("token")
            credential = str(credential_value) if credential_value else None
        else:
            restored_device_id = str(registration or "").strip()
        if not restored_device_id:
            raise RuntimeError("canonical device authority did not issue a device ID")

        revoked = None
        if lost_device_id:
            if lost_device_id == restored_device_id:
                raise ValueError("restored and lost device cannot be the same")
            self.revoke_device(lost_device_id)
            revoked = lost_device_id
        complete_payload = {
            **payload,
            "phase": "complete",
            "restored_device_id": restored_device_id,
            "revoked_device_id": revoked,
            "completed_at": utcnow(),
        }
        # Never persist credential/proof material.
        self.store.put(
            "owner_restore",
            restore_id,
            complete_payload,
            status="complete",
            owner_id=owner_id,
            device_id=restored_device_id,
        )
        self.store.audit(
            "identity",
            "restore_completed",
            actor=owner_id,
            subject=restored_device_id,
            payload={"lost_device_revoked": bool(revoked), "method": method},
        )
        return RecoveryResult(owner_id, restored_device_id, revoked, method, credential)


class MultiDeviceContinuity:
    """Policy-aware handoff and offline/online continuation metadata."""

    def __init__(self, store: TrustContinuityStore, *, is_trusted_device: Callable[[str], bool]):
        self.store = store
        self.is_trusted_device = is_trusted_device

    def create_task(
        self,
        *,
        owner_id: str,
        device_id: str,
        title: str,
        data_policy: str,
        state: dict[str, Any] | None = None,
    ) -> str:
        if data_policy not in DATA_POLICIES:
            raise ValueError("invalid data policy")
        if not self.is_trusted_device(device_id):
            raise PermissionError("source device is not trusted")
        task_id = uuid4().hex
        payload = {
            "title": title[:240],
            "data_policy": data_policy,
            "current_device_id": device_id,
            "online": True,
            "checkpoint": dict(state or {}),
            "handoff_count": 0,
            "created_at": utcnow(),
        }
        self.store.put("continuity_task", task_id, payload, owner_id=owner_id, device_id=device_id)
        self.store.audit("continuity", "task_created", actor=device_id, subject=task_id, payload={"policy": data_policy})
        return task_id

    def checkpoint(self, task_id: str, *, device_id: str, state: dict[str, Any], online: bool) -> dict[str, Any]:
        row = self._authorized_task(task_id, device_id)
        payload = dict(row["payload"])
        policy = payload["data_policy"]
        if policy == "progress_only":
            allowed = {
                key: value
                for key, value in state.items()
                if key in {"step", "status", "percent", "resume_token", "updated_at"}
            }
            payload["checkpoint"] = allowed
        else:
            payload["checkpoint"] = dict(state)
        payload["online"] = bool(online)
        payload["updated_at"] = utcnow()
        result = self.store.put(
            "continuity_task",
            task_id,
            payload,
            owner_id=row["owner_id"],
            device_id=payload["current_device_id"],
        )
        self.store.audit("continuity", "checkpoint", actor=device_id, subject=task_id, payload={"online": online})
        return result

    def handoff(
        self,
        task_id: str,
        *,
        from_device: str,
        to_device: str,
        explicit_on_demand: bool = False,
    ) -> dict[str, Any]:
        row = self._authorized_task(task_id, from_device)
        if not self.is_trusted_device(to_device):
            raise PermissionError("destination device is not trusted")
        payload = dict(row["payload"])
        policy = payload["data_policy"]
        if policy == "device_only":
            raise PermissionError("device_only tasks cannot be handed off")
        if policy == "on_demand" and not explicit_on_demand:
            raise PermissionError("on_demand handoff requires explicit owner request")
        payload["current_device_id"] = to_device
        payload["handoff_count"] = int(payload.get("handoff_count", 0)) + 1
        payload["last_handoff"] = {"from": from_device, "to": to_device, "at": utcnow()}
        result = self.store.put(
            "continuity_task",
            task_id,
            payload,
            owner_id=row["owner_id"],
            device_id=to_device,
        )
        self.store.audit(
            "continuity",
            "handoff",
            actor=from_device,
            subject=task_id,
            payload={"to_device": to_device, "policy": policy},
        )
        return result

    def set_connectivity(self, task_id: str, *, device_id: str, online: bool) -> dict[str, Any]:
        row = self._authorized_task(task_id, device_id)
        payload = dict(row["payload"])
        payload["online"] = bool(online)
        payload["connectivity_changed_at"] = utcnow()
        result = self.store.put(
            "continuity_task",
            task_id,
            payload,
            owner_id=row["owner_id"],
            device_id=row["device_id"],
        )
        self.store.audit(
            "continuity",
            "connectivity_changed",
            actor=device_id,
            subject=task_id,
            payload={"online": online},
        )
        return result

    def _authorized_task(self, task_id: str, device_id: str) -> dict[str, Any]:
        if not self.is_trusted_device(device_id):
            raise PermissionError("device is not trusted")
        row = self.store.get("continuity_task", task_id)
        if row is None:
            raise KeyError(task_id)
        current_device = str(row["payload"].get("current_device_id") or "")
        if current_device != device_id:
            raise PermissionError("task mutation is bound to its current trusted device")
        return row