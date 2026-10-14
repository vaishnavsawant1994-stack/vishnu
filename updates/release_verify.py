from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

if __package__:
    from .build_reproducibility_evidence import validate_evidence
else:
    from build_reproducibility_evidence import validate_evidence

_ALLOWED_CHANNELS = {"stable", "beta", "dev"}
_ALLOWED_PLATFORMS = {"windows", "macos", "linux"}
_ALLOWED_ARCHITECTURES = {"x86_64", "arm64"}
_ALLOWED_PACKAGE_TYPES = {"msi", "dmg", "deb", "zip"}
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize_architecture(value: str) -> str:
    arch = value.strip().lower()
    if arch in {"x64", "amd64", "x86_64"}:
        return "x86_64"
    if arch in {"arm64", "aarch64"}:
        return "arm64"
    raise ValueError(f"unsupported release architecture: {value}")


def validate_manifest(manifest: object) -> dict:
    if not isinstance(manifest, dict) or manifest.get("schema") != 2:
        raise ValueError("release manifest schema 2 is required")
    version = manifest.get("version")
    source_commit = manifest.get("source_commit")
    channel = manifest.get("channel")
    artifacts = manifest.get("artifacts")
    if not isinstance(version, str) or not version.strip():
        raise ValueError("release manifest version is invalid")
    if not isinstance(source_commit, str) or not _COMMIT_RE.fullmatch(source_commit):
        raise ValueError("release manifest source commit is invalid")
    if channel not in _ALLOWED_CHANNELS:
        raise ValueError("release manifest channel is invalid")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("release manifest must contain artifacts")

    names: set[str] = set()
    identities: set[tuple[str, str, str]] = set()
    for item in artifacts:
        if not isinstance(item, dict):
            raise ValueError("release manifest artifact is invalid")
        name = item.get("name")
        digest = item.get("sha256")
        size = item.get("size")
        platform_name = item.get("platform")
        architecture = item.get("architecture")
        package_type = item.get("package_type")
        if not isinstance(name, str) or not name or Path(name).name != name:
            raise ValueError("release artifact name is unsafe")
        if name in names:
            raise ValueError(f"duplicate release artifact name: {name}")
        names.add(name)
        if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
            raise ValueError(f"invalid sha256 for {name}")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise ValueError(f"invalid size for {name}")
        if platform_name not in _ALLOWED_PLATFORMS:
            raise ValueError(f"invalid platform for {name}")
        if architecture not in _ALLOWED_ARCHITECTURES:
            raise ValueError(f"invalid architecture for {name}")
        if package_type not in _ALLOWED_PACKAGE_TYPES:
            raise ValueError(f"invalid package type for {name}")
        if Path(name).suffix.lower() != f".{package_type}":
            raise ValueError(f"package type does not match filename for {name}")
        identity = (platform_name, architecture, package_type)
        if identity in identities:
            raise ValueError(f"duplicate release artifact identity: {identity}")
        identities.add(identity)
    if "reproducibility" in manifest:
        validate_evidence(
            manifest["reproducibility"],
            expected_source_sha=source_commit.lower(),
            expected_artifacts=artifacts,
        )
    return manifest


def select_artifact(
    manifest: dict,
    *,
    platform_name: str,
    architecture: str,
    package_type: str | None = None,
) -> dict:
    architecture = normalize_architecture(architecture)
    candidates = [
        item
        for item in manifest["artifacts"]
        if item["platform"] == platform_name
        and item["architecture"] == architecture
        and (package_type is None or item["package_type"] == package_type)
    ]
    if len(candidates) != 1:
        raise ValueError(
            f"expected exactly one release artifact for {platform_name}/{architecture}"
            + (f"/{package_type}" if package_type else "")
            + f", found {len(candidates)}"
        )
    return candidates[0]


def verify(
    manifest_path,
    signature_path,
    public_key_b64,
    artifact_dir=None,
    *,
    expected_version: str | None = None,
    expected_source_commit: str | None = None,
    expected_channel: str | None = None,
    expected_platform: str | None = None,
    expected_architecture: str | None = None,
):
    manifest_path = Path(manifest_path)
    signature_path = Path(signature_path)
    raw = manifest_path.read_bytes()
    try:
        signature = base64.b64decode(signature_path.read_text(encoding="utf-8").strip(), validate=True)
        public_key = base64.b64decode(public_key_b64, validate=True)
        key = Ed25519PublicKey.from_public_bytes(public_key)
        key.verify(signature, raw)
    except Exception as exc:
        raise ValueError("release manifest signature invalid") from exc

    manifest = validate_manifest(json.loads(raw))
    if expected_version is not None and manifest["version"] != expected_version:
        raise ValueError("release manifest version does not match expected version")
    if expected_source_commit is not None and manifest["source_commit"] != expected_source_commit.lower():
        raise ValueError("release manifest source commit does not match expected commit")
    if expected_channel is not None and manifest["channel"] != expected_channel:
        raise ValueError("release manifest channel does not match expected channel")
    if (expected_platform is None) != (expected_architecture is None):
        raise ValueError("expected platform and architecture must be provided together")
    if expected_platform is not None and expected_architecture is not None:
        select_artifact(
            manifest,
            platform_name=expected_platform,
            architecture=expected_architecture,
        )

    root = Path(artifact_dir) if artifact_dir else manifest_path.parent
    for item in manifest["artifacts"]:
        path = root / item["name"]
        if not path.is_file():
            raise FileNotFoundError(path)
        if path.stat().st_size != item["size"]:
            raise ValueError(f"size mismatch for {path.name}")
        if sha256(path) != item["sha256"].lower():
            raise ValueError(f"sha256 mismatch for {path.name}")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--signature", required=True)
    parser.add_argument("--public-key-b64", required=True)
    parser.add_argument("--artifact-dir")
    parser.add_argument("--expected-version")
    parser.add_argument("--expected-source-commit")
    parser.add_argument("--expected-channel", choices=sorted(_ALLOWED_CHANNELS))
    parser.add_argument("--expected-platform", choices=sorted(_ALLOWED_PLATFORMS))
    parser.add_argument("--expected-architecture")
    args = parser.parse_args()
    manifest = verify(
        args.manifest,
        args.signature,
        args.public_key_b64,
        args.artifact_dir,
        expected_version=args.expected_version,
        expected_source_commit=args.expected_source_commit,
        expected_channel=args.expected_channel,
        expected_platform=args.expected_platform,
        expected_architecture=args.expected_architecture,
    )
    print(
        json.dumps(
            {
                "ok": True,
                "schema": manifest["schema"],
                "version": manifest["version"],
                "source_commit": manifest["source_commit"],
                "channel": manifest["channel"],
                "artifacts": len(manifest["artifacts"]),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
