# Implemented but Inadequately Documented / Discoverable

**Audited main:** `5e2b88bff46bca2d4d212731ddad37fe59a7e88a`

This is not a claim that the listed features have zero documentation anywhere. Most have PR descriptions, tests or specialist docs. The issue is that current owner/top-level documentation does not consistently explain them as one product, or older docs still describe an earlier state.

## 1. Top-level README is not the full product map

The repository’s implementation has grown far beyond the original Personal AI/early Vishnu README narrative. Important systems that are substantially implemented but are not adequately discoverable from a single owner-facing top-level guide include:

- Canonical Work / WorkOrders / Evidence / Attention
- Agent Workforce and persistent-agent execution
- Universal OpenAPI/MCP Capabilities
- Capability credential lifecycle and approvals
- local-first Data Plane and Storage Fabric
- universal first-device identity/onboarding
- Sensorium Native Device Lab and later Sensorium intelligence layers
- Voice Intelligence / optional provider runtime / VoiceStudio / Voice Lab
- Our Products / Product Composer / platform runners
- Intelligence Lab
- REA integration
- governed release/SBOM/reproducibility/assurance systems

PR #252 is explicitly trying to improve this discoverability through a searchable owner capability guide, but it is still an open draft.

## 2. Current architecture vs historical architecture docs

Implemented current boundaries are better described by `docs/audit/CURRENT_ARCHITECTURE.md` and `docs/architecture/CURRENT.md` than by historical root snapshots:

- `ARCHITECTURE.md`
- `ARCHITECTURE_V4.md`
- `ARCHITECTURE_V5.md`

Those historical documents should remain for provenance but should not be treated as current authority.

## 3. Canonical Work is broader than ordinary “automation” documentation

The repository has a durable GoalSpec/WorkPlan/WorkOrder/Evidence/Claim lifecycle, attention/recovery/completion policies and project integration spanning PRs #62–#96.

Documentation gap: owner-facing docs should clearly distinguish:
- one-off conversation/tool use,
- Automation/Workflow definitions,
- durable WorkOrders and long-running project work,
- Attention/Approval/Recovery states.

Without this distinction, users can assume “Workflows” and “Live Work” are the same feature. The current PWA navigation ambiguity reinforces this documentation problem.

## 4. Data Plane policy semantics deserve a single owner explanation

Implemented policy values:
- `device_only`
- `progress_only`
- `sync_everywhere`
- `on_demand`

PR #251 finally adds first-run Data Placement and provider detail source, but owner documentation should state clearly that changing the default policy does **not** silently move existing data and that provider health/placement planning is not automatic cloud migration.

## 5. Universal Capabilities need a product-level capability directory

OpenAPI/MCP capability import, credentials, risk/approval, audit, revocation and native management are real systems. Today their understanding is split across PRs, source, tests and UI.

Documentation gap: a normal owner needs one truthful directory answering:
- what is built in,
- what is an external capability,
- which capability needs credentials,
- what is read-only vs write-capable,
- what needs approval,
- where it is configured,
- which platform can manage it,
- whether the provider was actually qualified.

PR #252 addresses this but is not merged at audit time.

## 6. Sensorium implementation is broader than the normal owner UI

Implemented source includes:
- privacy/permission foundations,
- camera/visual sensing,
- context/world modeling,
- native provider/evidence layer,
- emulator/simulator/hosted-VM qualification,
- advanced causal/procedural research.

Documentation gap: owner docs must separate **product sensing**, **qualification providers**, and **experimental world-model research**, otherwise the presence of research modules can be mistaken for unrestricted device control.

## 7. Voice has multiple layers that need clearer owner documentation

Implemented layers include:
- normal voice conversation controls,
- Voice Intelligence policy/director/personas,
- optional STT/TTS provider runtime,
- OpenVoice conversion adapter,
- VoiceStudio integration,
- Voice Lab and governed telephony.

Documentation gap: these should not be presented as one universally enabled “Voice” feature. Provider/runtime requirements and experimental/default-off behavior need to be explicit.

## 8. Production/release code is richer than deployment status documentation

Vishnu contains:
- package/build gates,
- release manifests/authority,
- preview/smoke/canary/rollback governance,
- SBOM,
- dependency locking,
- reproducibility evidence,
- cybersecurity assurance,
- product platform runners.

Documentation gap: these implementation capabilities do not answer the operational question “what exact commit is running as intended production right now, on what data root, with what accepted backup?” That operational truth must be kept separate.

## 9. UI source completion changed older audit findings

PR #250 recorded six missing canonical screen concepts. PR #251 implemented all six source surfaces. Any document still saying those concepts are missing is historical/stale unless it is clearly marked with its older baseline.

Current source truth:
- 63 canonical screens required
- 63 source-present
- 58 partial
- 5 experimental
- 0 missing
- 0 strict complete

Documentation should prefer `docs/ui/CURRENT_IMPLEMENTATION_STATUS.md` / `ui_truth.json` for current status rather than the pre-#251 missing-screen table alone.

## 10. Platform strategy is not “duplicate every screen natively”

The Android/iOS companions are intentionally OS-bound companions, while the PWA is the broadest owner product.

Documentation gap: platform matrices should distinguish:
- **missing where native implementation is expected**,
- **N/A by deliberate PWA delegation**,
- **partial source**, and
- **experimental**.

Without this, native parity numbers can be misread as dozens of defects when many are intentional N/A cells.

## 11. REA integration prerequisites need owner-level documentation

Canonical REA work is PR #224, not superseded #223. It uses official REA 6.5.0 through local stdio MCP, projected into Vishnu’s governed capability/tool system.

Owner documentation should state:
- REA/Node runtime prerequisites,
- it is not a sandbox by itself,
- tool execution remains governed by Vishnu authorities,
- native-analysis integrations may require their own binaries/licenses/environments.

## 12. SecretVault completion scope should be documented narrowly

Crash-safe root-key rotation is the one capability family this audit marks COMPLETE. That should never be rephrased as “all Vishnu data is fully encrypted at rest by SecretVault.” The vault protects its own secret domain; Memory/Data Plane and other data classes have their own storage/encryption authorities.

## 13. Test/qualification evidence needs a user-readable hierarchy

The repository has substantial CI, browser, emulator, simulator and VM evidence. Owner docs should explicitly separate:

1. source implemented
2. unit/integration tested
3. browser/CI qualified
4. emulator qualified
5. simulator qualified
6. hosted VM qualified
7. physical device qualified
8. signed/distributed
9. production verified

Current documentation mentions these boundaries in specialist audit files, but they should be part of the normal owner/status language to prevent overclaiming.

## 14. Recommended documentation consolidation

After this audit is accepted:

1. Keep `docs/audit/WHAT_VISHNU_HAS.md` as the technical capability directory.
2. Keep `docs/OWNER_GUIDE.md` as the owner-facing usage guide.
3. Link those from the README without copying all details into the README.
4. Keep `docs/ui/ui_truth.json` as machine UI truth.
5. Keep `feature_history.json` as machine feature/provenance truth.
6. Keep old architecture/UI reports but label their audited SHA prominently.
7. If PR #252 is retained, make its in-product capability directory derive its status vocabulary from these canonical machine-readable authorities so it does not drift.