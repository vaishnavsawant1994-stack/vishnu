from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from datetime import datetime, timezone

from .licensing import LICENSE_SCHEMA
from .package_export import inspect_portable_package
from .signing import PUBLIC_KEY_ENV, canonical_json, verify_payload


@dataclass(frozen=True)
class VerificationResult:
    valid: bool
    code: str
    detail: str
    manifest: dict | None = None
    license_payload: dict | None = None


def _trusted_public_key_b64(explicit: str | None = None) -> str:
    value = str(explicit or os.environ.get(PUBLIC_KEY_ENV, "")).strip()
    if not value:
        raise ValueError("Trusted Vishnu product signing public key is not configured")
    try:
        raw = base64.b64decode(value, validate=True)
    except Exception as exc:
        raise ValueError("Trusted Vishnu product signing public key must be valid base64") from exc
    if len(raw) != 32:
        raise ValueError("Trusted Vishnu product signing public key must decode to exactly 32 bytes")
    return value


def _signature_matches_trust_anchor(envelope: dict, trusted_public_key_b64: str) -> bool:
    try:
        embedded = base64.b64decode(str(envelope.get("public_key_b64", "")), validate=True)
        trusted = base64.b64decode(trusted_public_key_b64, validate=True)
    except Exception:
        return False
    return embedded == trusted


def verify_portable_product(
    raw: bytes,
    *,
    trusted_public_key_b64: str | None = None,
    allow_unsigned_development: bool = False,
) -> VerificationResult:
    try:
        inspected = inspect_portable_package(raw)
    except Exception as exc:
        return VerificationResult(False, "package_invalid", str(exc))
    manifest = inspected["manifest"]
    package = inspected["package"]
    signature = package.get("signature")
    if not package.get("signed") or not isinstance(signature, dict):
        if allow_unsigned_development:
            return VerificationResult(True, "unsigned_development", "Unsigned development package accepted by explicit policy", manifest=manifest)
        return VerificationResult(False, "signature_required", "Production product package must be signed", manifest=manifest)
    try:
        trusted = _trusted_public_key_b64(trusted_public_key_b64)
    except ValueError as exc:
        return VerificationResult(False, "trust_anchor_missing", str(exc), manifest=manifest)
    if not _signature_matches_trust_anchor(signature, trusted):
        return VerificationResult(False, "untrusted_signer", "Product package signer does not match the trusted Vishnu product key", manifest=manifest)
    if not verify_payload(canonical_json(manifest), signature):
        return VerificationResult(False, "signature_invalid", "Product package signature is invalid", manifest=manifest)
    if manifest.get("schema") != "vishnu.product/v1":
        return VerificationResult(False, "schema_invalid", "Unsupported Vishnu product schema", manifest=manifest)
    return VerificationResult(True, "verified", "Product package verified", manifest=manifest)


def verify_product_license(
    document: dict,
    *,
    product_id: str,
    version: str | None = None,
    client_name: str | None = None,
    trusted_public_key_b64: str | None = None,
    now: datetime | None = None,
) -> VerificationResult:
    if not isinstance(document, dict):
        return VerificationResult(False, "license_invalid", "License document is invalid")
    payload = document.get("payload")
    signature = document.get("signature")
    if not isinstance(payload, dict) or payload.get("schema") != LICENSE_SCHEMA:
        return VerificationResult(False, "license_schema_invalid", "Unsupported product license schema")
    if not isinstance(signature, dict):
        return VerificationResult(False, "license_signature_required", "Product license must be signed", license_payload=payload)
    try:
        trusted = _trusted_public_key_b64(trusted_public_key_b64)
    except ValueError as exc:
        return VerificationResult(False, "trust_anchor_missing", str(exc), license_payload=payload)
    if not _signature_matches_trust_anchor(signature, trusted):
        return VerificationResult(False, "untrusted_signer", "Product license signer does not match the trusted Vishnu product key", license_payload=payload)
    if not verify_payload(canonical_json(payload), signature):
        return VerificationResult(False, "license_signature_invalid", "Product license signature is invalid", license_payload=payload)
    if str(payload.get("product_id")) != str(product_id):
        return VerificationResult(False, "product_mismatch", "License belongs to a different product", license_payload=payload)
    if client_name is not None and str(payload.get("client_name", "")).strip() != str(client_name).strip():
        return VerificationResult(False, "client_mismatch", "License belongs to a different client", license_payload=payload)

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    for field, too_early in (("starts_at", True), ("expires_at", False)):
        value = payload.get(field)
        if not value:
            continue
        try:
            boundary = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if boundary.tzinfo is None:
                boundary = boundary.replace(tzinfo=timezone.utc)
        except ValueError:
            return VerificationResult(False, "license_time_invalid", f"License {field} is invalid", license_payload=payload)
        if too_early and current < boundary:
            return VerificationResult(False, "license_not_started", "License is not active yet", license_payload=payload)
        if not too_early and current >= boundary:
            return VerificationResult(False, "license_expired", "License has expired", license_payload=payload)

    constraint = str(payload.get("version_constraint") or "*").strip()
    if version is not None and not _version_matches(str(version), constraint):
        return VerificationResult(False, "version_not_licensed", "This product version is not covered by the license", license_payload=payload)
    return VerificationResult(True, "verified", "Product license verified", license_payload=payload)


def _version_matches(version: str, constraint: str) -> bool:
    """Small fail-closed matcher for exact, wildcard, or major/minor x constraints."""
    constraint = constraint.strip()
    if constraint in {"", "*"}:
        return True
    if constraint == version:
        return True
    expected = constraint.split(".")
    actual = version.split(".")
    if len(expected) > len(actual):
        return False
    for index, segment in enumerate(expected):
        if segment.lower() in {"x", "*"}:
            return True
        if actual[index] != segment:
            return False
    return len(expected) == len(actual)
