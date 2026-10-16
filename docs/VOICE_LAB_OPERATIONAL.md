# Vishnu Voice Lab — Operational v1

This document defines the software-side operational Voice Lab. The canonical production authority remains `STT -> CanonicalTurnRuntime -> TTS`; Voice Lab is an isolated research, benchmark and qualification workspace, not another assistant backend.

## Completed operational components

- **Experiment runner** — explicit Lab adapters only, isolated temporary workspaces, fail-closed missing adapters, bounded deadlines, cooperative cancellation and cleanup.
- **Hard-bounded external experiments** — `BoundedSubprocessAdapter` runs a fixed absolute argv with `shell=False`, bounded JSON I/O and forced terminate/kill on cancellation or deadline. It strips credential-like experiment metadata before handing work to the child process.
- **Evidence history** — append-only structured local SQLite evidence with exact experiment family, provider/model/revision, device/OS, route, fixture IDs, privacy-safe configuration, timestamps, metrics, gates, provenance and artifact SHA-256 digests. Artifact/raw-audio bytes are not stored in the evidence database.
- **Benchmark engine** — dependency-light WER, CER, endpoint latency, first-audio latency, real-time factor, barge-in latency, dropped blocks, code-switch retention and pronunciation gates plus reliability/failure-recovery, CPU/memory and objective signal-quality metrics. The acoustic score is an engineering signal metric and is not presented as MOS or human preference.
- **Fixture registry** — clean speech, noise, fast/slow speech, silence, overlap, names, multilingual, code-switch, long-form and interruption scenarios. Sensitive local voice fixtures require explicit consent; remote audio URLs are rejected.
- **Provider/model comparison** — candidates are comparable only when they use the exact same ordered fixtures and complete requested metrics. Results carry privacy, hardware, licensing, cost and reliability context beside quality/latency scores; missing context remains explicit.
- **Automatic regression analysis** — owner-accepted immutable baselines are keyed to a stable experiment family. Later provider/model/config runs automatically receive a `baseline-regression` gate. Missing metrics block the regression rather than silently passing it.
- **Device qualification bridge** — bounded Android Emulator, iOS Simulator and desktop VM evidence can be translated into software qualification evidence without importing the separate native-device runtime. It can never satisfy the physical-acoustic gate.
- **Physical qualification boundary** — real physical evidence requires microphone/speaker routes, Bluetooth, echo, noise, route-switch, measured acoustic latency and an attestation. Emulator/simulator/VM evidence is categorically blocked.
- **Telephony Lab** — provider-injected PSTN/SIP qualification is implemented as a default-off governed capability. It requires an explicit registered provider, exact owner-bound call approval by default, bounded call duration, explicit recording policy plus consent, masked/hashed destination evidence, connectivity/recording/duration gates and explicit hangup control. Recognized emergency-number calls are blocked inside Voice Lab.
- **Release candidates** — immutable digest-bound manifests require qualified evidence and exact owner approval. Promotion policy additionally requires telephony-specific gates before a telephony target can be promoted. The release manager and promotion evaluator never change production or Git refs.
- **Owner dashboard** — Owner Control Center exposes Voice Lab beside Voice Studio. It includes Overview, Conversation, STT, TTS, Voice Profiles, Voice Intelligence, Multilingual, Realtime, Audio/Sensorium, Devices, Providers & Models, Telephony, Experiments, Benchmarks, Qualification and Release. Experiment cancellation, evidence comparison, immutable baseline acceptance, telephony policy/provider status and release controls are operator-visible.
- **Continuous completeness** — tests enforce both the top-level `voice/*.py` capability inventory and the `voice/lab/*.py` operational-module registry.

## Cancellation and timeout contract

In-process Lab adapters receive `LabRunControl` and cooperate through `control.checkpoint()`. Vishnu deliberately does not use unsafe Python thread termination. For experiments that need a hard process boundary, `BoundedSubprocessAdapter` terminates the child when cancellation/deadline is observed and kills it if it ignores the termination grace period.

The Owner UI runs experiments on a worker thread, exposes Cancel and refuses to silently treat an unacknowledged in-process cancellation as successful completion.

## Telephony boundary

Telephony software is implemented, but no external phone provider is silently enabled. A runtime must explicitly inject `voice_lab_telephony_providers`; live providers additionally require `allow_live_provider=True`. The default policy is disabled and denies inbound/outbound calling and recording.

A telephony call request is bound to a deterministic request ID and SHA-256 destination fingerprint. Evidence views use the fingerprint and a masked destination rather than the raw phone number. Recording requires the request consent reference, policy permission and exact approval permission.

Voice Lab refuses recognized emergency destinations. It is a qualification framework, not an emergency calling service. Provider credentials, allocated phone numbers, caller identity, billing, country-specific consent/recording law, anti-abuse controls and real call quality are deployment-specific evidence and configuration; they are not fabricated by the repository.

## Privacy and isolation

Importing `voice.lab` does not open audio devices, contact providers, download models, read credentials, create an evidence database, allocate a phone number, place a call, record a call, or change production voice configuration. The database is created only when an explicit caller instantiates `EvidenceStore`.

Configuration keys that look credential-bearing are persisted only as SHA-256 digests; consent references are also persisted by digest in experiment evidence. Built-in fixtures contain no owner audio. A runtime may expose `voice_lab_adapters` and telephony adapters to the Owner UI, but no adapter is contacted merely because it is registered.

## Real-world evidence boundary

The software can capture, persist, compare and qualify real provider/model/device/call evidence, but it cannot truthfully manufacture it. OpenVoice checkpoints, VoiceStudio deployments, provider-native routes, actual PSTN/SIP providers and real phones/computers still require runs against the exact deployed model/checkpoint/revision/provider and hardware.

Android Emulator, iOS Simulator and hosted desktop VM runs remain useful software qualification but cannot become physical acoustic evidence.

## Release boundary

Preparing or owner-approving a Voice Lab release candidate never edits production configuration, changes canonical authority, merges a branch or updates a Git ref. Production promotion remains a separate governed action after exact-head CI/security review, scenario-specific evidence and explicit owner approval.
