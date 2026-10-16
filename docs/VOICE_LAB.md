# Vishnu Voice Lab

## Purpose

Vishnu Voice Lab is the isolated engineering and qualification area for voice work.

The Lab exists so Vishnu can aggressively test providers, models, devices, speech styles, voice conversion, multilingual behavior, latency, interruption, avatar timing, Sensorium audio, and future voice capabilities **without making an experimental provider a second Vishnu brain and without silently changing production voice behavior**.

The Lab does not define "perfect" as a marketing label. Its target is complete workstream coverage plus objective, repeatable evidence. A provider/model/device combination is qualified only when every required gate for that exact combination passes.

## Non-negotiable authority boundary

The canonical Vishnu production route remains:

```text
microphone / audio
    -> STT
    -> CanonicalTurnRuntime
    -> canonical Vishnu answer + ToolRegistry + ApprovalManager authority
    -> TTS
    -> local or trusted-device playback
```

Provider-native speech-to-speech implementations, including OpenAI Realtime, may be exercised in the Lab for compatibility and qualification. They do not silently become a second assistant, conversation authority, tool authority, approval authority, or memory authority.

Any proposal to change that boundary requires a separate architecture/security review and explicit owner approval. The Voice Lab cannot auto-promote it.

## Isolation rules

Importing `voice.lab` is inert. The Lab:

- does not start a microphone or speaker;
- does not start VoiceStudio, OpenVoice, OpenAI Realtime, or another provider;
- does not download models or checkpoints;
- does not read or copy provider credentials;
- does not change production environment variables or configuration;
- does not attach tools or grant approvals;
- does not mutate devices, profiles, memory, or Sensorium state;
- does not retain raw audio by default;
- does not merge or promote itself to production.

Production promotion is a separate, explicit act after qualification.

## Complete workstream coverage

The catalog in `voice/lab/catalog.py` tracks the full inspected Vishnu voice surface, including:

1. microphone capture and input/output device selection;
2. adaptive VAD and semantic endpointing;
3. local/offline STT and pluggable provider STT;
4. the canonical STT -> Vishnu runtime -> TTS authority bridge;
5. pluggable TTS and application-level chunk streaming;
6. barge-in cancellation and stale-output rejection;
7. personas, built-in voice packs, bounded style and affect/context signals;
8. multilingual planning, code switching and pronunciation lexicon;
9. bounded long-form speech;
10. voice-profile enrollment, consent, provenance, revocation and deletion;
11. governed OpenVoice tone-color/timbre conversion;
12. encrypted voice-profile import/export;
13. WAV/audio quality evaluation;
14. avatar expression and estimated viseme cues;
15. trusted-device synthesized-audio routing;
16. OpenAI Realtime compatibility and its governed tool bridge;
17. VoiceStudio HTTP provider integration and governed VoiceStudio MCP;
18. local audio/video transcription intelligence;
19. Sensorium Vision + Voice and environmental audio;
20. model license, provenance, hash/integrity and readiness governance;
21. raw-audio privacy and retention controls;
22. provider failure isolation, fallback and teardown;
23. strict default-off runtime configuration;
24. typed provider contracts and the governed voice registry;
25. isolated runtime lifecycle and teardown;
26. five-tier voice inference scheduling;
27. Sensorium SpeechIntent bridging without action authority;
28. local wake-phrase activation;
29. telephony/PSTN/SIP as an explicit current gap;
30. real physical-device acoustic qualification as required evidence;
31. cross-provider/model/device parity as required evidence.

A capability is never marked implemented just because a neighboring subsystem exists. `GAP` and `QUALIFICATION_REQUIRED` are first-class states.

The focused test suite also scans every top-level `voice/*.py` module and requires it to appear in at least one catalog evidence path. Adding a new voice module without cataloging its workstream therefore fails the Voice Lab coverage test instead of silently creating an untracked voice surface.

## What 100% voice workstream coverage means

It means every known voice workstream is represented and cannot disappear from qualification by accident. It does **not** mean every voice sounds perfect on every language, microphone, speaker, phone, operating system, provider or model.

Real acoustic quality must be measured for the exact tuple:

```text
provider + model/checkpoint/revision + language + voice/profile +
input device + output device + operating system + route
```

A change to one member of that tuple may require requalification.

## Experiment specifications

`VoiceExperimentSpec` creates deterministic experiment IDs from the complete immutable test definition. This makes repeated runs comparable and prevents ambiguous "we tested voice" claims.

Every experiment names its exact provider, model, device, language, route, fixtures and required gates. Raw voice retention defaults to disabled. If a Lab test genuinely requires temporary raw audio, it must explicitly enable retention, use a bounded duration of at most one hour, and include an explicit consent reference. Voice-biometric experiments also require an explicit consent reference.

The specification is policy metadata only; it does not itself store audio.

