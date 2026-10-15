from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timezone
from typing import Any, Callable, Protocol
from uuid import uuid4

from .store import TrustContinuityStore, utcnow


class SecretStore(Protocol):
    def put(self, name: str, value: str) -> str: ...
    def get(self, handle: str) -> str: ...
    def delete(self, handle: str) -> None: ...


class OAuthLifecycleManager:
    """Provider-neutral OAuth lifecycle with PKCE and secret-handle isolation."""

    def __init__(self, store: TrustContinuityStore, secrets_store: SecretStore):
        self.store = store
        self.secrets = secrets_store

    def begin(
        self,
        *,
        owner_id: str,
        provider: str,
        account_hint: str | None,
        scopes: list[str],
        redirect_uri: str,
    ) -> dict[str, Any]:
        if not redirect_uri.startswith("https://") and not redirect_uri.startswith("http://127.0.0.1"):
            raise ValueError("OAuth redirect must be HTTPS or loopback")
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(48)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        flow_id = uuid4().hex
        verifier_handle = self.secrets.put(f"oauth-pkce:{flow_id}", verifier)
        payload = {
            "provider": provider[:120],
            "account_hint": (account_hint or "")[:320],
            "scopes": sorted(set(scope[:200] for scope in scopes)),
            "redirect_uri": redirect_uri,
            "state_hash": hashlib.sha256(state.encode()).hexdigest(),
            "verifier_handle": verifier_handle,
            "phase": "authorization_pending",
            "created_at": utcnow(),
        }
        self.store.put("oauth_flow", flow_id, payload, status="pending", owner_id=owner_id)
        self.store.audit("oauth", "authorization_started", actor=owner_id, subject=flow_id, payload={"provider": provider, "scopes": payload["scopes"]})
        return {"flow_id": flow_id, "state": state, "code_challenge": challenge, "code_challenge_method": "S256"}

    def complete(
        self,
        flow_id: str,
        *,
        owner_id: str,
        state: str,
        authorization_code: str,
        exchange: Callable[[str, str, str], dict[str, Any]],
    ) -> str:
        row = self.store.get("oauth_flow", flow_id)
        if row is None or row["owner_id"] != owner_id or row["status"] != "pending":
            raise PermissionError("OAuth flow unavailable")
        payload = row["payload"]
        if not secrets.compare_digest(hashlib.sha256(state.encode()).hexdigest(), payload["state_hash"]):
            raise PermissionError("OAuth state mismatch")
        verifier = self.secrets.get(payload["verifier_handle"])
        tokens = exchange(authorization_code, verifier, payload["redirect_uri"])
        access = str(tokens.get("access_token") or "")
        if not access:
            raise RuntimeError("provider did not return an access token")
        connection_id = uuid4().hex
        access_handle = self.secrets.put(f"oauth-access:{connection_id}", access)
        refresh_handle = None
        if tokens.get("refresh_token"):
            refresh_handle = self.secrets.put(f"oauth-refresh:{connection_id}", str(tokens["refresh_token"]))
        connection = {
            "provider": payload["provider"],
            "account_id": str(tokens.get("account_id") or tokens.get("subject") or payload.get("account_hint") or "")[:320],
            "scopes": sorted(set(tokens.get("scopes") or payload["scopes"])),
            "access_handle": access_handle,
            "refresh_handle": refresh_handle,
            "expires_at": tokens.get("expires_at"),
            "verified_provider": bool(tokens.get("provider_verified", False)),
            "reauth_required": False,
            "connected_at": utcnow(),
        }
        self.store.put("oauth_connection", connection_id, connection, owner_id=owner_id)
        self.store.put("oauth_flow", flow_id, {**payload, "phase": "complete", "connection_id": connection_id}, status="complete", owner_id=owner_id)
        self.secrets.delete(payload["verifier_handle"])
        self.store.audit("oauth", "connected", actor=owner_id, subject=connection_id, payload={"provider": connection["provider"], "scopes": connection["scopes"]})
        return connection_id

    def access_token(self, connection_id: str, *, owner_id: str, required_scope: str, refresh: Callable[[str], dict[str, Any]] | None = None) -> str:
        row = self._connection(connection_id, owner_id)
        payload = dict(row["payload"])
        if required_scope not in payload["scopes"]:
            raise PermissionError("OAuth account scope denied")
        if payload.get("reauth_required"):
            raise PermissionError("OAuth re-authentication required")
        if self._expired(payload.get("expires_at")):
            handle = payload.get("refresh_handle")
            if not handle or refresh is None:
                payload["reauth_required"] = True
                self.store.put("oauth_connection", connection_id, payload, status="reauth", owner_id=owner_id)
                raise PermissionError("OAuth re-authentication required")
            refreshed = refresh(self.secrets.get(handle))
            access = str(refreshed.get("access_token") or "")
            if not access:
                raise RuntimeError("token refresh failed")
            self.secrets.delete(payload["access_handle"])
            payload["access_handle"] = self.secrets.put(f"oauth-access:{connection_id}", access)
            payload["expires_at"] = refreshed.get("expires_at")
            if refreshed.get("refresh_token"):
                self.secrets.delete(handle)
                payload["refresh_handle"] = self.secrets.put(f"oauth-refresh:{connection_id}", str(refreshed["refresh_token"]))
            self.store.put("oauth_connection", connection_id, payload, owner_id=owner_id)
            self.store.audit("oauth", "refreshed", actor=owner_id, subject=connection_id)
        return self.secrets.get(payload["access_handle"])

    def revoke(self, connection_id: str, *, owner_id: str, provider_revoke: Callable[[str], None] | None = None) -> None:
        row = self._connection(connection_id, owner_id)
        payload = row["payload"]
        token = self.secrets.get(payload["access_handle"])
        if provider_revoke:
            provider_revoke(token)
        for handle in (payload.get("access_handle"), payload.get("refresh_handle")):
            if handle:
                self.secrets.delete(handle)
        self.store.put("oauth_connection", connection_id, {**payload, "revoked_at": utcnow()}, status="revoked", owner_id=owner_id)
        self.store.audit("oauth", "revoked", actor=owner_id, subject=connection_id)

    def _connection(self, connection_id: str, owner_id: str) -> dict[str, Any]:
        row = self.store.get("oauth_connection", connection_id)
        if row is None or row["owner_id"] != owner_id or row["status"] == "revoked":
            raise PermissionError("OAuth connection unavailable")
        return row

    @staticmethod
    def _expired(value: str | None) -> bool:
        if not value:
            return False
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return datetime.now(timezone.utc) >= parsed.astimezone(timezone.utc)


