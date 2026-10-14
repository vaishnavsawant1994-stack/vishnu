from __future__ import annotations

import hashlib
import os
import re
import secrets
from datetime import datetime, timedelta, timezone

from .build_lifecycle import ProductBuildLifecycle
from .platform_jobs import REMOTE_PLATFORM_TARGETS
from core.sqlite import run_script_migration


RUNNER_LEASE_SECONDS_ENV = "VISHNU_PRODUCT_RUNNER_LEASE_SECONDS"
_RUNNER_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class RunnerLeaseError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def lease_seconds() -> int:
    raw = os.environ.get(RUNNER_LEASE_SECONDS_ENV, "").strip()
    if not raw:
        return 900
    try:
        value = int(raw)
    except ValueError as exc:
        raise RunnerLeaseError(f"{RUNNER_LEASE_SECONDS_ENV} must be an integer") from exc
    if value < 60 or value > 7200:
        raise RunnerLeaseError(f"{RUNNER_LEASE_SECONDS_ENV} must be between 60 and 7200 seconds")
    return value


def _token_hash(token: str) -> str:
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


def _runner_id(value: str) -> str:
    value = str(value or "").strip()
    if not _RUNNER_ID.fullmatch(value):
        raise RunnerLeaseError("Runner ID must use 1-128 safe identifier characters")
    return value


