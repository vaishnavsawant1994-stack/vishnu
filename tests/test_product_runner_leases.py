from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest

from products.build_lifecycle import ProductBuildLifecycle
from products.runner_leases import ProductRunnerLeases, RunnerLeaseError
from products.store import ProductStore


def runtime(tmp_path):
    store = ProductStore(tmp_path / "products.sqlite3")
    lifecycle = ProductBuildLifecycle(store.path)
    leases = ProductRunnerLeases(store, lifecycle)
    return store, lifecycle, leases


def android_build(store, name="Queue Product"):
    product = store.create(name=name, product_type="ai_employee", targets=["android"])
    store.create_version(product["id"], version="0.1.0")
    build = store.request_build(product["id"], target="android")
    assert build
    return product, build


def raw_build(store, product_id, build_id):
    with store.con() as con:
        row = con.execute("SELECT * FROM product_builds WHERE product_id=? AND id=?", (product_id, build_id)).fetchone()
    return dict(row)


def test_claim_is_exclusive_and_hashes_lease_token(tmp_path):
    store, lifecycle, leases = runtime(tmp_path)
    product, build = android_build(store)

    claimed = leases.claim(target="android", runner_id="android-runner-1")
    assert claimed["build_id"] == build["id"]
    assert claimed["product_id"] == product["id"]
    assert claimed["lease_token"]
    assert lifecycle.ensure(raw_build(store, product["id"], build["id"]))["status"] == "running"
    assert leases.claim(target="android", runner_id="android-runner-2") is None

    with store.con() as con:
        row = dict(con.execute("SELECT * FROM product_runner_leases WHERE build_id=?", (build["id"],)).fetchone())
    assert row["lease_token_hash"] == hashlib.sha256(claimed["lease_token"].encode()).hexdigest()
    assert claimed["lease_token"] not in json.dumps(row)


def test_claim_skips_unfrozen_build(tmp_path):
    store, _lifecycle, leases = runtime(tmp_path)
    product = store.create(name="Unfrozen", targets=["android"])
    build = store.request_build(product["id"], target="android")
    assert build
    assert leases.claim(target="android", runner_id="runner-1") is None


def test_heartbeat_requires_exact_token(tmp_path):
    store, _lifecycle, leases = runtime(tmp_path)
    _product, build = android_build(store)
    claimed = leases.claim(target="android", runner_id="runner-1")
    with pytest.raises(RunnerLeaseError, match="does not match"):
        leases.heartbeat(build["id"], "wrong-token")
    beat = leases.heartbeat(build["id"], claimed["lease_token"])
    assert beat["build_id"] == build["id"]
    assert beat["state"] == "active"
    assert "lease_token_hash" not in beat


def test_release_requeues_running_build(tmp_path):
    store, lifecycle, leases = runtime(tmp_path)
    product, build = android_build(store)
    claimed = leases.claim(target="android", runner_id="runner-1")
    released = leases.release(build["id"], claimed["lease_token"], reason="runner shutdown", retry=True)
    assert released["state"] == "released"
    assert lifecycle.ensure(raw_build(store, product["id"], build["id"]))["status"] == "queued"
    reclaimed = leases.claim(target="android", runner_id="runner-2")
    assert reclaimed["build_id"] == build["id"]
    assert reclaimed["attempt"] == 2


def test_expired_lease_recovers_build_for_retry(tmp_path):
    store, lifecycle, leases = runtime(tmp_path)
    product, build = android_build(store)
    claimed = leases.claim(target="android", runner_id="runner-1")
    expired = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
    with store.con() as con:
        con.execute("UPDATE product_runner_leases SET expires_at=? WHERE build_id=?", (expired, build["id"]))
    recovered = leases.recover_expired()
    assert recovered and recovered[0]["build_id"] == build["id"]
    assert recovered[0]["state"] == "expired"
    assert lifecycle.ensure(raw_build(store, product["id"], build["id"]))["status"] == "queued"
    with pytest.raises(RunnerLeaseError):
        leases.heartbeat(build["id"], claimed["lease_token"])
    reclaimed = leases.claim(target="android", runner_id="runner-2")
    assert reclaimed["attempt"] == 2


def test_complete_requires_terminal_build(tmp_path):
    store, lifecycle, leases = runtime(tmp_path)
    product, build = android_build(store)
    claimed = leases.claim(target="android", runner_id="runner-1")
    with pytest.raises(RunnerLeaseError, match="terminal"):
        leases.complete(build["id"], claimed["lease_token"])
    lifecycle.update(product["id"], build["id"], status="failed", failure_reason="compiler error")
    completed = leases.complete(build["id"], claimed["lease_token"])
    assert completed["state"] == "completed"


def test_queue_status_never_exposes_lease_secrets(tmp_path):
    store, _lifecycle, leases = runtime(tmp_path)
    _product, _build = android_build(store)
    claimed = leases.claim(target="android", runner_id="runner-1")
    status = leases.status()
    serialized = json.dumps(status)
    assert claimed["lease_token"] not in serialized
    assert "lease_token_hash" not in serialized
    assert any(row["target"] == "android" for row in status["queue"])