class OfflineIntelligence:
    """Local capability routing and later reconciliation; cloud is never mandatory."""

    def __init__(self, store: TrustContinuityStore):
        self.store = store

    def register_capability(self, *, device_id: str, name: str, kind: str, model: str, available: bool, quality: float = 0.5) -> str:
        if kind not in {"stt", "tts", "ocr", "multimodal", "embedding", "search", "language_model"}:
            raise ValueError("unsupported local capability")
        record_id = f"{device_id}:{kind}:{name}"
        self.store.put("offline_capability", record_id, {"name": name, "kind": kind, "model": model, "available": bool(available), "quality": max(0.0, min(float(quality), 1.0)), "updated_at": utcnow()}, device_id=device_id, status="available" if available else "unavailable")
        return record_id

    def route(self, *, device_id: str, kind: str, allow_cloud: bool) -> dict[str, Any]:
        local = [row for row in self.store.list("offline_capability", device_id=device_id, status="available") if row["payload"]["kind"] == kind]
        if local:
            best = max(local, key=lambda row: float(row["payload"].get("quality", 0.0)))
            return {"route": "local", "capability": best["payload"], "cloud_optional": True}
        if allow_cloud:
            return {"route": "cloud", "capability": None, "cloud_optional": True}
        raise RuntimeError(f"no offline {kind} capability is available")

    def enqueue(self, *, owner_id: str, device_id: str, task_type: str, payload: dict[str, Any]) -> str:
        task_id = uuid4().hex
        self.store.put("offline_queue", task_id, {"task_type": task_type[:120], "payload": payload, "phase": "pending", "queued_at": utcnow()}, owner_id=owner_id, device_id=device_id, status="pending")
        return task_id

    def reconcile(self, task_id: str, *, remote_version: dict[str, Any] | None, policy: str) -> dict[str, Any]:
        row = self.store.get("offline_queue", task_id)
        if row is None:
            raise KeyError(task_id)
        if policy not in {"local_wins", "remote_wins", "manual", "merge_progress"}:
            raise ValueError("invalid reconciliation policy")
        local = row["payload"]["payload"]
        if remote_version is None or policy == "local_wins":
            resolved = local
        elif policy == "remote_wins":
            resolved = remote_version
        elif policy == "merge_progress":
            resolved = {**remote_version, **local}
        else:
            return {"status": "conflict", "local": local, "remote": remote_version, "requires_owner": True}
        payload = {**row["payload"], "phase": "reconciled", "resolved": resolved, "reconciled_at": utcnow()}
        self.store.put("offline_queue", task_id, payload, owner_id=row["owner_id"], device_id=row["device_id"], status="complete")
        return {"status": "complete", "resolved": resolved}


