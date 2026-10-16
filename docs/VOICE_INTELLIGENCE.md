# Vishnu Voice Intelligence

Vishnu Voice Intelligence is the provider-agnostic presentation layer around the existing Vishnu voice runtime. It does not replace `ModelRouter`, `RealtimeVoiceSession`, the governed OpenVoice profile registry, approvals, device trust, or any other existing authority.

## Architecture

The intended flow is:

```text
conversation / user context
        |
        v
VoiceDirector
  persona + bounded expression + language + owner preferences
        |
        +--> pronunciation hints
        +--> device route requirements
        +--> avatar expression
        |
        v
existing ModelRouter.synthesize()
        |
        +--> selected TTS provider
        |
        +--> optional governed OpenVoice conversion
        |
        v
quality inspection
        |
        +--> application-level chunk streaming / cancellation
        +--> playback
        +--> estimated avatar cues when provider timestamps are unavailable
```

OpenVoice remains an optional post-TTS timbre-conversion provider. Vishnu does not depend on OpenVoice for its identity, conversation runtime, TTS routing, emotion/context analysis, barge-in behavior, or device trust.

## Voice personas and packs

A `VoicePersona` describes presentation policy instead of a raw model. It may include a stable governed voice-profile ID, default language, bounded expression style, speaking-rate preference, pitch/energy intent, formality, avatar expression, and character identity.

Built-in packs are:

- Vishnu Original
- Vishnu Warm
- Vishnu Professional
- Vishnu Storyteller
- Vishnu Calm
- Vishnu Energetic

Owner-created personas are stored locally under the Vishnu data directory. Built-in packs cannot be overwritten through the Voice Intelligence service.

A persona can reference only a stable enrolled voice-profile ID. It cannot contain arbitrary reference-audio paths or remote clone URLs.

## Voice Director

`VoiceDirector` deterministically resolves a voice plan from:

- explicit/manual style
- persisted owner preferences
- selected persona
- bounded emotion/context labels
- intent
- urgency
- language
- character
- privacy/offline requirements

Precedence is explicit rather than model-defined. Manual owner choices win over inferred context. Emotion labels are contextual signals; they are not claims that Vishnu experiences feelings or consciousness.

The bounded expression vocabulary is:

`neutral`, `warm`, `cheerful`, `calm`, `empathetic`, `serious`, `urgent`, and `storytelling`.

The legacy voice-conversion contract uses `normal`; the Voice Intelligence service maps canonical `neutral` to `normal` at that boundary so the existing OpenVoice integration remains compatible.

## Expression and prosody boundary

Vishnu now plans speaking rate, pitch intent, energy, formality, and expression style in a provider-agnostic `VoicePlan`. Actual acoustic realization depends on the selected TTS/conversion provider.

This distinction is intentional. OpenVoice's current Vishnu adapter is a timbre/tone-color conversion step, not a complete emotional prosody engine. Vishnu therefore does not claim that every provider can realize every planned rate, pitch, energy, or emotional nuance. Future providers can consume these plan fields without changing the persona or governance model.

## Multiple speakers

`VoiceUtterance` plus `VoiceDirector.plan_dialogue()` supports sequences in which different utterances use different personas, languages, styles, and enrolled voices. `VoiceIntelligenceService.synthesize_dialogue()` executes those plans through the existing model router.

This enables provider-independent foundations for narration, lessons, stories, character dialogue, podcast-style output, and other multi-speaker experiences without introducing another synthesis authority.

## Personalization

`VoicePreferenceStore` persists local per-owner presentation preferences, including:

- preferred persona
- language
- expression style
- speaking rate
- expression intensity
- formality

The store does not contain transcripts, reference audio, provider credentials, or voice-cloning consent records.

## Languages and code switching

A voice plan carries a BCP-47-like language tag. `segment_language_scripts()` provides bounded script-aware segmentation for application planning across Latin, Devanagari, Arabic, Cyrillic, and Han text.

