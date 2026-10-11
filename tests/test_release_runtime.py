from __future__ import annotations

import json

import pytest

from future_intelligence.release_control.runtime import build_release_control_runtime


RENDER_KEYS = (
    "VISHNU_RELEASE_RENDER_API_TOKEN",
    "VISHNU_RELEASE_RENDER_PREVIEW_SERVICE_ID",
    "VISHNU_RELEASE_RENDER_PRODUCTION_SERVICE_ID",
    "VISHNU_RELEASE_RENDER_PREVIEW_URL",
    "VISHNU_RELEASE_RENDER_PRODUCTION_URL",
)
VERCEL_KEYS = (
    "VISHNU_RELEASE_VERCEL_API_TOKEN",
    "VISHNU_RELEASE_VERCEL_PROJECT_ID",
    "VISHNU_RELEASE_VERCEL_PROJECT_NAME",
    "VISHNU_RELEASE_VERCEL_GITHUB_ORG",
    "VISHNU_RELEASE_VERCEL_GITHUB_REPO",
    "VISHNU_RELEASE_VERCEL_PRODUCTION_URL",
    "VISHNU_RELEASE_VERCEL_GIT_REF",
    "VISHNU_RELEASE_VERCEL_TEAM_ID",
    "VISHNU_RELEASE_VERCEL_PREVIEW_HOST_SUFFIX",
)


def clear_provider_env(monkeypatch):
    for key in (*RENDER_KEYS, *VERCEL_KEYS, "VISHNU_RELEASE_HEALTH_PATH"):
        monkeypatch.delenv(key, raising=False)


def test_runtime_without_provider_stays_operational_but_has_no_deploy_authority(tmp_path, monkeypatch):
    clear_provider_env(monkeypatch)
    runtime = build_release_control_runtime(data_dir=tmp_path)
    assert runtime.providers == {}
    assert runtime.summary()["provider_capabilities"] == {}
    assert runtime.controller.preview_qualifier is None
    assert runtime.controller.production_smoke is None
    assert runtime.policy().mode.value == "approval_required"


def test_partial_render_configuration_fails_closed(tmp_path, monkeypatch):
    clear_provider_env(monkeypatch)
    monkeypatch.setenv("VISHNU_RELEASE_RENDER_API_TOKEN", "token")
    with pytest.raises(RuntimeError, match="Render release provider configuration is incomplete"):
        build_release_control_runtime(data_dir=tmp_path)


def test_partial_vercel_configuration_fails_closed(tmp_path, monkeypatch):
    clear_provider_env(monkeypatch)
    monkeypatch.setenv("VISHNU_RELEASE_VERCEL_API_TOKEN", "token")
    with pytest.raises(RuntimeError, match="Vercel release provider configuration is incomplete"):
        build_release_control_runtime(data_dir=tmp_path)


def test_full_render_and_vercel_configuration_registers_both_without_network_calls(tmp_path, monkeypatch):
    clear_provider_env(monkeypatch)
    values = {
        "VISHNU_RELEASE_RENDER_API_TOKEN": "render-token",
        "VISHNU_RELEASE_RENDER_PREVIEW_SERVICE_ID": "srv-preview",
        "VISHNU_RELEASE_RENDER_PRODUCTION_SERVICE_ID": "srv-production",
        "VISHNU_RELEASE_RENDER_PREVIEW_URL": "https://preview.render.example.test",
        "VISHNU_RELEASE_RENDER_PRODUCTION_URL": "https://prod.render.example.test",
        "VISHNU_RELEASE_VERCEL_API_TOKEN": "vercel-token",
        "VISHNU_RELEASE_VERCEL_PROJECT_ID": "prj_test",
        "VISHNU_RELEASE_VERCEL_PROJECT_NAME": "vishnu",
        "VISHNU_RELEASE_VERCEL_GITHUB_ORG": "owner",
        "VISHNU_RELEASE_VERCEL_GITHUB_REPO": "repo",
        "VISHNU_RELEASE_VERCEL_PRODUCTION_URL": "https://vishnu.example.test",
        "VISHNU_RELEASE_VERCEL_GIT_REF": "main",
        "VISHNU_RELEASE_VERCEL_TEAM_ID": "team_test",
        "VISHNU_RELEASE_VERCEL_PREVIEW_HOST_SUFFIX": ".vercel.app",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)

    runtime = build_release_control_runtime(data_dir=tmp_path)
    assert sorted(runtime.providers) == ["render", "vercel"]
    qualifier = runtime.controller.preview_qualifier
    assert qualifier is runtime.controller.production_smoke
    assert "preview.render.example.test" in qualifier._allowed
    assert "prod.render.example.test" in qualifier._allowed
    assert "vishnu.example.test" in qualifier._allowed
    assert ".vercel.app" in qualifier._suffixes

    summary = runtime.summary()
    assert summary["provider_capabilities"] == {
        "render": {
            "production_observation": True,
            "production_telemetry": True,
            "telemetry_evidence_sanitized": True,
        },
        "vercel": {
            "production_observation": True,
            "production_telemetry": True,
            "telemetry_evidence_sanitized": True,
        },
    }
    serialized = json.dumps(summary, sort_keys=True)
    assert "render-token" not in serialized
    assert "vercel-token" not in serialized


def test_release_policy_persists_across_runtime_restart(tmp_path, monkeypatch):
    clear_provider_env(monkeypatch)
    runtime = build_release_control_runtime(data_dir=tmp_path)
    runtime.update_policy(mode="auto_low_risk", canary_min_requests=77, max_monitoring_observations=222)

    restored = build_release_control_runtime(data_dir=tmp_path)
    assert restored.policy().mode.value == "auto_low_risk"
    assert restored.policy().canary_min_requests == 77
    assert restored.policy().max_monitoring_observations == 222


def test_invalid_preview_suffix_is_rejected_at_runtime_construction(tmp_path, monkeypatch):
    clear_provider_env(monkeypatch)
    values = {
        "VISHNU_RELEASE_VERCEL_API_TOKEN": "vercel-token",
        "VISHNU_RELEASE_VERCEL_PROJECT_ID": "prj_test",
        "VISHNU_RELEASE_VERCEL_PROJECT_NAME": "vishnu",
        "VISHNU_RELEASE_VERCEL_GITHUB_ORG": "owner",
        "VISHNU_RELEASE_VERCEL_GITHUB_REPO": "repo",
        "VISHNU_RELEASE_VERCEL_PRODUCTION_URL": "https://vishnu.example.test",
        "VISHNU_RELEASE_VERCEL_PREVIEW_HOST_SUFFIX": "vercel.app/evil",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(ValueError, match="host suffix"):
        build_release_control_runtime(data_dir=tmp_path)
