# Current architecture authority

**Audited source:** `main` at `a8d3310b4d9090a42800621b1b27cb6045443c1e` (2026-10-16).

This file points engineers to the current, source-derived architecture and supersedes the top-level `ARCHITECTURE.md`, `ARCHITECTURE_V4.md`, and `ARCHITECTURE_V5.md` as a description of the current system. Those files are retained as historical snapshots. See [the detailed current map](../audit/CURRENT_ARCHITECTURE.md) and [the product truth map](../audit/VISHNU_PRODUCT_TRUTH_MAP.md).

The repository contains a single-owner Vishnu runtime with desktop, PWA, Android and iOS client surfaces; a Python runtime with FastAPI application compositions; owner identity and session security; local-first stores and data-plane policy; model, memory, knowledge, voice and perception systems; and governed tool, capability, device and work execution. Some advanced areas are deliberately isolated research or qualification systems. Their presence does not establish that they are enabled for product owners or accepted for production.

The current product authority is source code plus tests at an exact commit. Older readiness documents may describe prior SHAs or hosted environments. In particular, `docs/RELEASE_READINESS_2026-10-04.md` and `docs/CURRENT_PRODUCT_BASELINE.md` describe an earlier Railway observation while `render.yaml` defines a current Render deployment shape. Live deployment state was not inspected for this audit; neither configuration proves an active production runtime.

## Architecture references

- [Current architecture and flows](../audit/CURRENT_ARCHITECTURE.md)
- [Repository subsystem inventory](../audit/REPOSITORY_INVENTORY.md)
- [Feature inventory](../audit/FEATURE_INVENTORY.md)
- [UI and navigation inventories](../audit/UI_SCREEN_INVENTORY.md), [navigation map](../audit/NAVIGATION_MAP.md)
- [API inventory](../audit/API_INVENTORY.md)
- [Data architecture](../audit/DATA_ARCHITECTURE.md)
- [Backend/UI traceability](../audit/BACKEND_UI_TRACEABILITY.md)
- [Test evidence map](../audit/TEST_COVERAGE_MAP.md)
- [All PRs](../audit/pr_implementation_ledger.md) and [all commits](../audit/commit_ledger.csv)
