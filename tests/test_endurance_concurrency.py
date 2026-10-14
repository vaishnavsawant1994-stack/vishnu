from __future__ import annotations

import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from core.sqlite import connect_sqlite, transaction
from memory.store import MemoryStore
from security.vault import SecretVault


class _RotatingRootKeyStore:
    def __init__(self, initial: bytes):
        self.active = initial
        self.staged: dict[str, bytes] = {}

    def get(self) -> bytes:
        return self.active

    def get_or_create(self) -> bytes:
        return self.active

    def validate_rotation_id(self, rotation_id: str) -> str:
        if len(rotation_id) != 32 or any(c not in "0123456789abcdef" for c in rotation_id):
            raise ValueError("invalid rotation id")
        return rotation_id

    def stage_rotation(self, rotation_id: str) -> bytes:
        self.validate_rotation_id(rotation_id)
        return self.staged.setdefault(rotation_id, b"n" * 32)

    def promote_staged(self, rotation_id: str) -> bytes:
        self.active = self.staged[rotation_id]
        return self.active

    def discard_staged(self, rotation_id: str) -> None:
        self.staged.pop(rotation_id, None)


def test_shared_sqlite_endurance_with_concurrent_connections(tmp_path: Path) -> None:
    database = tmp_path / "writers.sqlite3"
    with connect_sqlite(database) as connection:
        connection.execute("CREATE TABLE writes(worker INTEGER NOT NULL, sequence INTEGER NOT NULL, PRIMARY KEY(worker, sequence))")

    workers = 8
    writes_per_worker = 30
    barrier = threading.Barrier(workers)

    def write_batch(worker: int) -> None:
        barrier.wait(timeout=10)
        for sequence in range(writes_per_worker):
            connection = connect_sqlite(database, timeout_seconds=30)
            try:
                with transaction(connection, immediate=True):
                    connection.execute(
                        "INSERT INTO writes(worker, sequence) VALUES(?, ?)",
                        (worker, sequence),
                    )
            finally:
                connection.close()

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(write_batch, worker) for worker in range(workers)]
        for future in futures:
            future.result(timeout=60)

    with connect_sqlite(database) as connection:
        count = connection.execute("SELECT COUNT(*) FROM writes").fetchone()[0]
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    assert count == workers * writes_per_worker
    assert integrity == "ok"


def test_memory_store_concurrent_write_search_and_restart(tmp_path: Path) -> None:
    database = tmp_path / "assistant.sqlite3"
    vault_path = tmp_path / "vault.json"
    password = "deterministic-test-vault-password"
    vault = SecretVault(vault_path, password)
    store = MemoryStore(database, vault=vault)

    workers = 6
    writes_per_worker = 15
    barrier = threading.Barrier(workers)
    sentinel = "MEMORY_STRESS_PRIVATE_CONTENT_"

    def write_batch(worker: int) -> list[str]:
        barrier.wait(timeout=10)
        created = []
        for sequence in range(writes_per_worker):
            marker = f"{sentinel}{worker}_{sequence}"
            memory_id = store.remember(
                type="note",
                subject=f"shared_marker_endurance_{worker}_{sequence}",
                content=marker,
                source="user",
                tags=["endurance"],
            )
            assert store.get(memory_id)["content"] == marker
            assert store.record_usage(memory_id, query=f"private_query_{worker}_{sequence}")
            created.append(memory_id)
        return created

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(write_batch, worker) for worker in range(workers)]
        memory_ids = [memory_id for future in futures for memory_id in future.result(timeout=60)]

    assert len(memory_ids) == workers * writes_per_worker
    found = store.search("shared_marker_endurance", limit=1000)
    assert len(found) == len(memory_ids)
    assert {item["id"] for item in found} == set(memory_ids)

    for path in (database, database.with_name(database.name + "-wal")):
        if path.exists():
            assert sentinel.encode("utf-8") not in path.read_bytes()

    # Reopening the persisted vault and store must preserve decryptability and search.
    reopened_vault = SecretVault(vault_path, password)
    reopened = MemoryStore(database, vault=reopened_vault)
    assert len(reopened.search("shared_marker_endurance", limit=1000)) == len(memory_ids)
    assert reopened.get(memory_ids[0])["content"].startswith(sentinel)


def test_secret_vault_reads_survive_concurrent_root_rotation(tmp_path: Path) -> None:
    root_keys = _RotatingRootKeyStore(b"a" * 32)
    vault_path = tmp_path / "vault.json"
    vault = SecretVault(vault_path, root_key_store=root_keys)
    vault.set("stable", "value-preserved-through-rotation")

    readers = 8
    barrier = threading.Barrier(readers + 1)

    def read_repeatedly() -> None:
        barrier.wait(timeout=10)
        for _ in range(100):
            assert vault.get("stable") == "value-preserved-through-rotation"

    def rotate() -> None:
        barrier.wait(timeout=10)
        vault.rotate_root_key()

    with ThreadPoolExecutor(max_workers=readers + 1) as executor:
        futures = [executor.submit(read_repeatedly) for _ in range(readers)]
        futures.append(executor.submit(rotate))
        for future in futures:
            future.result(timeout=30)

    assert root_keys.active == b"n" * 32
    assert root_keys.staged == {}
    assert not vault_path.with_suffix(".json.rotation").exists()
    reopened = SecretVault(vault_path, root_key_store=root_keys)
    assert reopened.get("stable") == "value-preserved-through-rotation"
