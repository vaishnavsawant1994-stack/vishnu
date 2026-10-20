from __future__ import annotations

import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from core.sqlite import (
    MIGRATION_TABLE,
    Migration,
    MigrationError,
    connect_sqlite,
    run_migrations,
    schema_version,
)
from devices.registry import DeviceRegistry


def test_connect_sqlite_enforces_foreign_keys_and_busy_timeout(tmp_path):
    path = tmp_path / 'nested' / 'foundation.sqlite3'
    con = connect_sqlite(path)
    try:
        assert con.execute('PRAGMA foreign_keys').fetchone()[0] == 1
        assert con.execute('PRAGMA busy_timeout').fetchone()[0] == 30000
        con.execute('CREATE TABLE parents(id INTEGER PRIMARY KEY)')
        con.execute(
            'CREATE TABLE children(id INTEGER PRIMARY KEY,parent_id INTEGER NOT NULL REFERENCES parents(id))'
        )
        with pytest.raises(sqlite3.IntegrityError):
            con.execute('INSERT INTO children(id,parent_id) VALUES(1,99)')
    finally:
        con.close()


def test_migrations_apply_once_and_record_component_version(tmp_path):
    path = tmp_path / 'once.sqlite3'
    calls = []

    def migration_1(con):
        calls.append(1)
        con.execute('CREATE TABLE alpha(id INTEGER PRIMARY KEY)')

    def migration_2(con):
        calls.append(2)
        con.execute('CREATE TABLE beta(id INTEGER PRIMARY KEY)')

    migrations = (
        Migration(1, 'alpha', migration_1),
        Migration(2, 'beta', migration_2),
    )
    con = connect_sqlite(path)
    try:
        assert run_migrations(con, component='example', migrations=migrations) == 2
        assert run_migrations(con, component='example', migrations=migrations) == 2
        assert schema_version(con, 'example') == 2
        assert calls == [1, 2]
    finally:
        con.close()


def test_failed_migration_rolls_back_and_retries_cleanly(tmp_path):
    path = tmp_path / 'rollback.sqlite3'

    def migration_1(con):
        con.execute('CREATE TABLE stable(id INTEGER PRIMARY KEY)')

    def broken_migration_2(con):
        con.execute('CREATE TABLE should_rollback(id INTEGER PRIMARY KEY)')
        raise RuntimeError('injected migration failure')

    con = connect_sqlite(path)
    try:
        first = (Migration(1, 'stable', migration_1),)
        assert run_migrations(con, component='recovery', migrations=first) == 1

        broken = (
            Migration(1, 'stable', migration_1),
            Migration(2, 'broken', broken_migration_2),
        )
        with pytest.raises(MigrationError):
            run_migrations(con, component='recovery', migrations=broken)

        assert schema_version(con, 'recovery') == 1
        assert con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='should_rollback'"
        ).fetchone() is None

        def repaired_migration_2(connection):
            connection.execute('CREATE TABLE recovered(id INTEGER PRIMARY KEY)')

        repaired = (
            Migration(1, 'stable', migration_1),
            Migration(2, 'repaired', repaired_migration_2),
        )
        assert run_migrations(con, component='recovery', migrations=repaired) == 2
        assert schema_version(con, 'recovery') == 2
        assert con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='recovered'"
        ).fetchone() is not None
    finally:
        con.close()


def test_fault_after_apply_rolls_back_schema_and_version(tmp_path):
    path = tmp_path / 'fault.sqlite3'
    con = connect_sqlite(path)
    try:
        migration = Migration(
            1,
            'create-payloads',
            lambda connection: connection.execute('CREATE TABLE payloads(id INTEGER PRIMARY KEY)'),
        )

        def fail_after_apply(phase, version):
            if phase == 'after_apply' and version == 1:
                raise RuntimeError('simulated crash')

        with pytest.raises(MigrationError):
            run_migrations(
                con,
                component='faulted',
                migrations=(migration,),
                fault_injector=fail_after_apply,
            )
        assert schema_version(con, 'faulted') == 0
        assert con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='payloads'"
        ).fetchone() is None

        assert run_migrations(con, component='faulted', migrations=(migration,)) == 1
    finally:
        con.close()


