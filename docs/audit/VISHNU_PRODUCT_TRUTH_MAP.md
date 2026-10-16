# Vishnu Product Truth Map

**Repository:** `vaishnavsawant1994-stack/vishnu`
**Audited main SHA:** `a8d3310b4d9090a42800621b1b27cb6045443c1e`
**Audit date:** 2026-10-16
**Audit scope:** current source, all Git-reachable commits, every PR returned by GitHub's paginated all-state PR API, repository workflows, source-derived route/UI/platform inventories, and exact-SHA GitHub checks.

## 1. Executive summary

Vishnu is a substantial single-owner personal AI repository with Python/FastAPI runtime compositions, a PyQt desktop surface, PWA/web owner product, Android and iOS companions, model and content intelligence, Memory and Knowledge, tools and governed capabilities, device trust, local-first storage, automation/work, Sensorium, voice, product runners, release controls, and a large test/qualification program.

This audit inventories 58 top-level subsystems, 240 PR records (204 merged, 36 closed without merge, 0 open at retrieval), 2,407 Git commits, 818 statically discovered API-style route declarations, and 33 domain-level feature records. GitHub reported seven exact-SHA checks passed on current `main`: `test`, `assurance`, `release-authority`, `local-first-security-and-recovery`, `voice-lab`, `qualification-evidence`, and `sbom`.

This does **not** establish that every product feature is complete. The machine feature map records 23 partial, 4 blocked, 5 experimental and 1 scoped internal-complete item. It intentionally uses conservative status: a source file or CI check does not prove the full user flow. The browser/native screens and each API's authorization edges were not exhaustively executed in this pass. Real external providers, physical devices, public signing, live production runtime, and production backup/restore remain unverified or blocked.

## 2. Architecture and source authority

The current architecture is documented in [CURRENT_ARCHITECTURE.md](CURRENT_ARCHITECTURE.md), with stable link [docs/architecture/CURRENT.md](../architecture/CURRENT.md). The product is composed from existing canonical identity, ToolRegistry, ApprovalManager, DeviceRegistry, DeviceGateway, SecretVault/RootKeyStore, Memory, Knowledge, Data Plane and audit authorities. The key boundary rule is to keep Memory and Knowledge separate and not add duplicate registries, credential stores or approval engines.

Top-level architecture files `ARCHITECTURE.md`, `ARCHITECTURE_V4.md`, and `ARCHITECTURE_V5.md` are historical snapshots; they do not fully describe current code. The checked-in README is also mixed-era: it still contains an October 4 Railway operational statement and does not mention all later product areas. `render.yaml` currently describes a Render deployment shape. No live hosting inspection was performed, so the actual runtime provider, active deployment SHA, health, data root and volume remain `NOT VERIFIED`.

## 3. Audited baseline and history

- Starting/frozen `main`: `a8d3310b4d9090a42800621b1b27cb6045443c1e`.
- Current Git history at that baseline: 2,407 commits.
- All-state PR list: 240 PR records, 204 merged, 36 closed unmerged, 0 open at retrieval. See [PR implementation ledger](pr_implementation_ledger.md) and [machine PR ledger](pr_implementation_ledger.json).
- Every commit reachable from that baseline is listed with SHA, date, parents, subject and changed paths in [commit_ledger.csv](commit_ledger.csv).
- PR descriptions provide author-stated implementation scopes; current code and tests provide implementation truth. Closed unmerged PR work is not assumed to exist in main.

## 4. Feature truth

The feature map is [`product_truth.json`](product_truth.json), validated by `scripts/validate_product_truth.py`. Counts are scoped to 33 audited product-domain records:

| Primary status | Count | Meaning |
|---|---:|---|
| Complete | 1 | Narrowly scoped internal root-key rotation behavior with regression evidence |
| Partial | 23 | Meaningful implementation exists; some wiring, platform, failure, provider or E2E layer is not proven |
| Internal | 0 | Internal behavior is represented as subfeatures in current rows; no whole product domain was promoted to this status |
| Experimental | 5 | Lab, research, gated, or not normal production owner behavior |
| Blocked | 4 | Owner/external dependency prevents full qualification |
| Missing / broken | 0 | No row is asserted absent without a focused full-tree absence audit |
| Legacy / dead | 0 | No row is asserted dead without usage/import/runtime analysis |

Zero missing/dead entries means “not assigned,” not “none exist.” No positive claim about no-op controls, unreachable pages, unused APIs or orphan modules is made without runtime/AST usage evidence. Those are explicit follow-up verification gaps.

Major implemented areas reflected in main include:

- Identity/session, first-run, recovery, passkeys and multi-device trust foundations.
- Versioned SQLite and security hardening, encrypted secrets, root-key rotation and fail-closed hosted configuration.
- Memory, Knowledge, file/content intelligence, conversation/model routing, PWA and native companion areas.
- Governed tools and capabilities, including OpenAPI/MCP import/discovery/execution, approval, credential handling, audit and restart rehydration.
- Local-first Data Plane and PR #245 governed storage-fabric foundation (resumable transfer, provider health, encryption reuse, placement planning and non-destructive reconciliation).
- Sensorium perception/context/world/lab providers, emulator/simulator/hosted VM qualification, with physical-device boundary retained.
- Voice Intelligence, optional provider-runtime layer in PR #239, VoiceStudio integration, Voice Lab, benchmarks and default-off governed telephony.
- Durable work and project orchestration, product composer/build runners, release control, SBOM, reproducibility and recovery/endurance qualification.

These are repository capabilities, not blanket statements that every platform, provider or production setup is accepted.

## 5. User interfaces and navigation