class TrustCenter:
    """Aggregated owner trust surface. Mutations call canonical runtime authorities."""

    def __init__(
        self,
        store: TrustContinuityStore,
        *,
        stop_sensing: Callable[[], None],
        stop_actions: Callable[[], None],
        revoke_device: Callable[[str], None],
        disconnect_provider: Callable[[str], None],
        emergency_stop: Callable[[bool], None],
        snapshot_sources: dict[str, Callable[[], Any]] | None = None,
    ):
        self.store = store
        self.stop_sensing_cb = stop_sensing
        self.stop_actions_cb = stop_actions
        self.revoke_device_cb = revoke_device
        self.disconnect_provider_cb = disconnect_provider
        self.emergency_stop_cb = emergency_stop
        self.snapshot_sources = dict(snapshot_sources or {})

    def snapshot(self) -> dict[str, Any]:
        data: dict[str, Any] = {"generated_at": utcnow(), "recent_audit": self.store.audit_entries(limit=100)}
        for name, callback in self.snapshot_sources.items():
            try:
                data[name] = callback()
            except Exception as exc:
                data[name] = {"status": "unavailable", "error": type(exc).__name__}
        return data

    def stop_sensing(self, *, actor: str) -> None:
        self.stop_sensing_cb()
        self.store.audit("trust_center", "stop_sensing", actor=actor)

    def stop_actions(self, *, actor: str) -> None:
        self.stop_actions_cb()
        self.store.audit("trust_center", "stop_actions", actor=actor)

    def revoke_device(self, device_id: str, *, actor: str) -> None:
        self.revoke_device_cb(device_id)
        self.store.audit("trust_center", "device_revoked", actor=actor, subject=device_id)

    def disconnect_provider(self, connection_id: str, *, actor: str) -> None:
        self.disconnect_provider_cb(connection_id)
        self.store.audit("trust_center", "provider_disconnected", actor=actor, subject=connection_id)

    def emergency_stop(self, enabled: bool, *, actor: str) -> None:
        self.emergency_stop_cb(bool(enabled))
        self.store.audit("trust_center", "emergency_stop", actor=actor, payload={"enabled": bool(enabled)})


class EvaluationLab:
    METRICS = {
        "reasoning_accuracy",
        "hallucination_rate",
        "task_success",
        "memory_correctness",
        "causal_reasoning",
        "action_verification",
        "privacy_violations",
        "permission_bypass_attempts_blocked",
        "crash_recovery",
        "device_continuity",
        "latency_ms",
        "cost",
        "battery_impact",
    }

    def __init__(self, store: TrustContinuityStore, *, commit_sha: str):
        self.store = store
        self.commit_sha = commit_sha

    def record(self, *, suite: str, metrics: dict[str, float], thresholds: dict[str, dict[str, float]] | None = None, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
        unknown = set(metrics) - self.METRICS
        if unknown:
            raise ValueError(f"unknown evaluation metrics: {sorted(unknown)}")
        normalized = {key: float(value) for key, value in metrics.items()}
        passed = True
        failures = []
        for key, rule in (thresholds or {}).items():
            if key not in normalized:
                passed = False
                failures.append(f"missing:{key}")
                continue
            value = normalized[key]
            if "min" in rule and value < float(rule["min"]):
                passed = False
                failures.append(f"below_min:{key}")
            if "max" in rule and value > float(rule["max"]):
                passed = False
                failures.append(f"above_max:{key}")
        scorecard_id = uuid4().hex
        payload = {"suite": suite[:200], "commit_sha": self.commit_sha, "metrics": normalized, "thresholds": thresholds or {}, "passed": passed, "failures": failures, "evidence": evidence or {}, "execution_authority": False, "recorded_at": utcnow()}
        self.store.put("evaluation_scorecard", scorecard_id, payload, status="passed" if passed else "failed")
        self.store.audit("evaluation", "scorecard", subject=scorecard_id, payload={"suite": suite, "passed": passed, "commit_sha": self.commit_sha})
        return {"scorecard_id": scorecard_id, **payload}
