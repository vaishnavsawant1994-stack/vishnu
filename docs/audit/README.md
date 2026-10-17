# Vishnu Historical Implementation Audit — Index

**Audited product:** `vaishnavsawant1994-stack/vishnu`  
**Pinned main:** `5e2b88bff46bca2d4d212731ddad37fe59a7e88a`  
**Audit date:** 2026-10-17

This directory reconstructs Vishnu from repository history and then reconciles that history against current source, APIs, storage, security, UI/navigation, platforms, tests and qualification evidence.

## Start here

1. `AUDIT_BASELINE.md` — exact repository/PR/commit/CI/UI baseline.
2. `WHAT_VISHNU_HAS.md` — 70-capability master inventory and owner-facing truth.
3. `VISHNU_CURRENT_COMPLETENESS.md` — strict completion scorecard and current gaps.
4. `FINAL_MASTER_MATRIX.md` — compact feature/backend/API/UI/platform/test/status matrix.
5. `../OWNER_GUIDE.md` — practical owner usage guide.

## Historical reconstruction

- `VISHNU_DEVELOPMENT_TIMELINE.md` — chronological phases from PR #1 through current main and open #252.
- `FEATURE_PROVENANCE.md` — logical feature lineage and canonical authorities.
- `PR_FEATURE_MATRIX.md` — PR campaigns mapped to logical features and current relevance.
- `CLOSED_UNMERGED_PR_INVENTORY.md` — all 39 closed-unmerged PRs with disposition.
- `closed_unmerged_pr_files.json` — exact changed filenames for all 39 closed-unmerged PRs.
- `pr_implementation_ledger.md` / `.json` — exhaustive row-level historical PR ledger through the PR #245 Product Truth baseline.
- `commit_ledger.csv` — every reachable commit at that baseline, including path-level changed-file sets.

## Current architecture and location

- `WHERE_EVERYTHING_LIVES.md` — canonical repository ownership and current product navigation.
- `SYSTEM_CONNECTIONS.md` — whole-system and domain flow graphs.
- Existing `CURRENT_ARCHITECTURE.md`, `BACKEND_UI_TRACEABILITY.md`, `API_INVENTORY.md`, `NAVIGATION_MAP.md`, `PLATFORM_COVERAGE_MATRIX.md`, `TEST_COVERAGE_MAP.md` — source-derived audit foundations from PR #246.

## Gaps and documentation truth

- `PLANNED_BUT_NOT_IMPLEMENTED.md` — planned, externally blocked or acceptance-incomplete work that must not be claimed as finished.
- `IMPLEMENTED_BUT_NOT_DOCUMENTED.md` — implemented systems that need better owner/top-level documentation.
- Existing UI truth under `docs/ui/` — canonical 63-screen source/implementation taxonomy after PRs #250/#251.

## Machine-readable authorities

- `feature_history.json` — 70 logical current capability families, merged introduction provenance, historical lineage, current paths/UI/platform/status/gaps.
- `closed_unmerged_pr_files.json` — abandoned-branch file provenance.
- Existing `product_truth.json` — source-derived domain truth from the earlier repository-wide audit.
- Existing `docs/ui/ui_truth.json` — current canonical UI truth.

## Claim rules

- A PR is not a feature.
- A folder is not a feature.
- A closed-unmerged PR is historical evidence, not current functionality.
- Source presence is not end-to-end acceptance.
- Tests are not physical-device or production acceptance.
- Emulator/simulator/hosted-VM qualification is not physical-hardware qualification.
- Merged is not deployed.
- Preview deployed is not necessarily intended production accepted.
- A user-facing feature is COMPLETE only when all applicable architecture, implementation, service/API, storage, security, UI, navigation, platform, error handling, tests and exact-SHA end-to-end evidence are present.

## Current headline

At the pinned main SHA this audit identifies **70 logical current capability families**: **1 COMPLETE, 50 PARTIAL, 6 INTERNAL, 8 EXPERIMENTAL, 5 BLOCKED**. The canonical UI truth has **63/63 source-present screens, 58 PARTIAL, 5 EXPERIMENTAL, 0 missing concepts and 0 strict COMPLETE**, with 35 explicit expected-platform cells still marked missing after excluding deliberate `N/A` delegation.

The recommended next campaign is acceptance/convergence rather than another parallel architecture build.