This is deliberately not advertised as universal language detection. Actual pronunciation, accent continuity, code-switch quality, and same-speaker multilingual quality depend on the selected TTS/model/provider and must be qualified with that exact provider/model revision.

## Pronunciation intelligence

`PronunciationLexicon` stores local owner-defined pronunciation hints for names, brands, technical terms, abbreviations, medicines, projects, and other vocabulary.

The lexicon returns matching hints to the synthesis layer. It does not silently rewrite the semantic source text and does not retain the spoken transcript.

## Streaming and interruption

`VoiceIntelligenceService.synthesize_stream()` provides sentence-biased application-level chunk streaming and accepts a cancellation callback. That allows the existing realtime voice runtime to stop generating later chunks when a barge-in or stale-output event occurs.

This is not a claim that OpenVoice performs native incremental streaming conversion. Native provider streaming remains provider-specific. `RealtimeVoiceSession` continues to own live microphone interaction, barge-in, stale-output handling, and cancellation authority.

## Quality inspection

`VoiceQualityEvaluator` performs dependency-light WAV checks for:

- readable WAV structure
- duration
- sample rate and channels
- peak and RMS levels
- excessive silence
- clipping

It does not transcribe or semantically inspect audio. Provider retry/fallback decisions can consume the quality report in future routing work without exposing raw speech in ordinary status/telemetry.

## Device continuity

A `VoicePlan` includes route requirements for language, privacy, offline operation, streaming preference, and whether governed conversion is requested. `VoiceDeviceCapabilities` can determine whether a device can satisfy that plan.

This creates a stable contract for preserving the same Vishnu persona across desktop, mobile, browser, car, speaker, or other trusted surfaces while allowing each surface to use the best permitted local/provider implementation. Actual provider availability and model parity must still be qualified per device.

## Avatar and character synchronization

A plan includes a bounded avatar expression. `estimated_avatar_cues()` can generate coarse mouth/viseme timing from final audio duration when a TTS provider does not supply phoneme timestamps.

These cues are explicitly marked `estimated`. Provider-supplied phoneme/viseme timestamps should replace them when available. This prevents approximate animation from being represented as phoneme-accurate alignment.

## Voice Studio

The desktop Owner Control Center exposes **Voice Studio** for:

- choosing the default Vishnu persona
- selecting language and expression preferences
- adjusting speaking-rate preference, expression intensity, and formality
- generating a bounded test sentence
- creating/deleting custom personas
- associating a persona with an already-authorized governed voice profile
- enrolling a local WAV with explicit consent attestation and owner reauthentication
- revoking or deleting non-canonical authorized voice profiles
- managing pronunciation hints
- reviewing privacy-safe voice status

Enrollment/revocation/deletion reuse the existing `VoiceProfileRegistry`. Voice Studio does not create a second clone/profile database.

## Safety and governance

The existing governed voice rules remain authoritative:

- explicit consent attestation is required for enrollment
- voice references are local files managed by the profile registry
- remote reference URLs and arbitrary synthesis-time clone paths are not supported
- the canonical Vishnu voice is protected from ordinary revoke/delete operations
- profile integrity is verified before conversion
- OpenVoice watermark configuration is retained
- model/checkpoint assets are local and are not silently downloaded
- ordinary voice status does not expose raw transcripts, raw audio, reference files, or reference hashes
- consequential profile changes in Voice Studio require owner reauthentication

## Deployment and qualification boundary

Repository support does not bundle OpenVoice model/checkpoint assets and does not enable OpenVoice by default. A deployment that enables real conversion must provision exact local assets and qualify them against the target hardware, operating system, TTS provider, language mix, reference voice, latency target, and model revision.

Likewise, provider-native emotional prosody, phoneme-accurate avatar timing, native streaming conversion, and cross-device acoustic parity are capabilities of specific model/provider/device combinations. The Voice Intelligence layer provides the stable plan, policy, management, and integration contracts for those capabilities without making unsupported runtime claims.
