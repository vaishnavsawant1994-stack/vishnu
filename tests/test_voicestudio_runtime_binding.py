from __future__ import annotations

import pytest

from voice.config import VoiceRuntimeSettings
from voice.runtime import VoiceRuntimeState
from voice.voicestudio import VoiceStudioSettings
from voice.voicestudio_runtime import compose_voicestudio_runtime


class FakeVault:
    def __init__(self, value=None):
        self.value = value
        self.lookups = []

    def get(self, name, default=None):
        self.lookups.append(name)
        return self.value if self.value is not None else default


def test_disabled_binding_allocates_no_provider_or_runtime():
    vault = FakeVault("unused")

    binding = compose_voicestudio_runtime(
        vault=vault,
        provider_settings=VoiceStudioSettings(enabled=False),
    )

    assert binding.enabled is False
    assert binding.provider is None
    assert binding.runtime is None
    assert vault.lookups == []


def test_disabled_environment_does_not_parse_stale_optional_configuration(monkeypatch):
    monkeypatch.setenv("VISHNU_VOICESTUDIO_ENABLED", "false")
    monkeypatch.setenv("VISHNU_VOICESTUDIO_URL", "not-a-url")

    binding = compose_voicestudio_runtime()

    assert binding.enabled is False
    assert binding.provider is None
    assert binding.runtime is None


def test_local_binding_reuses_existing_voice_runtime_for_application_lifetime(tmp_path):
    binding = compose_voicestudio_runtime(
        provider_settings=VoiceStudioSettings(enabled=True),
        runtime_settings=VoiceRuntimeSettings(
            enabled=False,
            workspace_root=tmp_path,
        ),
    )

    assert binding.enabled is True
    assert binding.provider is binding.runtime.stt_provider
    assert binding.provider is binding.runtime.tts_provider
    assert binding.runtime.settings.enabled is True
    assert binding.runtime.start() is True
    assert binding.runtime.state is VoiceRuntimeState.RUNNING
    assert binding.runtime.start() is True
    binding.runtime.stop()
    assert binding.runtime.state is VoiceRuntimeState.STOPPED


def test_remote_binding_reads_only_existing_secret_vault_key(tmp_path):
    vault = FakeVault("secret-token")

    binding = compose_voicestudio_runtime(
        vault=vault,
        provider_settings=VoiceStudioSettings(
            enabled=True,
            base_url="https://voice.example",
            allow_remote=True,
        ),
        runtime_settings=VoiceRuntimeSettings(workspace_root=tmp_path),
    )

    assert binding.enabled is True
    assert vault.lookups == ["voicestudio.api_key"]
    assert "secret-token" not in repr(binding.provider.capabilities())


def test_remote_binding_fails_closed_without_secret_vault_key():
    with pytest.raises(ValueError, match="API key"):
        compose_voicestudio_runtime(
            vault=FakeVault(),
            provider_settings=VoiceStudioSettings(
                enabled=True,
                base_url="https://voice.example",
                allow_remote=True,
            ),
        )
