from __future__ import annotations

import hashlib
from urllib.parse import parse_qs, urlparse

import pytest

from data_plane.envelopes import EnvelopeKeyManager
from data_plane.manager import UnifiedDataPlane
from data_plane.provider_adapters import ProviderAdapterFactory
from data_plane.storage_fabric import (
    ProviderHealth,
    StorageFabric,
    StorageFabricError,
    TransferJobState,
    provider_capabilities,
)


class Vault:
    def __init__(self):
        self.values = {}

    def get(self, name, default=None):
        return self.values.get(name, default)

    def set(self, name, value):
        self.values[name] = value


class Response:
    def __init__(self, status_code=200, *, content=b"", headers=None):
        self.status_code = status_code
        self.content = bytes(content)
        self.headers = dict(headers or {})

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeS3Client:
    """Small deterministic S3 multipart/range fixture."""

    def __init__(self, *, fail_part_once: int | None = None):
        self.uploads = {}
        self.objects = {}
        self.fail_part_once = fail_part_once
        self.failed = False
        self.calls = []

    def request(self, method, url, *, headers=None, content=b"", follow_redirects=False):
        assert follow_redirects is False
        parsed = urlparse(url)
        query = parse_qs(parsed.query, keep_blank_values=True)
        self.calls.append((method, parsed.path, query, dict(headers or {}), len(content or b"")))
        key = parsed.path.split("/", 2)[-1] if parsed.path.count("/") >= 2 else ""

        if method == "HEAD":
            payload = self.objects.get(key)
            if payload is None:
                return Response(404)
            return Response(
                200,
                headers={
                    "content-length": str(len(payload)),
                    "etag": '"complete-etag"',
                    "content-type": "application/vnd.vishnu.segmented+octet-stream",
                },
            )

        if method == "POST" and "uploads" in query:
            upload_id = f"upload-{len(self.uploads) + 1}"
            self.uploads[upload_id] = {"key": key, "parts": {}}
            xml = (
                "<InitiateMultipartUploadResult>"
                f"<UploadId>{upload_id}</UploadId>"
                "</InitiateMultipartUploadResult>"
            ).encode()
            return Response(200, content=xml)

        if method == "PUT" and "uploadId" in query and "partNumber" in query:
            upload_id = query["uploadId"][0]
            part = int(query["partNumber"][0])
            if self.fail_part_once == part and not self.failed:
                self.failed = True
                raise RuntimeError("simulated provider interruption")
            self.uploads[upload_id]["parts"][part] = bytes(content)
            return Response(200, headers={"etag": f'"etag-{part}"'})

        if method == "POST" and "uploadId" in query:
            upload_id = query["uploadId"][0]
            record = self.uploads[upload_id]
            self.objects[record["key"]] = b"".join(
                record["parts"][number] for number in sorted(record["parts"])
            )
            return Response(200, content=b"<CompleteMultipartUploadResult/>")

        if method == "DELETE" and "uploadId" in query:
            self.uploads.pop(query["uploadId"][0], None)
            return Response(204)

        if method == "GET":
            payload = self.objects.get(key)
            if payload is None:
                return Response(404)
            range_header = (headers or {}).get("Range") or (headers or {}).get("range")
            if not range_header:
                return Response(200, content=payload)
            start_text, end_text = range_header.removeprefix("bytes=").split("-", 1)
            start, end = int(start_text), int(end_text)
            return Response(206, content=payload[start:end + 1])

        raise AssertionError((method, url, query))


@pytest.fixture
def manager(tmp_path):
    value = UnifiedDataPlane(tmp_path / "data-plane.sqlite3")
    value.update_settings(cloud_enabled=True, cloud_mode="own_cloud")
    value.configure_provider(
        "s3",
        enabled=True,
        credential_ref="provider:s3",
        config={"bucket": "owner-vishnu", "region": "eu-central-1"},
        verified=True,
    )
    return value


