from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from products.artifact_builders import ProductArtifactBuilder
from products.build_lifecycle import ProductBuildLifecycle
from products.platform_jobs import (
    PlatformBuildJobError,
    ProductPlatformBuildJobs,
    RUNNER_TOKEN_ENV,
    runner_token_matches,
)
from products.signing import PUBLIC_KEY_ENV, SIGNING_KEY_ENV
from products.store import ProductStore


def configure_signing(monkeypatch):
    key = Ed25519PrivateKey.generate()
    private_raw = key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_raw = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    private_b64 = base64.b64encode(private_raw).decode("ascii")
    public_b64 = base64.b64encode(public_raw).decode("ascii")
    monkeypatch.setenv(SIGNING_KEY_ENV, private_b64)
    monkeypatch.setenv(PUBLIC_KEY_ENV, public_b64)
    return public_b64


def make_runtime(tmp_path):
    store = ProductStore(tmp_path / "products.sqlite3")
    lifecycle = ProductBuildLifecycle(store.path)
    artifacts = tmp_path / "artifacts"
    jobs = ProductPlatformBuildJobs(store, lifecycle, artifacts)
    resolver = ProductArtifactBuilder(store, lifecycle, artifacts)
    return store, lifecycle, jobs, resolver


def make_android_build(store):
    product = store.create(
        name="ACME Mobile Employee",
        product_type="ai_employee",
        targets=["android"],
    )
    store.set_ai_policy(
        product["id"],
        {
            "mode": "client_api",
            "provider": "openai",
            "secret_ref": "vault://owner/acme/openai",
        },
    )
    store.add_component(
        product["id"],
        component_type="agent",
        component_ref="agent.sales",
        name="Sales Agent",
        config={"instructions": "Qualify inbound sales leads."},
    )
    store.create_version(product["id"], version="0.1.0")
    build = store.request_build(product["id"], target="android")
    assert build is not None
    return product, build


def test_platform_job_is_signed_frozen_and_secret_free(tmp_path, monkeypatch):
    configure_signing(monkeypatch)
    store, _lifecycle, jobs, _resolver = make_runtime(tmp_path)
    product, build = make_android_build(store)

    filename, raw, metadata = jobs.prepare_job(product["id"], build["id"])
    assert filename.endswith(".vishnu-build-job")
    assert metadata["signed"] is True
    assert len(metadata["sha256"]) == 64
    assert "vault://owner/acme/openai" not in raw.decode("latin1")

    with zipfile.ZipFile(Path(tmp_path / "job.zip"), "w") as _unused:
        pass
    with zipfile.ZipFile(__import__("io").BytesIO(raw)) as archive:
        assert set(archive.namelist()) == {"job.json", "manifest.json", "checksums.json"}
        envelope = json.loads(archive.read("job.json"))
        manifest = json.loads(archive.read("manifest.json"))
        assert envelope["payload"]["product_id"] == product["id"]
        assert envelope["payload"]["target"] == "android"
        assert envelope["payload"]["version"] == "0.1.0"
        assert envelope["payload"]["constraints"]["raw_secrets_forbidden"] is True
        assert "secret_ref" not in manifest["ai_policy"]
        assert manifest["ai_policy"]["credentials"] == "runtime-provisioned"


def test_production_platform_job_requires_signing(tmp_path, monkeypatch):
    monkeypatch.delenv(SIGNING_KEY_ENV, raising=False)
    monkeypatch.delenv(PUBLIC_KEY_ENV, raising=False)
    store, _lifecycle, jobs, _resolver = make_runtime(tmp_path)
    product, build = make_android_build(store)
    with pytest.raises(ValueError, match="signing is not configured"):
        jobs.prepare_job(product["id"], build["id"])
    _, raw, meta = jobs.prepare_job(product["id"], build["id"], development=True)
    assert raw
    assert meta["signed"] is False


def test_runner_token_is_fail_closed_and_exact(monkeypatch):
    monkeypatch.delenv(RUNNER_TOKEN_ENV, raising=False)
    assert runner_token_matches("anything") is False
    monkeypatch.setenv(RUNNER_TOKEN_ENV, "runner-secret-123")
    assert runner_token_matches("runner-secret-123") is True
    assert runner_token_matches("runner-secret-124") is False
    assert runner_token_matches("") is False


