# Planned, Expected or Promised — But Not Fully Implemented/Accepted

**Audited main:** `5e2b88bff46bca2d4d212731ddad37fe59a7e88a`

This file prevents architecture documents, PR descriptions and intended product behavior from being mistaken for current finished functionality.

## A. Clearly not implemented as a complete product feature

### 1. Signed in-app Vishnu updater

**Evidence:** current About/Updates surface added by PR #251 explicitly states that a signed in-app updater is not connected.

- Existing: version/build/channel display, governed release status, packaging/release infrastructure.
- Missing: production-quality signed update download/install/rollback user journey integrated into the app.
- Current owner behavior: updates are platform/installation-owner managed.
- Classification: **PLANNED/NOT IMPLEMENTED AS IN-APP PRODUCT FEATURE**.

### 2. Full strict visual/behavior/accessibility acceptance for canonical UI

- Existing: 63/63 canonical screen concepts source-present.
- Missing: exact-SHA rendered acceptance for all required responsive, keyboard, screen-reader, text scaling, contrast, motion, loading/error/offline/denied/approval states.
- Current count: 0/63 strict COMPLETE; 0/63 exact-SHA visually verified in the current campaign.
- Classification: **ACCEPTANCE WORK NOT COMPLETED**.

### 3. Full platform parity where the canonical matrix expects a native/desktop implementation

The current UI truth retains **35 explicit expected-platform `missing` cells**, excluding intentional `N/A` delegation to the PWA.

Notable gaps include Desktop Projects/Live Work/Inbox/detail surfaces, Android onboarding steps, Android Sensorium privacy, Desktop/Android Device Detail gaps, PWA Computer & Browser Control and Desktop About/Updates.

Classification: **PARTIALLY IMPLEMENTED PLATFORM PARITY**.

### 4. Owner-facing capability directory from PR #252

- PR: #252, open draft.
- Branch: `feat/owner-capabilities-directory`.
- Purpose: searchable PWA guide covering capabilities, tools, specialists, skills, labs and REA.
- Current main: does not contain the draft.
- Classification: **IN PROGRESS / NOT CURRENT**.

## B. Implemented foundations but blocked by external owner/provider/hardware work

These are not “missing code” in the same sense; source exists, but the user cannot truthfully call the feature fully accepted yet.

### 5. Real external OAuth/provider lifecycle acceptance

Universal Capabilities, model providers and integrations have credential/security foundations. What remains provider-specific:

- production OAuth applications
- callback/domain registration
- provider consent screens
- token expiry/revocation behavior
- provider-side scopes/terms
- live account verification

Classification: **BLOCKED EXTERNALLY / PROVIDER-SPECIFIC**.

### 6. Live remote Storage Fabric acceptance

- Existing: provider abstractions, resumable/range/multipart transfer, encryption reuse, provider health, placement/reconciliation.
- Missing acceptance: configured real provider accounts, owner consent, real upload/download/resume/failure/reconciliation evidence.
- Classification: **BLOCKED EXTERNALLY**.

### 7. Accepted production backup + isolated restore

- Existing: recovery packages, DR tests, encrypted Memory recovery lineage, continuity and backup/restore tooling.
- Missing: a verified backup from the actual intended production data root plus an accepted isolated restore.
- Classification: **BLOCKED BY PRODUCTION ENVIRONMENT/OWNER ACCEPTANCE**.

### 8. Physical Android/iPhone/iPad L4 qualification

- Existing: Android Emulator, iOS Simulator, native app source, hosted VM evidence, physical-device handoff/workflow concepts.
- Missing: current exact-SHA physical-device acceptance across the required hardware matrix.
- Classification: **BLOCKED BY HARDWARE/OWNER QUALIFICATION**.

### 9. Public native distribution

- Existing: package/build targets and distribution/release governance.
- Missing: signing identities, notarization/app-store agreements and accepted signed release artifacts for every intended platform.
- Classification: **BLOCKED EXTERNALLY**.

### 10. Real voice-provider/acoustic qualification

