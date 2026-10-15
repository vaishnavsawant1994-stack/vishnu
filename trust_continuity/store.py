from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def bounded_json(value: Any, *, max_bytes: int = 131072) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    if len(encoded.encode("utf-8")) > max_bytes:
        raise ValueError("payload exceeds trust-continuity size limit")
    return encoded


class TrustContinuityStore:
    """Small durable state authority for cross-cutting trust/continuity metadata.

    This database stores metadata and evidence only. Credentials, device tokens and
    execution approvals stay in their existing Vishnu authorities.
    """

    SCHEMA_VERSION = 1

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except Exception:
                conn.rollback()
                raise
            else:
                conn.commit()

    def _initialize(self) -> None:
        with self.transaction() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS tc_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tc_records (
                    namespace TEXT NOT NULL,
                    record_id TEXT NOT NULL,
                    owner_id TEXT,
                    device_id TEXT,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(namespace, record_id)
                );
                CREATE INDEX IF NOT EXISTS tc_records_owner_idx
                    ON tc_records(namespace, owner_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS tc_records_device_idx
                    ON tc_records(namespace, device_id, updated_at DESC);
                CREATE TABLE IF NOT EXISTS tc_audit (
                    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    action TEXT NOT NULL,
                    actor TEXT,
                    subject TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS tc_audit_created_idx
                    ON tc_audit(created_at DESC);
                """
            )
            current = conn.execute("SELECT value FROM tc_meta WHERE key='schema_version'").fetchone()
            if current is not None and int(current["value"]) > self.SCHEMA_VERSION:
                raise RuntimeError("trust-continuity database was created by a newer Vishnu version")
            conn.execute(
                "INSERT INTO tc_meta(key,value) VALUES('schema_version',?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(self.SCHEMA_VERSION),),
            )

    def put(
        self,
        namespace: str,
        record_id: str,
        payload: dict[str, Any],
        *,
        status: str = "active",
        owner_id: str | None = None,
        device_id: str | None = None,
    ) -> dict[str, Any]:
        if not namespace or not record_id:
            raise ValueError("namespace and record_id are required")
        now = utcnow()
        encoded = bounded_json(payload)
        with self.transaction() as conn:
            previous = conn.execute(
                "SELECT created_at FROM tc_records WHERE namespace=? AND record_id=?",
                (namespace, record_id),
            ).fetchone()
            created_at = previous["created_at"] if previous else now
            conn.execute(
                """
                INSERT INTO tc_records(namespace,record_id,owner_id,device_id,status,payload_json,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(namespace,record_id) DO UPDATE SET
                    owner_id=excluded.owner_id,
                    device_id=excluded.device_id,
                    status=excluded.status,
                    payload_json=excluded.payload_json,
                    updated_at=excluded.updated_at
                """,
                (namespace, record_id, owner_id, device_id, status, encoded, created_at, now),
            )
        return self.get(namespace, record_id) or {}

    def get(self, namespace: str, record_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM tc_records WHERE namespace=? AND record_id=?",
                (namespace, record_id),
            ).fetchone()
        if row is None:
            return None
        return self._row(row)

    def list(
        self,
        namespace: str,
        *,
        owner_id: str | None = None,
        device_id: str | None = None,
        status: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        clauses = ["namespace=?"]
        params: list[Any] = [namespace]
        if owner_id is not None:
            clauses.append("owner_id=?")
            params.append(owner_id)
        if device_id is not None:
            clauses.append("device_id=?")
            params.append(device_id)
        if status is not None:
            clauses.append("status=?")
            params.append(status)
        params.append(max(1, min(int(limit), 1000)))
        sql = "SELECT * FROM tc_records WHERE " + " AND ".join(clauses) + " ORDER BY updated_at DESC LIMIT ?"
        with self._lock, self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row(row) for row in rows]

    def delete(self, namespace: str, record_id: str) -> bool:
        with self.transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM tc_records WHERE namespace=? AND record_id=?",
                (namespace, record_id),
            )
        return cursor.rowcount > 0

    def audit(
        self,
        category: str,
        action: str,
        *,
        actor: str | None = None,
        subject: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        encoded = bounded_json(payload or {}, max_bytes=65536)
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO tc_audit(category,action,actor,subject,payload_json,created_at) VALUES(?,?,?,?,?,?)",
                (category, action, actor, subject, encoded, utcnow()),
            )

    def audit_entries(self, *, limit: int = 200) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tc_audit ORDER BY audit_id DESC LIMIT ?",
                (max(1, min(int(limit), 1000)),),
            ).fetchall()
        return [
            {
                "audit_id": int(row["audit_id"]),
                "category": row["category"],
                "action": row["action"],
                "actor": row["actor"],
                "subject": row["subject"],
                "payload": json.loads(row["payload_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "namespace": row["namespace"],
            "record_id": row["record_id"],
            "owner_id": row["owner_id"],
            "device_id": row["device_id"],
            "status": row["status"],
            "payload": json.loads(row["payload_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
