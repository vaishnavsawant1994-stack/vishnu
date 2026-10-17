# Vishnu Feature Provenance and Canonical Lineages

**Audited main:** `5e2b88bff46bca2d4d212731ddad37fe59a7e88a`  
**Rule:** one logical feature may span many PRs. A PR is not treated as a separate product feature merely because it added files.

## 1. Product/runtime lineage

### Core runtime
`PR #1 imported baseline` → production/runtime expansions → `#207 typed runtime composition boundaries` → current `app/`, `server/`, `cloud_runtime/` composition roots.

**Canonical today:** current composition roots plus the authority boundaries documented in `docs/audit/CURRENT_ARCHITECTURE.md`. Multiple roots still require parity qualification.

### Conversation
Imported conversation/runtime → early PWA redesign `#3–#29` → later Home/Conversation/Projects integration → current PWA/Desktop conversation APIs and surfaces.

**Canonical today:** PWA/Home conversation in `server/iphone_pwa.py` + `pwa/`, desktop conversation in `desktop/`, shared agent/model authorities.

### Model routing
Earlier provider adapters → Agent Workforce/provider work around `#114` → adaptive modes `#117/#118` → trained-model lifecycle `#121/#122` → current `models/` and routing authorities.

**Canonical today:** model/provider routing remains provider-configuration dependent; no historical provider adapter should be treated as a separate canonical router.

## 2. Work / agent provenance

### Canonical Work
`#62 GoalSpec/WorkPlan/WorkOrder/Evidence/Claim` → `#63–#69 planning/runtime/replanning` → `#68–#72 Project/Live Work UI` → `#73–#78 Attention/approval/recovery` → `#80–#96 qualification/completion/release integrity`.

**Canonical today:** WorkOrder/WorkPlan/Evidence authorities and their Project/Attention projections. Do not introduce a second workflow truth model.

### Persistent agents
Early contracts `#97/#98` → durable identity/attempts/effects/evidence `#99–#108` → convergence analysis `#110` → **E9 convergence #111** → Agent Workforce `#112–#115`.

**Superseded:** narrower #97/#98 contracts are historical, not parallel canonical agent runtimes.

### Adaptive intelligence
`#117` explicit intelligence levels → `#118` AUTO routing.

**Canonical today:** modes are routing/policy, not a second independent agent runtime.

### Self-improvement / training
`#119` governed capture → `#120` training capture pipeline → `#121` trained model runtime/canary → `#122` artifact/release pipeline.

**Canonical today:** governed/experimental lifecycle. Presence does not mean arbitrary autonomous self-modification.

### Intelligence Lab
`#231 Phase 1` → `#232 Phase 2` → `#233 Phase 3` → `#234 governed distributed compute` → `#235 adaptive qualification`.

**Canonical today:** isolated opt-in research workspace using existing authorities; not production autonomy.

## 3. Memory / Knowledge / content provenance

### Memory
Imported Memory → richer Memory UI around `#56/#60` → migration hardening `#204` → sensitive-at-rest lineage `#205` → DR/concurrency/fault work.

**Canonical today:** `memory/` + owner Memory/governance APIs + shared SQLite. **Memory remains separate from Knowledge.**

### Knowledge
Imported Knowledge → PWA/UI expansion → SQLite adoption `#206` → portable Markdown/archive lineage `#221`.

**Canonical today:** `knowledge/` + Knowledge owner APIs + file/content ingestion.

### Universal Content Intelligence
Document/content foundations `#165–#182`: parsers → layout/forms/tables → OCR/handwriting → audio/video → graph/timelines/contradictions → grounded semantic/multimodal runtime → qualification contracts.

**Canonical today:** `file_intelligence/` and content ingestion APIs. Individual OCR/model prototypes are not separate current products.

### Vision / Sensorium vision
`#227` adds permissioned governed visual sensing and visual-memory bridges.

**Canonical today:** `vision/` integrated under Sensorium/privacy/device authority.

## 4. Voice provenance

### Voice Intelligence
`#237` personas/director/style/lexicon/evaluation → optional provider/runtime work `#238` → **canonical provider boundary #239** → integration/scheduling/device routing `#240`.

**Superseded:** #238 is not the canonical provider-runtime boundary after #239.

### OpenVoice
`#236` adds optional governed voice conversion.

**Canonical today:** adapter-only integration; model assets are not vendored as a general bundled production voice model.

