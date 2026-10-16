from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_pwa_first_run_exposes_exact_canonical_data_policies() -> None:
    source = (ROOT / "pwa" / "first-run.js").read_text(encoding="utf-8")
    for policy in ("device_only", "progress_only", "sync_everywhere", "on_demand"):
        assert f"['{policy}'" in source
    assert "Save data placement" in source
    assert "never silently moves data" in source


def test_pwa_first_run_persists_policy_through_data_plane_authority() -> None:
    source = (ROOT / "pwa" / "first-run-actions.js").read_text(encoding="utf-8")
    assert "api('/data-plane/settings'" in source
    assert "default_policy:dataPolicy.value" in source
    assert "existing data was not moved" in source


def test_pwa_first_run_requires_review_before_completion() -> None:
    source = (ROOT / "pwa" / "first-run-actions.js").read_text(encoding="utf-8")
    assert "Review setup" in (ROOT / "pwa" / "first-run.js").read_text(encoding="utf-8")
    assert "if(review.classList.contains('hidden'))" in source
    assert "Save your data placement policy before reviewing setup." in source
    assert "Review your setup before finishing." in source
    assert "api('/first-run/complete'" in source


def test_incomplete_first_run_allows_only_canonical_data_plane_settings_write() -> None:
    source = (ROOT / "server" / "pwa_session_middleware.py").read_text(encoding="utf-8")
    assert "'/iphone/api/data-plane/settings'" in source
    assert "never moves existing owner data during first-run" in source