def test_concurrent_initializers_apply_each_migration_once(tmp_path):
    path = tmp_path / 'concurrent.sqlite3'
    barrier = threading.Barrier(2)
    callback_calls = []

    def migration_1(con):
        callback_calls.append(threading.get_ident())
        con.execute('CREATE TABLE migration_effects(id INTEGER PRIMARY KEY)')
        con.execute('INSERT INTO migration_effects(id) VALUES(1)')

    migrations = (Migration(1, 'single-effect', migration_1),)

    def worker():
        con = connect_sqlite(path)
        try:
            barrier.wait(timeout=5)
            return run_migrations(con, component='concurrent', migrations=migrations)
        finally:
            con.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _value: worker(), range(2)))

    assert results == [1, 1]
    assert len(callback_calls) == 1
    con = connect_sqlite(path)
    try:
        assert schema_version(con, 'concurrent') == 1
        assert con.execute('SELECT COUNT(*) FROM migration_effects').fetchone()[0] == 1
    finally:
        con.close()


def test_schema_newer_than_code_fails_closed(tmp_path):
    path = tmp_path / 'future.sqlite3'
    con = connect_sqlite(path)
    try:
        con.execute(
            f'''CREATE TABLE {MIGRATION_TABLE}(
                component TEXT PRIMARY KEY,
                version INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            )'''
        )
        con.execute(
            f'INSERT INTO {MIGRATION_TABLE}(component,version,updated_at) VALUES(?,?,?)',
            ('future', 99, 'now'),
        )
        con.commit()
        with pytest.raises(MigrationError, match='newer than supported'):
            run_migrations(
                con,
                component='future',
                migrations=(Migration(1, 'old-code', lambda _con: None),),
            )
    finally:
        con.close()


def test_device_registry_upgrades_legacy_permissions_once(tmp_path):
    path = tmp_path / 'devices.sqlite3'
    raw = sqlite3.connect(path)
    try:
        raw.execute('''CREATE TABLE devices(id TEXT PRIMARY KEY,name TEXT NOT NULL,platform TEXT NOT NULL,salt TEXT NOT NULL,token_hash TEXT NOT NULL,created_at TEXT NOT NULL,last_seen_at TEXT,revoked INTEGER NOT NULL DEFAULT 0)''')
        raw.execute('''CREATE TABLE device_metadata(device_id TEXT NOT NULL,key TEXT NOT NULL,value TEXT NOT NULL,updated_at TEXT NOT NULL,PRIMARY KEY(device_id,key),FOREIGN KEY(device_id) REFERENCES devices(id) ON DELETE CASCADE)''')
        raw.execute('''CREATE TABLE device_permissions(device_id TEXT PRIMARY KEY,scopes_json TEXT NOT NULL,updated_at TEXT NOT NULL,FOREIGN KEY(device_id) REFERENCES devices(id) ON DELETE CASCADE)''')
        raw.execute(
            'INSERT INTO devices VALUES(?,?,?,?,?,?,?,0)',
            ('legacy-phone', 'Legacy Phone', 'android', 'salt', 'hash', 'created', None),
        )
        raw.execute(
            'INSERT INTO device_permissions VALUES(?,?,?)',
            ('legacy-phone', json.dumps(sorted(DeviceRegistry.LEGACY_DEFAULT_SCOPES)), 'old'),
        )
        raw.commit()
    finally:
        raw.close()

    registry = DeviceRegistry(path)
    assert set(registry.permissions('legacy-phone')['scopes']) == DeviceRegistry.DEFAULT_SCOPES

    con = connect_sqlite(path)
    try:
        assert schema_version(con, 'device_registry') == 5
    finally:
        con.close()

    # A restart must not re-run migration side effects or change customized state.
    customized = {'ai:chat', 'data:read'}
    registry.set_permissions('legacy-phone', customized)
    restarted = DeviceRegistry(path)
    assert set(restarted.permissions('legacy-phone')['scopes']) == customized


def test_device_registry_foreign_key_cascade_is_active(tmp_path):
    path = tmp_path / 'devices.sqlite3'
    registry = DeviceRegistry(path)
    device, _token = registry.enroll('Phone', 'android')
    assert registry.set_metadata(device['id'], 'label', 'primary') is True

    con = registry._con()
    try:
        with con:
            con.execute('DELETE FROM devices WHERE id=?', (device['id'],))
        assert con.execute(
            'SELECT 1 FROM device_permissions WHERE device_id=?', (device['id'],)
        ).fetchone() is None
        assert con.execute(
            'SELECT 1 FROM device_metadata WHERE device_id=?', (device['id'],)
        ).fetchone() is None
    finally:
        con.close()