## Baseline qualification gates

The baseline report is fail-closed and requires all of these gates:

- STT word error rate (WER);
- STT character error rate (CER);
- semantic endpoint latency;
- first-audio latency;
- real-time factor;
- barge-in cancellation latency;
- dropped audio blocks;
- stale-output rejection;
- code-switch retention;
- pronunciation accuracy;
- canonical authority preservation;
- no raw-audio retention;
- enrollment consent / revocation / integrity;
- model license / provenance / hash integrity;
- provider failure / fallback behavior;
- device-route correctness;
- MCP provider risk-floor enforcement.

Each harness should record the observed value and threshold used. Missing, duplicated, blocked, failed or not-run required gates fail qualification rather than being converted into a pass by assumption.

Special workstreams add gates. Real-device promotion requires a `physical-device-acoustics` pass from a real device. Emulator or simulator evidence does not satisfy it.

## Recommended qualification matrix

| Dimension | Required coverage |
| --- | --- |
| Route | canonical local, trusted-device output, each optional provider route |
| STT | local/offline plus every enabled external provider/model |
| TTS | every enabled provider/model/voice |
| Language | each supported production language plus intended code-switch pairs |
| Device | supported desktop/mobile class; real devices for physical qualification |
| Network | offline where supported, normal, latency, loss, provider unavailable |
| Conversation | short, long, interruption, rapid turn-taking, silence/noise |
| Speech | quiet/loud, fast/slow, intended accents, names/lexicon |
| Privacy | no retention, consent, revoke/delete, import/export, logs/audit |
| Security | tool risk floor, approvals, reauth, emergency stop, stale output |
| Reliability | crash/restart, cancellation, timeout, malformed provider output |
| Licensing | code license, weight license, redistribution, commercial policy |
| Avatar | expression/viseme alignment and provider-timestamp vs estimated timing |

No single synthetic fixture can replace this matrix.

## Provider-specific boundaries

### OpenVoice

OpenVoice remains optional governed post-TTS conversion. Vishnu does not imply that upstream model assets/checkpoints are bundled or qualified. Promotion requires the exact revision, model/checkpoint, source embedding, hardware, license/provenance and measured output.

### VoiceStudio

VoiceStudio remains a separately running external service. Vishnu's integration does not imply that VoiceStudio AGPL source, model weights, Electron application, Python backend or engine dependencies are vendored into Vishnu. Exact deployment and model licensing must be reviewed before production use.

VoiceStudio MCP starts inert from Vishnu's perspective: discovery and execution stay under Universal Capabilities, ToolRegistry, ApprovalManager, audit, revocation and provider-enforced risk floors.

### OpenAI Realtime

The implementation is a compatibility/qualification route. It does not replace the canonical production authority just because it can do provider-native speech-to-speech or tool-call transport.

## Telephony

The inspected Vishnu voice architecture does not currently establish a PSTN/SIP/Twilio-style phone-calling stack. Voice conversation is not the same as telephony.

The Lab therefore marks `telephony` as a `GAP`. Future telephony work must be a separate governed capability with identity, consent, call-state, recording, jurisdiction, emergency-call, abuse, cost, provider, audit and approval boundaries rather than being inferred from microphone/TTS support.

## Physical-device qualification

Android Emulator, iOS Simulator and hosted desktop VM evidence is useful for software qualification but does not establish microphone, speaker, echo, Bluetooth, route switching, interruption, acoustic latency or noisy-environment quality on physical hardware.

Physical-device promotion requires a dedicated real-device evidence gate.

## Promotion policy

`voice/lab/promotion.py` only evaluates a request; it cannot perform a promotion.

Promotion is blocked when:

- a target capability is unknown or is a known `GAP`;
- any required report gate is missing, duplicated, blocked, failed or not run;
- canonical authority preservation is not proven;
- model licensing/provenance/integrity is not proven;
- no-raw-audio-retention behavior is not proven;
- profile conversion lacks consent/revocation/integrity evidence;
- a physical-device target lacks real physical acoustic evidence;
- an authority-changing proposal lacks architecture/security review;
- the owner has not explicitly approved promotion.

This is intentionally stricter than a normal feature flag.

## Definition of done for a voice release candidate

A voice release candidate is ready to *request* production promotion only when:

1. all target workstreams are in the catalog;
2. there are no unresolved `GAP` targets;
3. the exact experiment specification is reproducible;
4. all baseline and scenario-specific gates pass;
5. privacy, consent, deletion, revocation and no-retention behavior pass;
6. model/provider licenses, provenance and hashes are exact;
7. cancellation, stale-output and provider-failure behavior pass;
8. the canonical Vishnu authority is preserved or a separate approved architecture/security change exists;
9. real devices have passed where physical-device claims are made;
10. the owner explicitly approves the separate promotion.

The Voice Lab should make untested claims harder, not easier.
