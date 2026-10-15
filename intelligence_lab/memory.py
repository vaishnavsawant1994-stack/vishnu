from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any


class LabMemory:
    """SQLite store owned exclusively by the Intelligence Lab.

    This store intentionally exposes no API for writing Vishnu's stable memory,
    preferences, policy, approvals, devices, secrets, or audit databases.
    """

    def __init__(self, path: Path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=15)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA foreign_keys=ON")
        return con

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

    def get(self, record_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as con:
            row = con.execute(
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
        limit = max(1, min(int(limit), 500))
        query = "SELECT id,kind,payload,created_at FROM lab_records"
        args: tuple[Any, ...]
        if kind:
            query += " WHERE kind=?"
            args = (kind, limit)
            query += " ORDER BY created_at DESC LIMIT ?"
        else:
            args = (limit,)
            query += " ORDER BY created_at DESC LIMIT ?"
        with self._lock, self._connect() as con:
            rows = con.execute(query, args).fetchall()
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
        with self._lock, self._connect() as con:
            rows = con.execute(
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
        limit = max(1, min(int(limit), 1000))
        with self._lock, self._connect() as con:
            rows = con.execute(
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
