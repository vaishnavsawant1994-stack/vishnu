from __future__ import annotations

from pathlib import Path

import pytest

from trust_continuity.runtime import build_trust_continuity_runtime


class FakeKeychain:
    def __init__(self):
        self.values = {}

    def set(self, key, value):
        self.values[key] = value

    def get(self, key):
        return self.values.get(key)

    def delete(self, key):
        self.values.pop(key, None)


def test_runtime_is_fail_closed_without_sensitive_callbacks(tmp_path: Path):
    runtime = build_trust_continuity_runtime(
        data_dir=tmp_path,
        commit_sha="a" * 40,
        is_trusted_device=lambda device: device == "phone",
    )
    status = runtime.status()
    assert status["execution_authority"] is False
    assert status["oauth_available"] is False
    assert status["recovery_available"] is False
    assert status["trust_center_available"] is False
    assert status["readiness"]["production_ready"] is False
    assert all(value == "pending" for value in status["l4"].values())


def test_runtime_uses_keychain_and_requires_verified_oauth_provider(tmp_path: Path):
    runtime = build_trust_continuity_runtime(
        data_dir=tmp_path,
        commit_sha="b" * 40,
        is_trusted_device=lambda _device: True,
        keychain=FakeKeychain(),
    )
    assert runtime.oauth is not None
    flow = runtime.oauth.begin(
        owner_id="owner",
        provider="example",
        account_hint=None,
        scopes=["mail.read"],
        redirect_uri="https://example.test/callback",
    )
    with pytest.raises(PermissionError):
        runtime.oauth.complete(
            flow["flow_id"],
            owner_id="owner",
            state=flow["state"],
            authorization_code="code",
            exchange=lambda _code, _verifier, _redirect: {
                "access_token": "unsafe",
                "provider_verified": False,
            },
        )


def test_operational_health_and_crash_recovery_are_durable(tmp_path: Path):
    runtime = build_trust_continuity_runtime(
        data_dir=tmp_path,
        commit_sha="c" * 40,
        is_trusted_device=lambda _device: True,
    )
    runtime.health.register_probe("database", lambda: {"healthy": True, "detail": "ok"})
    health = runtime.health.run_all()
    assert health["healthy"] is True
    runtime.health.mark_process_start("worker", clean_previous_shutdown=False)
    runtime.health.mark_checkpoint("worker", checkpoint={"job": "42", "step": 3})
    recovery = runtime.health.recovery_state("worker")
    assert recovery["requires_recovery"] is True
    assert recovery["checkpoint"]["step"] == 3
    runtime.health.mark_shutdown("worker")


def test_memory_export_import_and_retention_cleanup(tmp_path: Path):
    runtime = build_trust_continuity_runtime(
        data_dir=tmp_path,
        commit_sha="d" * 40,
        is_trusted_device=lambda _device: True,
    )
    runtime.memory.remember(
        owner_id="owner",
        entity="router",
        predicate="room",
        value="office",
        source={"kind": "owner"},
        confidence=1.0,
    )
    package = runtime.memory.export_owner("owner")
    other = build_trust_continuity_runtime(
        data_dir=tmp_path / "restore",
        commit_sha="d" * 40,
        is_trusted_device=lambda _device: True,
    )
    imported = other.memory.import_owner(owner_id="owner", package=package)
    assert imported == {"imported": 1, "skipped": 0}
    fact = other.memory.query(owner_id="owner")[0]
    assert fact["payload"]["source"]["kind"] == "memory_import"
    other.memory.remember(
        owner_id="owner",
        entity="temporary",
        predicate="state",
        value=True,
        source={"kind": "test"},
        confidence=1.0,
        retention_days=0,
    )
    assert other.memory.purge_expired(owner_id="owner") == 1


def test_runtime_wires_recovery_and_trust_center_only_with_all_authorities(tmp_path: Path):
    calls = []
    runtime = build_trust_continuity_runtime(
        data_dir=tmp_path,
        commit_sha="e" * 40,
        is_trusted_device=lambda _device: True,
        owner_authenticator=lambda owner, proof: owner == "owner" and proof == "ok",
        register_device=lambda _owner, _meta: "new-device",
        revoke_device=lambda device: calls.append(("revoke", device)),
        stop_sensing=lambda: calls.append(("stop", "sensing")),
        stop_actions=lambda: calls.append(("stop", "actions")),
        disconnect_provider=lambda provider: calls.append(("disconnect", provider)),
        emergency_stop=lambda enabled: calls.append(("emergency", enabled)),
    )
    assert runtime.recovery is not None
    assert runtime.trust_center is not None
    token = runtime.recovery.begin_restore(
        "owner",
        method="recovery_code",
        destination_platform="android",
    )
    result = runtime.recovery.complete_restore(
        token,
        owner_proof="ok",
        device_metadata={"platform": "android"},
        lost_device_id="lost-phone",
    )
    assert result.restored_device_id == "new-device"
    runtime.trust_center.emergency_stop(True, actor="new-device")
    assert ("revoke", "lost-phone") in calls
    assert ("emergency", True) in calls
