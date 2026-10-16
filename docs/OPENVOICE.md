# Governed OpenVoice voice conversion

Vishnu keeps its existing speech architecture authoritative. OpenVoice is an optional, local post-TTS voice-conversion engine:

`text -> existing Vishnu TTS provider -> WAV -> optional governed OpenVoice conversion -> existing playback/full-duplex path`

This design deliberately does not replace Vishnu's microphone capture, adaptive VAD, semantic endpointing, transcription, request-scoped events, barge-in, stale-output protection, playback cancellation, or model routing.

## Security and consent boundary

Voice cloning is not exposed as an arbitrary synthesis parameter. A voice must first be enrolled into Vishnu's local voice-profile registry. Enrollment requires:

- an explicit local WAV file; HTTP, HTTPS, and `file://` references are rejected;
- an explicit consent attestation;
- a stated intended purpose;
- a stable governed profile ID;
- reference-audio size and duration limits; and
- a SHA-256 provenance/integrity hash that is re-checked before use.

Profiles can be revoked or deleted. The reserved canonical Vishnu profile ID is `vishnu`; it requires explicit protected override flags to revoke or delete it.

Reference audio and the profile manifest stay under the configured local profile store. The synthesis API receives a profile ID, never an arbitrary reference path or URL. Raw text, source audio, and enrolled reference audio are not written into conversion audit/event payloads.

Only enroll a person's voice when that person has clearly consented to the intended cloning/use. Do not use the feature to impersonate people, bypass identity checks, or misrepresent the origin of speech.

## OpenVoice dependency boundary

Vishnu does not vendor OpenVoice and does not download OpenVoice code, model checkpoints, speaker embeddings, or other model assets during normal startup or CI.

The adapter was reviewed against MyShell OpenVoice commit:

`74a1d147b17a8c3092dd5430504bd83ef6c7eb23`

OpenVoice is licensed under the MIT License; see `THIRD_PARTY_NOTICES.md`. Operators are responsible for separately provisioning a reviewed OpenVoice installation and compatible local model assets according to the upstream project's requirements and the licenses/terms of any separate models or dependencies.

The Vishnu adapter uses OpenVoice's `ToneColorConverter` and `se_extractor`. `ToneColorConverter.convert(...)` accepts source and target speaker embeddings and an optional watermark message. Vishnu passes a watermark message by default.

## Configuration

OpenVoice conversion is disabled by default. The existing TTS path is unchanged unless it is explicitly enabled.

| Variable | Default | Purpose |
| --- | --- | --- |
| `VISHNU_OPENVOICE_ENABLED` | `false` | Enables the post-TTS conversion layer. |
| `VISHNU_OPENVOICE_DEFAULT_PROFILE_ID` | `vishnu` | Default enrolled voice profile. |
| `VISHNU_OPENVOICE_PROFILE_STORE` | `<PERSONAL_AI_DATA_DIR>/voice/profiles` | Local enrollment manifest/reference-audio store. |
| `VISHNU_OPENVOICE_CONVERTER_CONFIG` | empty | Existing local OpenVoice tone-converter config file. |
| `VISHNU_OPENVOICE_CONVERTER_CHECKPOINT` | empty | Existing local tone-converter checkpoint. |
| `VISHNU_OPENVOICE_SOURCE_SE_PATH` | empty | Existing local source-speaker embedding used for the source TTS voice. |
| `VISHNU_OPENVOICE_DEVICE` | `cpu` | Device passed to OpenVoice, for example `cpu` or an explicitly provisioned CUDA device. |
| `VISHNU_OPENVOICE_WATERMARK_MESSAGE` | `@VISHNU` | Bounded watermark message passed to OpenVoice conversion. |
| `VISHNU_OPENVOICE_FALLBACK_TO_SOURCE` | `true` | On conversion-engine failure, return the original source TTS WAV. |
| `VISHNU_OPENVOICE_MAX_REFERENCE_BYTES` | `20971520` | Maximum accepted enrollment WAV size. |
| `VISHNU_OPENVOICE_MAX_REFERENCE_SECONDS` | `120` | Maximum accepted enrollment WAV duration. |