- Existing: Voice Intelligence, optional provider runtime, VoiceStudio/OpenVoice adapters, Voice Lab, native/browser audio paths.
- Missing: provider account acceptance plus real microphone/speaker/acoustic benchmarks on intended hardware.
- Classification: **BLOCKED EXTERNALLY / HARDWARE**.

### 11. Governed telephony in real provider environment

- Existing: default-off governed telephony and emergency-number hard blocks in Voice Lab lineage.
- Missing: chosen telephony provider, account, consent/legal configuration, physical/network acceptance.
- Classification: **EXPERIMENTAL + EXTERNALLY BLOCKED**.

### 12. Production deployment acceptance

- Existing: deployment manifests, preview/canary/rollback authorities; current SHA shows a successful Railway secondary-preview status.
- Missing as a production claim: explicit intended production runtime, accepted deployed SHA, health, persisted data root, volume and backup/restore state.
- Classification: **NOT VERIFIED / OWNER-ENVIRONMENT BLOCKED**.

## C. Implemented research foundations that are deliberately not ordinary production features

### 13. Intelligence Lab high-autonomy research

The lab exists and has multiple phases, but remains isolated/opt-in and does not become general production authority.

Classification: **EXPERIMENTAL BY DESIGN**.

### 14. Sensorium causal/procedural/active-perception research

The source contains advanced world/task/procedure reasoning. What is intentionally absent is unrestricted physical execution authority.

Classification: **EXPERIMENTAL BY DESIGN**.

### 15. Capability Forge V3 as normal owner production workflow

Forge V3 exists as an advanced/testing capability and selected native implementation. It has not been promoted to a universally supported owner workflow across all surfaces/providers.

Classification: **EXPERIMENTAL / NOT GENERAL PRODUCTION**.

### 16. Our Products public production distribution

Product Composer/runners can construct artifacts and model lifecycle, but signed public distribution is still gated.

Classification: **EXPERIMENTAL/PARTIAL + EXTERNAL RELEASE BLOCKERS**.

### 17. Autonomous self-training/model promotion without governance

The repository has training/evaluation/promotion foundations, but unrestricted self-modification is not canonical product behavior and should not be implemented by bypassing qualification/owner controls.

Classification: **NOT A CURRENT PRODUCT PROMISE; GOVERNED RESEARCH ONLY**.

## D. Acceptance gaps that documentation previously described aspirationally

### 18. “Everything works on every platform”

Not true. Current platform coverage is intentionally uneven. The PWA is the broadest owner product; native companions concentrate on OS-bound tasks.

### 19. “Simulator qualification equals physical-device qualification”

Not true. Emulator/simulator/VM evidence remains separate from L4 physical hardware.

### 20. “Merged equals deployed”

Not true. Source merge, package build, preview deployment and intended production acceptance are separate states.

### 21. “Tests prove every UI control is connected”

Not true. No repository-wide callback graph or every-button persistence run has been executed. The current UI audit positively proves no disconnected canonical screens; it does not prove zero no-op controls anywhere.

### 22. “Every route’s authorization has been exhaustively traced”

Not true. The earlier source audit statically inventoried 818 API-style declarations at the PR #245 baseline, but a complete route→auth→approval→consumer mapping remains a follow-up.

## E. Recommended next implementation/acceptance order

1. Exact-SHA PWA/Desktop browser/GUI acceptance for high-frequency owner journeys.
2. Resolve `Live work` vs `Workflows` navigation ambiguity with executable evidence.
3. Close the 35 explicit expected-platform UI cells by priority, without duplicating screens marked `N/A` by design.
4. Run full fresh Create → Join → Restore scenarios on declared platforms with backend-state assertions.
5. Run one exact-SHA capability OpenAPI/MCP approve→execute→audit→revoke E2E.
6. Run one exact-SHA device enroll→scope→revoke/lost-device E2E on physical hardware.
7. Run one exact-SHA data policy→provider transfer→resume/failure→reconciliation E2E using a real test provider.
8. Run one exact-SHA Work/Project start→approval→cancel/recover→completion E2E.
9. Accept a production backup and isolated restore before production recovery claims.
10. Only then promote owner-facing capabilities from PARTIAL to COMPLETE based on evidence rather than source presence.