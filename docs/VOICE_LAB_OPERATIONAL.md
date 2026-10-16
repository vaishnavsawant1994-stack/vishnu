# Vishnu Voice Lab — Operational v1

This completes the software-side operational layer described by `docs/VOICE_LAB.md`. The canonical production authority remains `STT -> CanonicalTurnRuntime -> TTS`; Voice Lab is an isolated research, benchmark and qualification workspace and is not another assistant backend.

## Completed operational components

- **Experiment runner** — explicit Lab adapters only, isolated temporary workspace, fail-closed missing adapters, bounded deadlines, first-class cooperative cancellation control and cleanup.
- **Evidence history** — append-only structured local SQLite evidence with exact experiment family, provider/model/revision, device/OS, route, fixture IDs, privacy-safe configuration, timestamps, metrics, gates, provenance and artifact SHA-256 digests. Artifact/raw-audio bytes are not stored in the evidence database.
- **Benchmark engine** — dependency-light WER, CER, endpoint latency, first-audio latency, real-time factor, barge-in latency, dropped blocks, code-switch retention and pronunciation threshold gates.
- **Fixture registry** — clean speech, noise, fast/slow speech, silence, overlap, names, multilingual, code-switch, long-form and interruption scenarios. Sensitive local voice fixtures require explicit consent; remote audio URLs are rejected.
- **Provider/model comparison** — candidates are comparable only when they use the exact same ordered fixtures and complete requested metrics. The Owner UI exposes evidence comparison.
- **Automatic regression analysis** — owner-accepted immutable baselines are keyed to a stable experiment family. Later provider/model/config runs in that family automatically receive a `baseline-regression` gate. Missing metrics block the regression rather than silently passing it.
- **Device qualification bridge** — bounded Android Emulator, iOS Simulator and desktop VM evidence can be translated into software qualification evidence without importing the separate native-device branch/runtime. It can never satisfy the physical-acoustic gate.
- **Physical qualification boundary** — real physical evidence requires microphone/speaker routes, Bluetooth, echo, noise, route-switch, measured acoustic latency and an attestation. Emulator/simulator/VM evidence is categorically blocked.
- **Release candidates** — immutable digest-bound manifests require every baseline gate exactly once and PASS plus all scenario/regression gates PASS. Owner approval binds the exact manifest. The release manager never changes production or Git refs.
- **Owner dashboard** — Owner Control Center exposes Voice Lab beside Voice Studio. It includes Overview, Conversation, STT, TTS, Voice Profiles, Voice Intelligence, Multilingual, Realtime, Audio/Sensorium, Devices, Providers & Models, Experiments, Benchmarks, Qualification and Release; experiment cancellation, evidence comparison and immutable baseline acceptance are operator-visible.
- **Continuous completeness** — tests enforce both the top-level `voice/*.py` capability inventory and the `voice/lab/*.py` operational-module registry.

## Cancellation and timeout contract

Lab adapters receive `LabRunControl`. They must call `control.checkpoint()` around bounded units of work and terminate their own subprocess/network operation when cancellation/deadline is observed. Vishnu deliberately does not use unsafe Python thread termination. The Owner UI runs an experiment on a worker thread, exposes Cancel, and refuses to close the Lab while an adapter has not yet acknowledged cancellation.

## Privacy and isolation

Importing `voice.lab` does not open audio devices, contact providers, download models, read credentials, create an evidence database, or change production voice configuration. The database is created only when an explicit caller instantiates `EvidenceStore`. Configuration keys that look credential-bearing are persisted only as SHA-256 digests; consent references are also persisted by digest. Built-in fixtures contain no owner audio.

A runtime may expose `voice_lab_adapters` to the Owner UI. These adapters are explicit Lab composition only; the runner never imports or starts production providers by itself. If an adapter is absent, required gates are recorded as BLOCKED.

## Real-world evidence boundary

The software can capture, persist, compare and qualify real provider/model/device evidence, but it cannot truthfully manufacture it. OpenVoice checkpoints, VoiceStudio deployments, provider-native routes and real phones/computers still require runs against the exact deployed model/checkpoint/revision and hardware.

Android Emulator, iOS Simulator and hosted desktop VM runs remain useful software qualification but cannot become physical acoustic evidence. Telephony remains a separate future communications capability and is not a condition for Voice Lab v1 software completeness.

## Release boundary

Preparing or owner-approving a Voice Lab release candidate never edits production configuration, changes canonical authority, merges a branch or updates a Git ref. Production promotion remains a separate governed action after exact-head CI/security review and explicit owner approval.
