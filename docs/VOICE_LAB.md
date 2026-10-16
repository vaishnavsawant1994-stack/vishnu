# Vishnu Voice Lab

## Purpose

Vishnu Voice Lab is the isolated engineering and qualification area for voice work.

The Lab exists so Vishnu can aggressively test providers, models, devices, speech styles, voice conversion, multilingual behavior, latency, interruption, avatar timing, Sensorium audio, telephony and future voice capabilities **without making an experimental provider a second Vishnu brain and without silently changing production voice behavior**.

The Lab does not define "perfect" as a marketing label. Its target is complete workstream coverage plus objective, repeatable evidence. A provider/model/device/call combination is qualified only when every required gate for that exact combination passes.

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

Provider-native speech-to-speech implementations, including OpenAI Realtime, may be exercised in the Lab for compatibility and qualification. They do not silently become a second assistant, conversation authority, tool authority, approval authority or memory authority.

Any proposal to change that boundary requires a separate architecture/security review and explicit owner approval. The Voice Lab cannot auto-promote it.

## Isolation rules

Importing `voice.lab` is inert. The Lab:

- does not start a microphone or speaker;
- does not start VoiceStudio, OpenVoice, OpenAI Realtime or another provider;
- does not download models or checkpoints;
- does not read or copy provider credentials;
- does not allocate phone numbers or place calls;
- does not start call recording;
- does not change production environment variables or configuration;
- does not attach tools or grant approvals;
- does not mutate devices, profiles, memory or Sensorium state;
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
13. audio quality evaluation;
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
29. governed provider-injected telephony/PSTN/SIP qualification;
30. real physical-device acoustic qualification as required evidence;
31. cross-provider/model/device parity as required evidence.

A capability is never marked production-qualified merely because a neighboring subsystem exists. `GAP` and `QUALIFICATION_REQUIRED` remain first-class states where appropriate; an `IMPLEMENTED` software framework can still require exact live evidence before a concrete provider/device route is promoted.

The focused test suite also scans every top-level `voice/*.py` module and every `voice/lab/*.py` operational module. New voice code must be represented in the capability/completeness registries instead of silently becoming an untracked surface.

## What 100% voice workstream coverage means

It means every known voice workstream is represented and cannot disappear from qualification by accident. It does **not** mean every voice sounds perfect on every language, microphone, speaker, phone, operating system, provider or model.

Real acoustic quality must be measured for the exact tuple:

```text
provider + model/checkpoint/revision + language + voice/profile +
input device + output device + operating system + route
```

A change to one member of that tuple may require requalification.

For telephony the tuple additionally includes the exact telephony provider, destination/country class, call direction, media route, recording policy and network conditions.

## Experiment specifications and execution

`VoiceExperimentSpec` creates deterministic experiment IDs from the complete immutable test definition. Every experiment names its exact provider, model, device, language, route, fixtures and required gates.

Raw voice retention defaults to disabled. If a Lab test genuinely requires temporary raw audio, it must explicitly enable retention, use a bounded duration of at most one hour and include an explicit consent reference. Voice-biometric experiments also require an explicit consent reference.

`VoiceExperimentRunner` only executes explicitly injected Lab adapters. Missing adapters fail closed. Runs use isolated temporary workspaces and persist immutable evidence rather than changing production configuration.

In-process adapters cooperate through `LabRunControl.checkpoint()`. For tests that need a hard operating-system process boundary, `BoundedSubprocessAdapter` runs a fixed absolute argv with `shell=False`, bounded JSON input/output and terminate/kill enforcement on cancellation or deadline. Credential-like experiment metadata is not forwarded to the child.

## Evidence and baselines

`EvidenceStore` is append-only SQLite history. Evidence records include experiment family, provider/model/revision, device/OS, language, route, fixtures, privacy-safe configuration, provenance, metrics, qualification gates, regression results and artifact digests.

Raw artifact/audio bytes are not stored in the evidence database. Accepted baselines are immutable; replacing a baseline requires a new baseline family/version rather than rewriting history.

## Benchmark and comparison system

The dependency-light benchmark layer covers:

- WER and CER;
- endpoint latency;
- first-audio latency;
- real-time factor;
- barge-in cancellation latency;
- dropped audio blocks;
- code-switch retention;
- pronunciation accuracy;
- success/failure-recovery reliability metrics;
- CPU and memory observations;
- an objective signal-quality score derived from SNR, clipping and dropped-audio ratio.

The signal-quality score is an engineering metric, not a MOS/human-naturalness claim.

Provider/model comparison requires identical ordered fixtures and complete requested numeric metrics. It also carries privacy, hardware, licensing, cost and reliability context so the numerically best model is not mistaken for an automatically suitable production choice. Missing operational context remains explicit.

## Baseline qualification gates

The baseline report is fail-closed and requires all configured baseline gates, including:

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

Each harness records observed values and thresholds. Missing, duplicated, blocked, failed or not-run required gates fail qualification rather than being converted into a pass by assumption.

Special workstreams add gates. Real-device promotion requires a `physical-device-acoustics` pass from a real device. Telephony promotion requires its complete telephony gate family.

## Automatic regression analysis

