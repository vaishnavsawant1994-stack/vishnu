# Feature Inventory

Baseline: `a8d3310b4d9090a42800621b1b27cb6045443c1e`.

The authoritative human-readable feature matrix is the **Feature truth matrix** in `docs/audit/VISHNU_PRODUCT_TRUTH_MAP.md`; it records backend/API/storage/security/platform/navigation/E2E/status/gap fields for each audited feature. This file provides the domain index so feature scope is independent of folder structure.

## Domains and sub-features

- **Security**: governed ToolRegistry execution; durable exact-use approvals; SecretVault/root-key rotation; strict hosted config; security assurance/audit/emergency controls.
- **Identity/onboarding**: create/existing/restore; owner identity; session/request context; WebAuthn/recovery; trusted-device enrollment/revocation; first-device flow.
- **Devices**: registry/list/detail/trust/scopes/last-seen; DeviceGateway; pairing; local TLS/mDNS/pinning; continuity/revocation; emulator/simulator/hosted VM vs physical L4.
- **Conversation/intelligence**: conversation/context; routing; advanced reasoning; speculation/synthesis; cancellation; adaptive composer; model/provider configuration.
- **Memory**: capture/persistence/encryption/retrieval/context; desktop management; migration/backup; multi-device/data-policy interaction.
- **Knowledge/content**: ingestion/retrieval/indexing; portable Knowledge; PDF/Office/text/structured formats; OCR/visual docs; media transcription; semantic graph/Q&A/citations.
- **Agents/Work/Projects**: goals/plans; durable task lifecycle; approvals; retries/cancellation/restart; Attention Center; completion judging; Projects relationships; evidence/continuity.
- **Apps/Tools/Integrations**: internal tools; connector state; OAuth boundary; discovery/registration; credentials/scopes; revocation/audit.
- **Universal Capabilities**: OpenAPI import/catalog; MCP server/tool discovery; risk classification; read/write approval; credentials; rotation/revocation; restart rehydration; UI management.
- **Capability Forge**: capability creation, provenance, plans/forms/schedules, staged side effects, canary/readiness and native management.
- **Computer/browser control**: requested action -> risk/approval -> executor -> verification/receipt/rollback where supported.
- **Automation/proactive/notifications/activities**: schedules, recurring jobs, preferences, notification hooks, activity feed/filter/cursors.
- **Products**: product manifests/runtime; package/signing model; product composer; multi-platform development builds and qualification.
- **Data/storage**: four local-first policies; encrypted lease transport; provider adapters; relay/PWA continuation; conflicts/tombstones/recovery; storage fabric/range/multipart/placement/replicas.
- **Sensorium/vision**: virtual providers; emulator/simulator/VM providers; physical observation boundary; camera/visual memory; phone sensors; scene/causal/task/world models; action-observation feedback.
- **Voice**: recording/runtime/personas/director; OpenVoice; provider boundaries; VoiceStudio MCP; Voice Lab; telephony; physical acoustic evidence boundary.
- **Intelligence Lab/training**: gated research/self-improvement, distributed compute through core authorities, model artifacts/vault/offline packs/DR and real-world qualification gates.
- **Release/readiness**: CI/security/recovery/architecture/SBOM/reproducibility/package/platform/release gates; production deployment/signing/store acceptance remain distinct external evidence.

## Rule

A feature is not `COMPLETE` from file/API/UI existence alone. `COMPLETE` requires the declared-scope chain: implementation -> storage/security -> exposure -> intended UI/navigation if user-facing -> error behavior -> appropriate tests/executable evidence. Any unproven layer is explicitly Partial/Blocked/Not verified in the master matrix.
