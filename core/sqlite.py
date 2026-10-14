from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator, Sequence


MIGRATION_TABLE = 'vishnu_schema_versions'
_IDENTIFIER = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
MigrationCallback = Callable[[sqlite3.Connection], None]
FaultInjector = Callable[[str, int], None]


class MigrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    apply: MigrationCallback


def _identifier(value: str) -> str:
    text = str(value)
    if not _IDENTIFIER.fullmatch(text):
        raise ValueError(f'Invalid SQLite identifier: {text!r}')
    return text


def connect_sqlite(
    path: Path | str,
    *,
    timeout_seconds: float = 30.0,
    foreign_keys: bool = True,
) -> sqlite3.Connection:
    database = Path(path)
    database.parent.mkdir(parents=True, exist_ok=True)
    timeout = max(0.001, float(timeout_seconds))
    con = sqlite3.connect(database, timeout=timeout)
    con.row_factory = sqlite3.Row
    con.execute(f'PRAGMA busy_timeout={max(1, int(timeout * 1000))}')
    con.execute(f'PRAGMA foreign_keys={"ON" if foreign_keys else "OFF"}')
    return con


@contextmanager
def transaction(con: sqlite3.Connection, *, immediate: bool = False) -> Iterator[sqlite3.Connection]:
    if con.in_transaction:
        raise RuntimeError('Nested SQLite transactions are not supported by this helper')
    con.execute('BEGIN IMMEDIATE' if immediate else 'BEGIN')
    try:
        yield con
    except BaseException:
        con.rollback()
        raise
    else:
        con.commit()


def table_columns(con: sqlite3.Connection, table: str) -> set[str]:
    name = _identifier(table)
    return {str(row['name']) for row in con.execute(f'PRAGMA table_info({name})').fetchall()}


def add_column_if_missing(
    con: sqlite3.Connection,
    table: str,
    column: str,
    definition: str,
) -> bool:
    table_name = _identifier(table)
    column_name = _identifier(column)
    if column_name in table_columns(con, table_name):
        return False
    con.execute(f'ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}')
    return True


def _ensure_migration_table(con: sqlite3.Connection) -> None:
    with transaction(con, immediate=True):
        con.execute(
            f'''CREATE TABLE IF NOT EXISTS {MIGRATION_TABLE}(
                component TEXT PRIMARY KEY,
                version INTEGER NOT NULL CHECK(version >= 0),
                updated_at TEXT NOT NULL
            )'''
        )


def schema_version(con: sqlite3.Connection, component: str) -> int:
    row = con.execute(
        f'SELECT version FROM {MIGRATION_TABLE} WHERE component=?',
        (str(component),),
    ).fetchone()
    return int(row['version']) if row else 0


def _validated_migrations(migrations: Sequence[Migration]) -> tuple[Migration, ...]:
    ordered = tuple(sorted(migrations, key=lambda migration: migration.version))
    expected = tuple(range(1, len(ordered) + 1))
    actual = tuple(migration.version for migration in ordered)
    if actual != expected:
        raise ValueError(f'Migration versions must be contiguous starting at 1; received {actual!r}')
    if any(not str(migration.name).strip() for migration in ordered):
        raise ValueError('Migration names must not be empty')
    return ordered


def run_migrations(
    con: sqlite3.Connection,
    *,
    component: str,
    migrations: Sequence[Migration],
    target_version: int | None = None,
    fault_injector: FaultInjector | None = None,
) -> int:
    component_name = str(component).strip()
    if not component_name:
        raise ValueError('Migration component must not be empty')

    ordered = _validated_migrations(migrations)
    latest = len(ordered)
    requested = latest if target_version is None else int(target_version)
    if requested < 0 or requested > latest:
        raise ValueError(f'Invalid target schema version {requested}; latest is {latest}')

    _ensure_migration_table(con)
    current = schema_version(con, component_name)
    if current > latest:
        raise MigrationError(
            f'{component_name} database schema {current} is newer than supported schema {latest}'
        )
    if current > requested:
        raise MigrationError(
            f'{component_name} database schema {current} cannot be downgraded to {requested}'
        )

    while current < requested:
        version = current + 1
        migration = ordered[version - 1]
        try:
            with transaction(con, immediate=True):
                # Another process may have completed work while this connection
                # waited for the write lease, so always re-read under the lock.
                locked_version = schema_version(con, component_name)
                if locked_version > latest:
                    raise MigrationError(
                        f'{component_name} database schema {locked_version} is newer than supported schema {latest}'
                    )
                if locked_version >= version:
                    current = locked_version
                    continue
                if locked_version != version - 1:
                    raise MigrationError(
                        f'{component_name} migration order changed unexpectedly: '
                        f'expected {version - 1}, found {locked_version}'
                    )
                if fault_injector is not None:
                    fault_injector('before_apply', version)
                migration.apply(con)
                if fault_injector is not None:
                    fault_injector('after_apply', version)
                con.execute(
                    f'''INSERT INTO {MIGRATION_TABLE}(component,version,updated_at)
                        VALUES(?,?,?)
                        ON CONFLICT(component) DO UPDATE SET
                            version=excluded.version,
                            updated_at=excluded.updated_at''',
                    (component_name, version, datetime.now(timezone.utc).isoformat()),
                )
            current = version
        except MigrationError:
            raise
        except Exception as exc:
            raise MigrationError(
                f'{component_name} migration {version} ({migration.name}) failed'
            ) from exc

    return current


def run_script_migration(
    con: sqlite3.Connection,
    *,
    component: str,
    script: str,
    name: str = 'initial schema',
) -> int:
    """Apply a static SQL script as one versioned, atomic component migration.

    Statements execute individually inside run_migrations' transaction. This
    avoids executescript's implicit commit behavior and partial schema creation.
    """
    def apply(connection: sqlite3.Connection) -> None:
        pending = ''
        for line in str(script).splitlines(keepends=True):
            pending += line
            if sqlite3.complete_statement(pending):
                statement = pending.strip()
                pending = ''
                if statement:
                    connection.execute(statement)
        if pending.strip():
            raise MigrationError(f'{component} migration contains an incomplete SQL statement')

    return run_migrations(
        con,
        component=component,
        migrations=(Migration(1, name, apply),),
    )
