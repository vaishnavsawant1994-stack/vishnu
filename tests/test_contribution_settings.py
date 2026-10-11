from __future__ import annotations

import json

import pytest

from training.contribution_settings import ContributionSettingsService
from training.contributions import ContributionMode


def test_contribution_settings_default_to_private(tmp_path):
    service = ContributionSettingsService(tmp_path / "contributions.json")
    snapshot = service.snapshot()

    assert snapshot.preferences.mode is ContributionMode.PRIVATE
    assert snapshot.preferences.conversations is False
    assert snapshot.preferences.documents is False
    assert snapshot.preferences.agent_outcomes is True
    assert snapshot.preferences.tool_metrics is True


def test_contribution_settings_persist_owner_choice(tmp_path):
    path = tmp_path / "contributions.json"
    service = ContributionSettingsService(path)
    updated = service.update(mode="aggregate", agent_outcomes=True, tool_metrics=True)

    assert updated.preferences.mode is ContributionMode.AGGREGATE
    reloaded = ContributionSettingsService(path).snapshot()
    assert reloaded.preferences.mode is ContributionMode.AGGREGATE
    assert reloaded.preferences.agent_outcomes is True
    assert reloaded.preferences.tool_metrics is True
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["mode"] == "aggregate"


def test_documents_require_training_contributor_mode(tmp_path):
    service = ContributionSettingsService(tmp_path / "contributions.json")

    with pytest.raises(ValueError, match="document contribution"):
        service.update(mode="aggregate", documents=True)

    updated = service.update(mode="training_contributor", documents=True)
    assert updated.preferences.mode is ContributionMode.TRAINING_CONTRIBUTOR
    assert updated.preferences.documents is True


def test_invalid_contribution_mode_is_rejected(tmp_path):
    service = ContributionSettingsService(tmp_path / "contributions.json")
    with pytest.raises(ValueError, match="invalid contribution mode"):
        service.update(mode="everything")


def test_unknown_contribution_setting_is_rejected(tmp_path):
    service = ContributionSettingsService(tmp_path / "contributions.json")
    with pytest.raises(ValueError, match="unsupported contribution settings"):
        service.update(upload_all_private_files=True)
