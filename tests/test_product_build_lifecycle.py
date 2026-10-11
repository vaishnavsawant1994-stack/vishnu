from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from products.build_lifecycle import ProductBuildLifecycle
from products.store import ProductStore


def make_stores():
    directory = tempfile.TemporaryDirectory()
    path = Path(directory.name) / "products.sqlite3"
    store = ProductStore(path)
    lifecycle = ProductBuildLifecycle(path)
    return directory, store, lifecycle


def test_build_numbers_are_monotonic_and_persisted():
    directory, store, lifecycle = make_stores()
    try:
        product = store.create(name="Release Product", targets=["web"])
        first = lifecycle.ensure(store.request_build(product["id"], target="web"))
        second = lifecycle.ensure(store.request_build(product["id"], target="web"))

        assert first["build_number"] == 1
        assert second["build_number"] == 2

        reopened = ProductBuildLifecycle(store.path)
        builds = reopened.list(product["id"], store.builds(product["id"]))
        by_id = {item["id"]: item for item in builds}
        assert by_id[first["id"]]["build_number"] == 1
        assert by_id[second["id"]]["build_number"] == 2
    finally:
        directory.cleanup()


def test_pre_upgrade_builds_are_backfilled_in_chronological_order():
    directory, store, lifecycle = make_stores()
    try:
        product = store.create(name="Migrated Product", targets=["web"])
        first = store.request_build(product["id"], target="web")
        second = store.request_build(product["id"], target="web")

        # Simulate opening a newer build first after upgrading the runtime.
        second_enriched = lifecycle.ensure(second)
        first_enriched = lifecycle.ensure(first)

        assert first_enriched["build_number"] == 1
        assert second_enriched["build_number"] == 2
    finally:
        directory.cleanup()


def test_owner_state_updates_cannot_manufacture_artifact_evidence():
    directory, store, lifecycle = make_stores()
    try:
        product = store.create(name="Android Product", targets=["android"])
        build = lifecycle.ensure(store.request_build(product["id"], target="android"))

        queued = lifecycle.update(product["id"], build["id"], status="queued")
        running = lifecycle.update(product["id"], build["id"], status="running")
        succeeded = lifecycle.update(product["id"], build["id"], status="succeeded")

        assert queued["status"] == "queued"
        assert running["status"] == "running"
        assert succeeded["status"] == "succeeded"
        assert succeeded["metadata"]["artifact_ready"] is False

        with pytest.raises(ValueError, match="verified builder adapter"):
            lifecycle.update(
                product["id"],
                build["id"],
                artifact_name="product.apk",
                artifact_uri="file:///tmp/product.apk",
                checksum="sha256:fake",
                signing_verified=True,
            )
    finally:
        directory.cleanup()


def test_native_artifact_requires_verified_builder_and_signing():
    directory, store, lifecycle = make_stores()
    try:
        product = store.create(name="Signed Android Product", targets=["android"])
        build = lifecycle.ensure(store.request_build(product["id"], target="android"))
        lifecycle.update(product["id"], build["id"], status="running")

        unsigned = lifecycle.update(
            product["id"],
            build["id"],
            status="succeeded",
            artifact_name="product.apk",
            artifact_uri="artifact://android/product.apk",
            checksum="sha256:0123456789",
            signing_verified=False,
            verified_builder=True,
        )
        assert unsigned["metadata"]["artifact_ready"] is False

        signed = lifecycle.update(
            product["id"],
            build["id"],
            artifact_name="product.apk",
            artifact_uri="artifact://android/product.apk",
            checksum="sha256:0123456789",
            signing_verified=True,
            verified_builder=True,
        )
        assert signed["metadata"]["artifact_ready"] is True
    finally:
        directory.cleanup()


def test_invalid_build_transition_is_rejected():
    directory, store, lifecycle = make_stores()
    try:
        product = store.create(name="Transition Product", targets=["web"])
        build = lifecycle.ensure(store.request_build(product["id"], target="web"))
        with pytest.raises(ValueError, match="Invalid build transition"):
            lifecycle.update(product["id"], build["id"], status="succeeded")
    finally:
        directory.cleanup()