### VoiceStudio
`#241` provider integration → `#242` MCP capabilities routed through Universal Capabilities governance.

**Canonical today:** capability-governed VoiceStudio path; the narrow configured loopback transport exception does not create a second ungoverned tool system.

### Voice Lab / telephony
`#243` creates isolated Voice Lab qualification and default-off governed telephony.

**Canonical today:** experimental/qualification; external provider and real-acoustic evidence remains required.

## 5. Identity / devices / recovery provenance

### Owner identity and onboarding
Desktop Create/Connect/Restore `#192` → QR pairing `#193` → local TLS/mDNS/fingerprint connectivity `#194` → universal first-device model `#220` → missing onboarding UI source completion `#251`.

**Canonical today:** owner identity is separate from device identity. Any device may be Device 1 in the model; runtime hosting/provisioning still determines whether a particular surface can complete the real journey.

### Passkeys/sessions
Onboarding/security foundations → universal first-device/native passkey work `#220` → current identity/session/security authorities.

**Canonical today:** one owner identity with owner sessions and per-device trust/scopes.

### Recovery
Recovery-code/setup foundations → DR and encrypted restore work `#216` → universal restore `#220`.

**Canonical today:** recovery package/code + re-enrollment/revocation flow. Production restore acceptance is external evidence, not inferred from tests.

### Trusted devices / DeviceGateway
Capability/native device management `#183` → Native Device Lab `#188–#191` → pairing/connectivity `#193/#194` → universal device identity `#220` → trust/continuity hardening `#230`.

**Canonical today:** `DeviceRegistry` + `DeviceGateway` + trust/continuity authorities; no duplicate device manager should be introduced.

## 6. Security / approvals / secret provenance

### Approvals
Imported approval mechanisms → canonical Work approval context `#74` → Universal Capability one-use governed writes `#183` → atomic one-use hardening `#199`.

**Canonical today:** `ApprovalManager`; subsystems adapt into it instead of inventing separate approval tokens.

### Secret storage
Existing vault/root-key systems → **crash-safe root-key rotation #200** → strict configuration #201 and later security qualification.

**Canonical today:** `SecretVault` / `RootKeyStore`. This is the one current feature family classified COMPLETE in its narrow internal scope.

### Shared SQLite
DeviceRegistry migrations `#203` → Memory `#204` → Knowledge/Projects `#206` → product stores `#219`.

**Canonical today:** `core/sqlite.py` + versioned domain migrations. Legacy ad-hoc SQLite code should not become a second foundation.

### Cybersecurity assurance
`#226` establishes exact-SHA assurance artifacts/gates.

**Canonical today:** assurance/evidence system; does not substitute for live production security acceptance.

## 7. Capabilities / integrations provenance

### ToolRegistry / Apps & Tools
Imported tool system → Work/capability integration → current `tools/`/`apps_tools/`.

**Canonical today:** ToolRegistry remains the execution registry; connectors/skills/capabilities project into it.

### Universal OpenAPI
`#183` import/discovery/normalization/collision handling/credentials/risk/approval/governed execution → safety/target repair `#184` → current capability consoles/native management.

**Canonical today:** `capabilities/`, `integrations/`, `server/capability_console_api.py` and existing governance authorities.

### Universal MCP
`#183` discovery/schema/policy/execution/rehydration → specialized integrations such as REA `#224` and VoiceStudio governance `#242`.

**Canonical today:** MCP is one capability transport under Universal Capabilities, not separate ungoverned plugin runtimes.

### Capability Forge
V1 `#185` → V2 `#186` → V3 `#187`.

**Canonical today:** V3 advanced/experimental. V1/V2 are historical lineages.

### REA
Draft `#223` → **canonical merged #224** official REA 6.5.0 local stdio MCP integration.

**Superseded:** #223.

## 8. Data Plane / storage provenance

### Local-first policies
`#195` establishes `device_only`, `progress_only`, `sync_everywhere`, `on_demand` + cloud master/data permissions/item-location model → encrypted transport `#196` → provider/PWA/offline/DR qualification `#197` → universal Storage Fabric `#245` → first-run and provider-detail UI `#251`.

**Canonical today:** local-first Data Plane + governed Storage Fabric. Placement planning or health inspection is not permission to silently move owner data.

### Storage Fabric
Earlier provider adapters `#197` → `#245` resumable range/multipart transfer, provider health, encryption reuse, placement and non-destructive reconciliation.

