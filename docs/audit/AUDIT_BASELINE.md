# Vishnu Historical Audit Baseline

**Repository:** `vaishnavsawant1994-stack/vishnu`  
**Audit date:** 2026-10-17  
**Pinned product branch:** `main`  
**Pinned product SHA:** `5e2b88bff46bca2d4d212731ddad37fe59a7e88a`  
**Current main merge:** PR #251 — `feat(ui): complete canonical owner UI source gaps`  
**Main commit timestamp:** 2026-10-16T22:10:07Z

## Pull requests

- Total PRs discovered: **247**
- Merged: **207**
- Closed without merge: **39**
- Open: **1**
- Draft open: **1**

### Open draft

PR #252 — `Add owner-facing Vishnu capability guide`
- branch: `feat/owner-capabilities-directory`
- head: `3358cd9b962db1b32b83dd9513e717fe3c8d910e`
- base: `main` at `5e2b88bff46bca2d4d212731ddad37fe59a7e88a`
- changed files: 4
- current product status: **not on main**
- recommended action: continue and exact-head qualify; merge only if guide claims remain aligned with current audit truth.

## Relevant branches

- `main` — canonical product, `5e2b88b…`
- `feat/owner-capabilities-directory` — open draft #252
- `codex/ui-completion-20261017` — merged PR #251 historical head `dde97f854…`
- `codex/ui-product-blueprint-20261016` — merged PR #250 historical branch/head `8ed68e890…`
- `audit/product-truth-map` — merged PR #246 historical audit branch
- `audit/complete-history-20261017` — this audit deliverable branch, created from the pinned main SHA

Many older feature/draft branches remain visible in the repository. Branch existence does not make their content canonical; merge reachability and current source decide product truth.

## Commit history

The PR #245 Product Truth baseline recorded **2,407 reachable commits** at `a8d3310b4d9090a42800621b1b27cb6045443c1e`. Current main is **52 commits ahead** and 0 behind that baseline, producing **2,459 reachable commits** at this audit cutoff.

The raw baseline commit ledger is `docs/audit/commit_ledger.csv`.

## Existing forensic evidence reused

PR #246 merged a repository-wide source audit that had already enumerated:
- 58 top-level subsystem directories
- 1,827 tracked files
- 240 PR records at that historical cutoff
- 2,407 reachable commits
- 818 static Python API-style route declarations
- 647 `tests/test_*.py` modules / 684 test files
- 35 workflows
- 33 domain-level machine truth records

This historical audit does not blindly reuse those old status conclusions. The present audit reconciles the 52-commit delta through #251 and treats #252 as open/unmerged.

## CI / status at current main

The exact-current-main workflow query returned nine workflow runs. No `failure` or `cancelled` conclusion was present in that returned set. The current commit combined status is `success`, including a successful Railway secondary-preview status.

This means the audited SHA is not being reported as CI-red. It does **not** prove:
- intended production is accepted,
- a real provider account works,
- physical Android/iOS is qualified,
- signing/notarization/store delivery is complete,
- a current production backup has been restored successfully,
- all 63 canonical screens have rendered/a11y acceptance.

## UI baseline

Current `docs/ui/ui_truth.json` summary after PR #251:
- canonical required: **63**
- source-present: **63**
- strict COMPLETE: **0**
- PARTIAL: **58**
- EXPERIMENTAL: **5**
- MISSING concepts: **0**
- proven orphaned: **0**
- proven disconnected: **0**
- platform slots: **252**
- source-proven platform instances: **121**
- strict visually verified: **0**
- explicit expected-platform `missing` cells after excluding `N/A`: **35**

## Production truth boundary

A successful preview/deployment status is not automatically the intended production deployment. This audit did not alter production, rotate production secrets, run live migrations or claim an accepted production restore.

## Audit branch

This historical audit was written on `audit/complete-history-20261017` from the pinned current main. It is intentionally not merged by this audit. Product behavior on `main` is unchanged.