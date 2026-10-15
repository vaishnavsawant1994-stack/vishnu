# Vishnu — Current Product Baseline

Reviewed: 2026-10-15

This document records repository and hosted-runtime evidence observed on this date. It is not a production acceptance record.

## Repository

- Canonical repository: `vaishnavsawant1994-stack/vishnu` (public GitHub repository).
- Default branch: `main`
- Current main SHA: `b2910f4a94368018890a7521a05c9504a8e5f18b` (PR #149 squash merge, following PR #221 Knowledge notes and archives).
- PR #220 (first-device onboarding) is also merged.
- CI on PR #221's mainline head passed 3,539 tests with 70 warnings. PR #149's corrected exact head then passed CI, PWA, security, package, and qualification checks before merge. Automated CI is not a substitute for external, real-device, or production qualification.

## Production runtime — Railway

Project `personal-ai-runtime`, environment `production`:

| Item | Observed state |
| --- | --- |
| Main service | `personal-ai-runtime`, ID `c2dacbf5-b118-4ea1-89a3-ea8868b374c4` |
| Environment state | Offline; Railway reports no active deployments or replicas |
| Configured source | This repository, branch `main`; source commit field `8ba1cf4c2278f97b48100b26416bf3731a12ad53` |
| Latest deployment record | Failed deployment `9f5b7074-92bd-4704-9cda-ec63442219c4`, created 2026-09-07 |
| Recent deployment history | Most recent records dated 2026-09-29 are removed or skipped; none is a current successful deployment |
| Public service domain | `personal-ai-runtime-production.up.railway.app`; no successful live health request was evidenced |
| Storage | Live 500 MB Railway volume `personal-ai-runtime-data` is mounted at `/data` in IAD |
| Effective app data path | Not verified. The variable name `PERSONAL_AI_DATA_DIR` is configured, but its value was not read; there is no active runtime to verify the resolved path. |

The Railway service object still exists and its configuration lists the `main` source, but that does not mean an application commit is running. The deployment source commit is behind current `main`, and no exact running commit can be established. The environment health report says Offline; request metrics show zero requests in the prior 24 hours. Do not describe production as healthy or as running current `main`.

An empty staged Railway patch dated 2026-09-30 is present in the platform response. It contains no changes; its status should be reconciled in Railway before future production operations.

A second service, `personal-ai-iphone-qualification`, is also offline. Its separate 500 MB volume is mounted at `/data`; it is not the canonical production runtime.

## Backup and restore

The repository contains encrypted backup and portable disaster-recovery implementations. The current-main automated suite includes synthetic round-trip, wrong-key/corruption refusal, interrupted-restore rollback, legacy-format compatibility, and clean-host portable recovery coverage. These tests do not establish that a production backup exists or that owner production data has been restored.

**Production backup-and-restore qualification: BLOCKED.** The production runtime is offline, the effective data directory is unverified, and no production backup/restore artifact or restore acceptance record was found. Do not claim production recovery is proven until an encrypted backup is created from the mounted data root and restored to an isolated target with integrity and application-level checks.

## Pull-request triage

As observed 2026-10-15:

| PR | State | Current triage |
| --- | --- | --- |
| #149 — mobile preview Home-layout race | Merged to `main` as `b2910f4a94368018890a7521a05c9504a8e5f18b`; corrected exact-head CI/PWA/security/package/qualification checks passed | Complete |
| #145 — physical-device qualification dispatch | Open, ready; old base; latest PWA preview failed on stale head | Rebase/replay on current `main`, review current authority boundary, then rerun all required checks |
| #156 — commercial runtime and licensing | Open draft; old base; reported non-mergeable | Keep draft. Review product scope and licensing against current `main`, then qualify exact current head |
| #188 — virtual device lab and Sensorium | Open draft; old base; reported non-mergeable | Keep draft. Reconcile with existing device architecture and requalify on current `main` |

PR #149 was replayed on current main as a one-file change at head `563b2e2f867f8835feb6d4ea815177e3f4b6c5b2`; an initial PWA run caught a generated-source pattern error, which was corrected. The corrected head passed exact-head CI, PWA, security, package, and qualification checks and was squash-merged as `b2910f4a94368018890a7521a05c9504a8e5f18b`. PR #145 was not rewritten because its workflow, environment example, and owner API changes overlap later mainline work and require manual conflict resolution. PRs #156 and #188 remain drafts pending current-main review.

## Release claims

Keep these gates pending until evidence is recorded on the exact release candidate:

- Live third-party provider consent and connector end-to-end acceptance
- Physical iPhone/Android device qualification
- Native signing, notarization, and downloaded-artifact checks
- Production deployment of a pinned release candidate and healthy exact-SHA verification
- Production backup and isolated restore
- Owner acceptance, soak, and tested rollback

## Project licensing

Decision recorded for the project: **proprietary, all rights reserved; no open-source license is granted.** Keep external source/binary distribution and third-party reuse blocked until rights provenance and distribution terms are reviewed. The repository is public and can be viewed/forked under GitHub’s platform terms; that does not turn the code into an OSI-licensed project. This status decision is not a substitute for legal advice.