def test_unsigned_android_artifact_cannot_become_distribution_ready(tmp_path, monkeypatch):
    configure_signing(monkeypatch)
    store, _lifecycle, jobs, resolver = make_runtime(tmp_path)
    product, build = make_android_build(store)
    jobs.mark_running(product["id"], build["id"])
    payload = b"fake-debug-apk"
    result = jobs.accept_artifact(
        product["id"],
        build["id"],
        filename="acme-debug.apk",
        expected_sha256=hashlib.sha256(payload).hexdigest(),
        payload=payload,
        platform_signing_verified=False,
        runner_metadata={"variant": "debug"},
    )
    assert result["status"] == "succeeded"
    assert result["metadata"]["artifact_ready"] is False
    assert result["metadata"]["signing_verified"] is False
    with pytest.raises(Exception, match="qualified downloadable artifact"):
        resolver.resolve_artifact(product["id"], build["id"])


def test_signed_android_artifact_is_checksum_bound_and_downloadable(tmp_path, monkeypatch):
    configure_signing(monkeypatch)
    store, _lifecycle, jobs, resolver = make_runtime(tmp_path)
    product, build = make_android_build(store)
    jobs.mark_running(product["id"], build["id"])
    payload = b"fake-release-apk-with-runner-signature-verification"
    checksum = hashlib.sha256(payload).hexdigest()
    result = jobs.accept_artifact(
        product["id"],
        build["id"],
        filename="ACME-Mobile-Employee-0.1.0-release.apk",
        expected_sha256=checksum,
        payload=payload,
        platform_signing_verified=True,
        runner_metadata={"variant": "release", "compiler": "android-gradle"},
    )
    assert result["metadata"]["artifact_ready"] is True
    assert result["metadata"]["signing_verified"] is True
    path, resolved = resolver.resolve_artifact(product["id"], build["id"])
    assert path.read_bytes() == payload
    assert resolved["checksum"] == checksum
    path.write_bytes(payload + b"tamper")
    with pytest.raises(Exception, match="checksum"):
        resolver.resolve_artifact(product["id"], build["id"])


def test_platform_artifact_rejects_bad_digest_and_filename(tmp_path, monkeypatch):
    configure_signing(monkeypatch)
    store, _lifecycle, jobs, _resolver = make_runtime(tmp_path)
    product, build = make_android_build(store)
    jobs.mark_running(product["id"], build["id"])
    with pytest.raises(PlatformBuildJobError, match="filename"):
        jobs.accept_artifact(
            product["id"], build["id"], filename="../../escape.apk", expected_sha256="0" * 64, payload=b"x", platform_signing_verified=True
        )
    with pytest.raises(PlatformBuildJobError, match="SHA-256"):
        jobs.accept_artifact(
            product["id"], build["id"], filename="safe.apk", expected_sha256="0" * 64, payload=b"x", platform_signing_verified=True
        )


def test_android_runner_generates_bounded_source_project(tmp_path, monkeypatch):
    public_key = configure_signing(monkeypatch)
    store, _lifecycle, jobs, _resolver = make_runtime(tmp_path)
    product, build = make_android_build(store)
    _name, raw, _metadata = jobs.prepare_job(product["id"], build["id"])
    job = tmp_path / "android.vishnu-build-job"
    job.write_bytes(raw)
    output = tmp_path / "runner-output"
    env = dict(__import__("os").environ)
    env[PUBLIC_KEY_ENV] = public_key
    result = subprocess.run(
        [sys.executable, "packaging/product_platform_runner.py", str(job), "--output", str(output), "--source-only"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    report = json.loads(result.stdout)
    source_zip = Path(report["artifact"])
    assert source_zip.exists()
    assert report["platform_signing_verified"] is False
    assert report["variant"] == "source"
    assert report["sha256"] == hashlib.sha256(source_zip.read_bytes()).hexdigest()
    with zipfile.ZipFile(source_zip) as archive:
        names = set(archive.namelist())
        assert "app/src/main/AndroidManifest.xml" in names
        assert "app/src/main/assets/manifest.json" in names
        embedded = archive.read("app/src/main/assets/manifest.json").decode("utf-8")
        assert "vault://owner/acme/openai" not in embedded
        assert "secret_ref" not in embedded
        assert not any(name.startswith("agent/") or name.startswith("memory/") for name in names)
