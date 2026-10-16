from __future__ import annotations

import base64
import hashlib
import json
import secrets
import struct
import xml.etree.ElementTree as ET
from enum import Enum
from typing import Any, Iterable, Iterator, Mapping, Sequence
from urllib.parse import quote, urlencode

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .manager import _json, _now
from .policy import StoragePolicy
from .provider_adapters import ProviderAdapterError, ProviderObjectInfo, S3CompatibleAdapter


class StorageFabricError(RuntimeError):
    pass


class TransferJobState(str, Enum):
    QUEUED = "queued"
    ACTIVE = "active"
    RETRYABLE = "retryable"
    VERIFYING = "verifying"
    COMMITTED = "committed"
    ABORTED = "aborted"
    FAILED = "failed"


_SEGMENTED_FORMAT = "vishnu-segmented-provider-object-v2"
_SEGMENTED_MAGIC = b"VISHNU-SF2\x00"
_SEGMENTED_ALGORITHM = "AES-256-GCM"
_MIN_S3_PART_BYTES = 5 * 1024 * 1024
_DEFAULT_S3_PART_BYTES = 8 * 1024 * 1024
_MAX_S3_PART_BYTES = 64 * 1024 * 1024
_MAX_S3_PARTS = 10_000
_MAX_STREAM_BYTES = _MAX_S3_PART_BYTES * _MAX_S3_PARTS


def _validate_text(value: str, *, field: str, limit: int = 512) -> str:
    text = str(value or "").strip()
    if not text or len(text) > limit or "\x00" in text:
        raise ValueError(f"invalid {field}")
    return text


def _job_dict(row) -> dict[str, Any]:
    result = dict(row)
    for key in ("bytes_total", "bytes_done", "next_part", "retry_count"):
        if result.get(key) is not None:
            result[key] = int(result[key])
    result["metadata"] = json.loads(result.pop("metadata_json") or "{}")
    return result


