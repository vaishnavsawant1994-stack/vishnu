from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_windows_uses_canonical_genesis_design_and_all_ten_steps() -> None:
    wizard = (ROOT / "ui/first_run_wizard.py").read_text(encoding="utf-8")
    for page in (
        "_welcome_page()", "_owner_page()", "_security_choice_page()", "_security_page()",
        "_recovery_page()", "_device_page()", "_data_page()", "_model_page()",
        "_privacy_page()", "_review_page()",
    ):
        assert f"self.stack.addWidget(self.{page})" in wizard
    assert "Screen {step} of 10" in wizard
    assert "class VishnuCore" in wizard
    assert "#02060b" in wizard and "#4ddcff" in wizard


def test_android_uses_canonical_genesis_design_and_all_ten_steps() -> None:
    activity = (ROOT / "android-companion/app/src/main/java/ai/personal/companion/ConnectActivity.kt").read_text(encoding="utf-8")
    theme = (ROOT / "android-companion/app/src/main/java/ai/personal/companion/PersonalAITheme.kt").read_text(encoding="utf-8")
    core = (ROOT / "android-companion/app/src/main/java/ai/personal/companion/VishnuGenesisCoreView.kt").read_text(encoding="utf-8")
    assert "0xFF02060B" in theme
    assert "0xFF20B8FF" in theme
    assert "0xFF4DDCFF" in theme
    assert "VishnuGenesisCoreView" in activity and "class VishnuGenesisCoreView" in core
    for step in range(2, 11):
        assert f'"genesis-{step}"' in activity
    for title in (
        "Create your Vishnu identity", "Secure your Vishnu", "Configure your authentication",
        "Protect your Vishnu", "Register this device", "Choose where your data lives",
        "Set up Vishnu’s intelligence", "Choose what Vishnu can access",
        "Your Vishnu is ready to be created",
    ):
        assert title in activity
    assert '.put("data_policy"' in activity


def test_ios_uses_canonical_genesis_design_and_all_ten_steps() -> None:
    view = (ROOT / "ios-companion/PersonalAICompanion/ConnectOnboardingView.swift").read_text(encoding="utf-8")
    theme = (ROOT / "ios-companion/PersonalAICompanion/PersonalAITheme.swift").read_text(encoding="utf-8")
    assert "VishnuGenesisBackground" in view and "VishnuGenesisCore" in view
    assert r"Step \(genesisStep) of 10" in view
    for step in range(2, 11):
        assert f"genesisStep == {step}" in view or (step == 10 and "else {" in view)
    for title in (
        "Create your Vishnu identity", "Secure your Vishnu", "Configure your authentication",
        "Protect your Vishnu", "Register this device", "Choose where your data lives",
        "Set up Vishnu’s intelligence", "Choose what Vishnu can access",
        "Your Vishnu is ready to be created",
    ):
        assert title in view
    assert '"data_policy": dataPolicy' in view
    assert "accessibilityReduceMotion" in theme


def test_native_completion_persists_data_policy_through_data_plane() -> None:
    source = (ROOT / "server/iphone_pwa.py").read_text(encoding="utf-8")
    assert "data_policy: Literal['device_only', 'progress_only', 'sync_everywhere', 'on_demand']" in source
    assert "data_plane.update_settings(default_policy=body.data_policy)" in source
