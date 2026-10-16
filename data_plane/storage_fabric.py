from __future__ import annotations

import hashlib
import math
import secrets
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence

from .manager import _now
from .policy import StoragePolicy
from .provider_adapters import EncryptedProviderStore, ProviderAdapterFactory, S3CompatibleAdapter
from .storage_transfer import (
    _DEFAULT_S3_PART_BYTES,
    _MAX_S3_PART_BYTES,
    _MAX_S3_PARTS,
    _MIN_S3_PART_BYTES,
    DurableTransferStore,
    S3MultipartTransport,
    SegmentedEnvelopeCodec,
    StorageFabricError,
    TransferJobState,
    _coalesce_source,
    _validate_text,
)


class ProviderHealth(str, Enum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    provider_id: str
    range_read: bool = False
    multipart_upload: bool = False
    resumable_upload: bool = False
    server_copy: bool = False
    quota: bool = False
    change_feed: bool = False
    native_directories: bool = False
    presigned_access: bool = False
    max_single_object_bytes: int | None = None


@dataclass(frozen=True, slots=True)
class PlacementDecision:
    global_id: str
    policy: str
    purpose: str
    selected: Mapping[str, Any] | None
    eligible: tuple[Mapping[str, Any], ...]
    rejected: tuple[Mapping[str, Any], ...]


_PROVIDER_CAPABILITIES: dict[str, ProviderCapabilities] = {
    "local": ProviderCapabilities("local", range_read=True, resumable_upload=True, native_directories=True),
    "google_drive": ProviderCapabilities("google_drive", native_directories=True),
    "dropbox": ProviderCapabilities("dropbox", native_directories=True),
    "onedrive": ProviderCapabilities("onedrive", native_directories=True),
    "icloud_bridge": ProviderCapabilities("icloud_bridge", range_read=True, native_directories=True),
    "s3": ProviderCapabilities("s3", range_read=True, multipart_upload=True, resumable_upload=True),
    "cloudflare_r2": ProviderCapabilities("cloudflare_r2", range_read=True, multipart_upload=True, resumable_upload=True),
    "backblaze_b2": ProviderCapabilities("backblaze_b2", range_read=True, multipart_upload=True, resumable_upload=True),
    "postgres": ProviderCapabilities("postgres"),
    "supabase": ProviderCapabilities("supabase"),
    "neon": ProviderCapabilities("neon"),
    "aws_rds": ProviderCapabilities("aws_rds"),
    "vishnu_cloud": ProviderCapabilities("vishnu_cloud"),
}


def provider_capabilities(provider_id: str) -> ProviderCapabilities:
    provider_id = str(provider_id or "").strip()
    return _PROVIDER_CAPABILITIES.get(provider_id, ProviderCapabilities(provider_id))


class StorageFabric:
    """Universal storage fabric over Vishnu's existing data-plane authorities."""

    def __init__(self, manager, *, envelopes=None, provider_factory: ProviderAdapterFactory | None = None, events=None):
        self.manager = manager
        self.envelopes = envelopes
        self.provider_factory = provider_factory
        self.events = events
        self.transfers = DurableTransferStore(manager)
        self.codec = SegmentedEnvelopeCodec(envelopes) if envelopes is not None else None
        self._init_schema()

    def _init_schema(self) -> None:
        with self.manager._con() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS data_plane_provider_health(
                    provider_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    latency_ms REAL,
                    free_bytes INTEGER,
                    detail TEXT,
                    checked_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS data_plane_replica_reconciliation(
                    event_id TEXT PRIMARY KEY,
                    global_id TEXT NOT NULL,
                    provider_id TEXT NOT NULL,
                    location_id TEXT,
                    outcome TEXT NOT NULL,
                    detail TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(global_id) REFERENCES data_plane_items(global_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_data_plane_reconcile_item
                    ON data_plane_replica_reconciliation(global_id,created_at);
                """
            )

    def _emit(self, topic: str, **payload: Any) -> None:
        if self.events is not None:
            try:
                self.events.emit(topic, **payload)
            except Exception:
                pass

    def capabilities(self, provider_id: str) -> dict[str, Any]:
        caps = provider_capabilities(provider_id)
        return {
            "provider_id": caps.provider_id,
            "range_read": caps.range_read,
            "multipart_upload": caps.multipart_upload,
            "resumable_upload": caps.resumable_upload,
            "server_copy": caps.server_copy,
            "quota": caps.quota,
            "change_feed": caps.change_feed,
            "native_directories": caps.native_directories,
            "presigned_access": caps.presigned_access,
            "max_single_object_bytes": caps.max_single_object_bytes,
        }

    def record_health(
        self,
        provider_id: str,
        state: ProviderHealth,
        *,
        latency_ms: float | None = None,
        free_bytes: int | None = None,
        detail: str | None = None,
    ) -> dict[str, Any]:
        provider_id = _validate_text(provider_id, field="provider_id", limit=100)
        state = ProviderHealth(state)
        if latency_ms is not None and float(latency_ms) < 0:
            raise ValueError("latency_ms cannot be negative")
        if free_bytes is not None and int(free_bytes) < 0:
            raise ValueError("free_bytes cannot be negative")
        with self.manager._con() as con:
            con.execute(
                """INSERT INTO data_plane_provider_health(
                    provider_id,state,latency_ms,free_bytes,detail,checked_at
                ) VALUES(?,?,?,?,?,?)
                ON CONFLICT(provider_id) DO UPDATE SET
                    state=excluded.state,latency_ms=excluded.latency_ms,
                    free_bytes=excluded.free_bytes,detail=excluded.detail,
                    checked_at=excluded.checked_at""",
                (
                    provider_id, state.value,
                    float(latency_ms) if latency_ms is not None else None,
                    int(free_bytes) if free_bytes is not None else None,
                    str(detail)[:240] if detail else None,
                    _now(),
                ),
            )
        return self.health(provider_id)

    def health(self, provider_id: str) -> dict[str, Any]:
        with self.manager._con() as con:
            row = con.execute(
                "SELECT * FROM data_plane_provider_health WHERE provider_id=?",
                (str(provider_id),),
            ).fetchone()
        if row is None:
            return {
                "provider_id": str(provider_id),
                "state": ProviderHealth.UNKNOWN.value,
                "latency_ms": None,
                "free_bytes": None,
                "detail": None,
                "checked_at": None,
            }
        return dict(row)

    def probe_provider(self, provider_id: str) -> dict[str, Any]:
        if self.provider_factory is None:
            raise RuntimeError("provider factory is unavailable")
        try:
            adapter = self.provider_factory.build(str(provider_id))
            result = adapter.verify()
        except Exception as exc:
            self.record_health(provider_id, ProviderHealth.UNAVAILABLE, detail=type(exc).__name__)
            raise
        self.record_health(provider_id, ProviderHealth.HEALTHY)
        return {"provider": result, "health": self.health(provider_id), "capabilities": self.capabilities(provider_id)}

    def replicas(self, global_id: str) -> list[dict[str, Any]]:
        item = self.manager.item(global_id)
        result: list[dict[str, Any]] = []
        for location in item.get("locations") or ():
            entry = dict(location)
            provider_id = str(entry.get("provider_id") or "local")
            entry["replica_state"] = (
                "available"
                if entry.get("has_bytes") and entry.get("available")
                else "unreachable"
                if entry.get("has_bytes")
                else "missing"
            )
            entry["provider_health"] = self.health(provider_id)
            entry["capabilities"] = self.capabilities(provider_id)
            result.append(entry)
        return result

    @staticmethod
    def _score_candidate(candidate: Mapping[str, Any], *, existing_locations: set[tuple[str, str]]) -> float:
        score = 0.0
        if bool(candidate.get("healthy", True)):
            score += 40.0
        else:
            score -= 100.0
        if bool(candidate.get("local", False)):
            score += 25.0
        location_key = (str(candidate.get("location_type") or ""), str(candidate.get("location_id") or ""))
        if location_key in existing_locations:
            score += 20.0
        latency = candidate.get("latency_ms")
        if latency is not None:
            score += max(0.0, 15.0 - min(float(latency), 1500.0) / 100.0)
        free_bytes = candidate.get("free_bytes")
        required = max(1, int(candidate.get("required_bytes") or 1))
        if free_bytes is not None:
            ratio = min(1.0, max(0.0, int(free_bytes) / required))
            score += 20.0 * ratio
        score -= max(0.0, min(float(candidate.get("cost_weight") or 0.0), 20.0))
        if bool(candidate.get("adds_failure_domain", False)):
            score += 10.0
        return round(score, 6)

    def plan_placement(
        self,
        global_id: str,
        candidates: Sequence[Mapping[str, Any]],
        *,
        purpose: str = "explicit_copy",
        explicit: bool = True,
        required_bytes: int = 0,
    ) -> PlacementDecision:
        item = self.manager.item(global_id)
        policy = StoragePolicy(str(item["storage_policy"]))
        purpose = str(purpose or "explicit_copy")
        existing = {
            (str(location.get("location_type") or ""), str(location.get("location_id") or ""))
            for location in item.get("locations") or ()
            if location.get("has_bytes")
        }
        eligible: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        for raw in candidates:
            candidate = dict(raw)
            candidate["required_bytes"] = int(required_bytes)
            location_type = str(candidate.get("location_type") or "")
            location_id = str(candidate.get("location_id") or "")
            provider_id = str(candidate.get("provider_id") or ("local" if location_type == "device" else ""))
            reason = None
            if not location_type or not location_id:
                reason = "invalid_candidate"
            elif not bool(candidate.get("healthy", True)):
                reason = "unhealthy"
            elif policy in {StoragePolicy.DEVICE_ONLY, StoragePolicy.PROGRESS_ONLY}:
                if location_type != "device" or location_id != str(item["primary_device_id"]):
                    reason = f"{policy.value}_raw_bytes_must_stay_on_primary_device"
            elif location_type == "provider":
                if not bool(item.get("copy_allowed")):
                    reason = "copy_authority_required"
                elif policy is StoragePolicy.ON_DEMAND and not explicit and (location_type, location_id) not in existing:
                    reason = "on_demand_never_creates_automatic_replica"
                else:
                    try:
                        status = self.manager.provider_status(provider_id)
                    except Exception:
                        status = {"available": False}
                    if not status.get("available"):
                        reason = "provider_unavailable"
            if required_bytes > 0 and candidate.get("free_bytes") is not None:
                if int(candidate["free_bytes"]) < int(required_bytes):
                    reason = "insufficient_capacity"
            if reason:
                candidate["reason"] = reason
                rejected.append(candidate)
                continue
            candidate["score"] = self._score_candidate(candidate, existing_locations=existing)
            eligible.append(candidate)
        eligible.sort(key=lambda value: (-float(value["score"]), str(value.get("location_id") or "")))
        return PlacementDecision(
            global_id=str(global_id),
            policy=policy.value,
            purpose=purpose,
            selected=eligible[0] if eligible else None,
            eligible=tuple(eligible),
            rejected=tuple(rejected),
        )

    def _record_reconciliation(
        self,
        *,
        global_id: str,
        provider_id: str,
        location_id: str | None,
        outcome: str,
        detail: str | None = None,
    ) -> None:
        with self.manager._con() as con:
            con.execute(
                """INSERT INTO data_plane_replica_reconciliation(
                    event_id,global_id,provider_id,location_id,outcome,detail,created_at
                ) VALUES(?,?,?,?,?,?,?)""",
                (
                    f"recon-{secrets.token_urlsafe(18)}", str(global_id), str(provider_id),
                    str(location_id) if location_id else None, str(outcome),
                    str(detail)[:240] if detail else None, _now(),
                ),
            )

    def reconcile_provider_replica(
        self,
        global_id: str,
        provider_id: str,
        *,
        version: int | None = None,
    ) -> dict[str, Any]:
        if self.provider_factory is None:
            raise RuntimeError("provider factory is unavailable")
        item = self.manager.item(global_id)
        target_version = int(version or item["version"])
        object_key = EncryptedProviderStore.object_key(global_id, target_version)
        location_id = f"{provider_id}:{object_key}"
        existing = next(
            (location for location in item.get("locations") or () if location.get("location_id") == location_id),
            None,
        )
        try:
            adapter = self.provider_factory.build(provider_id)
            info = adapter.head(object_key)
        except Exception as exc:
            if existing is not None:
                with self.manager._con() as con:
                    con.execute(
                        """UPDATE data_plane_locations SET available=0,updated_at=?
                           WHERE global_id=? AND location_type='provider' AND location_id=?""",
                        (_now(), str(global_id), location_id),
                    )
            self.record_health(provider_id, ProviderHealth.DEGRADED, detail=type(exc).__name__)
            self._record_reconciliation(
                global_id=global_id, provider_id=provider_id, location_id=location_id,
                outcome="provider_unreachable", detail=type(exc).__name__,
            )
            return {"outcome": "provider_unreachable", "location_id": location_id}
        self.record_health(provider_id, ProviderHealth.HEALTHY)
        if existing is not None and info is None:
            with self.manager._con() as con:
                con.execute(
                    """UPDATE data_plane_locations SET has_bytes=0,available=0,updated_at=?
                       WHERE global_id=? AND location_type='provider' AND location_id=?""",
                    (_now(), str(global_id), location_id),
                )
            outcome = "confirmed_missing"
        elif existing is not None and info is not None:
            with self.manager._con() as con:
                con.execute(
                    """UPDATE data_plane_locations SET has_bytes=1,available=1,updated_at=?
                       WHERE global_id=? AND location_type='provider' AND location_id=?""",
                    (_now(), str(global_id), location_id),
                )
            outcome = "verified"
        elif existing is None and info is not None:
            outcome = "orphan_remote"
        else:
            outcome = "absent"
        self._record_reconciliation(
            global_id=global_id, provider_id=provider_id, location_id=location_id, outcome=outcome
        )
        return {
            "outcome": outcome,
            "location_id": location_id,
            "provider_id": str(provider_id),
            "object_key": object_key,
            "provider_object": None if info is None else {
                "size": info.size, "etag": info.etag, "content_type": info.content_type,
            },
        }

    def reconcile_item(self, global_id: str) -> list[dict[str, Any]]:
        """Verify recorded provider replicas without adopting or moving bytes."""
        if self.provider_factory is None:
            raise RuntimeError("provider factory is unavailable")
        item = self.manager.item(global_id)
        outcomes: list[dict[str, Any]] = []
        for location in item.get("locations") or ():
            if str(location.get("location_type")) != "provider":
                continue
            provider_id = str(location.get("provider_id") or "")
            location_id = str(location.get("location_id") or "")
            prefix = f"{provider_id}:"
            if not provider_id or not location_id.startswith(prefix):
                self._record_reconciliation(
                    global_id=global_id, provider_id=provider_id or "unknown",
                    location_id=location_id or None, outcome="invalid_location_metadata",
                )
                outcomes.append({"outcome": "invalid_location_metadata", "location_id": location_id})
                continue
            object_key = location_id[len(prefix):]
            try:
                adapter = self.provider_factory.build(provider_id)
                info = adapter.head(object_key)
            except Exception as exc:
                with self.manager._con() as con:
                    con.execute(
                        """UPDATE data_plane_locations SET available=0,updated_at=?
                           WHERE global_id=? AND location_type='provider' AND location_id=?""",
                        (_now(), str(global_id), location_id),
                    )
                self.record_health(provider_id, ProviderHealth.DEGRADED, detail=type(exc).__name__)
                outcome = "provider_unreachable"
                detail = type(exc).__name__
                info = None
            else:
                self.record_health(provider_id, ProviderHealth.HEALTHY)
                detail = None
                if info is None:
                    with self.manager._con() as con:
                        con.execute(
                            """UPDATE data_plane_locations SET has_bytes=0,available=0,updated_at=?
                               WHERE global_id=? AND location_type='provider' AND location_id=?""",
                            (_now(), str(global_id), location_id),
                        )
                    outcome = "confirmed_missing"
                else:
                    with self.manager._con() as con:
                        con.execute(
                            """UPDATE data_plane_locations SET has_bytes=1,available=1,updated_at=?
                               WHERE global_id=? AND location_type='provider' AND location_id=?""",
                            (_now(), str(global_id), location_id),
                        )
                    outcome = "verified"
            self._record_reconciliation(
                global_id=global_id, provider_id=provider_id, location_id=location_id,
                outcome=outcome, detail=detail,
            )
            outcomes.append(
                {
                    "outcome": outcome,
                    "provider_id": provider_id,
                    "location_id": location_id,
                    "object_key": object_key,
                    "provider_object": None if info is None else {
                        "size": info.size, "etag": info.etag, "content_type": info.content_type,
                    },
                }
            )
        return outcomes

    @staticmethod
    def segmented_object_key(global_id: str, version: int) -> str:
        opaque = hashlib.sha256(str(global_id).encode("utf-8")).hexdigest()
        return f"v2/{opaque[:2]}/{opaque}/{int(version)}.vishnu"

    def _require_streaming(self) -> tuple[ProviderAdapterFactory, SegmentedEnvelopeCodec]:
        if self.provider_factory is None or self.codec is None:
            raise RuntimeError("streaming storage fabric requires provider factory and canonical envelope authority")
        return self.provider_factory, self.codec

    def upload_s3_multipart(
        self,
        *,
        provider_id: str,
        global_id: str,
        source_factory: Callable[[int], Iterable[bytes]],
        total_bytes: int,
        idempotency_key: str,
        content_type: str = "application/octet-stream",
        expected_sha256: str | None = None,
        part_size: int = _DEFAULT_S3_PART_BYTES,
    ) -> dict[str, Any]:
        factory, codec = self._require_streaming()
        total = int(total_bytes)
        part_size = max(_MIN_S3_PART_BYTES, min(int(part_size), _MAX_S3_PART_BYTES))
        if total > part_size * _MAX_S3_PARTS:
            part_size = min(
                _MAX_S3_PART_BYTES,
                max(part_size, int(math.ceil(total / _MAX_S3_PARTS))),
            )
        if total > part_size * _MAX_S3_PARTS:
            raise ValueError("streaming object exceeds bounded multipart capacity")
        item = self.manager.item(global_id)
        version = int(item["version"])
        object_key = self.segmented_object_key(global_id, version)
        adapter = factory.build(provider_id)
        if not isinstance(adapter, S3CompatibleAdapter):
            raise ValueError("native multipart streaming is currently implemented only for S3-compatible providers")
        transport = S3MultipartTransport(adapter)
        job = self.transfers.start_upload(
            global_id=global_id,
            provider_id=provider_id,
            object_key=object_key,
            bytes_total=total,
            idempotency_key=idempotency_key,
            expected_sha256=expected_sha256,
        )
        if job["state"] == TransferJobState.COMMITTED.value:
            return job
        existing_info = adapter.head(object_key)
        if existing_info is not None and int(job["bytes_done"]) == total:
            self.manager.mark_location(
                global_id,
                location_type="provider",
                location_id=f"{provider_id}:{object_key}",
                provider_id=provider_id,
                has_bytes=True,
                available=True,
            )
            self.transfers.mark_state(job["job_id"], TransferJobState.COMMITTED)
            return self.transfers.job(job["job_id"])
        if existing_info is not None and int(job["bytes_done"]) != total:
            self.transfers.mark_state(job["job_id"], TransferJobState.FAILED, error_code="unexpected_existing_object")
            raise StorageFabricError("provider object already exists but durable checkpoint is incomplete")

        metadata = dict(job["metadata"])
        header = metadata.get("segmented_header")
        if header is None:
            header, data_key = codec.create_header(
                global_id,
                version,
                content_type=content_type,
                expected_plaintext_size=total,
                part_plaintext_bytes=part_size,
            )
            metadata["segmented_header"] = header
            metadata["part_plaintext_bytes"] = part_size
            self.transfers.update_metadata(job["job_id"], metadata)
        else:
            if (
                str(header.get("global_id")) != str(global_id)
                or int(header.get("object_version") or 0) != version
                or int(header.get("expected_plaintext_size") or -1) != total
            ):
                raise StorageFabricError("durable segmented transfer metadata does not match requested object")
            part_size = int(header["part_plaintext_bytes"])
            data_key = codec.key_from_header(header)

        if total == 0:
            payload = codec.header_only(header)
            adapter.put(object_key, payload, content_type="application/vnd.vishnu.segmented+octet-stream")
            self.manager.mark_location(
                global_id,
                location_type="provider",
                location_id=f"{provider_id}:{object_key}",
                provider_id=provider_id,
                has_bytes=True,
                available=True,
            )
            return self.transfers.mark_state(job["job_id"], TransferJobState.COMMITTED)

        job = self.transfers.job(job["job_id"])
        upload_id = job.get("provider_upload_id")
        if not upload_id:
            upload_id = transport.begin(
                object_key, content_type="application/vnd.vishnu.segmented+octet-stream"
            )
            job = self.transfers.set_upload_id(job["job_id"], upload_id)

        try:
            offset = int(job["bytes_done"])
            source = _coalesce_source(source_factory(offset), part_size)
            for plaintext in source:
                job = self.transfers.job(job["job_id"])
                number = int(job["next_part"])
                frame = (
                    codec.encode_first_part(header, data_key, plaintext=plaintext)
                    if number == 1
                    else codec.encode_frame(header, data_key, index=number - 1, plaintext=plaintext)
                )
                etag = transport.upload_part(object_key, upload_id, number, frame)
                self.transfers.record_part(
                    job["job_id"],
                    part_number=number,
                    etag=etag,
                    plaintext_bytes=len(plaintext),
                    ciphertext_bytes=len(frame),
                    plaintext_sha256=hashlib.sha256(plaintext).hexdigest(),
                )
            job = self.transfers.job(job["job_id"])
            if int(job["bytes_done"]) != total:
                self.transfers.mark_state(
                    job["job_id"], TransferJobState.RETRYABLE,
                    error_code="source_ended_before_declared_size", increment_retry=True,
                )
                raise StorageFabricError("source ended before declared transfer size")
            if expected_sha256:
                digest = hashlib.sha256()
                observed = 0
                for raw in source_factory(0):
                    block = bytes(raw)
                    observed += len(block)
                    if observed > total:
                        transport.abort(object_key, upload_id)
                        self.transfers.mark_state(
                            job["job_id"], TransferJobState.FAILED,
                            error_code="source_size_changed_during_verification",
                        )
                        raise StorageFabricError("source changed size during transfer verification")
                    digest.update(block)
                if observed != total or not secrets.compare_digest(digest.hexdigest(), expected_sha256):
                    transport.abort(object_key, upload_id)
                    self.transfers.mark_state(
                        job["job_id"], TransferJobState.FAILED,
                        error_code="source_digest_mismatch",
                    )
                    raise StorageFabricError("source digest did not match declared SHA-256")
            self.transfers.mark_state(job["job_id"], TransferJobState.VERIFYING)
            info = transport.complete(object_key, upload_id, self.transfers.parts(job["job_id"]))
            if info.size is None or int(info.size) <= 0:
                raise StorageFabricError("completed provider object did not report a valid size")
            self.manager.mark_location(
                global_id,
                location_type="provider",
                location_id=f"{provider_id}:{object_key}",
                provider_id=provider_id,
                has_bytes=True,
                available=True,
            )
            self.record_health(provider_id, ProviderHealth.HEALTHY)
            self.transfers.mark_state(job["job_id"], TransferJobState.COMMITTED)
            self._emit(
                "data_plane.storage_transfer_committed",
                global_id=str(global_id), provider_id=str(provider_id), job_id=str(job["job_id"]),
            )
            return self.transfers.job(job["job_id"])
        except StorageFabricError:
            raise
        except Exception as exc:
            try:
                self.transfers.mark_state(
                    job["job_id"], TransferJobState.RETRYABLE,
                    error_code=type(exc).__name__, increment_retry=True,
                )
            except Exception:
                pass
            raise

    def abort_upload(self, job_id: str) -> dict[str, Any]:
        factory, _codec = self._require_streaming()
        job = self.transfers.job(job_id)
        if job["state"] == TransferJobState.COMMITTED.value:
            raise ValueError("committed provider transfer cannot be aborted")
        upload_id = job.get("provider_upload_id")
        if upload_id:
            adapter = factory.build(job["provider_id"])
            if isinstance(adapter, S3CompatibleAdapter):
                S3MultipartTransport(adapter).abort(job["object_key"], upload_id)
        return self.transfers.mark_state(job_id, TransferJobState.ABORTED)

    def iter_s3_download(
        self,
        *,
        provider_id: str,
        global_id: str,
        version: int | None = None,
        request_bytes: int = _DEFAULT_S3_PART_BYTES,
    ) -> Iterator[bytes]:
        factory, codec = self._require_streaming()
        item = self.manager.item(global_id)
        target_version = int(version or item["version"])
        object_key = self.segmented_object_key(global_id, target_version)
        adapter = factory.build(provider_id)
        if not isinstance(adapter, S3CompatibleAdapter):
            raise ValueError("bounded range streaming is currently implemented only for S3-compatible providers")
        transport = S3MultipartTransport(adapter)
        yield from codec.iter_decrypt(
            transport.iter_range(object_key, request_bytes=request_bytes)
        )

    def diagnostics(self, global_id: str | None = None) -> dict[str, Any]:
        with self.manager._con() as con:
            jobs = {
                str(row["state"]): int(row["count"])
                for row in con.execute(
                    "SELECT state,COUNT(*) AS count FROM data_plane_storage_jobs GROUP BY state"
                ).fetchall()
            }
            health = [
                dict(row)
                for row in con.execute(
                    "SELECT * FROM data_plane_provider_health ORDER BY provider_id"
                ).fetchall()
            ]
            reconciliation_count = int(
                con.execute("SELECT COUNT(*) FROM data_plane_replica_reconciliation").fetchone()[0]
            )
        result: dict[str, Any] = {
            "format": "vishnu-storage-fabric-v1",
            "logical_object_authority": "data_plane_items",
            "replica_authority": "data_plane_locations",
            "provider_credentials_authority": "SecretVault",
            "transfer_authority": "existing data plane + durable storage checkpoints",
            "automatic_byte_movement": False,
            "jobs": jobs,
            "provider_health": health,
            "reconciliation_events": reconciliation_count,
            "capabilities": {
                provider_id: self.capabilities(provider_id)
                for provider_id in sorted(_PROVIDER_CAPABILITIES)
            },
        }
        if global_id is not None:
            result["item"] = self.manager.item(global_id)
            result["replicas"] = self.replicas(global_id)
            result["item_jobs"] = self.transfers.jobs_for_item(global_id)
        return result
