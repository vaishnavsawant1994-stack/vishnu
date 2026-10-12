from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path
from threading import RLock
from typing import Any, Protocol
from uuid import uuid4

from .engine import FileIntelligenceEngine


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _now() -> str:
    return _utcnow().isoformat()


def _safe_name(value: str) -> str:
    name = Path(str(value or "")).name.strip()
    if not name or name in {".", ".."} or len(name) > 240 or any(ord(ch) < 32 for ch in name):
        raise ValueError("A safe filename is required")
    return name


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


class UploadStatus(StrEnum):
    OPEN = "open"
    COMPLETE = "complete"
    CANCELLED = "cancelled"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ResourceClass(StrEnum):
    CPU = "cpu"
    GPU_PREFERRED = "gpu_preferred"
    GPU_REQUIRED = "gpu_required"


@dataclass(frozen=True)
class StoredObject:
    sha256: str
    size_bytes: int
    path: str
    existed: bool


class ObjectStore(Protocol):
    def put_file(self, source: Path, *, expected_sha256: str | None = None) -> StoredObject: ...
    def path_for(self, sha256: str) -> Path: ...


class ContentAddressedObjectStore:
    """Atomic SHA-256 object storage with deduplication and integrity checks."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.objects = self.root / "objects"
        self.tmp = self.root / "tmp"
        self.objects.mkdir(parents=True, exist_ok=True)
        self.tmp.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

    @staticmethod
    def valid_sha(value: str) -> str:
        value = str(value or "").strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError("Invalid SHA-256 object identifier")
        return value

    def path_for(self, sha256: str) -> Path:
        sha256 = self.valid_sha(sha256)
        target = (self.objects / sha256[:2] / sha256[2:4] / sha256).resolve()
        target.relative_to(self.objects)
        return target

    def put_file(self, source: Path, *, expected_sha256: str | None = None) -> StoredObject:
        source = Path(source)
        digest, size = _sha256_file(source)
        if expected_sha256 and digest != self.valid_sha(expected_sha256):
            raise ValueError("Object checksum does not match expected SHA-256")
        target = self.path_for(digest)
        with self._lock:
            if target.exists():
                old_digest, old_size = _sha256_file(target)
                if old_digest != digest or old_size != size:
                    raise RuntimeError("Existing content-addressed object failed integrity verification")
                return StoredObject(digest, size, str(target), True)
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, temp_name = tempfile.mkstemp(prefix=f".{digest}.", suffix=".tmp", dir=target.parent)
            os.close(fd)
            temp = Path(temp_name)
            try:
                with source.open("rb") as src, temp.open("wb") as dst:
                    shutil.copyfileobj(src, dst, length=1024 * 1024)
                    dst.flush()
                    os.fsync(dst.fileno())
                check, check_size = _sha256_file(temp)
                if check != digest or check_size != size:
                    raise RuntimeError("Object checksum failed after write")
                if target.exists():
                    current, current_size = _sha256_file(target)
                    if current != digest or current_size != size:
                        raise RuntimeError("Concurrent object write failed integrity verification")
                else:
                    os.replace(temp, target)
                return StoredObject(digest, size, str(target), False)
            finally:
                temp.unlink(missing_ok=True)

    def put_bytes(self, payload: bytes) -> StoredObject:
        fd, name = tempfile.mkstemp(prefix="vishnu-object-", dir=self.tmp)
        os.close(fd)
        path = Path(name)
        try:
            path.write_bytes(payload)
            return self.put_file(path)
        finally:
            path.unlink(missing_ok=True)

    def verify(self, sha256: str) -> bool:
        path = self.path_for(sha256)
        if not path.is_file():
            return False
        digest, _ = _sha256_file(path)
        return digest == self.valid_sha(sha256)


class ProductionContentStore:
    """Durable resumable uploads, extraction versions and lease-based ingestion jobs."""

    DEFAULT_MAX_UPLOAD_BYTES = 20 * 1024 * 1024 * 1024
    MAX_CHUNK_BYTES = 16 * 1024 * 1024

    def __init__(self, db_path: str | Path, object_root: str | Path, *, max_upload_bytes: int | None = None):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.object_store = ContentAddressedObjectStore(object_root)
        self.upload_root = self.object_store.root / "uploads"
        self.upload_root.mkdir(parents=True, exist_ok=True)
        self.max_upload_bytes = int(max_upload_bytes or self.DEFAULT_MAX_UPLOAD_BYTES)
        self._lock = RLock()
        self._init()

    def con(self):
        con = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=30000")
        return con

    def _init(self):
        with self.con() as con:
            con.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS content_uploads(
                    upload_id TEXT PRIMARY KEY,scope_type TEXT NOT NULL,scope_id TEXT NOT NULL,
                    filename TEXT NOT NULL,declared_mime TEXT NOT NULL,total_bytes INTEGER NOT NULL,
                    received_bytes INTEGER NOT NULL DEFAULT 0,expected_sha256 TEXT,object_sha256 TEXT,
                    status TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,completed_at TEXT,
                    temp_path TEXT NOT NULL,metadata_json TEXT NOT NULL DEFAULT '{}');
                CREATE INDEX IF NOT EXISTS idx_content_upload_scope ON content_uploads(scope_type,scope_id,status,created_at);
                CREATE TABLE IF NOT EXISTS content_ingestion_jobs(
                    job_id TEXT PRIMARY KEY,idempotency_key TEXT NOT NULL UNIQUE,object_sha256 TEXT NOT NULL,
                    filename TEXT NOT NULL,declared_mime TEXT NOT NULL,scope_type TEXT NOT NULL,scope_id TEXT NOT NULL,
                    extraction_version INTEGER NOT NULL,resource_class TEXT NOT NULL,status TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 0,attempts INTEGER NOT NULL DEFAULT 0,max_attempts INTEGER NOT NULL DEFAULT 3,
                    available_at TEXT NOT NULL,lease_owner TEXT,lease_expires_at TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
                    started_at TEXT,completed_at TEXT,result_sha256 TEXT,error_code TEXT,error_message TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}');
                CREATE INDEX IF NOT EXISTS idx_content_jobs_claim ON content_ingestion_jobs(status,available_at,priority,created_at);
                CREATE INDEX IF NOT EXISTS idx_content_jobs_scope ON content_ingestion_jobs(scope_type,scope_id,status,created_at);
                CREATE TABLE IF NOT EXISTS content_extractions(
                    object_sha256 TEXT NOT NULL,scope_type TEXT NOT NULL,scope_id TEXT NOT NULL,extraction_version INTEGER NOT NULL,
                    result_sha256 TEXT NOT NULL,document_id TEXT NOT NULL,schema_version TEXT NOT NULL,parser_version TEXT NOT NULL,
                    created_at TEXT NOT NULL,metadata_json TEXT NOT NULL DEFAULT '{}',
                    PRIMARY KEY(object_sha256,scope_type,scope_id,extraction_version));
                CREATE TABLE IF NOT EXISTS content_runtime_events(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,at TEXT NOT NULL,event_type TEXT NOT NULL,job_id TEXT,upload_id TEXT,
                    scope_type TEXT,scope_id TEXT,duration_ms REAL,bytes INTEGER,metadata_json TEXT NOT NULL DEFAULT '{}');
                CREATE INDEX IF NOT EXISTS idx_content_events_at ON content_runtime_events(at,event_type);
                """
            )

    def _event(self, con, event_type: str, *, job_id=None, upload_id=None, scope_type=None, scope_id=None, duration_ms=None, bytes_count=None, metadata=None):
        con.execute(
            "INSERT INTO content_runtime_events(at,event_type,job_id,upload_id,scope_type,scope_id,duration_ms,bytes,metadata_json) VALUES(?,?,?,?,?,?,?,?,?)",
            (_now(), event_type, job_id, upload_id, scope_type, scope_id, duration_ms, bytes_count, json.dumps(metadata or {}, sort_keys=True, default=str)),
        )

    def create_upload(self, *, scope_type: str, scope_id: str, filename: str, total_bytes: int, declared_mime: str = "application/octet-stream", expected_sha256: str | None = None, metadata: dict | None = None) -> dict:
        scope_type, scope_id = str(scope_type).strip(), str(scope_id).strip()
        if not scope_type or not scope_id:
            raise ValueError("Upload requires explicit scope_type and scope_id")
        filename = _safe_name(filename)
        total_bytes = int(total_bytes)
        if total_bytes <= 0 or total_bytes > self.max_upload_bytes:
            raise ValueError("Upload size is outside the configured limit")
        if expected_sha256:
            expected_sha256 = self.object_store.valid_sha(expected_sha256)
        upload_id = f"upl_{uuid4().hex}"
        temp_path = (self.upload_root / f"{upload_id}.part").resolve()
        temp_path.relative_to(self.upload_root.resolve())
        temp_path.touch(exist_ok=False)
        now = _now()
        with self.con() as con:
            con.execute(
                "INSERT INTO content_uploads VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (upload_id, scope_type, scope_id, filename, str(declared_mime or "application/octet-stream"), total_bytes, 0, expected_sha256, None, UploadStatus.OPEN.value, now, now, None, str(temp_path), json.dumps(metadata or {}, sort_keys=True, default=str)),
            )
            self._event(con, "upload.created", upload_id=upload_id, scope_type=scope_type, scope_id=scope_id, bytes_count=total_bytes)
        return self.upload(upload_id, scope_type=scope_type, scope_id=scope_id)

    def upload(self, upload_id: str, *, scope_type: str | None = None, scope_id: str | None = None) -> dict | None:
        sql, args = "SELECT * FROM content_uploads WHERE upload_id=?", [str(upload_id)]
        if scope_type is not None:
            sql += " AND scope_type=?"; args.append(str(scope_type))
        if scope_id is not None:
            sql += " AND scope_id=?"; args.append(str(scope_id))
        with self.con() as con:
            row = con.execute(sql, args).fetchone()
        if not row:
            return None
        item = dict(row)
        item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
        item["progress"] = item["received_bytes"] / item["total_bytes"] if item["total_bytes"] else 0.0
        item.pop("temp_path", None)
        return item

    def append_chunk(self, upload_id: str, *, offset: int, chunk: bytes, scope_type: str | None = None, scope_id: str | None = None) -> dict:
        if not chunk:
            raise ValueError("Upload chunk is empty")
        if len(chunk) > self.MAX_CHUNK_BYTES:
            raise ValueError("Upload chunk exceeds the configured limit")
        with self._lock, self.con() as con:
            con.execute("BEGIN IMMEDIATE")
            sql, args = "SELECT * FROM content_uploads WHERE upload_id=?", [str(upload_id)]
            if scope_type is not None:
                sql += " AND scope_type=?"; args.append(str(scope_type))
            if scope_id is not None:
                sql += " AND scope_id=?"; args.append(str(scope_id))
            row = con.execute(sql, args).fetchone()
            if not row:
                con.rollback(); raise KeyError(upload_id)
            if row["status"] != UploadStatus.OPEN.value:
                con.rollback(); raise ValueError("Upload is not open")
            expected = int(row["received_bytes"])
            if int(offset) != expected:
                con.rollback(); raise ValueError(f"Upload offset mismatch: expected {expected}")
            if expected + len(chunk) > int(row["total_bytes"]):
                con.rollback(); raise ValueError("Upload chunk exceeds declared total size")
            path = Path(row["temp_path"])
            if path.stat().st_size != expected:
                con.rollback(); raise RuntimeError("Upload temporary file length does not match durable offset")
            with path.open("ab") as stream:
                stream.write(chunk); stream.flush(); os.fsync(stream.fileno())
            received = expected + len(chunk)
            con.execute("UPDATE content_uploads SET received_bytes=?,updated_at=? WHERE upload_id=?", (received, _now(), upload_id))
            self._event(con, "upload.chunk", upload_id=upload_id, scope_type=row["scope_type"], scope_id=row["scope_id"], bytes_count=len(chunk), metadata={"offset": offset})
            con.commit()
        return self.upload(upload_id, scope_type=scope_type, scope_id=scope_id)

    def finalize_upload(self, upload_id: str, *, scope_type: str | None = None, scope_id: str | None = None) -> dict:
        with self._lock, self.con() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT * FROM content_uploads WHERE upload_id=?", (str(upload_id),)).fetchone()
            if not row or (scope_type is not None and row["scope_type"] != scope_type) or (scope_id is not None and row["scope_id"] != scope_id):
                con.rollback(); raise KeyError(upload_id)
            if row["status"] == UploadStatus.COMPLETE.value:
                con.commit(); return self.upload(upload_id, scope_type=scope_type, scope_id=scope_id)
            if row["status"] != UploadStatus.OPEN.value or int(row["received_bytes"]) != int(row["total_bytes"]):
                con.rollback(); raise ValueError("Upload is incomplete or not open")
            path = Path(row["temp_path"])
            obj = self.object_store.put_file(path, expected_sha256=row["expected_sha256"])
            if obj.size_bytes != int(row["total_bytes"]):
                con.rollback(); raise RuntimeError("Final object size does not match upload declaration")
            now = _now()
            con.execute("UPDATE content_uploads SET status=?,object_sha256=?,completed_at=?,updated_at=? WHERE upload_id=?", (UploadStatus.COMPLETE.value, obj.sha256, now, now, upload_id))
            self._event(con, "upload.completed", upload_id=upload_id, scope_type=row["scope_type"], scope_id=row["scope_id"], bytes_count=obj.size_bytes, metadata={"sha256": obj.sha256, "deduplicated": obj.existed})
            con.commit(); path.unlink(missing_ok=True)
        return self.upload(upload_id, scope_type=scope_type, scope_id=scope_id)

    def cancel_upload(self, upload_id: str) -> bool:
        with self._lock, self.con() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT * FROM content_uploads WHERE upload_id=?", (str(upload_id),)).fetchone()
            if not row:
                con.rollback(); return False
            if row["status"] == UploadStatus.COMPLETE.value:
                con.rollback(); raise ValueError("Completed upload cannot be cancelled")
            con.execute("UPDATE content_uploads SET status=?,updated_at=? WHERE upload_id=?", (UploadStatus.CANCELLED.value, _now(), upload_id))
            self._event(con, "upload.cancelled", upload_id=upload_id, scope_type=row["scope_type"], scope_id=row["scope_id"])
            con.commit(); Path(row["temp_path"]).unlink(missing_ok=True)
            return True

    @staticmethod
    def _idempotency(object_sha256: str, scope_type: str, scope_id: str, version: int) -> str:
        return hashlib.sha256(f"{object_sha256}\0{scope_type}\0{scope_id}\0{version}".encode()).hexdigest()

    @staticmethod
    def _job(row) -> dict | None:
        if row is None:
            return None
        item = dict(row); item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
        return item

    def next_extraction_version(self, object_sha256: str, *, scope_type: str, scope_id: str) -> int:
        with self.con() as con:
            a = con.execute("SELECT MAX(extraction_version) value FROM content_extractions WHERE object_sha256=? AND scope_type=? AND scope_id=?", (object_sha256, scope_type, scope_id)).fetchone()
            b = con.execute("SELECT MAX(extraction_version) value FROM content_ingestion_jobs WHERE object_sha256=? AND scope_type=? AND scope_id=?", (object_sha256, scope_type, scope_id)).fetchone()
        return max(int(a["value"] or 0), int(b["value"] or 0)) + 1

    def enqueue(self, *, object_sha256: str, filename: str, scope_type: str, scope_id: str, declared_mime: str = "application/octet-stream", extraction_version: int = 1, resource_class: ResourceClass | str = ResourceClass.CPU, priority: int = 0, max_attempts: int = 3, metadata: dict | None = None, force: bool = False) -> dict:
        object_sha256 = self.object_store.valid_sha(object_sha256)
        if not self.object_store.verify(object_sha256):
            raise ValueError("Cannot enqueue missing or corrupt object")
        filename, scope_type, scope_id = _safe_name(filename), str(scope_type).strip(), str(scope_id).strip()
        if not scope_type or not scope_id:
            raise ValueError("Ingestion job requires explicit scope")
        version = int(extraction_version)
        if version <= 0:
            raise ValueError("extraction_version must be positive")
        resource_class = ResourceClass(str(resource_class)); priority = max(-100, min(int(priority), 100)); max_attempts = max(1, min(int(max_attempts), 10))
        key = self._idempotency(object_sha256, scope_type, scope_id, version)
        now = _now()
        with self.con() as con:
            existing = con.execute("SELECT * FROM content_ingestion_jobs WHERE idempotency_key=?", (key,)).fetchone()
            if existing and not force:
                return self._job(existing)
            if existing and force:
                version = self.next_extraction_version(object_sha256, scope_type=scope_type, scope_id=scope_id)
                key = self._idempotency(object_sha256, scope_type, scope_id, version)
            job_id = f"cjob_{uuid4().hex}"
            con.execute(
                "INSERT INTO content_ingestion_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (job_id, key, object_sha256, filename, str(declared_mime or "application/octet-stream"), scope_type, scope_id, version, resource_class.value, JobStatus.QUEUED.value, priority, 0, max_attempts, now, None, None, now, now, None, None, None, None, None, json.dumps(metadata or {}, sort_keys=True, default=str)),
            )
            self._event(con, "job.queued", job_id=job_id, scope_type=scope_type, scope_id=scope_id, metadata={"resource_class": resource_class.value, "extraction_version": version})
            return self._job(con.execute("SELECT * FROM content_ingestion_jobs WHERE job_id=?", (job_id,)).fetchone())

    def enqueue_upload(self, upload_id: str, **kwargs) -> dict:
        with self.con() as con:
            row = con.execute("SELECT * FROM content_uploads WHERE upload_id=?", (str(upload_id),)).fetchone()
        if not row or row["status"] != UploadStatus.COMPLETE.value or not row["object_sha256"]:
            raise ValueError("Upload must be complete before ingestion")
        return self.enqueue(object_sha256=row["object_sha256"], filename=row["filename"], scope_type=row["scope_type"], scope_id=row["scope_id"], declared_mime=row["declared_mime"], metadata={"upload_id": upload_id}, **kwargs)

    def job(self, job_id: str, *, scope_type: str | None = None, scope_id: str | None = None) -> dict | None:
        sql, args = "SELECT * FROM content_ingestion_jobs WHERE job_id=?", [str(job_id)]
        if scope_type is not None:
            sql += " AND scope_type=?"; args.append(str(scope_type))
        if scope_id is not None:
            sql += " AND scope_id=?"; args.append(str(scope_id))
        with self.con() as con:
            return self._job(con.execute(sql, args).fetchone())

    def reclaim_expired(self) -> int:
        now = _now()
        with self.con() as con:
            con.execute("BEGIN IMMEDIATE")
            rows = con.execute("SELECT job_id,scope_type,scope_id FROM content_ingestion_jobs WHERE status=? AND lease_expires_at IS NOT NULL AND lease_expires_at<?", (JobStatus.RUNNING.value, now)).fetchall()
            for row in rows:
                con.execute("UPDATE content_ingestion_jobs SET status=?,lease_owner=NULL,lease_expires_at=NULL,available_at=?,updated_at=?,error_code=?,error_message=? WHERE job_id=?", (JobStatus.QUEUED.value, now, now, "lease_expired", "Worker lease expired before completion", row["job_id"]))
                self._event(con, "job.lease_expired", job_id=row["job_id"], scope_type=row["scope_type"], scope_id=row["scope_id"])
            con.commit(); return len(rows)

    def claim(self, *, worker_id: str, has_gpu: bool = False, lease_seconds: int = 300) -> dict | None:
        worker_id = str(worker_id).strip()
        if not worker_id:
            raise ValueError("worker_id is required")
        now_dt = _utcnow(); now = now_dt.isoformat(); expiry = (now_dt + timedelta(seconds=max(30, min(int(lease_seconds), 3600)))).isoformat()
        allowed = [ResourceClass.CPU.value, ResourceClass.GPU_PREFERRED.value]
        if has_gpu:
            allowed.append(ResourceClass.GPU_REQUIRED.value)
        with self._lock, self.con() as con:
            con.execute("BEGIN IMMEDIATE")
            expired = con.execute("SELECT job_id,scope_type,scope_id FROM content_ingestion_jobs WHERE status=? AND lease_expires_at IS NOT NULL AND lease_expires_at<?", (JobStatus.RUNNING.value, now)).fetchall()
            for item in expired:
                con.execute("UPDATE content_ingestion_jobs SET status=?,lease_owner=NULL,lease_expires_at=NULL,available_at=?,updated_at=?,error_code='lease_expired',error_message='Worker lease expired before completion' WHERE job_id=?", (JobStatus.QUEUED.value, now, now, item["job_id"]))
                self._event(con, "job.lease_expired", job_id=item["job_id"], scope_type=item["scope_type"], scope_id=item["scope_id"])
            marks = ",".join("?" for _ in allowed)
            row = con.execute(f"SELECT * FROM content_ingestion_jobs WHERE status=? AND available_at<=? AND resource_class IN ({marks}) ORDER BY priority DESC,created_at LIMIT 1", [JobStatus.QUEUED.value, now, *allowed]).fetchone()
            if not row:
                con.commit(); return None
            attempts = int(row["attempts"]) + 1
            con.execute("UPDATE content_ingestion_jobs SET status=?,attempts=?,lease_owner=?,lease_expires_at=?,started_at=COALESCE(started_at,?),updated_at=?,error_code=NULL,error_message=NULL WHERE job_id=?", (JobStatus.RUNNING.value, attempts, worker_id, expiry, now, now, row["job_id"]))
            self._event(con, "job.claimed", job_id=row["job_id"], scope_type=row["scope_type"], scope_id=row["scope_id"], metadata={"worker_id": worker_id, "attempt": attempts, "has_gpu": bool(has_gpu)})
            con.commit(); return self._job(con.execute("SELECT * FROM content_ingestion_jobs WHERE job_id=?", (row["job_id"],)).fetchone())

    def heartbeat(self, job_id: str, *, worker_id: str, lease_seconds: int = 300) -> bool:
        expiry = (_utcnow() + timedelta(seconds=max(30, min(int(lease_seconds), 3600)))).isoformat()
        with self.con() as con:
            return bool(con.execute("UPDATE content_ingestion_jobs SET lease_expires_at=?,updated_at=? WHERE job_id=? AND status=? AND lease_owner=?", (expiry, _now(), job_id, JobStatus.RUNNING.value, worker_id)).rowcount)

    def complete(self, job_id: str, *, worker_id: str, result_sha256: str, document_id: str, schema_version: str, parser_version: str, metadata: dict | None = None, duration_ms: float | None = None) -> dict:
        result_sha256 = self.object_store.valid_sha(result_sha256); now = _now()
        with self._lock, self.con() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT * FROM content_ingestion_jobs WHERE job_id=?", (job_id,)).fetchone()
            if not row:
                con.rollback(); raise KeyError(job_id)
            if row["status"] != JobStatus.RUNNING.value or row["lease_owner"] != worker_id:
                con.rollback(); raise PermissionError("Worker does not own the active job lease")
            con.execute("INSERT OR REPLACE INTO content_extractions VALUES(?,?,?,?,?,?,?,?,?,?)", (row["object_sha256"], row["scope_type"], row["scope_id"], row["extraction_version"], result_sha256, document_id, schema_version, parser_version, now, json.dumps(metadata or {}, sort_keys=True, default=str)))
            con.execute("UPDATE content_ingestion_jobs SET status=?,completed_at=?,updated_at=?,result_sha256=?,lease_owner=NULL,lease_expires_at=NULL,error_code=NULL,error_message=NULL WHERE job_id=?", (JobStatus.COMPLETED.value, now, now, result_sha256, job_id))
            size = self.object_store.path_for(row["object_sha256"]).stat().st_size
            self._event(con, "job.completed", job_id=job_id, scope_type=row["scope_type"], scope_id=row["scope_id"], duration_ms=duration_ms, bytes_count=size, metadata={"extraction_version": row["extraction_version"]})
            con.commit(); return self._job(con.execute("SELECT * FROM content_ingestion_jobs WHERE job_id=?", (job_id,)).fetchone())

    def fail(self, job_id: str, *, worker_id: str, error: Exception | str, retryable: bool = True, duration_ms: float | None = None) -> dict:
        code = type(error).__name__ if isinstance(error, Exception) else "processing_error"; message = str(error)[:2000]; now_dt = _utcnow(); now = now_dt.isoformat()
        with self._lock, self.con() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT * FROM content_ingestion_jobs WHERE job_id=?", (job_id,)).fetchone()
            if not row:
                con.rollback(); raise KeyError(job_id)
            if row["status"] != JobStatus.RUNNING.value or row["lease_owner"] != worker_id:
                con.rollback(); raise PermissionError("Worker does not own the active job lease")
            attempts = int(row["attempts"]); retry = bool(retryable and attempts < int(row["max_attempts"])); delay = min(3600, 5 * 2 ** max(0, attempts - 1)) if retry else 0
            status = JobStatus.QUEUED.value if retry else JobStatus.FAILED.value; available = (now_dt + timedelta(seconds=delay)).isoformat()
            con.execute("UPDATE content_ingestion_jobs SET status=?,available_at=?,updated_at=?,completed_at=?,lease_owner=NULL,lease_expires_at=NULL,error_code=?,error_message=? WHERE job_id=?", (status, available, now, None if retry else now, code, message, job_id))
            self._event(con, "job.retry_scheduled" if retry else "job.failed", job_id=job_id, scope_type=row["scope_type"], scope_id=row["scope_id"], duration_ms=duration_ms, metadata={"attempt": attempts, "max_attempts": row["max_attempts"], "error_code": code, "retry_delay_seconds": delay})
            con.commit(); return self._job(con.execute("SELECT * FROM content_ingestion_jobs WHERE job_id=?", (job_id,)).fetchone())

    def cancel_job(self, job_id: str) -> bool:
        with self._lock, self.con() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT * FROM content_ingestion_jobs WHERE job_id=?", (str(job_id),)).fetchone()
            if not row:
                con.rollback(); return False
            if row["status"] in {JobStatus.COMPLETED.value, JobStatus.FAILED.value, JobStatus.CANCELLED.value}:
                con.rollback(); return row["status"] == JobStatus.CANCELLED.value
            now = _now(); con.execute("UPDATE content_ingestion_jobs SET status=?,updated_at=?,completed_at=?,lease_owner=NULL,lease_expires_at=NULL WHERE job_id=?", (JobStatus.CANCELLED.value, now, now, job_id))
            self._event(con, "job.cancelled", job_id=job_id, scope_type=row["scope_type"], scope_id=row["scope_id"]); con.commit(); return True

    def result(self, job_id: str) -> dict | None:
        job = self.job(job_id)
        if not job or job["status"] != JobStatus.COMPLETED.value or not job.get("result_sha256"):
            return None
        path = self.object_store.path_for(job["result_sha256"])
        if not path.is_file() or path.stat().st_size > 128 * 1024 * 1024:
            raise RuntimeError("Extraction result is missing or exceeds the safe response limit")
        return {"job": job, "document": json.loads(path.read_text(encoding="utf-8")), "result_sha256": job["result_sha256"]}

    def metrics(self, *, since_hours: int = 24) -> dict:
        hours = max(1, min(int(since_hours), 24 * 90)); since = (_utcnow() - timedelta(hours=hours)).isoformat()
        with self.con() as con:
            statuses = {r["status"]: int(r["count"]) for r in con.execute("SELECT status,COUNT(*) count FROM content_ingestion_jobs GROUP BY status")}
            event = con.execute("SELECT COUNT(*) events,COALESCE(SUM(bytes),0) bytes,COALESCE(AVG(duration_ms),0) avg_duration_ms FROM content_runtime_events WHERE at>=?", (since,)).fetchone()
            failures = [dict(r) for r in con.execute("SELECT error_code,COUNT(*) count FROM content_ingestion_jobs WHERE status=? GROUP BY error_code ORDER BY count DESC", (JobStatus.FAILED.value,))]
        return {"jobs": statuses, "window_hours": hours, "events": int(event["events"]), "bytes": int(event["bytes"]), "avg_duration_ms": float(event["avg_duration_ms"] or 0), "failures": failures}

    def health(self) -> dict:
        with self.con() as con:
            queued = con.execute("SELECT COUNT(*) v FROM content_ingestion_jobs WHERE status=?", (JobStatus.QUEUED.value,)).fetchone()["v"]
            running = con.execute("SELECT COUNT(*) v FROM content_ingestion_jobs WHERE status=?", (JobStatus.RUNNING.value,)).fetchone()["v"]
            uploads = con.execute("SELECT COUNT(*) v FROM content_uploads WHERE status=?", (UploadStatus.OPEN.value,)).fetchone()["v"]
        return {"ready": True, "queued_jobs": int(queued), "running_jobs": int(running), "open_uploads": int(uploads), "max_upload_bytes": self.max_upload_bytes, "max_chunk_bytes": self.MAX_CHUNK_BYTES}


