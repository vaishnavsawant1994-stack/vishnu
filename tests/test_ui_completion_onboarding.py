from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_pwa_first_run_uses_short_three_stage_create_flow() -> None:
    source = (ROOT / "pwa" / "first-run.js").read_text(encoding="utf-8")
    assert "Create My Vishnu" in source
    assert "What should Vishnu call you?" in source
    assert "Secure your Vishnu" in source
    assert "Save your Vishnu Recovery Key" in source
    assert "Step ${journeyStep} of 3" in source
    assert "Math.min(4, n)" in source


def test_pwa_first_run_saves_safe_defaults_through_existing_setup_authority() -> None:
    source = (ROOT / "pwa" / "first-run-actions.js").read_text(encoding="utf-8")
    assert "setupApi('/first-run/data-policy'" in source
    assert "default_policy: 'device_only'" in source
    assert "provider_id: 'skip'" in source
    assert "privacy_mode: 'local_only'" in source
    assert "default_policy: 'device_only'" in source


def test_pwa_first_run_requires_recovery_confirmation_before_completion() -> None:
    source = (ROOT / "pwa" / "first-run-actions.js").read_text(encoding="utf-8")
    assert "if (!$('firstRunRecoverySaved')?.checked)" in source
    assert "setupApi('/first-run/complete'" in source


def test_pwa_first_run_review_is_invalidated_when_saved_choices_change() -> None:
    source = (ROOT / "pwa" / "first-run-actions.js").read_text(encoding="utf-8")
    adapter = (ROOT / "pwa" / "first-run.js").read_text(encoding="utf-8")
    assert "render(4)" in source
    assert "state.identityCreated = true" in source
    assert "if (event.detail.step === 4)" in source
    assert "setupApi('/first-run/recovery-saved'" in source


def test_incomplete_first_run_allows_only_canonical_data_plane_settings_write() -> None:
    source = (ROOT / "server" / "pwa_session_middleware.py").read_text(encoding="utf-8")
    assert "'/iphone/api/first-run/data-policy'" in source
    assert 'setup claim and first-device credential' in source


def test_desktop_wizard_uses_canonical_data_plane_and_short_secure_completion() -> None:
    source = (ROOT / "ui" / "first_run_wizard.py").read_text(encoding="utf-8")
    assert "from data_plane.runtime import get_data_plane" in source
    for policy in ("device_only", "progress_only", "sync_everywhere", "on_demand"):
        assert f"'{policy}'" in source
    assert "get_data_plane(self.runtime).update_settings" in source
    assert "get_data_plane(self.runtime).settings()" in source
    assert ".get_settings()" not in source
    assert "Step {step} of 3" in source
    assert "default_policy='device_only'" in source
    assert "def _confirm_recovery_codes" in source
    assert "self.coordinator.complete()" in source
