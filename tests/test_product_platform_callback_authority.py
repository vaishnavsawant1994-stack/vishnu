from __future__ import annotations

import hashlib

import pytest

from products.artifact_builders import ProductArtifactBuilder
from products.build_lifecycle import ProductBuildLifecycle
from products.platform_jobs import PlatformBuildJobError, ProductPlatformBuildJobs
from products.store import ProductStore


def runtime(tmp_path):
    store = ProductStore(tmp_path / "products.sqlite3")
    lifecycle = ProductBuildLifecycle(store.path)
    root = tmp_path / "artifacts"
    jobs = ProductPlatformBuildJobs(store, lifecycle, root)
    resolver = ProductArtifactBuilder(store, lifecycle, root)
    return store, lifecycle, jobs, resolver


def product_build(store, target: str, name: str):
    product = store.create(name=name, product_type="custom", targets=[target])
    store.create_version(product["id"], version="0.1.0")
    build = store.request_build(product["id"], target=target)
    assert build
    return product, build


def evidence(product, build, target: str, filename: str, checksum: str, **overrides):
    base = {
        "schema": "vishnu.platform-runner-evidence/v1",
        "product_id": product["id"],
        "build_id": build["id"],
        "version": "0.1.0",
        "target": target,
        "mode": "production",
        "host_os": "qualification",
        "artifact_name": filename,
        "artifact_kind": filename.rsplit(".", 1)[-1],
        "sha256": checksum,
        "compiler_verified": True,
        "signing_verified": target in {"android", "windows", "macos", "ios"},
        "provisioning_verified": target == "ios",
        "notarization_verified": target == "macos",
        "metadata": {},
    }
    base.update(overrides)
    return base


def test_exact_terminal_artifact_callback_is_idempotent(tmp_path):
    store, _lifecycle, jobs, resolver = runtime(tmp_path)
    product, build = product_build(store, "windows", "Idempotent Windows Product")
    payload = b"qualified-windows-executable"
    checksum = hashlib.sha256(payload).hexdigest()
    filename = "qualified-product.exe"
    runner_evidence = evidence(product, build, "windows", filename, checksum)

    first = jobs.accept_artifact(
        product["id"],
        build["id"],
        filename=filename,
        expected_sha256=checksum,
        payload=payload,
        runner_evidence=runner_evidence,
    )
    second = jobs.accept_artifact(
        product["id"],
        build["id"],
        filename=filename,
        expected_sha256=checksum,
        payload=payload,
        runner_evidence=runner_evidence,
    )
    assert first["status"] == "succeeded"
    assert first["metadata"]["artifact_ready"] is True
    assert second["id"] == first["id"]
    path, _ = resolver.resolve_artifact(product["id"], build["id"])
    assert path.read_bytes() == payload


def test_terminal_callback_cannot_replace_artifact(tmp_path):
    store, _lifecycle, jobs, _resolver = runtime(tmp_path)
    product, build = product_build(store, "windows", "Immutable Windows Product")
    payload = b"artifact-one"
    checksum = hashlib.sha256(payload).hexdigest()
    filename = "one.exe"
    jobs.accept_artifact(
        product["id"], build["id"], filename=filename, expected_sha256=checksum, payload=payload,
        runner_evidence=evidence(product, build, "windows", filename, checksum),
    )
    replacement = b"artifact-two"
    replacement_sha = hashlib.sha256(replacement).hexdigest()
    with pytest.raises(PlatformBuildJobError, match="different artifact evidence"):
        jobs.accept_artifact(
            product["id"], build["id"], filename="two.exe", expected_sha256=replacement_sha, payload=replacement,
            runner_evidence=evidence(product, build, "windows", "two.exe", replacement_sha),
        )


def test_docker_production_requires_attestation(tmp_path):
    store, _lifecycle, jobs, resolver = runtime(tmp_path)
    product, build = product_build(store, "docker", "Unattested Container")
    payload = b"oci-archive-without-attestation"
    checksum = hashlib.sha256(payload).hexdigest()
    filename = "container-oci.zip"
    result = jobs.accept_artifact(
        product["id"], build["id"], filename=filename, expected_sha256=checksum, payload=payload,
        runner_evidence=evidence(
            product, build, "docker", filename, checksum,
            signing_verified=False,
            metadata={"attestation_verified": False, "image_id": "sha256:abc"},
        ),
    )
    assert result["status"] == "succeeded"
    assert result["metadata"]["artifact_ready"] is False
    with pytest.raises(Exception, match="qualified downloadable artifact"):
        resolver.resolve_artifact(product["id"], build["id"])


def test_attested_docker_production_is_distribution_ready(tmp_path):
    store, _lifecycle, jobs, resolver = runtime(tmp_path)
    product, build = product_build(store, "docker", "Attested Container")
    payload = b"oci-archive-with-verified-attestation"
    checksum = hashlib.sha256(payload).hexdigest()
    filename = "container-oci.zip"
    result = jobs.accept_artifact(
        product["id"], build["id"], filename=filename, expected_sha256=checksum, payload=payload,
        runner_evidence=evidence(
            product, build, "docker", filename, checksum,
            signing_verified=False,
            metadata={"attestation_verified": True, "image_id": "sha256:def"},
        ),
    )
    assert result["metadata"]["artifact_ready"] is True
    path, resolved = resolver.resolve_artifact(product["id"], build["id"])
    assert path.read_bytes() == payload
    assert resolved["checksum"] == checksum
