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

Vishnu's existing `.github/workflows/product-production-qualification.yml`
remains the canonical protected production build/runner qualification path. It
materializes owner-controlled signing material only inside protected CI
environments, runs the product-production preflight, can claim one real queued
production build, and verifies returned distribution evidence. Existing
`release.yml`, `release-autonomy.yml`, platform runner workflows, TestFlight,
SBOM and qualification-evidence workflows remain authoritative rather than
being duplicated by this campaign.

Real production certificates, provisioning profiles, notarization authority,
container signing identity and production worker credentials remain externally
owned. CI cannot create or claim them.

## 2. Physical-device L4 qualification

`PhysicalL4Qualification` accepts only `physical_device` evidence and rejects
emulators, simulators, hosted VMs, virtual simulation and CI runners. Evidence
is exact-commit-bound and requires battery, thermal, background restriction,
permission UI and disconnect/reconnect metrics plus scenario results and a
SHA-256 evidence digest.

The existing Android/iOS physical-device and Sensorium L4 workflows remain the
mechanisms that must run on actual hardware. A repository implementation or L3
emulator/simulator pass is not an L4 certificate.

## 3. Universal owner identity and recovery

`UniversalOwnerRecovery` orchestrates short-lived, atomically one-shot restore
ceremonies without requiring a designated master device. In the full Vishnu
runtime, recovery-code proofs are consumed by the canonical
`OwnerAccessStore`, restored devices are enrolled by the canonical
`DeviceRegistry`, receive owner scopes, and a selected lost device is revoked.
Recovery proofs and newly issued device credentials are never persisted in the
trust-continuity metadata database.

Passkey and encrypted disaster-recovery-package restoration remain in the
existing canonical WebAuthn/onboarding recovery ceremonies. The generic
trust-continuity string-proof adapter deliberately refuses to downgrade those
stronger ceremonies into a reusable string proof.

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
failure state, scheduling metadata and explicit stop explanations. Dependency
cycles, self-dependencies and manual prerequisite bypasses are rejected.

The engine stores orchestration state and does not execute tools itself. In the
full runtime, a consequential action still has to flow through the existing
ToolRegistry/ApprovalManager execution path. The integration therefore never
turns a Work Engine plan record into execution authority.

## 6. Deep personal memory intelligence

`MemoryIntelligence` adds source provenance, confidence, timestamps,
contradictions, entity aliases, project timelines, consolidation, owner edits,
retention expiry, purge, export/import and `why_known` traceability. Imported
facts receive import provenance rather than inheriting secret/action authority.
Every fact explicitly carries `execution_authority=false`.

The owner-facing API binds these records to the stable canonical `owner_id`
rather than a hard-coded placeholder.

## 7. Universal integrations and OAuth

The full Vishnu composition reuses the existing canonical `OAuthAccountManager`
and connector state/SecretVault lifecycle for PKCE/state, owner/device/session
binding, scope health, refresh, relink/re-authentication and local/provider
revocation. `trust_continuity.runtime` accepts that canonical manager directly.

A provider-neutral `OAuthLifecycleManager` plus `KeychainSecretStore` remains
available only for reduced/test compositions. It is not a second production
OAuth authority. Provider verification and account-scoped permissions remain
fail-closed.

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
mutation authority.

`trust_continuity.integration` binds those callbacks to the real
`SensorPermissionStore`, `DeviceRegistry`, canonical OAuth authority and
`ToolRegistry.set_emergency_stop`. The dashboard/server composition attaches the
runtime and mounts `server/trust_continuity_api.py`. Aggregated trust/audit and
mutation endpoints require owner-admin device scope; memory export/import uses
sensitive-memory scope.

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

`attach_trust_continuity_runtime` is the full-product adapter. It is idempotent,
uses the canonical data directory and stable owner identity, reuses the existing
DeviceRegistry/OAuth/ToolRegistry/sensor-permission authorities, records
crash-recovery process state, and refuses to invent an owner or production
credential. `build_trust_continuity_runtime` remains the lower-level constructor
for tests and reduced compositions.

## Qualification semantics

"Implemented" means the repository contains the code, tests and fail-closed
integration boundary. "Software qualified" means the exact feature commit has
passed the repository qualification gates. "Production ready" additionally
requires real owner-controlled signing/provisioning/notarization/attestation
identity, recovery/rollback evidence and production health evidence. "L4"
additionally requires real physical-device evidence.

The dedicated Production Trust & Continuity workflow compiles the live server
integration, lints the campaign code and runs core/runtime/integration security
tests on the exact PR head. Repository-wide CI, reliability/security, product
production qualification/release evidence and the existing platform workflows
remain separate authorities and are not replaced by that focused gate.

No CI run, merge or emulator result may be represented as production signing or
physical-device L4 certification. No production deployment is performed by this
campaign.