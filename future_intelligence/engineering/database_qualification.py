from __future__ import annotations

import hashlib
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable


@dataclass(frozen=True)
class DatabaseQualificationResult:
    passed: bool
    integrity_ok: bool
    foreign_keys_ok: bool
    required_tables_ok: bool
    source_unchanged: bool
    schema_before_hash: str
    schema_after_hash: str
    missing_tables: tuple[str, ...] = ()
    details: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "integrity_ok": self.integrity_ok,
            "foreign_keys_ok": self.foreign_keys_ok,
            "required_tables_ok": self.required_tables_ok,
            "source_unchanged": self.source_unchanged,
            "schema_before_hash": self.schema_before_hash,
            "schema_after_hash": self.schema_after_hash,
            "missing_tables": list(self.missing_tables),
            "details": list(self.details),
        }


class SqliteMigrationSandbox:
    """Run a trusted migration callback against a temporary SQLite clone only.

    No SQL text is accepted from models or user content. The callback is supplied
    by trusted application code. The source database is opened read-only for the
    backup step and hashed before/after to prove it was not mutated by the sandbox.
    """

    def __init__(self, *, timeout_seconds: float = 10.0) -> None:
        self.timeout_seconds = max(1.0, min(float(timeout_seconds), 120.0))

    @staticmethod
    def _sha(path: Path) -> str:
        if not path.exists():
            return hashlib.sha256(b"").hexdigest()
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _schema_hash(connection: sqlite3.Connection) -> str:
        rows = connection.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type,name,tbl_name"
        ).fetchall()
        raw = "\n".join("|".join(str(item or "") for item in row) for row in rows)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def qualify(
        self,
        source: str | Path,
        *,
        migrate: Callable[[sqlite3.Connection], object],
        required_tables: Iterable[str] = (),
    ) -> DatabaseQualificationResult:
        if not callable(migrate):
            raise TypeError("migration sandbox requires a trusted callable")
        raw_source = Path(source).expanduser()
        if raw_source.is_symlink() or not raw_source.is_file():
            raise ValueError("source SQLite database must be a non-symlink regular file")
        source_path = raw_source.resolve(strict=True)
        source_before = self._sha(source_path)
        details: list[str] = []
        with tempfile.TemporaryDirectory(prefix="vishnu-db-qualification-") as tmp:
            clone = Path(tmp) / "candidate.sqlite3"
            source_uri = f"file:{source_path.as_posix()}?mode=ro"
            with sqlite3.connect(source_uri, uri=True, timeout=self.timeout_seconds) as source_connection:
                with sqlite3.connect(clone, timeout=self.timeout_seconds) as clone_connection:
                    source_connection.backup(clone_connection)
            with sqlite3.connect(clone, timeout=self.timeout_seconds) as connection:
                connection.execute("PRAGMA foreign_keys = ON")
                schema_before = self._schema_hash(connection)
                migrate(connection)
                connection.commit()
                schema_after = self._schema_hash(connection)
                integrity_rows = connection.execute("PRAGMA integrity_check").fetchall()
                integrity_ok = bool(integrity_rows) and all(str(row[0]).casefold() == "ok" for row in integrity_rows)
                foreign_rows = connection.execute("PRAGMA foreign_key_check").fetchall()
                foreign_keys_ok = len(foreign_rows) == 0
                tables = {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                required = tuple(dict.fromkeys(str(item) for item in required_tables if str(item)))
                missing = tuple(sorted(item for item in required if item not in tables))
                required_ok = not missing
                if not integrity_ok:
                    details.append("SQLite integrity_check failed")
                if not foreign_keys_ok:
                    details.append(f"foreign_key_check returned {len(foreign_rows)} violations")
                if missing:
                    details.append("missing required tables: " + ", ".join(missing))
        source_after = self._sha(source_path)
        source_unchanged = source_before == source_after
        if not source_unchanged:
            details.append("source database changed during sandbox qualification")
        passed = integrity_ok and foreign_keys_ok and required_ok and source_unchanged
        return DatabaseQualificationResult(
            passed=passed,
            integrity_ok=integrity_ok,
            foreign_keys_ok=foreign_keys_ok,
            required_tables_ok=required_ok,
            source_unchanged=source_unchanged,
            schema_before_hash=schema_before,
            schema_after_hash=schema_after,
            missing_tables=missing,
            details=tuple(details),
        )