def build_fabric(manager, client):
    vault = Vault()
    vault.set(
        "provider:s3",
        '{"access_key_id":"ACCESS","secret_access_key":"SECRET"}',
    )
    envelopes = EnvelopeKeyManager(manager, vault)
    factory = ProviderAdapterFactory(manager, vault, client_factory=lambda: client)
    fabric = StorageFabric(
        manager,
        envelopes=envelopes,
        provider_factory=factory,
    )
    manager.storage_fabric = fabric
    return fabric


def register(manager, global_id="file-1", *, policy="sync_everywhere", copy_allowed=True):
    return manager.register_item(
        global_id,
        entity_type="file",
        primary_device_id="device-a",
        policy=policy,
        copy_allowed=copy_allowed,
        content_digest=None,
        metadata={"name": "demo.bin"},
    )


def test_capability_contract_is_explicit_and_does_not_overclaim_google():
    s3 = provider_capabilities("s3")
    drive = provider_capabilities("google_drive")
    assert s3.multipart_upload is True
    assert s3.resumable_upload is True
    assert s3.range_read is True
    assert s3.server_copy is False
    assert drive.resumable_upload is False
    assert drive.multipart_upload is False


def test_placement_respects_device_only_progress_only_and_on_demand(manager):
    fabric = StorageFabric(manager)
    register(manager, "device-only", policy="device_only", copy_allowed=False)
    decision = fabric.plan_placement(
        "device-only",
        [
            {"location_type": "device", "location_id": "device-a", "local": True},
            {
                "location_type": "provider",
                "location_id": "s3:future",
                "provider_id": "s3",
                "free_bytes": 10_000,
            },
        ],
        required_bytes=100,
    )
    assert decision.selected["location_id"] == "device-a"
    assert decision.rejected[0]["reason"] == "device_only_raw_bytes_must_stay_on_primary_device"

    register(manager, "progress", policy="progress_only", copy_allowed=False)
    progress = fabric.plan_placement(
        "progress",
        [{"location_type": "provider", "location_id": "s3:x", "provider_id": "s3"}],
    )
    assert progress.selected is None
    assert progress.rejected[0]["reason"] == "progress_only_raw_bytes_must_stay_on_primary_device"

    register(manager, "ondemand", policy="on_demand", copy_allowed=True)
    ondemand = fabric.plan_placement(
        "ondemand",
        [{"location_type": "provider", "location_id": "s3:new", "provider_id": "s3"}],
        explicit=False,
    )
    assert ondemand.selected is None
    assert ondemand.rejected[0]["reason"] == "on_demand_never_creates_automatic_replica"


def test_transfer_checkpoint_is_idempotent_and_replay_safe(manager):
    register(manager)
    fabric = StorageFabric(manager)
    job = fabric.transfers.start_upload(
        global_id="file-1",
        provider_id="s3",
        object_key="v2/key",
        bytes_total=8,
        idempotency_key="upload:file-1:v1",
    )
    replay = fabric.transfers.start_upload(
        global_id="file-1",
        provider_id="s3",
        object_key="v2/key",
        bytes_total=8,
        idempotency_key="upload:file-1:v1",
    )
    assert replay["job_id"] == job["job_id"]
    fabric.transfers.set_upload_id(job["job_id"], "provider-upload")
    fabric.transfers.record_part(
        job["job_id"],
        part_number=1,
        etag="etag-1",
        plaintext_bytes=8,
        ciphertext_bytes=32,
        plaintext_sha256=hashlib.sha256(b"12345678").hexdigest(),
    )
    again = fabric.transfers.record_part(
        job["job_id"],
        part_number=1,
        etag="etag-1",
        plaintext_bytes=8,
        ciphertext_bytes=32,
        plaintext_sha256=hashlib.sha256(b"12345678").hexdigest(),
    )
    assert again["bytes_done"] == 8
    with pytest.raises(ValueError, match="replay"):
        fabric.transfers.record_part(
            job["job_id"],
            part_number=1,
            etag="different",
            plaintext_bytes=8,
            ciphertext_bytes=32,
            plaintext_sha256=hashlib.sha256(b"12345678").hexdigest(),
        )


