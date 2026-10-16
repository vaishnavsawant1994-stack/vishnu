"""Composition helpers for the optional Vishnu Voice Runtime.

This module is the safe integration point for product/runtime composition. It
never enables voice inference by import and never constructs model providers
implicitly. Callers explicitly pass providers and model metadata.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from voice.model_registry import VoiceModelRegistry, VoiceModelSpec
from voice.providers import STTProvider, TTSProvider
from voice.runtime_service import AuditHook, VoiceRuntimeService


def build_voice_runtime(
    *,
    env: Mapping[str, str] | None = None,
    models: Iterable[VoiceModelSpec] = (),
    tts_providers: Iterable[TTSProvider] = (),
    stt_providers: Iterable[STTProvider] = (),
    audit_hook: AuditHook | None = None,
) -> VoiceRuntimeService:
    """Compose a runtime without replacing any Vishnu authority.

    The returned service stays disabled unless ``VISHNU_VOICE_RUNTIME_ENABLED``
    is explicitly true. Providers are dependency-injected and therefore cannot
    perform downloads, initialize GPUs, or open microphones merely because this
    module was imported.
    """

    registry = VoiceModelRegistry()
    for model in models:
        registry.register(model)

    runtime = VoiceRuntimeService.from_env(env=env, registry=registry, audit_hook=audit_hook)
    for provider in tts_providers:
        runtime.register_tts_provider(provider)
    for provider in stt_providers:
        runtime.register_stt_provider(provider)
    return runtime