class ProductRunnerLeases:
    """Durable queue claims for autonomous external product platform runners.

    The global runner bearer token authenticates a runner installation. A lease
    then prevents two authenticated runners from compiling the same product build
    concurrently and gives Vishnu a bounded recovery point when a runner dies.
    Only the hash of the per-build lease token is persisted.
    """

    def __init__(self, store, lifecycle: ProductBuildLifecycle):
        self.store = store
        self.lifecycle = lifecycle
        self._init_schema()

    def _init_schema(self) -> None:
        with self.store.lock, self.store.con() as con:
            run_script_migration(con, component="products.runner_leases", script=
                """
                CREATE TABLE IF NOT EXISTS product_runner_leases(
                    build_id TEXT PRIMARY KEY,
                    product_id TEXT NOT NULL,
                    target TEXT NOT NULL,
                    runner_id TEXT NOT NULL,
                    lease_token_hash TEXT NOT NULL,
                    state TEXT NOT NULL,
                    attempt INTEGER NOT NULL DEFAULT 1,
                    claimed_at TEXT NOT NULL,
                    heartbeat_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    released_at TEXT,
                    last_reason TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(build_id) REFERENCES product_builds(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_product_runner_leases_state_expiry
                  ON product_runner_leases(state, expires_at);
                CREATE INDEX IF NOT EXISTS idx_product_runner_leases_runner
                  ON product_runner_leases(runner_id, state);
                """
            )

    def _raw_build(self, product_id: str, build_id: str) -> dict | None:
        with self.store.con() as con:
            row = con.execute(
                "SELECT * FROM product_builds WHERE id=? AND product_id=? LIMIT 1",
                (build_id, product_id),
            ).fetchone()
        if not row:
            return None
        value = dict(row)
        value["metadata"] = {}
        try:
            import json
            value["metadata"] = json.loads(value.pop("metadata_json", "{}") or "{}")
        except (TypeError, ValueError):
            value.pop("metadata_json", None)
        return value

    def recover_expired(self) -> list[dict]:
        now = _now()
        with self.store.con() as con:
            rows = con.execute(
                "SELECT * FROM product_runner_leases WHERE state='active' AND expires_at<=? ORDER BY expires_at",
                (_iso(now),),
            ).fetchall()
        recovered: list[dict] = []
        for row in rows:
            lease = dict(row)
            raw = self._raw_build(lease["product_id"], lease["build_id"])
            next_state = "expired"
            reason = "Runner lease expired before completion"
            if raw is None:
                next_state = "released"
                reason = "Build no longer exists"
            else:
                build = self.lifecycle.ensure(raw)
                if build["status"] == "running":
                    self.lifecycle.update(
                        lease["product_id"],
                        lease["build_id"],
                        status="failed",
                        failure_reason=reason,
                    )
                    self.lifecycle.update(lease["product_id"], lease["build_id"], status="queued")
                elif build["status"] in {"succeeded", "cancelled"}:
                    next_state = "completed"
                    reason = f"Build already {build['status']}"
            with self.store.lock, self.store.con() as con:
                con.execute(
                    "UPDATE product_runner_leases SET state=?,released_at=?,last_reason=? WHERE build_id=? AND state='active' AND expires_at<=?",
                    (next_state, _iso(now), reason, lease["build_id"], _iso(now)),
                )
            recovered.append({"build_id": lease["build_id"], "state": next_state, "reason": reason})
        return recovered

    def claim(self, *, target: str, runner_id: str, ttl_seconds: int | None = None) -> dict | None:
        target = str(target or "").strip().lower()
        if target not in REMOTE_PLATFORM_TARGETS:
            raise RunnerLeaseError(f"Unsupported runner target: {target}")
        runner_id = _runner_id(runner_id)
        ttl = int(ttl_seconds or lease_seconds())
        if ttl < 60 or ttl > 7200:
            raise RunnerLeaseError("Runner lease duration must be between 60 and 7200 seconds")
        self.recover_expired()
        now = _now()
        expires = now + timedelta(seconds=ttl)
        token = secrets.token_urlsafe(32)
        digest = _token_hash(token)
        candidate = None
        attempt = 0
        # BEGIN IMMEDIATE serializes the read-then-claim sequence across separate
        # Vishnu processes sharing this SQLite database. The in-process RLock is
        # not sufficient when multiple API workers or runner coordinators exist.
        with self.store.lock, self.store.con() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                """
                SELECT b.id,b.product_id,b.version,b.target,b.status,b.created_at,
                       COALESCE(l.attempt,0) previous_attempt
                  FROM product_builds b
                  LEFT JOIN product_runner_leases l ON l.build_id=b.id
                 WHERE b.target=?
                   AND b.status IN ('requested','queued')
                   AND EXISTS(
                       SELECT 1 FROM product_versions v
                        WHERE v.product_id=b.product_id AND v.version=b.version
                   )
                   AND (l.build_id IS NULL OR l.state!='active')
                 ORDER BY b.created_at,b.id
                 LIMIT 1
                """,
                (target,),
            ).fetchone()
            if row:
                candidate = dict(row)
                attempt = int(candidate.pop("previous_attempt") or 0) + 1
                con.execute(
                    """
                    INSERT INTO product_runner_leases(
                        build_id,product_id,target,runner_id,lease_token_hash,state,attempt,
                        claimed_at,heartbeat_at,expires_at,released_at,last_reason
                    ) VALUES(?,?,?,?,?,'active',?,?,?,?,NULL,'')
                    ON CONFLICT(build_id) DO UPDATE SET
                        product_id=excluded.product_id,target=excluded.target,runner_id=excluded.runner_id,
                        lease_token_hash=excluded.lease_token_hash,state='active',attempt=excluded.attempt,
                        claimed_at=excluded.claimed_at,heartbeat_at=excluded.heartbeat_at,
                        expires_at=excluded.expires_at,released_at=NULL,last_reason=''
                    """,
                    (
                        candidate["id"], candidate["product_id"], target, runner_id, digest, attempt,
                        _iso(now), _iso(now), _iso(expires),
                    ),
                )
        if candidate is None:
            return None
        try:
            build = self.lifecycle.ensure(self._raw_build(candidate["product_id"], candidate["id"]))
            if build["status"] in {"requested", "queued"}:
                build = self.lifecycle.update(candidate["product_id"], candidate["id"], status="running")
            if build["status"] != "running":
                raise RunnerLeaseError(f"Claimed build cannot run from status {build['status']}")
        except Exception:
            with self.store.lock, self.store.con() as con:
                con.execute(
                    "UPDATE product_runner_leases SET state='released',released_at=?,last_reason='Claim activation failed' WHERE build_id=? AND lease_token_hash=?",
                    (_iso(_now()), candidate["id"], digest),
                )
            raise
        return {
            "schema": "vishnu.product-runner-lease/v1",
            "build_id": candidate["id"],
            "product_id": candidate["product_id"],
            "version": candidate["version"],
            "target": target,
            "runner_id": runner_id,
            "attempt": attempt,
            "claimed_at": _iso(now),
            "heartbeat_at": _iso(now),
            "expires_at": _iso(expires),
            "lease_token": token,
        }

    def _active(self, build_id: str, token: str) -> dict:
        digest = _token_hash(token)
        with self.store.con() as con:
            row = con.execute(
                "SELECT * FROM product_runner_leases WHERE build_id=? AND state='active' AND lease_token_hash=? LIMIT 1",
                (str(build_id), digest),
            ).fetchone()
        if not row:
            raise RunnerLeaseError("Runner lease is missing, completed, expired or does not match")
        lease = dict(row)
        expires = _parse(lease.get("expires_at"))
        if expires is None or expires <= _now():
            self.recover_expired()
            raise RunnerLeaseError("Runner lease has expired")
        return lease

    def validate(self, build_id: str, token: str) -> dict:
        """Validate an active lease without exposing its persisted token hash."""
        lease = self._active(build_id, token)
        lease.pop("lease_token_hash", None)
        return lease

    def heartbeat(self, build_id: str, token: str, *, ttl_seconds: int | None = None) -> dict:
        lease = self._active(build_id, token)
        ttl = int(ttl_seconds or lease_seconds())
        if ttl < 60 or ttl > 7200:
            raise RunnerLeaseError("Runner lease duration must be between 60 and 7200 seconds")
        now = _now()
        expires = now + timedelta(seconds=ttl)
        with self.store.lock, self.store.con() as con:
            con.execute(
                "UPDATE product_runner_leases SET heartbeat_at=?,expires_at=? WHERE build_id=? AND lease_token_hash=? AND state='active'",
                (_iso(now), _iso(expires), str(build_id), _token_hash(token)),
            )
        lease["heartbeat_at"] = _iso(now)
        lease["expires_at"] = _iso(expires)
        lease.pop("lease_token_hash", None)
        return lease

    def complete(self, build_id: str, token: str) -> dict:
        lease = self._active(build_id, token)
        raw = self._raw_build(lease["product_id"], build_id)
        if raw is not None:
            build = self.lifecycle.ensure(raw)
            if build["status"] not in {"succeeded", "failed", "cancelled"}:
                raise RunnerLeaseError("Runner lease cannot complete before the build reaches a terminal state")
        now = _now()
        with self.store.lock, self.store.con() as con:
            con.execute(
                "UPDATE product_runner_leases SET state='completed',released_at=?,last_reason='Build callback completed' WHERE build_id=? AND lease_token_hash=? AND state='active'",
                (_iso(now), str(build_id), _token_hash(token)),
            )
        lease["state"] = "completed"
        lease["released_at"] = _iso(now)
        lease.pop("lease_token_hash", None)
        return lease

    def release(self, build_id: str, token: str, *, reason: str = "Runner released lease", retry: bool = True) -> dict:
        lease = self._active(build_id, token)
        raw = self._raw_build(lease["product_id"], build_id)
        if raw is not None:
            build = self.lifecycle.ensure(raw)
            if build["status"] == "running":
                self.lifecycle.update(lease["product_id"], build_id, status="failed", failure_reason=str(reason)[:2000])
                if retry:
                    self.lifecycle.update(lease["product_id"], build_id, status="queued")
        now = _now()
        with self.store.lock, self.store.con() as con:
            con.execute(
                "UPDATE product_runner_leases SET state='released',released_at=?,last_reason=? WHERE build_id=? AND lease_token_hash=? AND state='active'",
                (_iso(now), str(reason or "Runner released lease")[:2000], str(build_id), _token_hash(token)),
            )
        lease["state"] = "released"
        lease["released_at"] = _iso(now)
        lease.pop("lease_token_hash", None)
        return lease

    def status(self) -> dict:
        recovered = self.recover_expired()
        with self.store.con() as con:
            lease_rows = con.execute(
                "SELECT target,state,count(*) count FROM product_runner_leases GROUP BY target,state"
            ).fetchall()
            queue_rows = con.execute(
                "SELECT target,status,count(*) count FROM product_builds WHERE target IN ('android','ios','windows','macos','linux','docker') GROUP BY target,status"
            ).fetchall()
        return {
            "leases": [dict(row) for row in lease_rows],
            "queue": [dict(row) for row in queue_rows],
            "recovered": recovered,
        }