class DurableTransferStore:
    """Durable, idempotent provider-transfer checkpoints.

    This is state only. It does not gain storage, device, approval, or credential
    authority. The canonical data-plane policy remains authoritative.
    """

    def __init__(self, manager):
        self.manager = manager
        self._init_schema()

    def _init_schema(self) -> None:
        with self.manager._con() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS data_plane_storage_jobs(
                    job_id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    global_id TEXT NOT NULL,
                    provider_id TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    object_key TEXT NOT NULL,
                    state TEXT NOT NULL,
                    bytes_total INTEGER NOT NULL,
                    bytes_done INTEGER NOT NULL DEFAULT 0,
                    next_part INTEGER NOT NULL DEFAULT 1,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    provider_upload_id TEXT,
                    expected_sha256 TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    error_code TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(global_id) REFERENCES data_plane_items(global_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS data_plane_storage_job_parts(
                    job_id TEXT NOT NULL,
                    part_number INTEGER NOT NULL,
                    etag TEXT NOT NULL,
                    plaintext_bytes INTEGER NOT NULL,
                    ciphertext_bytes INTEGER NOT NULL,
                    plaintext_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(job_id,part_number),
                    FOREIGN KEY(job_id) REFERENCES data_plane_storage_jobs(job_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_data_plane_storage_jobs_item
                    ON data_plane_storage_jobs(global_id,updated_at);
                CREATE INDEX IF NOT EXISTS idx_data_plane_storage_jobs_state
                    ON data_plane_storage_jobs(state,updated_at);
                """
            )

    def start_upload(
        self,
        *,
        global_id: str,
        provider_id: str,
        object_key: str,
        bytes_total: int,
        idempotency_key: str,
        expected_sha256: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        global_id = _validate_text(global_id, field="global_id", limit=240)
        provider_id = _validate_text(provider_id, field="provider_id", limit=100)
        object_key = _validate_text(object_key, field="object_key", limit=1024)
        idem = _validate_text(idempotency_key, field="idempotency_key", limit=240)
        total = int(bytes_total)
        if total < 0 or total > _MAX_STREAM_BYTES:
            raise ValueError("streaming provider transfer size is outside the bounded limit")
        if expected_sha256 is not None:
            expected_sha256 = str(expected_sha256).lower()
            if len(expected_sha256) != 64 or any(c not in "0123456789abcdef" for c in expected_sha256):
                raise ValueError("expected_sha256 must be a lowercase SHA-256 hex digest")
        item = self.manager.item(global_id)
        policy = StoragePolicy(str(item["storage_policy"]))
        if policy in {StoragePolicy.DEVICE_ONLY, StoragePolicy.PROGRESS_ONLY}:
            raise PermissionError(f"{policy.value} data cannot create a provider byte replica")
        if not bool(item.get("copy_allowed")):
            raise PermissionError("durable provider copy requires explicit copy authority")
        status = self.manager.provider_status(provider_id)
        if not status.get("available"):
            raise PermissionError("provider is not connected, enabled, and verified")
        stamp = _now()
        metadata_json = _json(dict(metadata or {}))
        with self.manager._lock, self.manager._con() as con:
            existing = con.execute(
                "SELECT * FROM data_plane_storage_jobs WHERE idempotency_key=?", (idem,)
            ).fetchone()
            if existing is not None:
                result = _job_dict(existing)
                immutable = (
                    result["global_id"], result["provider_id"], result["object_key"], result["bytes_total"]
                )
                requested = (global_id, provider_id, object_key, total)
                if immutable != requested:
                    raise ValueError("idempotency key already belongs to a different transfer")
                return result
            job_id = f"sf-{secrets.token_urlsafe(18)}"
            con.execute(
                """INSERT INTO data_plane_storage_jobs(
                    job_id,idempotency_key,global_id,provider_id,direction,object_key,state,
                    bytes_total,bytes_done,next_part,retry_count,provider_upload_id,
                    expected_sha256,metadata_json,error_code,created_at,updated_at
                ) VALUES(?,?,?,?,? ,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    job_id, idem, global_id, provider_id, "upload", object_key,
                    TransferJobState.QUEUED.value, total, 0, 1, 0, None,
                    expected_sha256, metadata_json, None, stamp, stamp,
                ),
            )
        return self.job(job_id)

    def job(self, job_id: str) -> dict[str, Any]:
        with self.manager._con() as con:
            row = con.execute(
                "SELECT * FROM data_plane_storage_jobs WHERE job_id=?",
                (_validate_text(job_id, field="job_id", limit=160),),
            ).fetchone()
        if row is None:
            raise KeyError("storage transfer job not found")
        return _job_dict(row)

    def jobs_for_item(self, global_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        bounded = max(1, min(int(limit), 200))
        with self.manager._con() as con:
            rows = con.execute(
                """SELECT * FROM data_plane_storage_jobs WHERE global_id=?
                   ORDER BY updated_at DESC LIMIT ?""",
                (str(global_id), bounded),
            ).fetchall()
        return [_job_dict(row) for row in rows]

    def update_metadata(self, job_id: str, metadata: Mapping[str, Any]) -> dict[str, Any]:
        encoded = _json(dict(metadata))
        if len(encoded.encode("utf-8")) > 64 * 1024:
            raise ValueError("transfer metadata is too large")
        with self.manager._con() as con:
            con.execute(
                "UPDATE data_plane_storage_jobs SET metadata_json=?,updated_at=? WHERE job_id=?",
                (encoded, _now(), str(job_id)),
            )
        return self.job(job_id)

    def set_upload_id(self, job_id: str, upload_id: str) -> dict[str, Any]:
        upload_id = _validate_text(upload_id, field="provider_upload_id", limit=2048)
        with self.manager._con() as con:
            row = con.execute(
                "SELECT provider_upload_id FROM data_plane_storage_jobs WHERE job_id=?",
                (str(job_id),),
            ).fetchone()
            if row is None:
                raise KeyError("storage transfer job not found")
            current = row["provider_upload_id"]
            if current not in {None, "", upload_id}:
                raise ValueError("provider upload id cannot change for an active transfer")
            con.execute(
                """UPDATE data_plane_storage_jobs
                   SET provider_upload_id=?,state=?,updated_at=? WHERE job_id=?""",
                (upload_id, TransferJobState.ACTIVE.value, _now(), str(job_id)),
            )
        return self.job(job_id)

    def record_part(
        self,
        job_id: str,
        *,
        part_number: int,
        etag: str,
        plaintext_bytes: int,
        ciphertext_bytes: int,
        plaintext_sha256: str,
    ) -> dict[str, Any]:
        number = int(part_number)
        plain = int(plaintext_bytes)
        cipher = int(ciphertext_bytes)
        digest = str(plaintext_sha256).lower()
        if number < 1 or number > _MAX_S3_PARTS:
            raise ValueError("invalid multipart part number")
        if plain < 0 or cipher <= 0 or len(digest) != 64:
            raise ValueError("invalid multipart checkpoint")
        etag = _validate_text(etag, field="etag", limit=512)
        with self.manager._lock, self.manager._con() as con:
            job = con.execute(
                "SELECT * FROM data_plane_storage_jobs WHERE job_id=?", (str(job_id),)
            ).fetchone()
            if job is None:
                raise KeyError("storage transfer job not found")
            existing = con.execute(
                """SELECT * FROM data_plane_storage_job_parts
                   WHERE job_id=? AND part_number=?""",
                (str(job_id), number),
            ).fetchone()
            if existing is not None:
                same = (
                    str(existing["etag"]) == etag
                    and int(existing["plaintext_bytes"]) == plain
                    and int(existing["ciphertext_bytes"]) == cipher
                    and str(existing["plaintext_sha256"]) == digest
                )
                if not same:
                    raise ValueError("multipart checkpoint replay does not match durable state")
                return _job_dict(job)
            if number != int(job["next_part"]):
                raise ValueError("multipart checkpoint is out of sequence")
            if int(job["bytes_done"]) + plain > int(job["bytes_total"]):
                raise ValueError("multipart checkpoint exceeds declared transfer size")
            con.execute(
                """INSERT INTO data_plane_storage_job_parts(
                    job_id,part_number,etag,plaintext_bytes,ciphertext_bytes,plaintext_sha256,created_at
                ) VALUES(?,?,?,?,?,?,?)""",
                (str(job_id), number, etag, plain, cipher, digest, _now()),
            )
            con.execute(
                """UPDATE data_plane_storage_jobs
                   SET bytes_done=bytes_done+?,next_part=?,state=?,error_code=NULL,updated_at=?
                   WHERE job_id=?""",
                (plain, number + 1, TransferJobState.ACTIVE.value, _now(), str(job_id)),
            )
        return self.job(job_id)

    def parts(self, job_id: str) -> list[dict[str, Any]]:
        with self.manager._con() as con:
            rows = con.execute(
                """SELECT part_number,etag,plaintext_bytes,ciphertext_bytes,plaintext_sha256,created_at
                   FROM data_plane_storage_job_parts WHERE job_id=? ORDER BY part_number""",
                (str(job_id),),
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_state(
        self,
        job_id: str,
        state: TransferJobState,
        *,
        error_code: str | None = None,
        increment_retry: bool = False,
    ) -> dict[str, Any]:
        state = TransferJobState(state)
        with self.manager._con() as con:
            row = con.execute(
                "SELECT state FROM data_plane_storage_jobs WHERE job_id=?", (str(job_id),)
            ).fetchone()
            if row is None:
                raise KeyError("storage transfer job not found")
            current = TransferJobState(str(row["state"]))
            if current in {TransferJobState.COMMITTED, TransferJobState.ABORTED, TransferJobState.FAILED}:
                if current is not state:
                    raise ValueError("terminal transfer state cannot be changed")
                return self.job(job_id)
            con.execute(
                """UPDATE data_plane_storage_jobs SET state=?,error_code=?,
                   retry_count=retry_count+?,updated_at=? WHERE job_id=?""",
                (
                    state.value,
                    str(error_code)[:160] if error_code else None,
                    1 if increment_retry else 0,
                    _now(),
                    str(job_id),
                ),
            )
        return self.job(job_id)


class SegmentedEnvelopeCodec:
    """Bounded-memory provider object format using the canonical envelope KEK.

    The raw data key exists only in memory. Only its canonical-vault-wrapped form
    is written to durable transfer metadata and provider ciphertext.
    """

    def __init__(self, envelopes):
        self.envelopes = envelopes

    @staticmethod
    def _context_name(global_id: str) -> str:
        return f"{global_id}:segmented-provider-v2"

    def create_header(
        self,
        global_id: str,
        object_version: int,
        *,
        content_type: str,
        expected_plaintext_size: int,
        part_plaintext_bytes: int,
    ) -> tuple[dict[str, Any], bytes]:
        if object_version < 1:
            raise ValueError("object_version must be positive")
        data_key = secrets.token_bytes(32)
        wrapped = self.envelopes.wrap_key(
            self._context_name(str(global_id)), int(object_version), data_key
        )
        header = {
            "format": _SEGMENTED_FORMAT,
            "algorithm": _SEGMENTED_ALGORITHM,
            "global_id": str(global_id),
            "object_version": int(object_version),
            "content_type": str(content_type),
            "expected_plaintext_size": int(expected_plaintext_size),
            "part_plaintext_bytes": int(part_plaintext_bytes),
            **wrapped,
        }
        return header, data_key

    def key_from_header(self, header: Mapping[str, Any]) -> bytes:
        if str(header.get("format")) != _SEGMENTED_FORMAT:
            raise ValueError("unsupported segmented provider object format")
        if str(header.get("algorithm")) != _SEGMENTED_ALGORITHM:
            raise ValueError("unsupported segmented provider object algorithm")
        return self.envelopes.unwrap_key(
            self._context_name(str(header["global_id"])),
            int(header["object_version"]),
            header,
        )

    @staticmethod
    def _frame_aad(header: Mapping[str, Any], meta: Mapping[str, Any]) -> bytes:
        return _json(
            {
                "format": _SEGMENTED_FORMAT,
                "global_id": str(header["global_id"]),
                "object_version": int(header["object_version"]),
                "content_type": str(header.get("content_type") or "application/octet-stream"),
                "index": int(meta["index"]),
                "plaintext_size": int(meta["plaintext_size"]),
                "plaintext_sha256": str(meta["plaintext_sha256"]),
                "nonce": str(meta["nonce"]),
            }
        ).encode("utf-8")

    def encode_frame(
        self,
        header: Mapping[str, Any],
        data_key: bytes,
        *,
        index: int,
        plaintext: bytes,
    ) -> bytes:
        data = bytes(plaintext)
        nonce = secrets.token_bytes(12)
        meta = {
            "index": int(index),
            "plaintext_size": len(data),
            "plaintext_sha256": hashlib.sha256(data).hexdigest(),
            "nonce": base64.b64encode(nonce).decode("ascii"),
        }
        ciphertext = AESGCM(data_key).encrypt(
            nonce, data, self._frame_aad(header, meta)
        )
        encoded_meta = _json({**meta, "ciphertext_size": len(ciphertext)}).encode("utf-8")
        if len(encoded_meta) > 16 * 1024:
            raise StorageFabricError("segmented frame metadata exceeded bound")
        return struct.pack(">I", len(encoded_meta)) + encoded_meta + ciphertext

    def encode_first_part(
        self,
        header: Mapping[str, Any],
        data_key: bytes,
        *,
        plaintext: bytes,
    ) -> bytes:
        encoded_header = _json(dict(header)).encode("utf-8")
        if len(encoded_header) > 64 * 1024:
            raise StorageFabricError("segmented provider header exceeded bound")
        return (
            _SEGMENTED_MAGIC
            + struct.pack(">I", len(encoded_header))
            + encoded_header
            + self.encode_frame(header, data_key, index=0, plaintext=plaintext)
        )

    @staticmethod
    def header_only(header: Mapping[str, Any]) -> bytes:
        encoded = _json(dict(header)).encode("utf-8")
        return _SEGMENTED_MAGIC + struct.pack(">I", len(encoded)) + encoded

    def iter_decrypt(self, chunks: Iterable[bytes]) -> Iterator[bytes]:
        reader = _ChunkReader(chunks)
        magic = reader.read_exact(len(_SEGMENTED_MAGIC))
        if magic != _SEGMENTED_MAGIC:
            raise ProviderAdapterError("provider object is not a Vishnu segmented encrypted object")
        header_size = struct.unpack(">I", reader.read_exact(4))[0]
        if header_size <= 0 or header_size > 64 * 1024:
            raise ProviderAdapterError("segmented provider header is invalid")
        try:
            header = json.loads(reader.read_exact(header_size))
        except Exception as exc:
            raise ProviderAdapterError("segmented provider header is invalid") from exc
        data_key = self.key_from_header(header)
        index = 0
        total = 0
        while True:
            prefix = reader.read_exact(4, allow_eof=True)
            if prefix is None:
                break
            meta_size = struct.unpack(">I", prefix)[0]
            if meta_size <= 0 or meta_size > 16 * 1024:
                raise ProviderAdapterError("segmented provider frame metadata is invalid")
            try:
                meta = json.loads(reader.read_exact(meta_size))
            except Exception as exc:
                raise ProviderAdapterError("segmented provider frame metadata is invalid") from exc
            if int(meta.get("index", -1)) != index:
                raise ProviderAdapterError("segmented provider frame sequence mismatch")
            cipher_size = int(meta.get("ciphertext_size") or 0)
            if cipher_size <= 16 or cipher_size > _MAX_S3_PART_BYTES + 64 * 1024:
                raise ProviderAdapterError("segmented provider ciphertext size is invalid")
            ciphertext = reader.read_exact(cipher_size)
            try:
                nonce = base64.b64decode(str(meta["nonce"]), validate=True)
                plaintext = AESGCM(data_key).decrypt(
                    nonce, ciphertext, self._frame_aad(header, meta)
                )
            except (InvalidTag, ValueError, KeyError) as exc:
                raise ProviderAdapterError("segmented provider frame authentication failed") from exc
            if len(plaintext) != int(meta["plaintext_size"]):
                raise ProviderAdapterError("segmented provider frame size verification failed")
            digest = hashlib.sha256(plaintext).hexdigest()
            if not secrets.compare_digest(digest, str(meta["plaintext_sha256"])):
                raise ProviderAdapterError("segmented provider frame digest verification failed")
            total += len(plaintext)
            index += 1
            yield plaintext
        if total != int(header.get("expected_plaintext_size") or 0):
            raise ProviderAdapterError("segmented provider object total-size verification failed")


class _ChunkReader:
    def __init__(self, chunks: Iterable[bytes]):
        self._source = iter(chunks)
        self._buffer = bytearray()
        self._eof = False

    def read_exact(self, size: int, *, allow_eof: bool = False) -> bytes | None:
        size = int(size)
        if size < 0:
            raise ValueError("read size must be non-negative")
        while len(self._buffer) < size and not self._eof:
            try:
                chunk = next(self._source)
            except StopIteration:
                self._eof = True
                break
            data = bytes(chunk)
            if not data:
                continue
            self._buffer.extend(data)
        if len(self._buffer) < size:
            if allow_eof and not self._buffer:
                return None
            raise ProviderAdapterError("segmented provider object ended unexpectedly")
        result = bytes(self._buffer[:size])
        del self._buffer[:size]
        return result


class S3MultipartTransport:
    """Native S3-compatible multipart/range transport with bounded requests."""

    def __init__(self, adapter: S3CompatibleAdapter):
        if not isinstance(adapter, S3CompatibleAdapter):
            raise TypeError("S3MultipartTransport requires S3CompatibleAdapter")
        self.adapter = adapter

    def _request(
        self,
        method: str,
        object_key: str,
        *,
        query: Sequence[tuple[str, str]] = (),
        payload: bytes = b"",
        extra: Mapping[str, str] | None = None,
    ):
        pairs = sorted((str(k), str(v)) for k, v in query)
        encoded_query = urlencode(pairs, doseq=True, quote_via=quote, safe="~")
        url = self.adapter._url(object_key)
        if encoded_query:
            url = f"{url}?{encoded_query}"
        headers = self.adapter._signed_headers(method, url, payload, extra)
        return self.adapter.client.request(
            method, url, headers=headers, content=payload, follow_redirects=False
        )

    def begin(self, object_key: str, *, content_type: str) -> str:
        response = self._request(
            "POST", object_key, query=(("uploads", ""),),
            extra={"content-type": content_type},
        )
        response.raise_for_status()
        try:
            root = ET.fromstring(bytes(response.content))
            upload_id = next(
                (str(node.text or "").strip() for node in root.iter() if node.tag.endswith("UploadId")),
                "",
            )
        except Exception as exc:
            raise ProviderAdapterError("S3 multipart initiation returned invalid XML") from exc
        if not upload_id:
            raise ProviderAdapterError("S3 multipart initiation did not return an upload id")
        return upload_id

    def upload_part(
        self,
        object_key: str,
        upload_id: str,
        part_number: int,
        payload: bytes,
    ) -> str:
        number = int(part_number)
        data = bytes(payload)
        if number < 1 or number > _MAX_S3_PARTS:
            raise ValueError("invalid S3 multipart part number")
        if not data or len(data) > _MAX_S3_PART_BYTES + 128 * 1024:
            raise ValueError("S3 multipart part exceeds bounded request size")
        response = self._request(
            "PUT",
            object_key,
            query=(("partNumber", str(number)), ("uploadId", str(upload_id))),
            payload=data,
        )
        response.raise_for_status()
        etag = str(response.headers.get("etag") or "").strip('"')
        if not etag:
            raise ProviderAdapterError("S3 multipart upload part did not return an ETag")
        return etag

    def complete(
        self,
        object_key: str,
        upload_id: str,
        parts: Sequence[Mapping[str, Any]],
    ) -> ProviderObjectInfo:
        root = ET.Element("CompleteMultipartUpload")
        expected = 1
        for part in parts:
            number = int(part["part_number"])
            if number != expected:
                raise ValueError("multipart completion parts must be contiguous")
            child = ET.SubElement(root, "Part")
            ET.SubElement(child, "PartNumber").text = str(number)
            ET.SubElement(child, "ETag").text = f'"{str(part["etag"]).strip(chr(34))}"'
            expected += 1
        if expected == 1:
            raise ValueError("multipart completion requires at least one part")
        payload = ET.tostring(root, encoding="utf-8", xml_declaration=False)
        response = self._request(
            "POST",
            object_key,
            query=(("uploadId", str(upload_id)),),
            payload=payload,
            extra={"content-type": "application/xml"},
        )
        response.raise_for_status()
        info = self.adapter.head(object_key)
        if info is None:
            raise ProviderAdapterError("S3 multipart completion could not be verified")
        return info

    def abort(self, object_key: str, upload_id: str) -> None:
        response = self._request(
            "DELETE", object_key, query=(("uploadId", str(upload_id)),)
        )
        if response.status_code not in {200, 204, 404}:
            response.raise_for_status()

    def iter_range(
        self,
        object_key: str,
        *,
        request_bytes: int = _DEFAULT_S3_PART_BYTES,
    ) -> Iterator[bytes]:
        block = max(64 * 1024, min(int(request_bytes), _MAX_S3_PART_BYTES))
        info = self.adapter.head(object_key)
        if info is None:
            raise FileNotFoundError(object_key)
        if info.size is None:
            raise ProviderAdapterError("S3 range streaming requires provider object size")
        total = int(info.size)
        offset = 0
        while offset < total:
            end = min(total - 1, offset + block - 1)
            response = self._request(
                "GET", object_key, extra={"range": f"bytes={offset}-{end}"}
            )
            response.raise_for_status()
            payload = bytes(response.content)
            expected = end - offset + 1
            if len(payload) != expected:
                raise ProviderAdapterError("S3 range response size mismatch")
            offset += len(payload)
            yield payload


def _coalesce_source(source: Iterable[bytes], part_size: int) -> Iterator[bytes]:
    target = int(part_size)
    if target < _MIN_S3_PART_BYTES or target > _MAX_S3_PART_BYTES:
        raise ValueError("provider streaming part size is outside bounds")
    buffer = bytearray()
    for raw in source:
        view = memoryview(bytes(raw))
        position = 0
        while position < len(view):
            room = target - len(buffer)
            take = min(room, len(view) - position)
            buffer.extend(view[position:position + take])
            position += take
            if len(buffer) == target:
                yield bytes(buffer)
                buffer.clear()
    if buffer:
        yield bytes(buffer)