Model/config paths must be local files. Network URLs are rejected. Enabling conversion without provisioning the local OpenVoice installation, model files, source embedding, and an active enrolled default profile is not a valid production configuration.

## Enroll a voice locally

Enrollment is intentionally an owner/local administrative action. Example:

```bash
python scripts/manage_voice_profiles.py enroll \
  --wav /secure/local/path/reference.wav \
  --profile-id owner-voice \
  --display-name "Owner voice" \
  --purpose "Personal Vishnu speech output" \
  --consent-attested
```

For the protected canonical Vishnu identity, use profile ID `vishnu` with `--canonical`.

List profiles:

```bash
python scripts/manage_voice_profiles.py list
python scripts/manage_voice_profiles.py list --include-revoked
```

Revoke a normal profile:

```bash
python scripts/manage_voice_profiles.py revoke owner-voice
```

Delete a revoked or unused profile and its local reference WAV:

```bash
python scripts/manage_voice_profiles.py delete owner-voice
```

The canonical `vishnu` profile requires the explicit `--allow-canonical` flag for revocation/deletion.

## Synthesis contract

Existing code remains valid:

```python
audio_wav = models.synthesize(text)
```

Advanced callers can select an already-enrolled profile and a bounded style label:

```python
audio_wav = models.synthesize(
    text,
    voice_profile_id='owner-voice',
    voice_style='warm',
)
```

Allowed style labels are currently `normal`, `warm`, `empathetic`, `cheerful`, `serious`, `urgent`, `storytelling`, and `calm`.

These style labels are a bounded Vishnu pipeline capability for current/future expressive source-TTS planning. The current OpenVoice `ToneColorConverter` integration performs tone-color/timbre conversion; it does not by itself implement Vishnu's emotional-behavior model or guarantee those expressive styles. Vishnu must not claim that a style label means the AI actually feels an emotion.

## Failure behavior and realtime latency

If OpenVoice is disabled, synthesis is exact source-TTS passthrough.

When enabled, a successfully synthesized source WAV is converted only after the source TTS call completes. Conversion therefore adds latency. Vishnu's existing full-duplex, barge-in, request cancellation, and stale-output controls remain outside this adapter and are unchanged.

By default, an OpenVoice engine/runtime conversion failure returns the original source TTS WAV and emits a safe `voice.conversion.fallback` event. `VISHNU_OPENVOICE_FALLBACK_TO_SOURCE=false` changes engine failures to fail closed. Invalid, unknown, or revoked voice profiles remain governed errors rather than being silently treated as arbitrary clone requests.

## Observability

`ModelRouter.status()` includes a safe `voice_conversion` object containing enablement state, provider name, active profile IDs, fallback policy, and in-memory converted/fallback/failure counters. It does not expose reference audio, raw text, model secrets, or checkpoint paths.

Successful conversions emit `voice.conversion.completed`; engine fallbacks emit `voice.conversion.fallback`. Audit/event payloads contain bounded metadata only.

## Qualification

Normal CI must not require OpenVoice model downloads or GPU access. Unit tests use generated local WAV fixtures and a fake converter to qualify:

- explicit consent enforcement;
- WAV/size bounds;
- reference integrity checks;
- revocation;
- canonical Vishnu profile protection;
- disabled passthrough;
- bounded style/profile selection;
- watermark propagation;
- source-audio fallback and fail-closed behavior; and
- lazy OpenVoice initialization when local model files are absent.

A deployment that enables the real engine still requires separate live qualification with the exact locally provisioned OpenVoice code revision, model/checkpoint set, hardware/device, and representative enrolled voice. Passing normal Vishnu CI does not by itself claim that those external model assets were live-qualified.
