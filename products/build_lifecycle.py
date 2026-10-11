from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock


BUILD_STATUSES = ("requested", "queued", "running", "succeeded", "failed", "cancelled")
NATIVE_SIGNED_TARGETS = {"android", "ios", "windows", "macos"}
_ALLOWED_TRANSITIONS = {
    "requested": {"requested", "queued", "running", "failed", "cancelled"},
    "queued": {"queued", "running", "failed", "cancelled"},
    "running": {"running", "succeeded", "failed", "cancelled"},
    "succeeded": {"succeeded"},
    "failed": {"failed", "queued"},
    "cancelled": {"cancelled", "queued"},
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _loads(value, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


class ProductBuildLifecycle:
    """Governed lifecycle metadata for Our Products build requests.

    The foundation store intentionally records only a truthful build request. This
    companion store adds monotonic build numbers and adapter lifecycle state while
    keeping artifact readiness derived from verified build evidence rather than UI
    claims. Raw artifact evidence is accepted only from an internal caller that sets
    ``verified_builder=True``.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        self._init()

    def con(self):
        con = sqlite3.connect(self.path, timeout=10)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        return con

    def _init(self):
        with self.con() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS product_build_lifecycle(
                    build_id TEXT PRIMARY KEY REFERENCES product_builds(id) ON DELETE CASCADE,
                    product_id TEXT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                    build_number INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'requested',
                    artifact_uri TEXT,
                    signing_verified INTEGER NOT NULL DEFAULT 0,
                    failure_reason TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(product_id, build_number)
                );
                CREATE INDEX IF NOT EXISTS idx_product_build_lifecycle_product
                    ON product_build_lifecycle(product_id, build_number DESC);
                """
            )

    def _build_exists(self, con, build_id: str, product_id: str | None = None):
        if product_id is None:
            return con.execute("SELECT * FROM product_builds WHERE id=?", (build_id,)).fetchone()
        return con.execute(
            "SELECT * FROM product_builds WHERE id=? AND product_id=?", (build_id, product_id)
        ).fetchone()

    def _backfill_product(self, con, product_id: str):
        """Assign chronological build numbers, including pre-upgrade build requests."""
        builds = con.execute(
            "SELECT * FROM product_builds WHERE product_id=? ORDER BY created_at ASC,id ASC",
            (product_id,),
        ).fetchall()
        lifecycle_rows = con.execute(
            "SELECT * FROM product_build_lifecycle WHERE product_id=?", (product_id,)
        ).fetchall()
        existing = {row["build_id"]: dict(row) for row in lifecycle_rows}
        expected = {row["id"]: index for index, row in enumerate(builds, start=1)}
        if len(existing) == len(builds) and all(
            int(existing[build_id]["build_number"]) == number
            for build_id, number in expected.items()
        ):
            return

        # Move current numbers out of the positive namespace first so UNIQUE does
        # not obstruct deterministic renumbering during a migration/backfill.
        con.execute(
            "UPDATE product_build_lifecycle SET build_number=-(build_number+1000000) WHERE product_id=?",
            (product_id,),
        )
        stamp = _now()
        for number, build in enumerate(builds, start=1):
            current = existing.get(build["id"])
            if current:
                con.execute(
                    "UPDATE product_build_lifecycle SET build_number=?,updated_at=? WHERE build_id=?",
                    (number, stamp, build["id"]),
                )
            else:
                con.execute(
                    """INSERT INTO product_build_lifecycle(
                           build_id,product_id,build_number,status,artifact_uri,signing_verified,
                           failure_reason,created_at,updated_at
                       ) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (
                        build["id"],
                        product_id,
                        number,
                        str(build["status"] or "requested"),
                        None,
                        0,
                        "",
                        stamp,
                        stamp,
                    ),
                )

    def ensure(self, build: dict):
        if not build or not build.get("id") or not build.get("product_id"):
            raise ValueError("A valid build request is required")
        with self.lock, self.con() as con:
            self._backfill_product(con, build["product_id"])
            lifecycle = con.execute(
                "SELECT * FROM product_build_lifecycle WHERE build_id=?", (build["id"],)
            ).fetchone()
        if not lifecycle:
            raise ValueError("Build lifecycle could not be initialized")
        return self.decorate(build, lifecycle=dict(lifecycle))

    def decorate(self, build: dict, *, lifecycle: dict | None = None):
        if not build:
            return build
        value = dict(build)
        if lifecycle is None:
            with self.con() as con:
                row = con.execute(
                    "SELECT * FROM product_build_lifecycle WHERE build_id=?", (value["id"],)
                ).fetchone()
            lifecycle = dict(row) if row else None
        if lifecycle is None:
            return value
        metadata = dict(value.get("metadata") or {})
        status = lifecycle["status"]
        artifact_uri = lifecycle.get("artifact_uri")
        signing_verified = bool(lifecycle.get("signing_verified"))
        checksum = value.get("checksum")
        target = value.get("target")
        artifact_ready = bool(
            status == "succeeded"
            and artifact_uri
            and value.get("artifact_name")
            and checksum
            and (target not in NATIVE_SIGNED_TARGETS or signing_verified)
        )
        metadata.update(
            {
                "artifact_ready": artifact_ready,
                "artifact_uri": artifact_uri,
                "signing_verified": signing_verified,
                "failure_reason": lifecycle.get("failure_reason") or "",
                "builder_state": status,
            }
        )
        value.update(
            {
                "build_number": int(lifecycle["build_number"]),
                "status": status,
                "metadata": metadata,
            }
        )
        return value

    def list(self, product_id: str, builds: list[dict]):
        return [self.ensure(build) for build in builds if build.get("product_id") == product_id]

    def update(
        self,
        product_id: str,
        build_id: str,
        *,
        status: str | None = None,
        artifact_name: str | None = None,
        artifact_uri: str | None = None,
        checksum: str | None = None,
        signing_verified: bool | None = None,
        failure_reason: str | None = None,
        verified_builder: bool = False,
    ):
        evidence_supplied = any(
            item is not None
            for item in (artifact_name, artifact_uri, checksum, signing_verified)
        )
        if evidence_supplied and not verified_builder:
            raise ValueError("Artifact evidence may only be recorded by a verified builder adapter")

        with self.lock, self.con() as con:
            build = self._build_exists(con, build_id, product_id)
            if not build:
                return None
            base = dict(build)
            base["metadata"] = _loads(base.pop("metadata_json", "{}"), {})
        self.ensure(base)

        with self.lock, self.con() as con:
            build = self._build_exists(con, build_id, product_id)
            row = con.execute(
                "SELECT * FROM product_build_lifecycle WHERE build_id=?", (build_id,)
            ).fetchone()
            current = dict(row)
            next_status = str(status or current["status"]).strip().lower()
            if next_status not in BUILD_STATUSES:
                raise ValueError(f"Unsupported build status: {next_status}")
            if next_status not in _ALLOWED_TRANSITIONS.get(current["status"], set()):
                raise ValueError(
                    f"Invalid build transition: {current['status']} -> {next_status}"
                )
            next_artifact_name = artifact_name if artifact_name is not None else build["artifact_name"]
            next_checksum = checksum if checksum is not None else build["checksum"]
            next_artifact_uri = artifact_uri if artifact_uri is not None else current["artifact_uri"]
            next_signing = (
                int(bool(signing_verified))
                if signing_verified is not None
                else int(current["signing_verified"])
            )
            next_failure = (
                str(failure_reason or "").strip()
                if failure_reason is not None
                else current["failure_reason"]
            )
            stamp = _now()
            con.execute(
                """UPDATE product_build_lifecycle
                   SET status=?,artifact_uri=?,signing_verified=?,failure_reason=?,updated_at=?
                   WHERE build_id=? AND product_id=?""",
                (
                    next_status,
                    next_artifact_uri,
                    next_signing,
                    next_failure,
                    stamp,
                    build_id,
                    product_id,
                ),
            )
            metadata = _loads(build["metadata_json"], {})
            metadata.update(
                {
                    "builder_state": next_status,
                    "artifact_uri": next_artifact_uri,
                    "signing_verified": bool(next_signing),
                    "failure_reason": next_failure,
                }
            )
            completed_at = stamp if next_status in {"succeeded", "failed", "cancelled"} else None
            con.execute(
                """UPDATE product_builds
                   SET status=?,artifact_name=?,checksum=?,metadata_json=?,completed_at=?
                   WHERE id=? AND product_id=?""",
                (
                    next_status,
                    next_artifact_name,
                    next_checksum,
                    _json(metadata),
                    completed_at,
                    build_id,
                    product_id,
                ),
            )
            updated = self._build_exists(con, build_id, product_id)
            lifecycle = con.execute(
                "SELECT * FROM product_build_lifecycle WHERE build_id=?", (build_id,)
            ).fetchone()
        value = dict(updated)
        value["metadata"] = _loads(value.pop("metadata_json", "{}"), {})
        return self.decorate(value, lifecycle=dict(lifecycle))
