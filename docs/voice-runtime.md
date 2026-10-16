# Vishnu Voice Runtime

The Voice Runtime is an additive, bounded execution layer for speech-to-text and text-to-speech providers. It extends the existing Vishnu voice stack; it does not replace Voice Intelligence, full-duplex conversation, OpenAI Realtime, voice conversion, ToolRegistry, ApprovalManager, DeviceRegistry, or DeviceGateway.

## Activation

The provider runtime is disabled by default. Enable it explicitly with `VISHNU_VOICE_RUNTIME_ENABLED=true`. Optional controls are `VISHNU_VOICE_RUNTIME_WORKERS`, `VISHNU_VOICE_RUNTIME_MAX_PENDING`, and `VISHNU_VOICE_RUNTIME_WORKSPACE_ROOT`.

When disabled, `VoiceRuntime.start()` allocates no worker and creates no workspace. The legacy listening/frame/speak API remains unchanged.

## Boundaries

- Each running `VoiceRuntime` receives a unique ephemeral workspace that is deleted during clean shutdown.
- Provider execution is admitted through a bounded priority scheduler; interactive speech outranks normal and background work.
- STT and TTS providers implement small protocol contracts with health and capability reporting.
- The model registry is metadata-only and fail-closed for unknown/unapproved licenses by default. It does not download or execute models.
- Model metadata can record redistribution, commercial-use, and local-only constraints.
- The runtime has no device-control, owner-approval, credential-vault, or persistent-storage authority. Those remain with Vishnu's existing authorities.
- No external model or provider is bundled by this layer.

## Provider contracts

`voice.providers` defines request/result dataclasses and the `SpeechToTextProvider` / `TextToSpeechProvider` protocols. Providers are injected into `VoiceRuntime`; callers can therefore add local or remote engines without coupling the runtime to a model framework.

## Scheduling

`voice.scheduler.InferenceScheduler` uses a bounded queue and configurable worker count. It supports interactive, normal, and background priorities, future cancellation, caller-side result timeouts, and pre-execution job expiry. Shutdown rejects new jobs and can cancel queued jobs.

## Licensing

`voice.registry.VoiceModelRegistry` requires explicit model metadata. Unknown licenses are rejected unless a caller constructs a registry with `allow_unverified=True`. Commercial use and redistribution can be checked independently. This is an engineering guardrail, not legal advice; provider/model terms still require review before distribution or production use.
