from __future__ import annotations

import importlib.util
from pathlib import Path

from products.platform_runners import validate_runner_evidence


ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_apple_runner_development_evidence_is_fail_closed(tmp_path):
    runner = _load("vishnu_test_apple_runner", "packaging/product_apple_runner.py")
    artifact = tmp_path / "sample.dmg"
    artifact.write_bytes(b"compiled-macos-product")
    result = runner._result(
        {
            "product_id": "product-1",
            "build_id": "build-1",
            "version": "1.0.0",
            "target": "macos",
            "development": True,
        },
        artifact,
        artifact_kind="dmg",
        variant="qualification",
    )
    evidence = validate_runner_evidence(result["evidence"])
    assert evidence.compiler_verified is True
    assert evidence.signing_verified is False
    assert evidence.notarization_verified is False
    assert evidence.production_ready is False


def test_ios_runner_evidence_requires_signing_and_provisioning(tmp_path):
    runner = _load("vishnu_test_ios_runner", "packaging/product_apple_runner.py")
    artifact = tmp_path / "sample.ipa"
    artifact.write_bytes(b"compiled-ios-product")
    result = runner._result(
        {
            "product_id": "product-2",
            "build_id": "build-2",
            "version": "2.0.0",
            "target": "ios",
            "development": False,
        },
        artifact,
        artifact_kind="ipa",
        variant="device",
        signing_verified=True,
        provisioning_verified=True,
    )
    evidence = validate_runner_evidence(result["evidence"])
    assert evidence.signing_verified is True
    assert evidence.provisioning_verified is True
    assert evidence.production_ready is True


def test_apple_bundle_identifier_is_stable_and_product_scoped():
    runner = _load("vishnu_test_bundle_runner", "packaging/product_apple_runner.py")
    first = runner._bundle_id("product-abc")
    second = runner._bundle_id("product-abc")
    other = runner._bundle_id("product-def")
    assert first == second
    assert first != other
    assert first.startswith("ai.vishnu.product.p")
    assert len(first) < 64


def test_desktop_container_runner_development_evidence_is_fail_closed(tmp_path):
    runner = _load("vishnu_test_desktop_runner", "packaging/product_desktop_container_runner.py")
    artifact = tmp_path / "sample.exe"
    artifact.write_bytes(b"compiled-windows-product")
    result = runner._result(
        {
            "product_id": "product-3",
            "build_id": "build-3",
            "version": "3.0.0",
            "target": "windows",
            "development": True,
        },
        artifact,
        artifact_kind="exe",
        variant="qualification",
    )
    evidence = validate_runner_evidence(result["evidence"])
    assert evidence.compiler_verified is True
    assert evidence.signing_verified is False
    assert evidence.production_ready is False
