from __future__ import annotations

import pytest

from products.commercial_store import CommercialProductStore
from products.licensing import LicenseAuthority, LicenseVerifier
from products.store import ProductStore


def test_commercial_license_installation_limit_and_usage(tmp_path):
    path = tmp_path / "products.sqlite3"
    products = ProductStore(path)
    product = products.create(name="Sales Employee", product_type="ai_employee", targets=["web"])
    commercial = CommercialProductStore(path)
    client = commercial.upsert_client(client_id="acme", name="ACME Ltd")

    authority = LicenseAuthority.generate()
    verifier = LicenseVerifier({authority.key_id: authority.public_key})
    document = authority.issue(
        license_id="LIC-ACME-1",
        product_id=product["id"],
        client_id=client["id"],
        license_type="annual",
        device_limit=1,
        managed_ai_allowed=True,
    ).as_dict()
    saved = commercial.save_license(product_id=product["id"], client_id=client["id"], document=document)
    assert saved["status"] == "active"

    installation = commercial.activate_installation(
        license_id="LIC-ACME-1",
        device_fingerprint="device-a",
        platform="web",
        version="0.1.0",
        verifier=verifier,
    )
    assert installation["status"] == "active"

    with pytest.raises(ValueError, match="device limit"):
        commercial.activate_installation(
            license_id="LIC-ACME-1",
            device_fingerprint="device-b",
            platform="web",
            version="0.1.0",
            verifier=verifier,
        )

    commercial.record_usage(
        product_id=product["id"],
        client_id="acme",
        license_id="LIC-ACME-1",
        event_type="model.tokens",
        quantity=1250,
        unit="tokens",
    )
    summary = commercial.usage_summary(product["id"])
    assert summary == [{"event_type": "model.tokens", "unit": "tokens", "events": 1, "quantity": 1250.0}]

    deployment = commercial.record_deployment(
        product_id=product["id"],
        target="web",
        version="0.1.0",
        status="healthy",
        url="https://example.invalid",
    )
    assert commercial.deployments(product["id"])[0]["id"] == deployment["id"]

    assert commercial.revoke_license("LIC-ACME-1") is True
    assert commercial.installations(product["id"])[0]["status"] == "revoked"


def test_license_product_and_client_binding_is_enforced(tmp_path):
    path = tmp_path / "products.sqlite3"
    products = ProductStore(path)
    product = products.create(name="Research Employee")
    commercial = CommercialProductStore(path)
    authority = LicenseAuthority.generate()
    document = authority.issue(
        license_id="LIC-1",
        product_id=product["id"],
        client_id="client-a",
        license_type="trial",
    ).as_dict()

    with pytest.raises(ValueError, match="binding"):
        commercial.save_license(product_id=product["id"], client_id="client-b", document=document)
