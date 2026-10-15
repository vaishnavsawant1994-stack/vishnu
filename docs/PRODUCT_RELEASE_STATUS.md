# Vishnu Product Release Status

Reviewed: 2026-10-15

## Current decision

**Whole-product release: HOLD.** Current-main CI is green, but production is offline and several acceptance gates depend on real devices, provider consent, signing identities, and owner acceptance.

## Repository baseline

- Repository: `vaishnavsawant1994-stack/vishnu`
- Current `main`: `b2910f4a94368018890a7521a05c9504a8e5f18b`
- PR #221 Knowledge notes and archives: merged.
- PR #220 first-device onboarding: merged.
- PR #221 mainline CI: 3,539 passed, 70 warnings. PR #149 then passed all exact-head required checks before merge.
- This does not qualify production, physical devices, provider consent, or signed native distributions.

## Release gates

| Gate | Status | Evidence still required |
| --- | --- | --- |
| Current-main automated tests | PASS | Current-main CI is green; warnings remain recorded |
| Production service health / exact running SHA | HOLD | Railway reports Offline, no active deployment, and no current running SHA |
| Durable production data path | HOLD | Confirm effective `PERSONAL_AI_DATA_DIR` is under mounted `/data` from an active runtime |
| Production backup and restore | HOLD | Encrypted production backup restored to an isolated target with integrity and application-level validation |
| Third-party provider consent | PENDING_OWNER | Real OAuth consent and connector E2E, including revocation and expiry |
| Physical-device acceptance | PENDING_OWNER | Physical iPhone/Android final-candidate qualification |
| Native signing and notarization | PENDING_OWNER | Signed artifacts, identity validation, and installation/update checks |
| Production candidate and rollback | HOLD | Pinned exact-SHA deployment, health/version checks, restart persistence, and verified rollback |
| Owner acceptance and soak | PENDING_OWNER | Recorded owner checklist and release-representative soak |
| Project license/distribution | DECIDED — PROPRIETARY | No OSS license or third-party reuse grant; provenance and commercial terms review before external distribution |

## Railway production reconciliation

The canonical Railway project `personal-ai-runtime`, environment `production`, contains the `personal-ai-runtime` service. The service configuration references this repository and `main`, and a 500 MB volume is mounted at `/data`. However, the environment health report says Offline, has no active deployments or replicas, and metrics show zero requests in the prior 24 hours. The latest deployment record is failed (2026-09-07); later history is removed/skipped.

The configured source commit field is `8ba1cf4c2278f97b48100b26416bf3731a12ad53`, which is not current `main`; it is not evidence that this SHA is running. No current production commit or healthy response can be claimed.

The environment also contains an empty staged patch from 2026-09-30. Reconcile that platform record before any deploy.

## Pull-request triage

- **#149** — merged as `b2910f4a94368018890a7521a05c9504a8e5f18b` after corrected exact-head CI, PWA, security, package, and qualification checks passed.
- **#145** — ready, stale base, prior PWA preview failed. Rebase/replay and review its authority boundary on current `main`, then rerun all required exact-head checks.
- **#156** — draft, stale base, non-mergeable. Review commercial runtime scope against current `main`; keep draft until current-head qualification and target adapters are addressed.
- **#188** — draft, stale base, non-mergeable. Review overlap with existing device architecture; maintain the distinction between simulated and real-device evidence.

PR #149 was replayed at `563b2e2f867f8835feb6d4ea815177e3f4b6c5b2`; its corrected head passed exact-head CI, PWA, security, package, and qualification checks and was squash-merged as `b2910f4a94368018890a7521a05c9504a8e5f18b`. PR #145 has overlapping changes with later mainline updates in the qualification workflow and owner API, so it needs manual reconciliation before requalification. PRs #156 and #188 remain stale drafts.

## Release statement

Do not describe Vishnu as production-ready or declare the release perfect. Use only claims backed by the exact current candidate and observed runtime. Provider consent, real-device testing, signing, production acceptance, and production recovery remain pending.
