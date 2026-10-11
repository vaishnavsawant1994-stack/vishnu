from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import os
import platform
import re
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


TARGETS = ("android", "ios", "windows", "macos", "linux", "docker")
SCOPES = ("server", "compiler", "worker")
_RUNNER_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


@dataclass(frozen=True)
class Check:
    id: str
    ok: bool
    required: bool
    detail: str


class PreflightError(ValueError):
    pass


def _configured(env: dict[str, str], name: str) -> bool:
    return bool(str(env.get(name, "")).strip())


def _b64_raw(env: dict[str, str], name: str, length: int | None = None) -> bytes | None:
    raw = str(env.get(name, "")).strip()
    if not raw:
        return None
    try:
        value = base64.b64decode(raw, validate=True)
    except Exception:
        return b""
    if length is not None and len(value) != length:
        return b""
    return value


def _file(env: dict[str, str], name: str) -> Path | None:
    value = str(env.get(name, "")).strip()
    if not value:
        return None
    return Path(value).expanduser()


def _tool(which, *names: str) -> bool:
    return any(bool(which(name)) for name in names)


def _tool_check(checks: list[Check], which, check_id: str, *names: str) -> None:
    label = "/".join(names)
    checks.append(Check(check_id, _tool(which, *names), True, f"{label} {'available' if _tool(which, *names) else 'missing'}"))


def _env_check(checks: list[Check], env: dict[str, str], check_id: str, name: str) -> None:
    ok = _configured(env, name)
    checks.append(Check(check_id, ok, True, f"{name} {'configured' if ok else 'missing'}"))


def _public_key_check(checks: list[Check], env: dict[str, str]) -> None:
    value = _b64_raw(env, "VISHNU_PRODUCT_SIGNING_PUBLIC_KEY_B64", 32)
    checks.append(
        Check(
            "product_signing_public_key",
            value not in {None, b""},
            True,
            "product signing public key configured as a valid raw Ed25519 key" if value not in {None, b""} else "product signing public key missing or invalid",
        )
    )


def _server_checks(env: dict[str, str]) -> list[Check]:
    checks: list[Check] = []
    public = _b64_raw(env, "VISHNU_PRODUCT_SIGNING_PUBLIC_KEY_B64", 32)
    private = _b64_raw(env, "VISHNU_PRODUCT_SIGNING_PRIVATE_KEY_B64", 32)
    checks.append(Check("product_signing_public_key", public not in {None, b""}, True, "public key valid" if public not in {None, b""} else "public key missing or invalid"))
    checks.append(Check("product_signing_private_key", private not in {None, b""}, True, "private key valid" if private not in {None, b""} else "private key missing or invalid"))
    pair_ok = False
    if public not in {None, b""} and private not in {None, b""}:
        try:
            derived = Ed25519PrivateKey.from_private_bytes(private).public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
            pair_ok = derived == public
        except Exception:
            pair_ok = False
    checks.append(Check("product_signing_key_pair", pair_ok, True, "public/private signing keys match" if pair_ok else "public/private signing keys do not form a valid pair"))

    token = str(env.get("VISHNU_PRODUCT_RUNNER_TOKEN", "")).strip()
    checks.append(Check("runner_bearer_token", len(token) >= 32, True, "runner bearer token length is acceptable" if len(token) >= 32 else "runner bearer token must contain at least 32 characters"))

    max_bytes = str(env.get("VISHNU_PRODUCT_RUNNER_MAX_ARTIFACT_BYTES", "536870912")).strip()
    try:
        parsed_max = int(max_bytes)
        max_ok = 1024 * 1024 <= parsed_max <= 4 * 1024 * 1024 * 1024
    except ValueError:
        max_ok = False
    checks.append(Check("artifact_byte_limit", max_ok, True, "artifact byte limit is valid" if max_ok else "artifact byte limit must be 1 MiB..4 GiB"))

    lease = str(env.get("VISHNU_PRODUCT_RUNNER_LEASE_SECONDS", "900")).strip()
    try:
        parsed_lease = int(lease)
        lease_ok = 60 <= parsed_lease <= 7200
    except ValueError:
        lease_ok = False
    checks.append(Check("runner_lease_duration", lease_ok, True, "runner lease duration is valid" if lease_ok else "runner lease duration must be 60..7200 seconds"))
    return checks