class ContentResourceRouter:
    GPU_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".mp3", ".wav", ".m4a", ".flac", ".ogg", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}

    def classify(self, filename: str, *, prefer_gpu: bool = True, require_gpu: bool = False) -> ResourceClass:
        if require_gpu:
            return ResourceClass.GPU_REQUIRED
        return ResourceClass.GPU_PREFERRED if prefer_gpu and Path(str(filename or "")).suffix.lower() in self.GPU_EXTENSIONS else ResourceClass.CPU


class ContentWorker:
    """One lease-holding worker; multiple worker processes may share one durable runtime store."""

    def __init__(self, store: ProductionContentStore, *, worker_id: str, has_gpu: bool = False, engine_factory=None, max_materialize_bytes: int = 2 * 1024 * 1024 * 1024):
        self.store = store; self.worker_id = str(worker_id).strip(); self.has_gpu = bool(has_gpu); self.engine_factory = engine_factory or (lambda max_bytes: FileIntelligenceEngine(max_file_bytes=max_bytes)); self.max_materialize_bytes = int(max_materialize_bytes)
        if not self.worker_id:
            raise ValueError("worker_id is required")

    def process_once(self) -> dict | None:
        job = self.store.claim(worker_id=self.worker_id, has_gpu=self.has_gpu)
        if not job:
            return None
        started = time.perf_counter()
        try:
            path = self.store.object_store.path_for(job["object_sha256"]); size = path.stat().st_size
            if size > self.max_materialize_bytes:
                raise ValueError("Object exceeds this worker's bounded materialization limit")
            data = path.read_bytes()
            document = self.engine_factory(max(size + 1, FileIntelligenceEngine.MAX_FILE_BYTES)).extract(filename=job["filename"], data=data, declared_mime=job["declared_mime"])
            document.document_id = f"{job['scope_type']}:{job['scope_id']}:{job['object_sha256']}:{job['extraction_version']}"
            document.metadata.update({"production_ingestion": True, "scope_type": job["scope_type"], "scope_id": job["scope_id"], "object_sha256": job["object_sha256"], "extraction_version": job["extraction_version"], "worker_id": self.worker_id, "resource_class": job["resource_class"]})
            result = self.store.object_store.put_bytes(json.dumps(document.as_dict(), sort_keys=True, ensure_ascii=False, default=str).encode())
            elapsed = (time.perf_counter() - started) * 1000
            return self.store.complete(job["job_id"], worker_id=self.worker_id, result_sha256=result.sha256, document_id=document.document_id, schema_version=document.schema_version, parser_version=document.parser_version, metadata={"result_size_bytes": result.size_bytes, "content_kind": document.content_kind.value}, duration_ms=elapsed)
        except Exception as exc:
            return self.store.fail(job["job_id"], worker_id=self.worker_id, error=exc, retryable=not isinstance(exc, (ValueError, PermissionError)), duration_ms=(time.perf_counter() - started) * 1000)


class ContentBenchmark:
    @staticmethod
    def extraction_latency(engine: FileIntelligenceEngine, fixtures: list[tuple[str, bytes, str]]) -> dict:
        durations=[]; size=blocks=0
        for filename, payload, mime in fixtures:
            started=time.perf_counter(); doc=engine.extract(filename=filename,data=payload,declared_mime=mime); durations.append((time.perf_counter()-started)*1000); size+=len(payload); blocks+=len(doc.blocks)
        ordered=sorted(durations); p95=ordered[min(len(ordered)-1,max(0,int((len(ordered)-1)*.95)))] if ordered else 0.0
        return {"fixtures":len(fixtures),"bytes":size,"blocks":blocks,"avg_ms":sum(durations)/len(durations) if durations else 0.0,"p95_ms":p95}

    @staticmethod
    def classification_accuracy(pairs: list[tuple[str, str]]) -> dict:
        total=len(pairs); correct=sum(expected==actual for expected,actual in pairs)
        return {"records":total,"correct":correct,"accuracy":correct/total if total else 0.0}
