from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from security.projection_redaction import sanitize_sensitive_text


_WS = re.compile(r"\s+")
_HEX = re.compile(r"\b[0-9a-f]{12,}\b", re.I)
_NUM = re.compile(r"\b\d{2,}\b")


def normalized_failure_text(value: str) -> str:
    text = sanitize_sensitive_text(str(value or ""))[:8000]
    text = _HEX.sub("<hex>", text)
    text = _NUM.sub("<n>", text)
    return _WS.sub(" ", text).strip().casefold()


@dataclass(frozen=True)
class FailureFingerprint:
    fingerprint: str
    check_name: str
    normalized_excerpt: str

    @classmethod
    def build(cls, check_name: str, excerpt: str) -> "FailureFingerprint":
        name = str(check_name or "unknown")[:240]
        normalized = normalized_failure_text(excerpt)
        digest = hashlib.sha256(f"{name.casefold()}|{normalized}".encode("utf-8")).hexdigest()
        return cls(digest, name, normalized[:4000])


@dataclass(frozen=True)
class FlakyAssessment:
    test_name: str
    total_runs: int
    pass_count: int
    fail_count: int
    flaky: bool
    failure_rate: float


class EngineeringFailureStore:
    """Local sanitized failure history. It may recommend; it cannot mute gates."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS engineering_failures (
                    fingerprint TEXT PRIMARY KEY,
                    check_name TEXT NOT NULL,
                    normalized_excerpt TEXT NOT NULL,
                    occurrences INTEGER NOT NULL,
                    first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS engineering_test_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_name TEXT NOT NULL,
                    candidate_revision TEXT NOT NULL,
                    passed INTEGER NOT NULL,
                    recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_engineering_test_history_name
                    ON engineering_test_history(test_name, recorded_at);
                """
            )

    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        return connection

    def record_failure(self, check_name: str, excerpt: str) -> FailureFingerprint:
        item = FailureFingerprint.build(check_name, excerpt)
        with self._connect() as con:
            con.execute(
                """
                INSERT INTO engineering_failures(fingerprint,check_name,normalized_excerpt,occurrences)
                VALUES(?,?,?,1)
                ON CONFLICT(fingerprint) DO UPDATE SET
                    occurrences=engineering_failures.occurrences+1,
                    last_seen_at=CURRENT_TIMESTAMP
                """,
                (item.fingerprint, item.check_name, item.normalized_excerpt),
            )
        return item

    def record_test(self, test_name: str, *, candidate_revision: str, passed: bool) -> None:
        name = str(test_name or "").strip()[:500]
        revision = str(candidate_revision or "").strip()[:200]
        if not name or not revision:
            raise ValueError("test name and candidate revision are required")
        with self._connect() as con:
            con.execute(
                "INSERT INTO engineering_test_history(test_name,candidate_revision,passed) VALUES(?,?,?)",
                (name, revision, 1 if passed else 0),
            )

    def assess_flaky(self, test_name: str, *, window: int = 20, min_runs: int = 4) -> FlakyAssessment:
        limit = max(1, min(int(window), 200))
        with self._connect() as con:
            rows = con.execute(
                "SELECT passed FROM engineering_test_history WHERE test_name=? ORDER BY id DESC LIMIT ?",
                (str(test_name), limit),
            ).fetchall()
        passes = sum(1 for row in rows if int(row["passed"]) == 1)
        failures = len(rows) - passes
        flaky = len(rows) >= max(2, int(min_runs)) and passes > 0 and failures > 0
        rate = 0.0 if not rows else failures / len(rows)
        return FlakyAssessment(str(test_name), len(rows), passes, failures, flaky, rate)

    def regression_requirement(self, fingerprint: str) -> dict[str, object]:
        with self._connect() as con:
            row = con.execute(
                "SELECT check_name,occurrences FROM engineering_failures WHERE fingerprint=?",
                (str(fingerprint),),
            ).fetchone()
        if row is None:
            raise KeyError(fingerprint)
        return {
            "failure_fingerprint": str(fingerprint),
            "check_name": str(row["check_name"]),
            "occurrences": int(row["occurrences"]),
            "permanent_regression_test_required": True,
            "automatic_gate_suppression": False,
        }