def _transport_checks(env: dict[str, str]) -> list[Check]:
    checks: list[Check] = []
    token = str(env.get("VISHNU_PRODUCT_RUNNER_TOKEN", "")).strip()
    checks.append(Check("runner_bearer_token", len(token) >= 32, True, "runner bearer token length is acceptable" if len(token) >= 32 else "runner bearer token must contain at least 32 characters"))
    runner_id = str(env.get("VISHNU_PRODUCT_RUNNER_ID", "")).strip()
    checks.append(Check("runner_id", bool(_RUNNER_ID.fullmatch(runner_id)), True, "runner ID is valid" if _RUNNER_ID.fullmatch(runner_id) else "runner ID is missing or invalid"))
    raw_url = str(env.get("VISHNU_PRODUCT_RUNNER_BASE_URL", "")).strip().rstrip("/")
    parsed = urlparse(raw_url) if raw_url else None
    local = bool(parsed and parsed.hostname in {"127.0.0.1", "localhost", "::1"})
    url_ok = bool(parsed and parsed.netloc and (parsed.scheme == "https" or (parsed.scheme == "http" and local)))
    checks.append(Check("runner_server_url", url_ok, True, "runner server URL uses an accepted transport" if url_ok else "runner server URL must use HTTPS (localhost HTTP only for development)"))
    return checks


def _compiler_checks(
    target: str,
    env: dict[str, str],
    *,
    host_os: str,
    which=shutil.which,
    module_finder=importlib.util.find_spec,
) -> list[Check]:
    checks: list[Check] = []
    _public_key_check(checks, env)
    host = str(host_os or "").strip().lower()

    if target == "android":
        checks.append(Check("host_os", host in {"linux", "darwin", "windows"}, True, "supported Android build host" if host in {"linux", "darwin", "windows"} else "unsupported Android build host"))
        _tool_check(checks, which, "gradle", "gradle")
        _tool_check(checks, which, "java", "java")
        apksigner_ok = _tool(which, "apksigner")
        if not apksigner_ok:
            sdk = str(env.get("ANDROID_HOME") or env.get("ANDROID_SDK_ROOT") or "").strip()
            if sdk:
                root = Path(sdk) / "build-tools"
                apksigner_ok = root.exists() and any(root.glob("*/apksigner*"))
        checks.append(Check("apksigner", apksigner_ok, True, "apksigner available" if apksigner_ok else "apksigner missing"))
        path = _file(env, "VISHNU_ANDROID_KEYSTORE_PATH")
        checks.append(Check("android_keystore", bool(path and path.is_file()), True, "Android keystore file available" if path and path.is_file() else "Android keystore file missing"))
        for name in ("VISHNU_ANDROID_KEY_ALIAS", "VISHNU_ANDROID_KEYSTORE_PASSWORD", "VISHNU_ANDROID_KEY_PASSWORD"):
            _env_check(checks, env, name.lower(), name)

    elif target == "windows":
        checks.append(Check("host_os", host == "windows", True, "Windows host" if host == "windows" else "Windows compiler requires a Windows host"))
        pyinstaller_ok = bool(module_finder("PyInstaller"))
        checks.append(Check("pyinstaller", pyinstaller_ok, True, "PyInstaller import available" if pyinstaller_ok else "PyInstaller missing"))
        _tool_check(checks, which, "signtool", "signtool", "signtool.exe")
        cert_path = _file(env, "VISHNU_WINDOWS_SIGNING_CERT_PATH")
        cert_b64 = _b64_raw(env, "VISHNU_WINDOWS_SIGNING_CERT_B64")
        cert_ok = bool((cert_path and cert_path.is_file()) or (cert_b64 not in {None, b""}))
        checks.append(Check("windows_signing_certificate", cert_ok, True, "Windows signing certificate configured" if cert_ok else "Windows signing certificate missing or invalid"))
        _env_check(checks, env, "windows_signing_password", "VISHNU_WINDOWS_SIGNING_PASSWORD")

    elif target == "docker":
        checks.append(Check("host_os", host in {"linux", "darwin", "windows"}, True, "supported Docker build host" if host in {"linux", "darwin", "windows"} else "unsupported Docker build host"))
        _tool_check(checks, which, "docker", "docker")
        _tool_check(checks, which, "cosign", "cosign")
        key = _file(env, "VISHNU_DOCKER_COSIGN_KEY")
        key_ok = bool(key and key.is_file())
        checks.append(Check("docker_cosign_key", key_ok, True, "cosign key file available" if key_ok else "cosign key file missing"))

    elif target == "macos":
        checks.append(Check("host_os", host == "darwin", True, "macOS host" if host == "darwin" else "macOS compiler requires a macOS host"))
        for check_id, names in (("xcrun", ("xcrun",)), ("swiftc", ("swiftc",)), ("hdiutil", ("hdiutil",)), ("codesign", ("codesign",))):
            _tool_check(checks, which, check_id, *names)
        _env_check(checks, env, "macos_signing_identity", "VISHNU_MACOS_SIGNING_IDENTITY")
        _env_check(checks, env, "macos_notary_profile", "VISHNU_MACOS_NOTARY_KEYCHAIN_PROFILE")

    elif target == "ios":
        checks.append(Check("host_os", host == "darwin", True, "macOS host" if host == "darwin" else "iOS compiler requires a macOS host"))
        for check_id, names in (("xcrun", ("xcrun",)), ("security", ("security",)), ("codesign", ("codesign",))):
            _tool_check(checks, which, check_id, *names)
        _env_check(checks, env, "ios_signing_identity", "VISHNU_IOS_SIGNING_IDENTITY")
        profile = _file(env, "VISHNU_IOS_PROVISIONING_PROFILE")
        checks.append(Check("ios_provisioning_profile", bool(profile and profile.is_file()), True, "iOS provisioning profile available" if profile and profile.is_file() else "iOS provisioning profile missing"))

    elif target == "linux":
        checks.append(Check("host_os", host == "linux", True, "Linux host" if host == "linux" else "Linux compiler requires a Linux host"))
        pyinstaller_ok = bool(module_finder("PyInstaller"))
        checks.append(Check("pyinstaller", pyinstaller_ok, True, "PyInstaller import available" if pyinstaller_ok else "PyInstaller missing"))
        _tool_check(checks, which, "dpkg_deb", "dpkg-deb")
    else:
        raise PreflightError(f"Unsupported product target: {target}")
    return checks


