# Vishnu — Production Readiness, Owner Trust & Universal Continuity

This campaign turns Vishnu's existing identity, device, data-plane, memory,
automation, Sensorium, security and release authorities into one production
readiness and continuity model. It does **not** replace those authorities and it
does not make perception, prediction, memory, learning or planning equivalent to
execution permission.

## Permanent authority boundary

- Knowing something does not authorize action.
- Predicting an action does not authorize action.
- Learning a procedure does not authorize action.
- A continuity handoff does not broaden data permissions.
- A production-readiness record does not manufacture signing credentials or
  physical-device evidence.
- Computer, device, IoT, sensor and tool actions remain governed by Vishnu's
  existing policy, device, approval and execution authorities.

## 1. Production readiness and owner trust

`trust_continuity.production` provides fail-closed, exact-commit readiness
records for Android signing, iOS distribution/provisioning, Windows
Authenticode, macOS signing/notarization, container attestation, deployment
worker identity, backup/restore drills, rollback drills and health
observability. Evidence stores only references, SHA-256 digests and bounded
metadata; secret material is rejected.

`DeploymentTransaction` records crash-safe prepare/install/health/commit or
rollback phases and refuses a commit without a verified health check. The
existing release/update authority still performs the real update.

`OperationalHealthMonitor` records bounded probe, metric and crash/recovery
checkpoint evidence. `BackupRestoreVerifier` verifies restored bytes by digest.

Real production certificates, provisioning profiles, notarization authority,
container signing identity and production worker credentials remain externally
owned. CI cannot create or claim them.

## 2. Physical-device L4 qualification

`PhysicalL4Qualification` accepts only `physical_device` evidence and rejects
emulators, simulators, hosted VMs, virtual simulation and CI runners. Evidence
is exact-commit-bound and requires battery, thermal, background restriction,
permission UI and disconnect/reconnect metrics plus scenario results and a
SHA-256 evidence digest.

The existing Sensorium physical workflow remains the mechanism that must run on
actual hardware. A repository implementation or L3 emulator/simulator pass is
not an L4 certificate.

## 3. Universal owner identity and recovery

`UniversalOwnerRecovery` can restore from a recovery code, encrypted recovery
package or passkey proof without requiring approval from a lost or designated
master device. Owner authentication, trusted-device registration and device
revocation are callbacks into Vishnu's canonical authorities. A successful
lost-device restore can immediately revoke the lost device.

## 4. Multi-device continuity

`MultiDeviceContinuity` preserves the existing policies:

- `device_only`: state remains on the current device and cannot be handed off.
- `progress_only`: only bounded progress/resume metadata is retained for
  continuity.
- `sync_everywhere`: permitted state may continue on another trusted device.
- `on_demand`: cross-device handoff requires an explicit request.

Mutation is bound to the task's current trusted device; merely being another
trusted device does not allow a stale participant to change task state.

## 5. Autonomous Work Engine 2.0

`WorkEngineV2` provides durable plans, dependency-aware steps, checkpoints,
resume state, deadlines, bounded retries, budgets, approval gates, partial
failure state, scheduling metadata and explicit stop explanations. Approval is
deny-by-default unless the existing Vishnu approval authority authorizes the
step. The engine stores orchestration state and does not execute tools itself.

## 6. Deep personal memory intelligence

`MemoryIntelligence` adds source provenance, confidence, timestamps,
contradictions, entity aliases, project timelines, consolidation, owner edits,
retention expiry, purge, export/import and `why_known` traceability. Imported
facts receive import provenance rather than inheriting secret/action authority.
Every fact explicitly carries `execution_authority=false`.

## 7. Universal integrations and OAuth

`OAuthLifecycleManager` implements provider-neutral PKCE, state validation,
account scopes, refresh, reauthentication and revocation. Access and refresh
tokens are stored only through the `SecretStore` protocol; the
`KeychainSecretStore` adapter uses Vishnu's existing security keychain and the
metadata database stores only opaque handles. Provider verification state is
retained and production consumers can fail closed on unverified providers.

## 8. Local/offline intelligence

`OfflineIntelligence` registers local STT, TTS, OCR, multimodal, embedding,
search and language-model capabilities and routes locally when available.
Cloud use is optional. Offline work can be queued and reconciled with explicit
`local_wins`, `remote_wins`, `merge_progress` or owner-mediated `manual`
policies.

## 9. Safety / Trust Center

`TrustCenter` aggregates owner-visible trust data through injected snapshot
sources and delegates Stop Sensing, Stop Actions, Revoke Device, Disconnect
Provider and Emergency Stop to canonical runtime callbacks. It has no fallback
mutation authority. `server/trust_continuity_api.py` exposes owner/device-scoped
readiness, L4, audit, continuity, work, memory, evaluation and emergency-control
routes using the existing device authentication function.

## 10. Vishnu Evaluation Lab

`EvaluationLab` records exact-commit scorecards for reasoning accuracy,
hallucination rate, task success, memory correctness, causal reasoning, action
verification, privacy violations, blocked permission bypasses, crash recovery,
device continuity, latency, cost and battery impact. Threshold failure remains
a failing scorecard; it is never rewritten as success.

## Governed future extensions

`GovernedFutureCapabilities` defines proposal/test/delegation contracts for
agent teams, learned skills, robotics, home automation, third-party skills,
emotional/social intelligence, teaching/coaching, developer SDKs and
self-improvement proposals. Even after owner approval these records retain
`execution_authority=false`; execution must be delegated to existing Vishnu
authorities.

## Runtime architecture

The target composition is:

Owner Identity
→ Goals / Life / Projects
→ Memory + Knowledge + World Model
→ Planning / Autonomous Work
→ Devices + Apps + Sensorium
→ Reasoning / Simulation
→ Safety + Permissions + Approvals
→ Actions
→ Verification
→ Learning
→ Reliable continuation across devices and time

`build_trust_continuity_runtime` composes the cross-cutting layer. OAuth,
recovery and Trust Center mutation services are omitted unless their canonical
security callbacks are explicitly supplied.

## Qualification semantics

"Implemented" means the repository contains the code, tests and fail-closed
integration boundary. "Software qualified" means the exact feature commit has
passed the repository qualification gates. "Production ready" additionally
requires real owner-controlled signing/provisioning/notarization/attestation
identity, recovery/rollback evidence and production health evidence. "L4"
additionally requires real physical-device evidence.

No CI run, merge or emulator result may be represented as production signing or
physical-device L4 certification. No production deployment is performed by this
campaign.
