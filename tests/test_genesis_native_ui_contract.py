from pathlib import Path
import hashlib


ROOT = Path(__file__).resolve().parents[1]


def test_genesis_native_clients_share_canonical_art_assets_and_palette() -> None:
    shared_assets = (
        ROOT / "pwa/assets/genesis/vishnu-core.png",
        ROOT / "android-companion/app/src/main/res/drawable-nodpi/vishnu_genesis_core.png",
        ROOT / "ios-companion/PersonalAICompanion/vishnu-genesis-core.png",
        ROOT / "pwa/assets/genesis/cosmic-mobile.png",
        ROOT / "android-companion/app/src/main/res/drawable-nodpi/vishnu_genesis_cosmic_mobile.png",
        ROOT / "ios-companion/PersonalAICompanion/vishnu-genesis-cosmic-mobile.png",
    )
    core_hashes = {hashlib.sha256(path.read_bytes()).hexdigest() for path in shared_assets[:3]}
    mobile_background_hashes = {hashlib.sha256(path.read_bytes()).hexdigest() for path in shared_assets[3:]}
    assert len(core_hashes) == 1, "web, Android, and iOS must package the exact same core image"
    assert len(mobile_background_hashes) == 1, "web, Android, and iOS must package the exact same mobile background"

    pwa = (ROOT / "pwa/genesis.css").read_text(encoding="utf-8")
    desktop = (ROOT / "ui/design_tokens.py").read_text(encoding="utf-8")
    android = (ROOT / "android-companion/app/src/main/java/ai/personal/companion/PersonalAITheme.kt").read_text(encoding="utf-8")
    ios = (ROOT / "ios-companion/PersonalAICompanion/PersonalAITheme.swift").read_text(encoding="utf-8")
    assert "--genesis-bg: #02060b" in pwa and '"background": "#02060B"' in desktop
    assert "0xFF20B8FF" in android and "red: 32/255, green: 184/255" in ios
    assert "0xFF4DDCFF" in android and "red: 77/255, green: 220/255" in ios


def test_desktop_uses_canonical_genesis_design_and_four_create_steps() -> None:
    wizard = (ROOT / "ui/first_run_wizard.py").read_text(encoding="utf-8")
    for page in (
        "_welcome_page()", "_owner_page()", "_security_choice_page()", "_security_page()",
        "_recovery_page()", "_device_page()", "_data_page()", "_model_page()",
        "_privacy_page()", "_review_page()",
    ):
        assert f"self.stack.addWidget(self.{page})" in wizard
    assert "Step {step} of 4" in wizard
    assert "self.coordinator.ensure_first_device(device_name)" in wizard
    assert "form.addRow('First trusted device', self.device_name)" in wizard
    assert "Secure Vishnu  →" in wizard
    assert "default_policy='device_only'" in wizard
    assert "class VishnuCore" in wizard
    assert "#02060b" in wizard and "#4ddcff" in wizard


def test_android_uses_canonical_genesis_design_and_four_step_create() -> None:
    activity = (ROOT / "android-companion/app/src/main/java/ai/personal/companion/ConnectActivity.kt").read_text(encoding="utf-8")
    theme = (ROOT / "android-companion/app/src/main/java/ai/personal/companion/PersonalAITheme.kt").read_text(encoding="utf-8")
    core = (ROOT / "android-companion/app/src/main/java/ai/personal/companion/VishnuGenesisCoreView.kt").read_text(encoding="utf-8")
    assert "0xFF02060B" in theme and "0xFF20B8FF" in theme and "0xFF4DDCFF" in theme
    assert "VishnuGenesisCoreView" in activity and "class VishnuGenesisCoreView" in core
    assert "Step $genesisStep of 4" in activity
    for step in range(2, 5):
        assert f'"genesis-{step}"' in activity
    for title in ("What should Vishnu call you?", "Secure Your Vishnu", "Save Your Recovery Codes"):
        assert title in activity
    assert 'firstDeviceName.text.toString().trim()' in activity
    assert "CreateDocument" in activity and "Copy All Codes" in activity
    assert 'setSelection(0)' in activity  # conservative device_only
    assert '.put("data_policy"' in activity


def test_ios_uses_canonical_genesis_design_and_four_step_create() -> None:
    view = (ROOT / "ios-companion/PersonalAICompanion/ConnectOnboardingView.swift").read_text(encoding="utf-8")
    theme = (ROOT / "ios-companion/PersonalAICompanion/PersonalAITheme.swift").read_text(encoding="utf-8")
    assert "VishnuGenesisBackground" in view and "VishnuGenesisCore" in view
    assert r"Step \(genesisStep) of 4" in view
    assert "ForEach(1...4" in view
    assert "genesisStep == 2" in view and "genesisStep == 3" in view
    assert "genesisStep = 4" in view
    for title in ("What should Vishnu call you?", "Secure Your Vishnu", "Save Your Recovery Codes"):
        assert title in view
    assert "Quick review" in view
    assert "Copy all recovery codes" in view
    assert '"data_policy": dataPolicy' in view
    assert 'dataPolicy = "device_only"' in view
    assert 'privacyMode = "local_only"' in view
    assert "accessibilityReduceMotion" in theme
    assert "VishnuGenesisWordmark" in view and "vishnuGenesisInput()" in view


def test_native_completion_persists_data_policy_through_data_plane() -> None:
    source = (ROOT / "server/iphone_pwa.py").read_text(encoding="utf-8")
    assert "data_policy: Literal['device_only', 'progress_only', 'sync_everywhere', 'on_demand']" in source
    assert "data_plane.update_settings(default_policy=body.data_policy)" in source