**Canonical today:** `data_plane/storage_fabric.py` and provider adapters. Live provider acceptance remains external.

### Backup/DR
Data-plane/recovery foundations → encrypted MemoryStore DR `#216` + later resilience/fault tests.

**Canonical today:** recovery/backup verification code; a current accepted production backup still has to be demonstrated from the actual intended data root.

## 9. Products / packaging / release provenance

### Our Products / Product Composer
`#150–#164` foundations → lifecycle → `.vishnu-product` → deterministic artifacts → cross-platform runners/compiler → distribution gates and owner UI.

**Canonical today:** `products/` + build/distribution runners. Public signing/store delivery remains blocked/experimental.

### Packaging/update/release
Whole-product integrity `#96` → governed production release `#143` → reproducibility/SBOM/license `#212–#215` → production-readiness reconciliation `#222` → truthful About/Updates owner surface `#251`.

**Canonical today:** packaging/release authorities exist; there is explicitly **no fabricated signed in-app updater**. Platform/install owner remains responsible for actual installation updates.

### Deployment
`#143` governed preview/smoke/canary/rollback → later production-readiness records `#222`.

**Canonical today:** deployment manifests/governance exist. A successful preview status is not proof that intended production is deployed and accepted.

## 10. Sensorium provenance

### Native Device Lab
`#188–#191`: provider model → Android Emulator → iOS Simulator → hosted desktop VM evidence.

**Canonical today:** qualification evidence layer. Physical L4 remains a separate higher tier.

### Sensorium 2
`#228`: context/world model, privacy zones, environment/screen/audio/spatial sources, wearables/IoT/read-only home integration.

### Sensorium 3
`#229`: causal hypotheses, active perception, scene/task state, procedures, simulator/action-observation loop.

**Canonical today:** one Sensorium architecture with product/privacy foundations plus experimental intelligence layers; not separate competing sensor systems.

## 11. UI provenance

### Early PWA taxonomies
PRs #3–#29 and later UI work produced many overlapping page/shell implementations.

### First repository-wide UI audit
`#248` produced a 29-screen draft and a Web Companion overlap fix; unmerged.

### Stacked 30-screen attempt
`#249` added Data & Storage/About work and a 30-screen draft taxonomy; unmerged.

### Canonical 63-screen blueprint
`#250`, merge `1e6e89b64ca67c77c6189d37db8e581997af75f7`, froze the current logical screen taxonomy.

### Canonical source-gap completion
`#251`, merge/current main `5e2b88bff46bca2d4d212731ddad37fe59a7e88a`, implemented the six missing source surfaces.

**Canonical today:** 63 logical screens, 63 source-present, 58 PARTIAL, 5 EXPERIMENTAL, 0 MISSING, 0 strict COMPLETE. The 29/30-screen draft taxonomies are superseded.

### Owner capability directory
`#252` is an open draft. It is not canonical/current until merged.

## 12. Canonical authority table

| Concern | Canonical authority today | Do not duplicate with |
|---|---|---|
| Owner identity/session | `identity/`, security/session services | feature-local identity stores |
| Devices | `DeviceRegistry` / `DeviceGateway` | independent device registries |
| Tools | `ToolRegistry` | per-integration execution registries |
| Approvals | `ApprovalManager` | per-feature write approval token systems |
| Secrets | `SecretVault` / `RootKeyStore` | plaintext/local parallel credential vaults |
| Memory | `memory/` | Knowledge-as-Memory or duplicate memory DBs |
| Knowledge | `knowledge/` | Memory-as-document-store shortcuts |
| Local storage | shared SQLite + domain migrations | ad-hoc unversioned SQLite authorities |
| Data location | Data Plane / Storage Fabric | silent connector-managed sync |
| Work | canonical WorkOrder/WorkPlan/Evidence | unrelated agent task truth models |
| Capabilities | Universal Capabilities | arbitrary ungoverned MCP/OpenAPI execution |
| Release | governed release/evidence authorities | direct provider deploy authority |

## 13. Raw provenance sources

For historical row-by-row PR metadata through the #245 baseline, use:
- `docs/audit/pr_implementation_ledger.md`
- `docs/audit/pr_implementation_ledger.json`

For every reachable commit at that baseline, use:
- `docs/audit/commit_ledger.csv`

This audit appends/reconciles #246–#252 and the 52-commit delta through current `main`. The feature lineages above are the canonical interpretation of those raw change records.