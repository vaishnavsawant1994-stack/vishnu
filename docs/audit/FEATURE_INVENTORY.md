# Feature inventory and product truth

**Baseline:** `a8d3310b4d9090a42800621b1b27cb6045443c1e`.

This inventory is organized by product capability rather than folder. The machine-readable feature traceability file is `product_truth.json`. It records domain-level features and known cross-platform status. Subfeatures are listed below. The PR ledger covers every PR returned by GitHub's all-state listing; the commit ledger covers every commit reachable from the audited branch. A merge or file presence is not a proof of current feature completeness.

## Identity, setup and device trust

- Create owner, authenticate, create passkey, configure password, generate/use recovery, complete first run, provision runtime, choose data policy, connect/join existing Vishnu, restore identity/data, register/revoke trusted device, assign scopes, inspect device and last-seen.
- Status: meaningful server, PWA and native code exists. Cross-platform runtime bootstrap, recovery on another platform, physical-device execution and complete UI/result/error parity have not all been exercised together. Treat as partial until exact flow qualification is recorded.
- Source anchors: `identity/`, `onboarding/`, `server/iphone_pwa.py`, `server/identity_api.py`, native `RuntimeProvisioning*`, `Passkey*`, `PortableRecovery*`, `ConnectOnboarding*`.

## Conversation, models, Memory, Knowledge and files

- Conversation: create/list/activate/edit/export/delete conversations; send text/voice turn; approval prompts; cancel/barge-in where implemented; persist history; route configured model.
- Models: configure/test provider, select default/model, inspect availability; local model support exists. Actual external-provider consent and real API calls are not established by fixture tests.
- Memory: capture, retrieve, inspect/manage graph/tree/details and policy/retention controls. Memory remains separate from Knowledge.
- Knowledge: ingest notes/files, search/retrieve with sources/citations, update/remove. PWA notes/archive support exists; format coverage and indexing error states vary by parser and provider.
- Files: source has text/document/PDF/spreadsheet/presentation/image/audio/video/code parsing paths and optional model-assisted extraction. The exact supported format set depends on installed optional libraries/models; OCR and external model availability are configuration-dependent.
- Status: core local functions are implemented in multiple layers, but user journey and provider/physical parity remain partial or not verified. See file-intelligence tests and `TEST_COVERAGE_MAP.md`.

## Tools, capabilities and integrations

- Internal tools, connector catalog, OpenAPI import, operation normalization/collision handling, encrypted credentials, rotation, risk classification, owner approval, governed read/write execution, one-use approval, audit and revocation.
- MCP: connect/discover, schema persistence, read-only attestation/risk floor, governed execution and restart rehydration; untrusted public endpoints are HTTPS/public-address constrained; internal VoiceStudio loopback is a narrow exception.
- Browser, desktop, apps/tools and plugins are adapters around existing governance rather than an arbitrary import/execution path.
- Status: backend and owner API coverage is substantial. OpenAPI/MCP fixture and security tests provide executable evidence for specific paths. Cross-platform capability management and real third-party acceptance are partial/blocked.

## Data and recovery

- SQLite foundation/versioned migrations, owner-local policy, provider placement planning, resumable encrypted transfers, range/multipart support, replica health/reconciliation, offline PWA continuation, backup verification/restore, continuity and tombstones/leases.
- Storage policy options: `device_only`, `progress_only`, `sync_everywhere`, `on_demand`.
- Status: foundation and synthetic qualification exist; live provider setup and production backup/restore are not proven. No silent cloud movement is intended.

## Work, products, automation and evolution

- Projects/work orders, task lifecycle, agent workforce and attention, workflow run/approve/reject/cancel/resume/recovery, product composition/build runners, distribution/license gates, release approvals/canary/rollback controls.
- Training, self-improvement, code evolution and Intelligence Lab workflows are separately governed and gated. A subsystem or owner console is not evidence that arbitrary self-modification is active.
- Status: many API and domain tests exist; end-to-end user journeys and actual external worker/production provider execution are not all verified. Lab/research features are experimental.

## Voice and Sensorium

- Voice includes persona/style/delivery controls, optional STT/TTS provider adapters, voice conversion, Voice Lab benchmarks/baselines/regression, evidence, release candidates and default-off telephony.
- Sensorium includes context permissions/privacy zones, snapshots/audio/document/spatial data, world observations/relations, causal hypotheses/tasks/procedures, IoT/wearables, proactive sessions and emulator/simulator/VM providers.
- Status: voice runtime/providers and real acoustics require configuration/consent; Voice Lab is experimental and gated. Sensorium includes internal/qualification surfaces; physical L4 and real-device claims are blocked until owner evidence.

## Exact per-feature machine fields

`product_truth.json` includes a unique feature ID, domain, layers, four native/browser platform statuses, navigation, tests/E2E, primary status, gap and source evidence. Status model: `COMPLETE`, `PARTIAL`, `INTERNAL`, `EXPERIMENTAL`, `BLOCKED`, `MISSING`, `LEGACY`. Unknown facts must use `NOT VERIFIED` and a reason. The JSON covers product-domain features, while the PR ledger adds the full change-by-change implementation history.
