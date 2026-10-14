from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

if __package__:
    from .build_reproducibility_evidence import validate_evidence
else:
    from build_reproducibility_evidence import validate_evidence

_ALLOWED_CHANNELS = {"stable", "beta", "dev"}
_PLATFORM_PACKAGE = {"windows": "msi", "macos": "dmg", "linux": "deb"}
_ARTIFACT_RE = re.compile(
    r"-(windows|macos|linux)-(x64|x86_64|amd64|arm64|aarch64)\.(msi|dmg|deb|zip)$",
    re.IGNORECASE,
)
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)


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


def artifact_metadata(path: Path) -> dict:
    match = _ARTIFACT_RE.search(path.name)
    if not match:
        raise ValueError(
            f"release artifact name must end with -<platform>-<architecture>.<type>: {path.name}"
        )
    platform_name, architecture, package_type = match.groups()
    platform_name = platform_name.lower()
    package_type = package_type.lower()
    if package_type != "zip" and _PLATFORM_PACKAGE.get(platform_name) != package_type:
        raise ValueError(f"package type {package_type} is invalid for {platform_name}")
    return {
        "name": path.name,
        "sha256": sha256(path),
        "size": path.stat().st_size,
        "platform": platform_name,
        "architecture": normalize_architecture(architecture),
        "package_type": package_type,
    }


def build_manifest(
    *,
    version: str,
    source_commit: str,
    channel: str,
    artifacts: list[Path],
    provenance: dict | None = None,
) -> dict:
    source_commit = source_commit.strip().lower()
    channel = channel.strip().lower()
    if not version.strip():
        raise ValueError("release version is required")
    if not _COMMIT_RE.fullmatch(source_commit):
        raise ValueError("source commit must be an exact 40-character Git SHA")
    if channel not in _ALLOWED_CHANNELS:
        raise ValueError(f"release channel must be one of {sorted(_ALLOWED_CHANNELS)}")
    if not artifacts or any(not artifact.is_file() for artifact in artifacts):
        raise ValueError("all release artifacts must exist before signing")

    entries = [artifact_metadata(artifact) for artifact in artifacts]
    names = [entry["name"] for entry in entries]
    if len(set(names)) != len(names):
        raise ValueError("release artifact names must be unique")
    identities = [
        (entry["platform"], entry["architecture"], entry["package_type"])
        for entry in entries
    ]
    if len(set(identities)) != len(identities):
        raise ValueError("release artifact platform/architecture/package identities must be unique")

    manifest = {
        "schema": 2,
        "version": version.strip(),
        "source_commit": source_commit,
        "channel": channel,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "artifacts": sorted(entries, key=lambda entry: entry["name"]),
    }
    if provenance is not None:
        manifest["reproducibility"] = validate_evidence(
            provenance,
            expected_source_sha=source_commit,
            expected_artifacts=entries,
        )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--channel", required=True, choices=sorted(_ALLOWED_CHANNELS))
    parser.add_argument("--output", required=True)
    parser.add_argument("--provenance-json")
    parser.add_argument("artifacts", nargs="+")
    args = parser.parse_args()

    key_b64 = os.environ.get("PERSONAL_AI_RELEASE_PRIVATE_KEY_B64", "").strip()
    if not key_b64:
        raise SystemExit("PERSONAL_AI_RELEASE_PRIVATE_KEY_B64 is required")
    try:
        raw_key = base64.b64decode(key_b64, validate=True)
    except Exception as exc:
        raise SystemExit("release signing key must be valid base64") from exc
    if len(raw_key) != 32:
        raise SystemExit("release signing key must decode to exactly 32 bytes")

    try:
        manifest = build_manifest(
            version=args.version,
            source_commit=args.source_commit,
            channel=args.channel,
            artifacts=[Path(value) for value in args.artifacts],
            provenance=(
                json.loads(Path(args.provenance_json).read_text(encoding="utf-8"))
                if args.provenance_json
                else None
            ),
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    raw = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(raw)
    key = Ed25519PrivateKey.from_private_bytes(raw_key)
    output.with_suffix(output.suffix + ".sig").write_text(
        base64.b64encode(key.sign(raw)).decode(), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
