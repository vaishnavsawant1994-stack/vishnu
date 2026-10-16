# Vishnu Voice Runtime Provider Layer

## Purpose

This layer adds a bounded, opt-in speech inference boundary around Vishnu's existing Voice Intelligence implementation. It is deliberately additive: it does not replace Voice Intelligence, ToolRegistry, ApprovalManager, DeviceRegistry, DeviceGateway, SecretVault, Memory, Knowledge, Sensorium, Computer Control, durable execution, or the audit system.

The layer is inspired by proven local-first voice-studio patterns while remaining native to Vishnu's existing authorities.

## Safety and isolation

Voice inference is **disabled by default**.

```text
VISHNU_VOICE_RUNTIME_ENABLED=false
VISHNU_VOICE_COMMERCIAL_MODE=true
```

Set `VISHNU_VOICE_RUNTIME_ENABLED=true` only in a composition that has explicitly registered approved providers and model metadata.

Importing any module in this layer does not download models, initialize a GPU, open a microphone, start a worker, or create a new device/approval authority.

Provider failures are isolated to the submitted voice job. The scheduler is not started while the runtime is disabled.

## Architecture

```text
Existing Voice Intelligence
        VoicePlan
           |
           v
    plan_adapter.py
           |
           v
 VoiceRuntimeService
      /          \
 TTSProvider   STTProvider
      \          /
 VoiceModelRegistry
          |
 VoiceInferenceScheduler
          |
 existing audio/device composition
```

`VoicePlan` remains the authority for persona, language, style, delivery controls, privacy/offline requirements, avatar expression, and device-aware routing. The provider layer only translates an already-decided plan into model-agnostic inference requests.

## Provider contracts

`voice/providers.py` defines stable `TTSProvider` and `STTProvider` protocols plus normalized request/result objects. Model-specific adapters should live outside the protocol module and should not import heavy dependencies until actually invoked.

A provider is identified by `provider_id`. A model entry in the registry maps a `model_id` to that provider.

This means OpenVoice, Qwen, Kokoro, Chatterbox, Whisper, Parakeet, or a future engine can be added or removed without changing Voice Intelligence.

## Model and license registry

Every model used by the runtime must be represented by `VoiceModelSpec` before inference. Metadata includes:

- model and provider IDs
- version
- capabilities such as TTS, STT, cloning, design, streaming, and emotion control
- code license
- model-weights license
- commercial-use approval
- redistribution approval
- attribution requirement
- languages
- hardware targets
- memory requirement
- download size
- quality and latency scores
- verified artifact hash
- source

The registry fails closed for commercial use. `commercial_allowed` defaults to `False`; a model is not usable by proprietary Vishnu merely because its wrapper code is open source.

No third-party model weights are bundled or approved by this layer.

## Inference scheduling

`VoiceInferenceScheduler` serializes accelerator work to avoid TTS/STT models competing for the same GPU or accelerator.

Priority order:

1. emergency
2. live conversation
3. agent response
4. notification
5. long-form speech

Priority changes queue order only for work that has not started. Running inference is not force-preempted.

## Voice-cloning consent and provenance

`voice/governance.py` provides persistence-agnostic records for explicit consent and sample provenance.

A clone sample records its subject, source kind, consent record, content hash, and Vishnu storage policy. Raw voice material defaults to `device_only`.

Clone use fails closed when:

- consent is missing, revoked, or not affirmative
- the sample subject does not match the consent subject
- the sample points to another consent record
- commercial use is requested but the consent does not grant it

Persistence, encryption, authorization, and audit storage must continue to use Vishnu's existing data/security authorities rather than creating a voice-specific secret store.

## Audit boundary

The runtime accepts an injected audit hook. Runtime events include lifecycle, synthesis/transcription request, completion, and failure.

Do not place raw spoken text or audio bytes into audit metadata. Current runtime events contain identifiers and operational metadata only.

## Long-form speech

`voice/chunking.py` splits text at sentence/word boundaries with a hard 50,000-character ceiling and configurable per-chunk limit from 100 to 5,000 characters.

The utility intentionally returns text chunks rather than concatenating encoded audio bytes. Crossfade/decoding/encoding belongs in the selected audio pipeline or provider implementation.

## Composition

Use `build_voice_runtime()` from `voice/bootstrap.py` as the integration surface.

```python
runtime = build_voice_runtime(
    env=os.environ,
    models=approved_model_specs,
    tts_providers=tts_providers,
    stt_providers=stt_providers,
    audit_hook=audit.emit,
)
```

The factory remains default-off unless the feature flag is explicitly enabled.

## Existing device and Sensorium integration

This layer does not own microphones, speakers, devices, pairing, or trust.

Input should arrive through the existing Sensorium/device path and be submitted as a `TranscriptionRequest`. Output should be returned to existing product/device composition and delivered through DeviceGateway under its existing trust and scope rules.

A future speaker-recognition provider must be separately permissioned because speaker identity is biometric-like sensitive data; it must not be implicitly enabled by STT or voice cloning.

## Provider onboarding checklist

Before registering a production provider/model:

1. Verify code and weight licenses separately.
2. Record commercial and redistribution rights explicitly.
3. Pin model version and verified hash.
4. Add bounded resource requirements and supported hardware.
5. Ensure downloads are explicit and do not happen on import/startup.
6. Ensure secrets use SecretVault rather than provider-local storage.
7. Ensure external/network inference follows Vishnu approvals and capability governance.
8. Add regression tests for cancellation, failure isolation, invalid output, resource exhaustion, and restart behavior.
9. Record voice-clone consent/provenance when a provider supports cloning.
10. Qualify the exact provider/model artifact before enabling it by default anywhere.

## Non-goals of this PR

This layer does not silently install or ship OpenVoice, Qwen, Kokoro, Chatterbox, Whisper, or other model weights. It also does not create a second MCP server, second device registry, second approval manager, or second voice database.