An owner may accept a fully passing evidence record as an immutable baseline for its experiment family. Later comparable runs automatically receive a `baseline-regression` gate. WER/CER, endpoint/first-audio/barge-in latency, real-time factor, dropped blocks, code-switch retention and pronunciation are direction-aware with bounded degradation tolerances. Missing baseline/current metrics block the regression rather than passing by omission.

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
| Reliability | crash/restart, cancellation, hard timeout, malformed provider output |
| Resources | CPU, working memory/peak memory and provider/runtime constraints |
| Licensing | code license, weight license, redistribution, commercial policy |
| Avatar | expression/viseme alignment and provider-timestamp vs estimated timing |
| Telephony | sandbox/live provider, inbound/outbound policy, owner approval, recording consent, connection, duration, hangup, billing/jurisdiction evidence |

No single synthetic fixture can replace this matrix.

## Provider-specific boundaries

### OpenVoice

OpenVoice remains optional governed post-TTS conversion. Vishnu does not imply that upstream model assets/checkpoints are bundled or qualified. Promotion requires the exact revision, model/checkpoint, source embedding, hardware, license/provenance and measured output.

### VoiceStudio

VoiceStudio remains a separately running external service. Vishnu's integration does not imply that VoiceStudio source, model weights, Electron application, Python backend or engine dependencies are vendored into Vishnu. Exact deployment and model licensing must be reviewed before production use.

VoiceStudio MCP starts inert from Vishnu's perspective: discovery and execution stay under Universal Capabilities, ToolRegistry, ApprovalManager, audit, revocation and provider-enforced risk floors.

### OpenAI Realtime

The implementation is a compatibility/qualification route. It does not replace the canonical production authority just because it can do provider-native speech-to-speech or tool-call transport.

## Telephony

Telephony is implemented in Voice Lab as a provider-agnostic governed qualification framework in `voice/lab/telephony.py`. It does not silently create or purchase a phone number and does not assume any particular vendor.

The default policy is off. Inbound/outbound calling, recording and live-provider use are independently controlled. A call request binds provider, destination fingerprint, purpose, direction and recording/consent state to a deterministic request ID. Exact owner approval is required by default.

No provider is contacted unless the complete preflight policy passes. Sandbox providers may be injected for qualification. Live providers require explicit live-provider permission. Evidence uses a masked destination and SHA-256 fingerprint rather than the raw destination.

Recording requires all three: policy permission, an explicit consent reference and exact approval that permits recording. Provider-reported recording state must match the approved request.

Voice Lab blocks recognized emergency-number destinations. It is not an emergency calling service. Actual PSTN/SIP credentials, allocated numbers, caller identity, billing, abuse controls, country/jurisdiction-specific consent and recording rules, and real call quality remain deployment-specific configuration/evidence.

Telephony promotion additionally requires passing gates for enablement, direction policy, provider boundary, exact owner approval, recording consent, emergency boundary, connectivity, recording state, duration bound and hangup control. A generic STT/TTS report cannot promote telephony.

## Physical-device qualification

Android Emulator, iOS Simulator and hosted desktop VM evidence is useful for software qualification but does not establish microphone, speaker, echo, Bluetooth, route switching, interruption, acoustic latency or noisy-environment quality on physical hardware.

Physical-device promotion requires a dedicated real-device evidence gate.

## Owner Voice Lab UI

Owner Control Center exposes Voice Lab beside Voice Studio. Voice Lab contains:

- Overview;
- Conversation;
- STT;
- TTS;
- Voice Profiles;
- Voice Intelligence;
- Multilingual;
- Realtime;
- Audio / Sensorium;
- Devices;
- Providers & Models;
- Telephony;
- Experiments;
- Benchmarks;
- Qualification;
- Release.

The UI runs isolated experiments, supports cancellation, exposes recent immutable evidence, exact-fixture provider/model comparison, baseline acceptance, telephony policy/provider status and immutable release-candidate preparation/owner approval. It never auto-enables a provider or auto-promotes production.

## Promotion policy

`voice/lab/promotion.py` only evaluates a request; it cannot perform a promotion.

Promotion is blocked when:

- a target capability is unknown or is a known `GAP`;
- any required report gate is missing, duplicated, blocked, failed or not run;
- canonical authority preservation is not proven;
- model licensing/provenance/integrity is not proven;
- no-raw-audio-retention behavior is not proven;
- profile conversion lacks consent/revocation/integrity evidence;
- a telephony target lacks its telephony-specific live evidence gates;
- a physical-device target lacks real physical acoustic evidence;
- an authority-changing proposal lacks architecture/security review;
- the owner has not explicitly approved promotion.

This is intentionally stricter than a normal feature flag.

## Definition of done for a Voice Lab v1 software release candidate

A Voice Lab v1 software release candidate is ready to *request* production promotion only when:

1. all target workstreams are in the catalog;
2. there are no unresolved `GAP` targets;
3. the exact experiment specification is reproducible;
4. all baseline and scenario-specific gates pass;
5. privacy, consent, deletion, revocation and no-retention behavior pass;
6. model/provider licenses, provenance and hashes are exact;
7. cancellation, hard timeout, stale-output and provider-failure behavior pass;
8. provider/model comparison carries quality plus operational context;
9. the canonical Vishnu authority is preserved or a separate approved architecture/security change exists;
10. telephony targets have exact provider/call/consent/emergency/hangup evidence;
11. real devices have passed where physical-device claims are made;
12. the owner explicitly approves the separate promotion.

The repository can complete the framework and its qualification machinery. It must never fabricate unavailable real-world provider, legal, phone-number or physical-hardware evidence. Voice Lab should make untested claims harder, not easier.
