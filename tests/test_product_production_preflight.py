from __future__ import annotations

import base64
import importlib.util
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


ROOT = Path(__file__).resolve().parents[1]


def module():
    spec = importlib.util.spec_from_file_location(
        "vishnu_test_product_production_preflight",
        ROOT / "packaging" / "product_production_preflight.py",
    )
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def signing_env():
    key = Ed25519PrivateKey.generate()
    private_raw = key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_raw = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return {
        "VISHNU_PRODUCT_SIGNING_PRIVATE_KEY_B64": base64.b64encode(private_raw).decode(),
        "VISHNU_PRODUCT_SIGNING_PUBLIC_KEY_B64": base64.b64encode(public_raw).decode(),
    }


def fake_which(name):
    return f"/qualification/{name}"


def fake_module_finder(name):
    return object() if name == "PyInstaller" else None


def test_server_preflight_accepts_valid_matching_signing_authority():
    preflight = module()
    env = signing_env()
    env.update(
        {
            "VISHNU_PRODUCT_RUNNER_TOKEN": "r" * 48,
            "VISHNU_PRODUCT_RUNNER_MAX_ARTIFACT_BYTES": str(512 * 1024 * 1024),
            "VISHNU_PRODUCT_RUNNER_LEASE_SECONDS": "900",
        }
    )
    result = preflight.preflight(scope="server", env=env, host_os="Linux")
    assert result["ready"] is True
    assert result["target"] is None
    assert result["secret_values_exposed"] is False
    assert all(item["ok"] for item in result["checks"])
    serialized = str(result)
    assert env["VISHNU_PRODUCT_RUNNER_TOKEN"] not in serialized
    assert env["VISHNU_PRODUCT_SIGNING_PRIVATE_KEY_B64"] not in serialized


def test_server_preflight_rejects_mismatched_key_pair():
    preflight = module()
    env = signing_env()
    other = signing_env()
    env["VISHNU_PRODUCT_SIGNING_PUBLIC_KEY_B64"] = other["VISHNU_PRODUCT_SIGNING_PUBLIC_KEY_B64"]
    env["VISHNU_PRODUCT_RUNNER_TOKEN"] = "r" * 48
    result = preflight.preflight(scope="server", env=env, host_os="Linux")
    assert result["ready"] is False
    pair = next(item for item in result["checks"] if item["id"] == "product_signing_key_pair")
    assert pair["ok"] is False


def test_worker_preflight_requires_https_transport_and_safe_runner_id():
    preflight = module()
    env = signing_env()
    env.update(
        {
            "VISHNU_PRODUCT_RUNNER_TOKEN": "r" * 48,
            "VISHNU_PRODUCT_RUNNER_BASE_URL": "http://production.example.com",
            "VISHNU_PRODUCT_RUNNER_ID": "linux-runner-1",
        }
    )
    result = preflight.preflight(
        scope="worker",
        target="linux",
        env=env,
        host_os="Linux",
        which=fake_which,
        module_finder=fake_module_finder,
    )
    assert result["ready"] is False
    transport = next(item for item in result["checks"] if item["id"] == "runner_server_url")
    assert transport["ok"] is False

    env["VISHNU_PRODUCT_RUNNER_BASE_URL"] = "https://production.example.com"
    result = preflight.preflight(
        scope="worker",
        target="linux",
        env=env,
        host_os="Linux",
        which=fake_which,
        module_finder=fake_module_finder,
    )
    assert result["ready"] is True


def test_android_compiler_preflight_requires_real_keystore_file(tmp_path):
    preflight = module()
    env = signing_env()
    env.update(
        {
            "VISHNU_ANDROID_KEYSTORE_PATH": str(tmp_path / "missing.jks"),
            "VISHNU_ANDROID_KEY_ALIAS": "client",
            "VISHNU_ANDROID_KEYSTORE_PASSWORD": "secret",
            "VISHNU_ANDROID_KEY_PASSWORD": "secret",
        }
    )
    result = preflight.preflight(
        scope="compiler",
        target="android",
        env=env,
        host_os="Linux",
        which=fake_which,
        module_finder=fake_module_finder,
    )
    assert result["ready"] is False
    keystore = next(item for item in result["checks"] if item["id"] == "android_keystore")
    assert keystore["ok"] is False

    path = tmp_path / "client.jks"
    path.write_bytes(b"qualification-keystore-placeholder")
    env["VISHNU_ANDROID_KEYSTORE_PATH"] = str(path)
    result = preflight.preflight(
        scope="compiler",
        target="android",
        env=env,
        host_os="Linux",
        which=fake_which,
        module_finder=fake_module_finder,
    )
    assert result["ready"] is True


def test_docker_compiler_preflight_requires_cosign_key_file(tmp_path):
    preflight = module()
    env = signing_env()
    env["VISHNU_DOCKER_COSIGN_KEY"] = str(tmp_path / "missing.key")
    result = preflight.preflight(
        scope="compiler",
        target="docker",
        env=env,
        host_os="Linux",
        which=fake_which,
        module_finder=fake_module_finder,
    )
    assert result["ready"] is False

    key = tmp_path / "cosign.key"
    key.write_text("encrypted-key-placeholder")
    env["VISHNU_DOCKER_COSIGN_KEY"] = str(key)
    result = preflight.preflight(
        scope="compiler",
        target="docker",
        env=env,
        host_os="Linux",
        which=fake_which,
        module_finder=fake_module_finder,
    )
    assert result["ready"] is True


def test_ios_compiler_preflight_requires_macos_profile_and_identity(tmp_path):
    preflight = module()
    env = signing_env()
    profile = tmp_path / "client.mobileprovision"
    profile.write_bytes(b"profile")
    env.update(
        {
            "VISHNU_IOS_SIGNING_IDENTITY": "Apple Distribution: Example",
            "VISHNU_IOS_PROVISIONING_PROFILE": str(profile),
        }
    )
    result = preflight.preflight(
        scope="compiler",
        target="ios",
        env=env,
        host_os="Darwin",
        which=fake_which,
        module_finder=fake_module_finder,
    )
    assert result["ready"] is True

    wrong_host = preflight.preflight(
        scope="compiler",
        target="ios",
        env=env,
        host_os="Linux",
        which=fake_which,
        module_finder=fake_module_finder,
    )
    assert wrong_host["ready"] is False


def test_linux_compiler_preflight_does_not_require_target_signing_secret():
    preflight = module()
    env = signing_env()
    result = preflight.preflight(
        scope="compiler",
        target="linux",
        env=env,
        host_os="Linux",
        which=fake_which,
        module_finder=fake_module_finder,
    )
    assert result["ready"] is True