See [UI inventory](UI_SCREEN_INVENTORY.md) and [navigation map](NAVIGATION_MAP.md). Current source contains desktop, PWA/web, Android and iOS surfaces; PWA is the broadest browser product surface. Native mobile apps include connect, passkey, provisioning, recovery, Data Plane and selected Sensorium/Forge flows. Voice Lab, Intelligence Lab, release and product runner screens are owner/admin/qualification tools.

Exact per-screen reachability and every interactive control were not exhaustively exercised. Consequently the audit does not yet label screens as orphaned or controls as no-op based only on source. Mobile parity is partial; simulator/emulator and hosted VM success does not equal physical-device success.

## 6. Backend, API and integration traceability

The static route index is [`api_inventory.json`](api_inventory.json) with 818 routes at the audited SHA. Its extraction is syntax-based and does not resolve dynamic mounts, auth dependencies, all consumers or runtime reachability. `API_INVENTORY.md` describes the limits. Key execution paths and known gaps are in [BACKEND_UI_TRACEABILITY.md](BACKEND_UI_TRACEABILITY.md).

Evidence supports specific bounded execution/security paths such as OpenAPI/MCP fixtures, pinned/limited network behavior, response bounds, approval and credential lifecycle tests. Real third-party consent/provider behavior is not established. No live provider was connected or called in this audit.

## 7. Data, security and owner control

The storage architecture is described in [DATA_ARCHITECTURE.md](DATA_ARCHITECTURE.md). Local-first labels are `device_only`, `progress_only`, `sync_everywhere`, and `on_demand`. PR #245 extends the existing logical item/location foundation; it does not authorize silent cloud copy or automatic reconciliation writes. Device trust, credentials, approvals, data movement and releases remain explicit governed actions.

Security code and tests cover important narrow boundaries: owner sessions/one-time credentials, vault rotation, strict config, approval use, capability execution, device scopes, encrypted transfer and recovery. The generated API inventory does not prove each route's full authorization. A route-by-route security and client-call trace remains a concrete gap. No production data, secrets or deployment changes were touched.

## 8. Platform truth

See [platform coverage matrix](PLATFORM_COVERAGE_MATRIX.md). Current source and workflows support desktop, browser/PWA, Android and iOS development/qualification, but feature parity is not uniform. Android emulator, iOS simulator, browser viewport and hosted VM results apply only to those exact environments. Physical-device, signing/notarization/store acceptance and live provider behavior remain blocked/not verified.

## 9. Test evidence

At the audited exact main SHA, GitHub reported seven checks completed successfully: `test`, `assurance`, `release-authority`, `local-first-security-and-recovery`, `voice-lab`, `qualification-evidence`, and `sbom`. This exact-SHA evidence is stronger than old PR status, but it does not cover future audit branch docs or claim production acceptance.

The repository has 647 Python test modules, plus browser/mobile/CI qualification suites. Initial local `pytest -q` could not start because `pytest` was absent. Running the repo installer with `--system` was denied when it attempted to replace a shared runtime dependency. A separate local `.venv` was populated from the locked tools profile. First run: 3,837 passed and 3 storage-provider adapter tests failed because the container injected an unsupported SOCKS `ALL_PROXY`; all 12 provider contract tests passed after unsetting it. The second full run passed **3,840 tests with 73 warnings in 115.48 seconds**. On exact main SHA, GitHub also reported seven named checks successful. See [TEST_COVERAGE_MAP.md](TEST_COVERAGE_MAP.md) for gates and the distinction between fixture and external evidence.

## 10. Blockers and NOT VERIFIED items

### Engineering and audit follow-up

- Exercise complete fresh create/join/restore flows on each supported surface with backend-state assertions.
- Browser-test all key settings, buttons, errors and navigation paths; instrument unreachable controls and disconnected APIs.
- Complete route-level authorization/approval/source-consumer mapping; static path extraction alone is insufficient.
- Verify data classification and policy support per domain, browser storage content, native secret persistence and cross-device failure behavior.
- Run high-value E2E flows for conversation/model, capability approve/execute/audit, device enroll/revoke, data placement and work cancellation/recovery at one exact qualified SHA.
- Identify dead/orphan modules using import, router, route, and runtime coverage rather than file-count heuristics.

### Owner/external actions

- Determine and verify the intended live host/runtime and active commit. Historical Railway readiness notes and current Render manifest conflict; no live check was made.
- Supply provider consent/configuration and validate real provider expiry/revocation/data destination.
- Run physical Android/iPhone tests and L4 hardware qualification.
- Supply signing identities/agreements for public native distribution.
- Create and accept an isolated restore from the actual production data root before any production recovery claim.
- Keep distribution proprietary; any change to license or customer terms requires explicit owner/legal decision.

## 11. Work completed in this audit

- Added the canonical current architecture pointer and source-derived architecture diagrams.
- Added repository, feature, UI, navigation, backend/UI, API, data, platform and test maps.
- Generated all-PR and all-commit ledgers from current GitHub/Git history.
- Generated a source-derived 818-route index and 58-subsystem inventory.
- Added a machine-readable 33-feature truth map and validation script.
- Verified current main SHA and exact-SHA GitHub check conclusions.
- Made no product behavior changes and performed no production operation.

## 12. Confidence statement

The repository's current architecture, major subsystems and historical PR/commit lineage are now inventoried from `main` at a pinned SHA. Product feature records carry explicit status and evidence limitations. This is a source-level and CI-history audit with conservative gaps; it is not a declaration that every UI control, screen, provider, physical device or production deployment has been accepted. Any unknown is called out as `NOT VERIFIED` rather than treated as complete.