def test_segmented_s3_upload_resumes_after_interruption_and_downloads_in_ranges(manager):
    register(manager)
    client = FakeS3Client(fail_part_once=2)
    fabric = build_fabric(manager, client)
    payload = (b"A" * (8 * 1024 * 1024)) + (b"B" * (1024 * 1024 + 17))
    digest = hashlib.sha256(payload).hexdigest()

    def source(offset):
        data = payload[offset:]
        step = 700_001
        return (data[pos:pos + step] for pos in range(0, len(data), step))

    with pytest.raises(RuntimeError, match="interruption"):
        fabric.upload_s3_multipart(
            provider_id="s3",
            global_id="file-1",
            source_factory=source,
            total_bytes=len(payload),
            idempotency_key="file-1:s3:v1",
            expected_sha256=digest,
        )

    jobs = fabric.transfers.jobs_for_item("file-1")
    assert jobs[0]["state"] == TransferJobState.RETRYABLE.value
    assert jobs[0]["bytes_done"] == 8 * 1024 * 1024
    upload_id = jobs[0]["provider_upload_id"]

    completed = fabric.upload_s3_multipart(
        provider_id="s3",
        global_id="file-1",
        source_factory=source,
        total_bytes=len(payload),
        idempotency_key="file-1:s3:v1",
        expected_sha256=digest,
    )
    assert completed["state"] == TransferJobState.COMMITTED.value
    assert completed["provider_upload_id"] == upload_id
    assert completed["bytes_done"] == len(payload)
    assert any(location["location_id"].startswith("s3:v2/") for location in manager.item("file-1")["locations"])

    downloaded = b"".join(
        fabric.iter_s3_download(provider_id="s3", global_id="file-1", request_bytes=1024 * 1024)
    )
    assert downloaded == payload


def test_digest_mismatch_aborts_before_commit(manager):
    register(manager)
    client = FakeS3Client()
    fabric = build_fabric(manager, client)
    payload = b"payload" * 900_000

    def source(offset):
        return [payload[offset:]]

    with pytest.raises(StorageFabricError, match="digest"):
        fabric.upload_s3_multipart(
            provider_id="s3",
            global_id="file-1",
            source_factory=source,
            total_bytes=len(payload),
            idempotency_key="file-1:bad-digest",
            expected_sha256="0" * 64,
        )
    job = fabric.transfers.jobs_for_item("file-1")[0]
    assert job["state"] == TransferJobState.FAILED.value
    assert not any(location["location_id"].startswith("s3:v2/") for location in manager.item("file-1")["locations"])


def test_reconciliation_marks_confirmed_missing_but_never_silently_replicates(manager):
    register(manager)
    client = FakeS3Client()
    fabric = build_fabric(manager, client)
    payload = b"z" * (6 * 1024 * 1024)

    def source(offset):
        return [payload[offset:]]

    fabric.upload_s3_multipart(
        provider_id="s3",
        global_id="file-1",
        source_factory=source,
        total_bytes=len(payload),
        idempotency_key="file-1:reconcile",
    )
    location = next(
        value for value in manager.item("file-1")["locations"]
        if value["location_id"].startswith("s3:v2/")
    )
    object_key = location["location_id"].split(":", 1)[1]
    client.objects.pop(object_key)

    outcomes = fabric.reconcile_item("file-1")
    assert outcomes[0]["outcome"] == "confirmed_missing"
    current = next(
        value for value in manager.item("file-1")["locations"]
        if value["location_id"] == location["location_id"]
    )
    assert current["has_bytes"] is False
    assert current["available"] is False
    assert len([value for value in manager.item("file-1")["locations"] if value["has_bytes"]]) == 1


def test_provider_health_is_non_secret_and_persistent(manager):
    fabric = StorageFabric(manager)
    health = fabric.record_health(
        "s3", ProviderHealth.HEALTHY, latency_ms=12.5, free_bytes=123456
    )
    assert health["state"] == "healthy"
    diagnostics = fabric.diagnostics()
    assert diagnostics["automatic_byte_movement"] is False
    assert diagnostics["provider_credentials_authority"] == "SecretVault"
    assert "ACCESS" not in str(diagnostics)
