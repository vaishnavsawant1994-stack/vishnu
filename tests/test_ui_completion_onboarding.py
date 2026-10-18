from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_pwa_first_run_exposes_exact_canonical_data_policies() -> None:
    source = (ROOT / "pwa" / "first-run.js").read_text(encoding="utf-8")
    for policy in ("device_only", "progress_only", "sync_everywhere", "on_demand"):
        assert f"'{policy}'" in source
    assert "Choose where your data lives" in source
    assert "never silently moves data" in source


def test_pwa_first_run_persists_policy_through_data_plane_authority() -> None:
    source = (ROOT / "pwa" / "first-run-actions.js").read_text(encoding="utf-8")
    assert "api('/data-plane/settings'" in source
    assert "default_policy:s.dataPolicy" in source
    assert "s.policySaved=true" in source


def test_pwa_first_run_requires_review_before_completion() -> None:
    source = (ROOT / "pwa" / "first-run-actions.js").read_text(encoding="utf-8")
    adapter = (ROOT / "pwa" / "first-run.js").read_text(encoding="utf-8")
    assert "Your Vishnu is ready to be created" in adapter
    assert "if(step===10)await finish()" in source
    assert "s.recoverySaved=true" in source
    assert "s.policySaved=true" in source
    assert "api('/first-run/complete'" in source


def test_pwa_first_run_review_is_invalidated_when_saved_choices_change() -> None:
    source = (ROOT / "pwa" / "first-run-actions.js").read_text(encoding="utf-8")
    adapter = (ROOT / "pwa" / "first-run.js").read_text(encoding="utf-8")
    assert "render(s.step-1)" in adapter
    assert "s.dataPolicy=x.value" in adapter
    assert "s.intelligence=x.value" in adapter
    assert "s.privacy=$('firstRunPrivacy')" in source
    assert "s.modelSaved=true" in source
    assert "s.identityCreated=true" in source


def test_incomplete_first_run_allows_only_canonical_data_plane_settings_write() -> None:
    source = (ROOT / "server" / "pwa_session_middleware.py").read_text(encoding="utf-8")
    assert "'/iphone/api/data-plane/settings'" in source
    assert "never moves existing owner data during first-run" in source


def test_desktop_wizard_uses_canonical_data_plane_and_review_before_complete() -> None:
    source = (ROOT / "ui" / "first_run_wizard.py").read_text(encoding="utf-8")
    assert "from data_plane.runtime import get_data_plane" in source
    for policy in ("device_only", "progress_only", "sync_everywhere", "on_demand"):
        assert f"'{policy}'" in source
    assert "get_data_plane(self.runtime).update_settings" in source
    assert "get_data_plane(self.runtime).settings()" in source
    assert ".get_settings()" not in source
    assert "Changing this default never silently moves data" in source
    assert "self.stack.addWidget(self._review_page())" in source
    assert "Review setup" in source
    assert "def _finish_review" in source
    assert "self.coordinator.complete()" in source
