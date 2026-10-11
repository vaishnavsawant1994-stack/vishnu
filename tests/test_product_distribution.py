from __future__ import annotations

import base64
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from products.license_store import ProductLicenseStore
from products.licensing import verify_license_document
from products.package_export import build_portable_package, inspect_portable_package
from products.signing import SIGNING_KEY_ENV, PUBLIC_KEY_ENV, canonical_json, verify_payload
from products.store import ProductStore
from products.verification import verify_portable_product, verify_product_license


def configure_signing(monkeypatch):
    key = Ed25519PrivateKey.generate()
    raw_private = key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    raw_public = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    private_b64 = base64.b64encode(raw_private).decode("ascii")
    public_b64 = base64.b64encode(raw_public).decode("ascii")
    monkeypatch.setenv(SIGNING_KEY_ENV, private_b64)
    monkeypatch.setenv(PUBLIC_KEY_ENV, public_b64)
    return private_b64, public_b64


def make_stores():
    directory = tempfile.TemporaryDirectory()
    path = Path(directory.name) / "products.sqlite3"
    products = ProductStore(path)
    licenses = ProductLicenseStore(path)
    return directory, products, licenses


def test_signed_portable_package_contains_only_canonical_distribution_files(monkeypatch):
    _, public_key = configure_signing(monkeypatch)
    directory, products, _ = make_stores()
    try:
        product = products.create(
            name="ACME Research Employee",
            product_type="ai_employee",
            client_name="ACME",
            targets=["web", "android"],
        )
        products.set_ai_policy(
            product["id"],
            {"mode": "client_api", "provider": "openai", "secret_ref": "vault://clients/acme/openai"},
        )
        manifest = products.manifest(product["id"])
        filename, raw, metadata = build_portable_package(manifest)
        assert filename.endswith(".vishnu-product")
        assert metadata["signed"] is True
        assert metadata["package_sha256"]

        inspected = inspect_portable_package(raw)
        assert inspected["manifest"]["product_id"] == product["id"]
        assert "secret_ref" not in inspected["manifest"]["ai_policy"]
        assert inspected["manifest"]["ai_policy"]["credentials"] == "runtime-provisioned"
        assert "vault://clients/acme/openai" not in raw.decode("latin1")
        assert verify_payload(canonical_json(inspected["manifest"]), inspected["package"]["signature"])
        assert "api_key" not in raw.decode("latin1").lower()

        verified = verify_portable_product(raw, trusted_public_key_b64=public_key)
        assert verified.valid is True
        assert verified.code == "verified"
    finally:
        directory.cleanup()


def test_portable_package_rejects_untrusted_signer(monkeypatch):
    configure_signing(monkeypatch)
    _, raw, _ = build_portable_package(
        {"schema": "vishnu.product/v1", "product_id": "p1", "name": "Demo", "version": "1.0.0"}
    )
    other = Ed25519PrivateKey.generate().public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    result = verify_portable_product(raw, trusted_public_key_b64=base64.b64encode(other).decode("ascii"))
    assert result.valid is False
    assert result.code == "untrusted_signer"


def test_production_package_fails_closed_without_signing(monkeypatch):
    monkeypatch.delenv(SIGNING_KEY_ENV, raising=False)
    monkeypatch.delenv(PUBLIC_KEY_ENV, raising=False)
    manifest = {"schema": "vishnu.product/v1", "product_id": "p1", "name": "Demo", "version": "1.0.0"}
    with pytest.raises(ValueError, match="signing is not configured"):
        build_portable_package(manifest)
    _, raw, metadata = build_portable_package(manifest, require_signature=False)
    assert raw
    assert metadata["signed"] is False
    assert verify_portable_product(raw).code == "signature_required"
    assert verify_portable_product(raw, allow_unsigned_development=True).valid is True


def test_signed_license_is_persisted_downloadable_and_revocable(monkeypatch):
    _, public_key = configure_signing(monkeypatch)
    directory, products, licenses = make_stores()
    try:
        product = products.create(name="Recruitment Employee", product_type="ai_employee", client_name="ABC Recruitment")
        issued = licenses.issue(
            product=product,
            client_name="ABC Recruitment",
            license_type="organization",
            version_constraint="1.x",
            max_users=20,
            max_devices=30,
            managed_ai=True,
        )
        assert issued["status"] == "active"
        assert issued["managed_ai"] is True
        assert verify_license_document(issued["document"])
        assert licenses.list_for_product(product["id"])[0]["license_id"] == issued["license_id"]

        verified = verify_product_license(
            issued["document"],
            product_id=product["id"],
            version="1.4.2",
            client_name="ABC Recruitment",
            trusted_public_key_b64=public_key,
        )
        assert verified.valid is True

        revoked = licenses.revoke(product["id"], issued["license_id"])
        assert revoked["status"] == "revoked"
        assert revoked["revoked_at"]
        # The original signed entitlement remains cryptographically verifiable;
        # revocation is enforced by the authoritative registry/status check.
        assert verify_license_document(revoked["document"])
    finally:
        directory.cleanup()


def test_license_runtime_verification_checks_expiry_product_version_and_trust(monkeypatch):
    _, public_key = configure_signing(monkeypatch)
    directory, products, licenses = make_stores()
    try:
        product = products.create(name="Operations Worker", product_type="automation", client_name="Example Co")
        now = datetime.now(timezone.utc)
        issued = licenses.issue(
            product=product,
            client_name="Example Co",
            version_constraint="2.x",
            starts_at=(now - timedelta(days=2)).isoformat(),
            expires_at=(now + timedelta(days=2)).isoformat(),
        )
        document = issued["document"]
        assert verify_product_license(document, product_id=product["id"], version="2.3.0", trusted_public_key_b64=public_key, now=now).valid
        assert verify_product_license(document, product_id="different", version="2.3.0", trusted_public_key_b64=public_key, now=now).code == "product_mismatch"
        assert verify_product_license(document, product_id=product["id"], version="3.0.0", trusted_public_key_b64=public_key, now=now).code == "version_not_licensed"
        assert verify_product_license(document, product_id=product["id"], version="2.3.0", trusted_public_key_b64=public_key, now=now + timedelta(days=3)).code == "license_expired"

        other = Ed25519PrivateKey.generate().public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        assert verify_product_license(document, product_id=product["id"], trusted_public_key_b64=base64.b64encode(other).decode("ascii")).code == "untrusted_signer"
    finally:
        directory.cleanup()
