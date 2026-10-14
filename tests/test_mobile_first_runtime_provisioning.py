from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def _blueprint_service() -> dict:
    payload = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
    services = payload.get("services") or []
    assert len(services) == 1
    return services[0]


def test_render_blueprint_is_persistent_fail_closed_and_manual_deploy() -> None:
    service = _blueprint_service()
    assert service["type"] == "web"
    assert service["runtime"] == "python"
    assert service["autoDeployTrigger"] == "off"
    assert service["startCommand"] == "python -m server.hosted_runtime"
    assert service["healthCheckPath"] == "/hosted-health"
    assert service["disk"]["mountPath"] == "/var/data"
    assert int(service["disk"]["sizeGB"]) >= 5

    env = {entry["key"]: entry for entry in service["envVars"]}
    assert env["PERSONAL_AI_DATA_DIR"]["value"] == "/var/data/vishnu"
    assert env["PERSONAL_AI_STRICT_CONFIG"]["value"] == "true"
    assert env["PERSONAL_AI_TRUST_PROXY_HEADERS"]["value"] == "true"
    assert env["PERSONAL_AI_OWNER_BOOTSTRAP_SECRET"]["sync"] is False
    assert "value" not in env["PERSONAL_AI_OWNER_BOOTSTRAP_SECRET"]
    assert env["PERSONAL_AI_VAULT_PASSWORD"]["generateValue"] is True


def test_hosted_runtime_reuses_canonical_runtime_and_waits_for_owner_setup() -> None:
    source = (ROOT / "server" / "hosted_runtime.py").read_text(encoding="utf-8")
    assert "build_runtime()" in source
    assert "FirstRunCoordinator.apply_pending_restore" in source
    assert "FirstRunCoordinator(settings.data_dir, runtime=runtime)" in source
    assert 'runtime["setup_surface"] = "hosted"' in source
    assert "if not setup.ready:" in source
    assert "start_e9_services(runtime)" in source
    assert "composition.work.automation_engine.start()" in source
    assert 'host="0.0.0.0"' in source
    assert 'os.environ.get("PORT", "8000")' in source


def test_mobile_runtime_bootstrap_secret_is_device_generated_and_never_in_deploy_url() -> None:
    android = (ROOT / "android-companion" / "app" / "src" / "main" / "java" / "ai" / "personal" / "companion" / "RuntimeProvisioningActivity.kt").read_text(encoding="utf-8")
    ios = (ROOT / "ios-companion" / "PersonalAICompanion" / "RuntimeProvisioningView.swift").read_text(encoding="utf-8")

    assert "SecureRandom" in android
    assert "EncryptedSharedPreferences" in android
    assert 'appendQueryParameter("repo", "https://github.com/vaishnavsawant1994-stack/vishnu")' in android
    assert "appendQueryParameter(\"bootstrap" not in android
    assert "PERSONAL_AI_OWNER_BOOTSTRAP_SECRET" in android

    assert "SecRandomCopyBytes" in ios
    assert "KeychainStore.shared.set" in ios
    assert 'URLQueryItem(name: "repo", value: "https://github.com/vaishnavsawant1994-stack/vishnu")' in ios
    assert 'URLQueryItem(name: "bootstrap' not in ios
    assert "PERSONAL_AI_OWNER_BOOTSTRAP_SECRET" in ios


def test_no_laptop_runtime_provisioning_is_reachable_from_android_and_ios_onboarding() -> None:
    android_app = (ROOT / "android-companion" / "app" / "src" / "main" / "java" / "ai" / "personal" / "companion" / "VishnuApplication.kt").read_text(encoding="utf-8")
    android_manifest = (ROOT / "android-companion" / "app" / "src" / "main" / "AndroidManifest.xml").read_text(encoding="utf-8")
    ios_app = (ROOT / "ios-companion" / "PersonalAICompanion" / "PersonalAICompanionApp.swift").read_text(encoding="utf-8")

    assert "attachRuntimeProvisioningButton(activity)" in android_app
    assert "RuntimeProvisioningActivity::class.java" in android_app
    assert '.RuntimeProvisioningActivity' in android_manifest
    assert "showRuntimeProvisioning = true" in ios_app
    assert "RuntimeProvisioningView()" in ios_app
