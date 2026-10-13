from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path
from typing import Any


class CapabilityProvenanceError(PermissionError):
    pass


def _canonical(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


class CapabilityPackageProvenance:
    """Vault-keyed provenance for immutable generated capability packages.

    The signing key stays in Vishnu's existing credential vault.  The package
    receives only a HMAC signature and public key identifier, never the secret.
    Every declared source file, the manifest digest, and Forge build lineage are
    bound into the signed statement.  Unexpected package files fail closed.
    """

    VAULT_KEY = "capability-forge:provenance:hmac:v1"
    SIDECAR = "provenance.json"
    MAX_FILE_BYTES = 2_000_000
    MAX_FILES = 64

    def __init__(self, vault):
        if vault is None or not hasattr(vault, "get") or not hasattr(vault, "set"):
            raise ValueError("Capability Forge provenance requires Vishnu credential vault")
        self.vault = vault

    def _key(self) -> bytes:
        raw = self.vault.get(self.VAULT_KEY)
        if raw:
            try:
                key = base64.urlsafe_b64decode(str(raw).encode("ascii"))
            except Exception as exc:
                raise CapabilityProvenanceError("Capability Forge provenance key is invalid") from exc
            if len(key) < 32:
                raise CapabilityProvenanceError("Capability Forge provenance key is too short")
            return key
        key = secrets.token_bytes(32)
        self.vault.set(self.VAULT_KEY, base64.urlsafe_b64encode(key).decode("ascii"))
        return key

    @staticmethod
    def _inside(root: Path, candidate: Path) -> bool:
        root = root.resolve()
        candidate = candidate.resolve()
        return candidate == root or root in candidate.parents

    def _statement(self, package_path: str | Path, *, expected_manifest_digest: str | None = None) -> dict[str, Any]:
        root = Path(package_path).resolve()
        manifest_path = root / "manifest.json"
        raw = manifest_path.read_bytes()
        manifest_digest = hashlib.sha256(raw).hexdigest()
        if expected_manifest_digest is not None and not hmac.compare_digest(manifest_digest, str(expected_manifest_digest)):
            raise CapabilityProvenanceError("generated capability manifest digest mismatch")
        try:
            manifest = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise CapabilityProvenanceError("generated capability manifest is invalid") from exc
        if not isinstance(manifest, dict) or manifest.get("type") != "generated_capability":
            raise CapabilityProvenanceError("generated capability manifest is invalid")
        declared = tuple(str(x) for x in (manifest.get("source_files") or ()))
        if not declared or len(declared) > self.MAX_FILES or len(set(declared)) != len(declared):
            raise CapabilityProvenanceError("generated capability source manifest is invalid")
        file_hashes: dict[str, str] = {}
        for rel in sorted(declared):
            rel_path = Path(rel)
            if rel_path.is_absolute() or ".." in rel_path.parts or rel in {"manifest.json", self.SIDECAR}:
                raise CapabilityProvenanceError("generated capability source path is invalid")
            path = (root / rel_path).resolve()
            if not self._inside(root, path) or not path.is_file() or path.is_symlink():
                raise CapabilityProvenanceError("generated capability source file is missing or unsafe")
            data = path.read_bytes()
            if len(data) > self.MAX_FILE_BYTES:
                raise CapabilityProvenanceError("generated capability source exceeds provenance size limit")
            file_hashes[rel] = hashlib.sha256(data).hexdigest()
        allowed = set(declared) | {"manifest.json", self.SIDECAR}
        actual: set[str] = set()
        for path in root.rglob("*"):
            if path.is_symlink():
                raise CapabilityProvenanceError("generated capability package contains a symbolic link")
            if path.is_file():
                rel = path.relative_to(root).as_posix()
                actual.add(rel)
        unexpected = sorted(actual - allowed)
        if unexpected:
            raise CapabilityProvenanceError("generated capability package contains undeclared files")
        forge = dict(manifest.get("forge") or {})
        return {
            "schema_version": 1,
            "capability_id": str(manifest.get("id") or ""),
            "version": str(manifest.get("version") or ""),
            "manifest_digest": manifest_digest,
            "files": file_hashes,
            "lineage": {
                "spec_id": str(forge.get("spec_id") or ""),
                "plan_id": str(forge.get("plan_id") or ""),
                "work_order_id": str(forge.get("work_order_id") or ""),
                "attempt_id": str(forge.get("attempt_id") or ""),
                "candidate_revision": str(forge.get("candidate_revision") or ""),
                "qualification_digest": str(forge.get("qualification_digest") or ""),
                "build_id": str(forge.get("build_id") or ""),
            },
        }

    def sign(self, package_path: str | Path, *, expected_manifest_digest: str | None = None) -> dict[str, Any]:
        root = Path(package_path).resolve()
        # Ignore a previous valid sidecar while recomputing the statement.
        sidecar = root / self.SIDECAR
        statement = self._statement(root, expected_manifest_digest=expected_manifest_digest)
        key = self._key()
        signature = hmac.new(key, _canonical(statement), hashlib.sha256).hexdigest()
        record = {
            **statement,
            "algorithm": "HMAC-SHA256",
            "key_id": hashlib.sha256(key).hexdigest()[:24],
            "signature": signature,
        }
        sidecar.write_bytes(_canonical(record))
        try:
            os.chmod(sidecar, 0o600)
        except OSError:
            pass
        return {k: v for k, v in record.items() if k != "files"} | {"file_count": len(statement["files"])}

    def verify(self, package_path: str | Path, *, expected_manifest_digest: str | None = None) -> dict[str, Any]:
        root = Path(package_path).resolve()
        sidecar = root / self.SIDECAR
        if not sidecar.is_file() or sidecar.is_symlink():
            raise CapabilityProvenanceError("generated capability provenance is missing")
        try:
            record = json.loads(sidecar.read_text(encoding="utf-8"))
        except Exception as exc:
            raise CapabilityProvenanceError("generated capability provenance is invalid") from exc
        if not isinstance(record, dict) or record.get("algorithm") != "HMAC-SHA256":
            raise CapabilityProvenanceError("generated capability provenance algorithm is invalid")
        signature = str(record.get("signature") or "")
        statement = {k: v for k, v in record.items() if k not in {"algorithm", "key_id", "signature"}}
        current = self._statement(root, expected_manifest_digest=expected_manifest_digest)
        if statement != current:
            raise CapabilityProvenanceError("generated capability package changed after provenance signing")
        key = self._key()
        expected_key_id = hashlib.sha256(key).hexdigest()[:24]
        if not hmac.compare_digest(str(record.get("key_id") or ""), expected_key_id):
            raise CapabilityProvenanceError("generated capability provenance key binding mismatch")
        expected = hmac.new(key, _canonical(statement), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise CapabilityProvenanceError("generated capability provenance signature mismatch")
        return {
            "verified": True,
            "capability_id": current["capability_id"],
            "version": current["version"],
            "manifest_digest": current["manifest_digest"],
            "key_id": expected_key_id,
            "file_count": len(current["files"]),
            "lineage": dict(current["lineage"]),
        }
