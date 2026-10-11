from __future__ import annotations

import secrets
from datetime import datetime, timezone

from .signing import canonical_json, sign_payload, verify_payload


LICENSE_SCHEMA = "vishnu.product-license/v1"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_license_document(
    *,
    product_id: str,
    product_name: str,
    version_constraint: str,
    client_name: str,
    license_type: str = "organization",
    starts_at: str | None = None,
    expires_at: str | None = None,
    max_users: int | None = None,
    max_devices: int | None = None,
    managed_ai: bool = False,
    metadata: dict | None = None,
    require_signature: bool = True,
) -> dict:
    if not str(product_id).strip() or not str(product_name).strip():
        raise ValueError("Product identity is required for a license")
    if not str(client_name).strip():
        raise ValueError("Client name is required for a license")
    if max_users is not None and int(max_users) < 1:
        raise ValueError("max_users must be at least 1")
    if max_devices is not None and int(max_devices) < 1:
        raise ValueError("max_devices must be at least 1")
    license_id = f"VPL-{secrets.token_hex(8).upper()}"
    payload = {
        "schema": LICENSE_SCHEMA,
        "license_id": license_id,
        "product_id": str(product_id),
        "product_name": str(product_name),
        "version_constraint": str(version_constraint or "*").strip() or "*",
        "client_name": str(client_name).strip(),
        "license_type": str(license_type or "organization").strip(),
        "issued_at": _iso_now(),
        "starts_at": starts_at,
        "expires_at": expires_at,
        "max_users": int(max_users) if max_users is not None else None,
        "max_devices": int(max_devices) if max_devices is not None else None,
        "managed_ai": bool(managed_ai),
        "metadata": metadata or {},
    }
    signature = sign_payload(canonical_json(payload), require_key=require_signature)
    return {"payload": payload, "signature": signature.as_dict() if signature else None}


def verify_license_document(document: dict) -> bool:
    payload = document.get("payload") if isinstance(document, dict) else None
    signature = document.get("signature") if isinstance(document, dict) else None
    if not isinstance(payload, dict) or payload.get("schema") != LICENSE_SCHEMA:
        return False
    if not isinstance(signature, dict):
        return False
    return verify_payload(canonical_json(payload), signature)
