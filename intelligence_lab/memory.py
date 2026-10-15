from __future__ import annotations

import atexit
import json
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any, Iterable


class LabMemory:
    """SQLite store owned exclusively by the Intelligence Lab.

    Phase 3 keeps the original isolation boundary while reducing connection
    churn with thread-local reusable connections, WAL/NORMAL tuning, batched
    writes and bounded indexed reads. This store intentionally exposes no API
    for writing Vishnu's stable memory, preferences, policy, approvals,
    devices, secrets, or audit databases.
    """

    def __init__(self, path: Path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._local = threading.local()
        self._connections: list[sqlite3.Connection] = []
        self._connections_lock = threading.RLock()
        self._initialize()
        atexit.register(self.close)

    def _new_connection(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=15)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA synchronous=NORMAL")
        con.execute("PRAGMA temp_store=MEMORY")
        con.execute("PRAGMA busy_timeout=15000")
        con.execute("PRAGMA cache_size=-8192")
        with self._connections_lock:
            self._connections.append(con)
        return con

    def _connect(self) -> sqlite3.Connection:
        con = getattr(self._local, "connection", None)
        if con is None:
            con = self._new_connection()
            self._local.connection = con
        return con

    def close(self) -> None:
        with self._connections_lock:
            connections = tuple(self._connections)
            self._connections.clear()
        for con in connections:
            try:
                con.close()
            except Exception:
                pass
        try:
            self._local.connection = None
        except Exception:
            pass

    def _initialize(self) -> None:
        with self._lock, self._connect() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS lab_records (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_lab_records_kind_time
                    ON lab_records(kind, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_lab_records_time
                    ON lab_records(created_at DESC);
                CREATE TABLE IF NOT EXISTS lab_skills (
                    name TEXT PRIMARY KEY,
                    description TEXT NOT NULL,
                    evidence TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    status TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS lab_audit (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    action TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_lab_audit_category_time
                    ON lab_audit(category, created_at DESC);
                """
            )

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)

    def put(self, record_id: str, kind: str, payload: dict[str, Any]) -> str:
        now = time.time()
        with self._lock, self._connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO lab_records(id, kind, payload, created_at) VALUES(?,?,?,?)",
                (record_id, kind, self._json(payload), now),
            )
        return record_id

    def put_many(
        self,
        records: Iterable[tuple[str, str, dict[str, Any]]],
    ) -> int:
        rows = [
            (str(record_id), str(kind), self._json(payload), time.time())
            for record_id, kind, payload in records
        ]
        if not rows:
            return 0
        with self._lock, self._connect() as con:
            con.executemany(
                "INSERT OR REPLACE INTO lab_records(id, kind, payload, created_at) VALUES(?,?,?,?)",
                rows,
            )
        return len(rows)

    def get(self, record_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connect().execute(
                "SELECT id,kind,payload,created_at FROM lab_records WHERE id=?",
                (record_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "kind": row["kind"],
            "payload": json.loads(row["payload"]),
            "created_at": row["created_at"],
        }

    def recent(self, kind: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 50000))
        query = "SELECT id,kind,payload,created_at FROM lab_records"
        args: tuple[Any, ...]
        if kind:
            query += " WHERE kind=?"
            args = (kind, limit)
            query += " ORDER BY created_at DESC LIMIT ?"
        else:
            args = (limit,)
            query += " ORDER BY created_at DESC LIMIT ?"
        with self._lock:
            rows = self._connect().execute(query, args).fetchall()
        return [
            {
                "id": row["id"],
                "kind": row["kind"],
                "payload": json.loads(row["payload"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def recent_since(
        self,
        since: float,
        *,
        kind: str | None = None,
        limit: int = 5000,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 50000))
        if kind:
            query = (
                "SELECT id,kind,payload,created_at FROM lab_records "
                "WHERE kind=? AND created_at>=? ORDER BY created_at DESC LIMIT ?"
            )
            args = (kind, float(since), limit)
        else:
            query = (
                "SELECT id,kind,payload,created_at FROM lab_records "
                "WHERE created_at>=? ORDER BY created_at DESC LIMIT ?"
            )
            args = (float(since), limit)
        with self._lock:
            rows = self._connect().execute(query, args).fetchall()
        return [
            {
                "id": row["id"],
                "kind": row["kind"],
                "payload": json.loads(row["payload"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def upsert_skill(
        self,
        name: str,
        description: str,
        evidence: list[str] | tuple[str, ...],
        confidence: float,
        *,
        status: str = "experimental",
    ) -> None:
        confidence = max(0.0, min(float(confidence), 1.0))
        if status not in {"experimental", "evaluated", "verified", "eligible"}:
            raise ValueError("invalid lab skill status")
        with self._lock, self._connect() as con:
            con.execute(
                """
                INSERT INTO lab_skills(name,description,evidence,confidence,status,updated_at)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(name) DO UPDATE SET
                    description=excluded.description,
                    evidence=excluded.evidence,
                    confidence=excluded.confidence,
                    status=excluded.status,
                    updated_at=excluded.updated_at
                """,
                (name, description, self._json(list(evidence)), confidence, status, time.time()),
            )

    def skills(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connect().execute(
                "SELECT name,description,evidence,confidence,status,updated_at FROM lab_skills ORDER BY name"
            ).fetchall()
        return [
            {
                "name": row["name"],
                "description": row["description"],
                "evidence": json.loads(row["evidence"]),
                "confidence": row["confidence"],
                "status": row["status"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def audit(self, category: str, action: str, payload: dict[str, Any] | None = None) -> None:
        with self._lock, self._connect() as con:
            con.execute(
                "INSERT INTO lab_audit(category,action,payload,created_at) VALUES(?,?,?,?)",
                (category, action, self._json(payload or {}), time.time()),
            )

    def audit_log(self, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 5000))
        with self._lock:
            rows = self._connect().execute(
                "SELECT seq,category,action,payload,created_at FROM lab_audit ORDER BY seq DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {
                "seq": row["seq"],
                "category": row["category"],
                "action": row["action"],
                "payload": json.loads(row["payload"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def performance_pragmas(self) -> dict[str, Any]:
        with self._lock:
            con = self._connect()
            values = {}
            for pragma in ("journal_mode", "synchronous", "cache_size", "temp_store", "busy_timeout"):
                row = con.execute(f"PRAGMA {pragma}").fetchone()
                values[pragma] = row[0] if row is not None else None
        return {
            **values,
            "thread_local_connection_reuse": True,
            "batched_writes": True,
        }