def preflight(
    *,
    scope: str,
    target: str | None = None,
    env: dict[str, str] | None = None,
    host_os: str | None = None,
    which=shutil.which,
    module_finder=importlib.util.find_spec,
) -> dict:
    scope = str(scope or "").strip().lower()
    if scope not in SCOPES:
        raise PreflightError(f"Unsupported preflight scope: {scope}")
    env = dict(os.environ if env is None else env)
    host_os = str(host_os or platform.system()).strip()
    checks: list[Check] = []
    normalized_target = str(target or "").strip().lower() or None
    if scope == "server":
        if normalized_target is not None:
            raise PreflightError("Server preflight does not accept a target")
        checks.extend(_server_checks(env))
    else:
        if normalized_target not in TARGETS:
            raise PreflightError("Compiler and worker preflight require a supported target")
        if scope == "worker":
            checks.extend(_transport_checks(env))
        checks.extend(
            _compiler_checks(
                normalized_target,
                env,
                host_os=host_os,
                which=which,
                module_finder=module_finder,
            )
        )
    ready = all(item.ok for item in checks if item.required)
    return {
        "schema": "vishnu.product-production-preflight/v1",
        "scope": scope,
        "target": normalized_target,
        "host_os": host_os.lower(),
        "ready": ready,
        "checks": [asdict(item) for item in checks],
        "secret_values_exposed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Preflight Vishnu production product distribution authority")
    parser.add_argument("--scope", choices=SCOPES, required=True)
    parser.add_argument("--target", choices=TARGETS)
    parser.add_argument("--require-ready", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = preflight(scope=args.scope, target=args.target)
    except PreflightError as exc:
        parser.error(str(exc))
    raw = json.dumps(result, sort_keys=True, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(raw + "\n", encoding="utf-8")
    print(raw)
    if args.require_ready and not result["ready"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
