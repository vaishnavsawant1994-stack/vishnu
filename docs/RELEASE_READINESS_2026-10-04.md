# Release Readiness — Current Snapshot

Reviewed: 2026-10-15

This document supersedes the 2026-10-04 snapshot below. The earlier commit and deployment identifiers are historical and must not be used as current release evidence.

## Decision

**HOLD — no production release is accepted.**

Current `main` is `b2910f4a94368018890a7521a05c9504a8e5f18b`, after PR #149's corrected exact-head CI passed. PR #221 mainline CI passed 3,539 tests with 70 warnings. This is code-level evidence, not production acceptance.

## Production state

Railway project `personal-ai-runtime`, production environment:

- Canonical service: `personal-ai-runtime` (`c2dacbf5-b118-4ea1-89a3-ea8868b374c4`).
- Railway environment status: **Offline**, with no active deployment or replica.
- Latest deployment record: failed deployment `9f5b7074-92bd-4704-9cda-ec63442219c4`, created 2026-09-07.
- Configured source is repository `vaishnavsawant1994-stack/vishnu`, branch `main`; source commit field is `8ba1cf4c2278f97b48100b26416bf3731a12ad53`. This is not current `main` and is not a running-commit claim.
- A live 500 MB persistent volume is mounted at `/data`.
- The effective `PERSONAL_AI_DATA_DIR` value is unverified. There is no live process from which to verify the resolved directory.
- Request metrics: zero requests in the prior 24 hours. No successful health response was observed during this review.
- An empty staged Railway environment patch from 2026-09-30 remains visible; reconcile it before the next deployment.

No deploy or restart was performed as part of this review.

## Recovery qualification

The encrypted backup and disaster-recovery code has automated synthetic fixture coverage in CI. Production recovery remains **HOLD** because no production backup was created and restored to an isolated target. Complete that qualification only after a pinned runtime is online and its mounted data root has been verified.

## Required gates before release

1. Restore an approved pinned production deployment; verify exact SHA and healthy `/health`.
2. Confirm effective data path under `/data`; perform encrypted backup and isolated restore, then verify database/application integrity.
3. Rebase/requalify open PR work independently; do not rely on checks from stale heads.
4. Complete real provider consent, physical-device checks, signing/notarization, owner acceptance, soak, and rollback evidence.
5. Keep public release claims limited to evidence tied to the pinned candidate.

## Open PRs

PR #149 was replayed on current main at `563b2e2f867f8835feb6d4ea815177e3f4b6c5b2`; its corrected head passed CI, PWA, security, package, and qualification checks and was squash-merged as `b2910f4a94368018890a7521a05c9504a8e5f18b`. PR #145 remains unreconciled because its qualification workflow and owner API hunks overlap later mainline changes. PRs #156 and #188 remain stale drafts for current-main review and qualification.

## License decision

Project policy: **proprietary, all rights reserved; no open-source license is granted.** No external source or binary distribution is approved until ownership/provenance, third-party notices, and commercial terms are reviewed. This project policy does not constitute legal advice.
