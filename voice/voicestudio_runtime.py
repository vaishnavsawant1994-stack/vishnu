from __future__ import annotations

import os
from dataclasses import dataclass, replace

from voice.config import VoiceRuntimeSettings
from voice.runtime import VoiceRuntime
from voice.voicestudio import VoiceStudioProvider, VoiceStudioSettings, build_voicestudio_provider

_FALSE_VALUES = frozenset({"0", "false", "no", "off", ""})
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


@dataclass(frozen=True, slots=True)
class VoiceStudioRuntimeBinding:
    """Additive application-lifetime binding for the external VoiceStudio provider."""

    provider: VoiceStudioProvider | None
    runtime: VoiceRuntime | None

    @property
    def enabled(self) -> bool:
        return self.provider is not None and self.runtime is not None


def _provider_enabled_from_env() -> bool:
    raw = os.getenv("VISHNU_VOICESTUDIO_ENABLED")
    if raw is None:
        return False
    normalized = raw.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise ValueError("VISHNU_VOICESTUDIO_ENABLED must be a boolean value")


def compose_voicestudio_runtime(
    *,
    vault=None,
    events=None,
    provider_settings: VoiceStudioSettings | None = None,
    runtime_settings: VoiceRuntimeSettings | None = None,
) -> VoiceStudioRuntimeBinding:
    """Compose VoiceStudio behind Vishnu's existing bounded provider runtime.

    No service is created when VoiceStudio is disabled. When explicitly enabled,
    this reuses ``VoiceRuntime`` rather than introducing a second scheduler or
    lifecycle authority. A remote bearer key, when needed, comes only from the
    already-authenticated canonical SecretVault.
    """

    if provider_settings is None:
        # Do not parse or validate any other VoiceStudio configuration while the
        # integration is disabled. A stale optional URL must never disturb the
        # existing Vishnu startup path.
        if not _provider_enabled_from_env():
            return VoiceStudioRuntimeBinding(provider=None, runtime=None)
        resolved_provider_settings = VoiceStudioSettings.from_env()
    else:
        resolved_provider_settings = provider_settings

    if not resolved_provider_settings.enabled:
        return VoiceStudioRuntimeBinding(provider=None, runtime=None)

    api_key = None
    if resolved_provider_settings.is_remote and vault is not None:
        api_key = vault.get("voicestudio.api_key")

    provider = build_voicestudio_provider(
        settings=resolved_provider_settings,
        api_key=api_key,
    )
    if provider is None:
        return VoiceStudioRuntimeBinding(provider=None, runtime=None)

    resolved_runtime_settings = runtime_settings or VoiceRuntimeSettings.from_env()
    # Enabling the provider is an explicit opt-in, so make the already-bounded
    # VoiceRuntime live for the same application lifetime without requiring a
    # second feature flag. All default behavior remains unchanged while the
    # provider itself is disabled.
    if not resolved_runtime_settings.enabled:
        resolved_runtime_settings = replace(resolved_runtime_settings, enabled=True)

    runtime = VoiceRuntime(
        events=events,
        settings=resolved_runtime_settings,
        stt_provider=provider,
        tts_provider=provider,
    )
    return VoiceStudioRuntimeBinding(provider=provider, runtime=runtime)
