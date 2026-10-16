# Vishnu Voice Runtime

The Voice Runtime is an additive, bounded execution layer for speech-to-text and text-to-speech providers. It extends the existing Vishnu voice stack; it does not replace Voice Intelligence, full-duplex conversation, OpenAI Realtime, voice conversion, ToolRegistry, ApprovalManager, DeviceRegistry, DeviceGateway, Sensorium, or SecretVault.

## Activation

The provider runtime is disabled by default. Enable it explicitly with `VISHNU_VOICE_RUNTIME_ENABLED=true`. Optional controls are `VISHNU_VOICE_RUNTIME_WORKERS`, `VISHNU_VOICE_RUNTIME_MAX_PENDING`, and `VISHNU_VOICE_RUNTIME_WORKSPACE_ROOT`.

When disabled, `VoiceRuntime.start()` allocates no worker and creates no workspace. The legacy listening/frame/speak API remains unchanged.

## Boundaries

- Each running `VoiceRuntime` receives a unique ephemeral workspace that is deleted during clean shutdown.
- Provider execution is admitted through a bounded priority scheduler.
- STT and TTS providers implement small protocol contracts with health and capability reporting.
- The model registry is metadata-only and fail-closed for unknown/unapproved licenses by default. It does not download or execute models.
- The runtime has no device-control, owner-approval, credential-vault, tool, or persistent-data authority. Those remain with Vishnu's existing authorities.
- No external model, checkpoint, or provider is bundled or silently downloaded by this layer.

## Provider contracts

`voice.providers` defines request/result dataclasses and the `SpeechToTextProvider` / `TextToSpeechProvider` protocols. Providers are injected into `VoiceRuntime`; callers can therefore add local or remote engines without coupling the runtime to a model framework.

`VoiceRuntime.transcribe_intent()` composes STT with `SpeechIntentBridge`. The resulting `SpeechIntent` can carry bounded Sensorium acoustic context, but explicitly has no execution authority. Raw audio is not retained by the bridge.

## Scheduling

`voice.scheduler.InferenceScheduler` uses a bounded queue and configurable worker count. The canonical priority order is:

1. `EMERGENCY`
2. `LIVE`
3. `AGENT`
4. `NOTIFICATION`
5. `LONG_FORM`

Legacy `INTERACTIVE`, `NORMAL`, and `BACKGROUND` names remain aliases for compatibility. The scheduler supports future cancellation, caller-side result timeouts, pre-execution job expiry, bounded admission, and pending-job cancellation on shutdown.

## Model licensing and local assets

`voice.registry.VoiceModelRegistry` records code and weights licenses independently, along with upstream locations, exact artifact SHA-256, revision, language compatibility, hardware compatibility, commercial-use status, redistribution status, and local-only policy. Unknown code or weights licenses fail closed unless an explicitly unverified registry is created.

`voice.model_manager.LocalVoiceModelManager` manages only explicitly provisioned local artifacts. It has no download API. It verifies exact file size and SHA-256 before a model can be reported `READY`; missing, unverified, size-mismatched, and hash-mismatched states remain non-ready.

This is an engineering guardrail, not legal advice; provider/model terms still require review before distribution or production use.

## Streaming progress

The existing Voice Intelligence service already supports sentence-biased application-level chunk synthesis and barge-in cancellation. `voice.streaming.ProgressiveVoiceStreamer` adds privacy-safe progress reporting (`STARTED`, `CHUNK`, `COMPLETED`, `CANCELLED`) without exposing transcript text in progress telemetry. It still does not claim provider-native incremental OpenVoice conversion.

## Trusted multi-device output

`voice.device_output.TrustedVoiceOutputRouter` reuses the existing `DeviceGateway`; it does not create another device transport or trust registry. Only online trusted devices that explicitly advertise `voice.play_audio` are eligible. Audio payloads are bounded, integrity-labeled with SHA-256, and ordinary output events contain metadata rather than audio bytes.

## Consented voice profiles, encrypted samples, and portability

The existing governed `VoiceProfileRegistry` remains authoritative for enrollment, explicit consent, purpose, provenance hash, revocation, canonical Vishnu profile protection, and OpenVoice reference selection.

`voice.profile_archive` adds two bounded capabilities without replacing that registry:

- `EncryptedVoiceSampleStore` keeps additional consented WAV samples inside the existing `SecretVault` encryption authority.
- `VoiceProfileArchive` exports/imports password-encrypted multi-sample profile bundles using `SecretVault`. Import requires a fresh explicit consent attestation and re-enrolls the primary sample through `VoiceProfileRegistry`; additional samples are returned to encrypted sample storage when configured.

The existing primary OpenVoice reference-file behavior remains compatible. Portable bundles and additional sample stores do not grant cloning consent merely by possessing an archive.

## Qualification boundary

Repository tests can qualify contracts, governance, cancellation, encryption behavior, routing, local hash verification, and failure handling without bundling external voice models. Real model quality, GPU/CPU performance, provider-native streaming, microphone acoustics, and cross-device speaker quality still require qualification against the exact externally provisioned model revision and target hardware before production claims are made.
