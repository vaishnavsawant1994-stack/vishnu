# Vishnu Voice Lab — Operational v1

This document completes the software-side operational layer described by `docs/VOICE_LAB.md`.
The canonical production authority remains `STT -> CanonicalTurnRuntime -> TTS`; Voice Lab is an isolated research, benchmark and qualification workspace and is not another assistant backend.

## Implemented operational components

- **Experiment runner** — `voice/lab/runner.py` executes only explicitly injected Lab adapters. Missing adapters fail closed. Each run uses an isolated temporary workspace and produces a qualification report.
- **Evidence history** — `voice/lab/evidence.py` stores append-only structured evidence in an explicitly created local SQLite database. It stores hashes for returned artifacts, not raw artifact bytes or raw voice audio.
- **Benchmark engine** — `voice/lab/benchmarks.py` implements dependency-light WER, CER and objective threshold evaluation for latency, real-time factor, barge-in, dropped blocks, code-switch retention and pronunciation accuracy.
- **Fixture registry** — `voice/lab/fixtures.py` covers clean speech, noise, fast/slow speech, silence, overlap, names, multilingual, code-switch, long-form and interruption scenarios. Built-ins contain metadata/text only. Sensitive local voice fixtures require an explicit consent reference.
- **Provider/model comparison** — `voice/lab/comparison.py` compares candidates only when they use the exact same ordered fixtures and complete requested metrics.
- **Regression analysis** — `voice/lab/regression.py` compares current metrics to an accepted baseline with explicit direction and tolerances. Missing baselines/metrics are blocked, never silently passed.
- **Device qualification** — `voice/lab/devices.py` makes the physical-device boundary explicit. Emulator, simulator and hosted VM evidence can never satisfy the physical acoustic gate.
- **Release candidates** — `voice/lab/release.py` creates immutable digest-bound release-candidate manifests only from full baseline-qualified evidence. Owner approval binds the exact candidate digest. It does not modify production or Git refs.
- **Owner dashboard** — `ui/voice_lab.py` exposes Overview, Conversation, STT, TTS, Voice Profiles, Voice Intelligence, Multilingual, Realtime, Audio/Sensorium, Devices, Providers & Models, Experiments, Benchmarks, Qualification and Release. It is opened from Owner Control Center beside Voice Studio.
- **Continuous completeness** — `voice/lab/components.py` is enforced by tests so a newly added `voice/lab/*.py` module cannot silently escape the operational inventory. Existing tests continue to protect top-level `voice/*.py` capability coverage.

## Privacy and isolation

Importing `voice.lab` does not open audio devices, contact providers, download models, read credentials, create an evidence database, or change production voice configuration. The evidence store is created only when an explicit caller such as the Voice Lab Owner UI instantiates it. Built-in fixtures contain no owner audio.

A runtime may expose `voice_lab_adapters` to the Owner UI. These adapters are explicit Lab composition only; the runner never imports or starts production providers by itself. If an adapter is absent, required gates are recorded as BLOCKED.

## Real-world evidence boundary

The Voice Lab software can now capture, persist, compare and qualify real provider/model/device evidence, but it cannot truthfully manufacture that evidence. OpenVoice checkpoints, VoiceStudio deployments, provider-native routes and real phones/computers still require runs against the exact deployed model/checkpoint/revision and hardware.

Physical acoustic qualification requires a real physical device with microphone and speaker routes, Bluetooth, echo, noise, route-switch and measured acoustic-latency evidence plus an attestation. Android Emulator, iOS Simulator and hosted desktop VM runs remain useful software qualification but are categorically blocked from satisfying the physical acoustic gate.

## Release boundary

A Voice Lab release candidate is only a request-ready manifest. Preparing or owner-approving it never edits production configuration, changes the canonical authority path, merges a branch, or updates a Git ref. Production promotion remains a separate governed action after exact-head CI/security review and explicit owner approval.

Telephony remains a separate future communications capability and is not a condition for Voice Lab v1 software completeness.
