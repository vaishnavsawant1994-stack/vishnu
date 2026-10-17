# What Vishnu Has — Historical + Current Capability Inventory

**Repository:** `vaishnavsawant1994-stack/vishnu`  
**Audited branch:** `main`  
**Audited SHA:** `5e2b88bff46bca2d4d212731ddad37fe59a7e88a`  
**Audit date:** 2026-10-17  
**Historical backbone:** `pr_implementation_ledger.{md,json}` + `commit_ledger.csv` generated at PR #245 baseline, reconciled through PR #252 in this audit.

## Executive truth

This audit identifies **70 current logical capability families**. These are product capabilities, not folders or screens. Their primary current classification is:

- **1 COMPLETE** — narrowly scoped internal SecretVault/root-key rotation behavior.
- **50 PARTIAL** — meaningful implementation exists, but at least one required layer or exact-SHA owner journey is not fully accepted.
- **6 INTERNAL** — infrastructure/qualification authorities that do not require their own normal-product UI.
- **8 EXPERIMENTAL** — research/lab/advanced surfaces not promoted to ordinary production behavior.
- **5 BLOCKED** — meaningful code exists, but owner/external provider/hardware/production evidence prevents full use or qualification.
- **0 current logical families classified BROKEN or REMOVED.** Historical/superseded implementations are listed separately below.

Under the stricter **user-facing completion** definition, there are currently **0 fully accepted canonical owner screens**: the current 63-screen UI truth map records **58 PARTIAL, 5 EXPERIMENTAL, 0 MISSING and 0 strict COMPLETE**. All 63 have source implementation, but rendered exact-SHA visual/behavioral/accessibility acceptance is still outstanding.

## How to read the table

`Find/use` describes the owner path when one exists. `Internal` means a dedicated UI is not required. Platform shorthand: **D** desktop (Windows/macOS/Linux), **W** web/PWA, **A** Android companion, **I** iPhone/iPad companion. `P` = source/focused evidence but incomplete acceptance; `B` = externally blocked; `N/A` = a native duplicate is not required by current product design.

| # | Capability | Provenance / major lineage | Canonical implementation now | Find / use today | Platforms | Status | Main remaining gap |
|---:|---|---|---|---|---|---|---|
| 1 | Core runtime composition | imported #1; typed boundaries #207 | `app/`, `server/`, `cloud_runtime/` | automatic when Vishnu starts | D/W/A/I composition differs | PARTIAL | multiple composition roots are not yet proven behaviorally identical |
| 2 | Conversation lifecycle | #1; UI #3–#29; product wiring later | `agent/`, `server/iphone_pwa.py`, `pwa/`, `desktop/` | Home → composer / Conversation | D:P W:P A:companion I:companion | PARTIAL | no exact-SHA live-provider conversation acceptance across surfaces |
| 3 | Model/provider routing | #114; provider work thereafter | `models/`, owner product/provider APIs | Settings → AI Models & Providers | D:P W:P A:P I:P | PARTIAL | real account consent, expiry/revocation and provider acceptance vary by provider |
| 4 | Adaptive intelligence modes | #117 STANDARD/SMART/DEEP/RESEARCH; #118 AUTO | `agent/`, intelligence routing/config | conversation/runtime setting where exposed | D:P W:P | PARTIAL | end-to-end mode selection/results not accepted across all clients |
| 5 | Persistent agent identity & durable execution | #99–#111 | `agent/`, durable work/evidence stores | mostly automatic; advanced agent/work surfaces | D/W | PARTIAL | complete crash/cross-host owner journey remains unverified |
| 6 | Agent workforce & specialist teams | #112–#115 | `agent/`, workforce APIs/UI | Advanced/Agents; work delegation | W:P D:gap | PARTIAL | broad owner UX and production worker acceptance incomplete |
| 7 | Visualize / visual intelligence | #116 plus later integrations | `visual_intelligence/`, visualization APIs | Create/visualization pathways where offered | D/W | PARTIAL | exact supported models and full UI journeys not accepted |
| 8 | Self-improvement & training pipeline | #119–#122 | `training/`, model qualification/release code | advanced/admin only | D/W advanced | EXPERIMENTAL | training capture/model promotion remains governed and not general autonomous behavior |
| 9 | Intelligence Lab | #231–#235 | `intelligence_lab/`, lab APIs | Advanced/Labs | D/W advanced | EXPERIMENTAL | isolated research system; not ordinary production authority |
| 10 | Engineering evolution / code autonomy | #142 and evolution work | `evolution/`, `future_intelligence/` | engineering/qualification only | Internal | EXPERIMENTAL | no blanket push/merge/deploy authority; governed qualification only |
| 11 | Memory | imported #1; UI #56/#60; migration #204 | `memory/`, `server/owner_product_memory.py`, `server/memory_governance_api.py` | Home → Memory → search/detail | D:P W:P A:NV I:NV | PARTIAL | full capture→retrieve→edit/manage lifecycle not browser/native accepted |
| 12 | Memory governance & sensitive at-rest protection | #199–#205 | `memory/`, `security/`, SQLite migrations/envelopes | automatic + Memory/Privacy controls | D/W | PARTIAL | not all application data domains are covered by one uniform encrypted-at-rest claim |
| 13 | Knowledge | imported #1; UI #56; SQLite #206; notes/archive #221 lineage | `knowledge/`, owner knowledge APIs | Home → Knowledge → source/upload | D:P W:P A:P I:P | PARTIAL | parser/format/native parity and error-state acceptance incomplete |
| 14 | File & content intelligence | #165–#182 | `file_intelligence/`, content ingestion APIs | Knowledge → Add Source / file attachment | D:P W:P A:P I:P | PARTIAL | optional OCR/model dependencies and real-world format corpus qualification vary |
| 15 | Vision | #227 | `vision/` and governed camera/snapshot paths | permissioned visual input where configured | D/W/A/I | PARTIAL | physical camera/provider/privacy journeys not fully accepted |
| 16 | Sensorium Vision | #227 | `sensorium/` + vision bridges | native Sensorium controls / governed observations | D/W/A/I | PARTIAL | real-device evidence and cross-device behavior incomplete |
| 17 | Sensorium context & world model | #228 | `sensorium/` context/world modules | Advanced/Sensorium; mostly agent/internal | D/W/A/I | EXPERIMENTAL | many sensing/world-model paths are research/qualification surfaces |
| 18 | Sensorium causal/procedural intelligence | #229 | `sensorium/` causal/task/procedure modules | advanced/internal | D/W/A/I | EXPERIMENTAL | no claim of unrestricted physical action authority |
| 19 | Sensorium native provider/evidence layer | #188–#191; #228–#229 | `sensorium/`, native lab/evidence APIs | Settings/Advanced → Sensorium status; native privacy controls | emulator/simulator/VM qualified; physical blocked | PARTIAL | L4 physical-device qualification remains outstanding |
| 20 | Voice conversation controls | baseline + later voice work | `voice/`, conversation/PWA/native voice paths | Conversation microphone/voice settings | D:P W:P A:P I:P | PARTIAL | live STT/TTS and real acoustic parity not accepted |
| 21 | Voice Intelligence / director | #237 | `voice/` personas, director, delivery/lexicon | Settings → Voice / desktop Voice Studio | D:P W:P | PARTIAL | provider/device output quality remains configuration-dependent |
| 22 | Voice provider runtime | #238 superseded by canonical #239; integrated #240 | optional `voice/` provider runtime | enabled only by explicit configuration | D/W/A/I | BLOCKED | real provider credentials/consent and acoustic acceptance required |
| 23 | OpenVoice conversion | #236 | governed optional voice conversion adapter | advanced voice configuration | configured hosts only | BLOCKED | model assets/provider setup/license/real voice acceptance not bundled or proven |
| 24 | VoiceStudio integration | #241; governed MCP #242 | VoiceStudio adapter + capability projection | Voice Studio / configured local service | D mainly | PARTIAL | external VoiceStudio install/model availability and live acceptance vary |
| 25 | Voice Lab & governed telephony | #243 | Voice Lab, benchmarks, release candidates, telephony gates | owner/admin Voice Lab | advanced | EXPERIMENTAL | telephony/provider/physical acoustic evidence remains gated and default-off |
| 26 | Owner identity & first run | #192; universalized #220; UI completion #251 | `identity/`, `onboarding/`, desktop/PWA/native sources | Welcome → Create my Vishnu | D:P W:P A:P I:P | PARTIAL | one fresh-create acceptance run across every declared surface is still missing |
| 27 | Authentication & owner sessions | #192/#220 + security hardening | `identity/`, `security/`, session APIs | Sign in / unlock | D:P W:P A:P I:P | PARTIAL | every composition root/session expiry/reauth flow not accepted end-to-end |
| 28 | Passkeys | #220 and native passkey sources | identity/WebAuthn/native passkey adapters | Security setup / Sign-in Methods | W:P A:P I:P D:P | PARTIAL | physical biometric/provider behavior not fully qualified |
| 29 | Recovery | #192/#216/#220 | `recovery/`, identity recovery, portable package/backup | Welcome/Sign In → Restore Vishnu; Settings → Recovery | D:P W:P A:P I:P | PARTIAL | no accepted restore from actual production data root |
| 30 | Trusted devices | #183 mobile management; #220 universal identity/device model | `devices/`, owner APIs/native clients | Settings → Devices | D:P W:P A:P I:P | PARTIAL | physical device enrollment/revoke/lost-device journey not accepted at one exact SHA |
| 31 | Device Gateway & connectivity | #191 plus pairing/connectivity #193/#194 | `devices/`, `DeviceGateway`, mDNS/TLS/pairing | Add Device / native Connect | D/W/A/I | PARTIAL | real heterogeneous-network/device acceptance incomplete |
| 32 | Continuity & trust continuity | #108; #195+ data continuation; #230 | `continuity/`, `trust_continuity/` | automatic; device/work recovery surfaces | D/W/A/I | PARTIAL | complete offline→reconnect→resume cross-device journey not accepted |
| 33 | ApprovalManager / one-use approvals | baseline; strengthened #183/#199 | `approvals/`, governed action APIs | approval prompts / Approvals Center | D:P W:P A:P I:P | PARTIAL | every write path has not been route-by-route traced to approval authority |
| 34 | SecretVault / crash-safe root-key rotation | #200 | `security/`, root-key/vault code | Internal; protects stored secrets | Internal | COMPLETE | scoped completion only; not a claim that all Vishnu data is encrypted by SecretVault |
| 35 | Audit & security events | baseline + work/capability/release hardening | security/audit/evidence stores/APIs | Settings → Security → Audit History | W:P D:gap | PARTIAL | route/action coverage and desktop parity incomplete |
| 36 | Cybersecurity assurance program | #226 | assurance scripts/workflow/evidence | no normal UI required | Internal | INTERNAL | proves defined gates, not production penetration testing or zero vulnerabilities |
| 37 | ToolRegistry / Apps & Tools | baseline; broadened by work/capabilities | `tools/`, `apps_tools/` | Apps & Tools | D:P W:P | PARTIAL | consumer/action coverage across all integrations not fully traced |
| 38 | OpenAPI capabilities | #183; production-target repair #184 | `capabilities/`, `integrations/`, capability API | Apps & Tools → Capabilities → Add → OpenAPI | D:P W:P A:P I:P | PARTIAL | arbitrary external API/provider acceptance and OAuth setup not proven |
| 39 | MCP capabilities | #183; VoiceStudio governance #242; REA #224 | `capabilities/`, MCP adapters/registry | Apps & Tools → Capabilities → Add → MCP | D:P W:P A:P I:P | PARTIAL | live third-party servers/consent remain configuration-dependent |
| 40 | Capability credential lifecycle | #183; atomicity #199 | capability credentials + `SecretVault` | Capability detail → credentials/rotate/revoke | D/W/A/I | PARTIAL | provider-side revocation/expiry behavior not universally accepted |
| 41 | Capability Forge V3 | #185→#186→#187 | Forge V3 sources, especially iOS advanced surface | Advanced/testing only | I:E; others not normal product | EXPERIMENTAL | internal/advanced readiness and external OAuth/provider setup remain |
| 42 | REA integration | #223 superseded by merged #224 | MCP integration to official REA 6.5.0 local stdio | Apps & Tools / capability/tool use when installed | D primarily | PARTIAL | Node/REA runtime and real native-analysis tools are external prerequisites |
| 43 | Browser & computer control | imported/follow-on governance; UI audit | `browser/`, computer-control adapters, approvals | Settings/Advanced → Computer & Browser Control | D:P W:gap | PARTIAL | owner status/stop controls and platform E2E are incomplete |
| 44 | Plugins & integrations | baseline + universal capability work | `plugins/`, `integrations/` | Apps & Tools | D/W | PARTIAL | each external service has separate consent/configuration/qualification |
| 45 | Shared SQLite & versioned migrations | #203 DeviceRegistry; #204 Memory; #206 Knowledge/Projects; #219 product stores | `core/sqlite.py` + domain migrations | Internal | Internal | INTERNAL | still requires production DB-path/restore acceptance; no UI needed |
| 46 | Local-first Data Plane policies | #195; transfer expansion #196/#197; UI #251 | `data_plane/`, policy APIs/PWA/native caches | Settings → Data & Storage; first-run Data Placement | D:P W:P A:P I:P | PARTIAL | full per-domain placement parity and existing-data migration UX not fully accepted |
| 47 | Encrypted data transport | #196 + #245 | `data_plane/` segmented authenticated transfer/envelopes | Internal, used during governed transfer | Internal | INTERNAL | live remote transport/provider environment remains separate qualification |
| 48 | Remote storage providers / Storage Fabric | #197; universal storage fabric #245; detail UI #251 | `data_plane/storage_fabric.py` + provider adapters | Settings → Data & Storage → provider detail | D/W | BLOCKED | live provider account/consent/transfer acceptance not established |
| 49 | Backup & disaster recovery foundation | #216 + recovery/data-plane work | recovery/backup verification and restore code | Settings → Recovery / operational tooling | D/W/A/I | BLOCKED | actual production backup-and-isolated-restore acceptance required |
| 50 | Canonical Work / WorkOrders | #62–#96 | work orchestration, evidence, claims, completion/recovery | Live Work / Work Detail / Today | W:P D:gap | PARTIAL | complete owner work run/cancel/recover flow not accepted in one E2E |
| 51 | Projects | #46/#51; canonical work integration #68–#72 | `projects/`, work/project APIs and PWA | Home → Projects → Project Workspace | W:P D:gap | PARTIAL | desktop parity and complete long-running work acceptance incomplete |
| 52 | Automation / workflows | baseline; expanded by work system | `automation/`, workflow APIs | Automations / Workflows | D:P W:P | PARTIAL | external/background execution and failure/recovery journeys not fully accepted |
| 53 | Attention / Inbox | #73–#78 | attention queues/deep links/approvals/recovery context | Home → Inbox/Attention | W:P D:gap | PARTIAL | desktop parity and all attention sources not accepted end-to-end |
| 54 | Notifications | #77; work events #89 | `notifications/` + work/activity projection | notification settings / attention | D:P W:P | PARTIAL | real platform delivery/background behavior is configuration-dependent |
| 55 | Activities & evidence | #76/#89 plus evidence systems | `activities/`, `evidence/` | Activity / work detail | D:P W:P | PARTIAL | complete claim/evidence lifecycle UI acceptance incomplete |
| 56 | Proactive systems | existing + later attention/sensorium work | `proactive/` | mostly automatic/owner-controlled | D/W | PARTIAL | background/live behavior and notification delivery not fully accepted |
| 57 | Our Products / Product Composer & runners | #150–#164 | `products/`, runner/compiler/distribution code | Our Products → Product Detail/Build | D:E W:E | EXPERIMENTAL | real signing, store/distribution and production runner acceptance remain external |
| 58 | Desktop UI | imported + #26/#56/#57/#60; canonical map #250/#251 | `desktop/`, `ui/`, `app/main.py` | launch desktop Vishnu; 9 canonical top-level destinations | Win/macOS/Linux:P | PARTIAL | many secondary owner journeys and strict visual/a11y acceptance incomplete |
| 59 | PWA / web owner product | #3–#29 and continuing; #250/#251 | `pwa/`, `server/iphone_pwa.py`, `server/cloud_app.py` | browser `/iphone/` owner product | Web desktop/mobile:P | PARTIAL | broadest UI, but 0 canonical screens have strict exact-SHA visual/a11y acceptance |
| 60 | Android companion | baseline + capability/device/data/onboarding work #183/#191/#220 | `android-companion/` | native Connect/Trust/OS-bound features + open PWA | Android:P | PARTIAL | physical-device behavior, signing/store and some native parity gaps remain |
| 61 | iOS companion | baseline + #183/#191/#220 | `ios-companion/` | Create/Join/Restore, Trust, Capabilities, Sensorium, Recovery; open PWA | iPhone/iPad:P | PARTIAL | physical-device/signing/store acceptance incomplete |
| 62 | Web companion & dashboard | baseline/polish #26; overlap repair lineage #248/#251 | `web-companion/`, `dashboard/` | companion/control dashboard where configured | Web:P | PARTIAL | secondary-surface E2E and accessibility acceptance incomplete |
| 63 | Universal first-device onboarding | #192 foundation; #220 universal device-1 campaign; #251 UI source completion | `onboarding/`, identity + native/PWA provisioning | Welcome → Create / Join / Restore | D:P W:P A:P I:P | PARTIAL | complete phone/browser-only provisioning + restore acceptance depends on runtime hosting/configuration |
| 64 | Packaging & installers | #96; product runners #150–#164; later package gates | `packaging/`, `installer/` | installation/build tooling | Win/macOS/Linux + mobile targets | PARTIAL | public signing/notarization/store acceptance is separate and not complete |
| 65 | Updates & governed release authority | #96/#143 and UI #251 | `updates/`, release authorities, owner About/Updates | Settings → About / Updates | D/W | PARTIAL | no signed in-app updater is connected; platform/install owner performs updates |
| 66 | SBOM / dependency locking / reproducibility / licensing | #212–#215; proprietary policy #222/#225 | lockfiles, SBOM/reproducibility/license workflows/docs | Internal/owner release evidence | Internal | INTERNAL | external legal/release acceptance remains separate from build evidence |
| 67 | Deployment / governed production autonomy | #143; readiness reconciliation #222 | `deploy/`, manifests, canary/rollback governance | owner/release tooling | hosted env dependent | BLOCKED | actual intended production runtime/SHA/health/data root still must be accepted independently |
| 68 | Qualification & evidence infrastructure | #80–#96; #144+; later dedicated workflows | `qualification/`, `readiness/`, `evidence/`, workflows | owner/admin evidence; CI | Internal | INTERNAL | evidence is SHA/environment-specific and never substitutes for production/physical acceptance |
| 69 | Native emulator / simulator / hosted VM lab | #188–#191 | Sensorium Native Device Lab + Android Emulator/iOS Simulator/hosted VM workflows | qualification only; Sensorium status can show saved evidence | Android emulator/iOS simulator/Linux/Win/macOS VM | INTERNAL | physical devices are explicitly a higher qualification level |
| 70 | Canonical UI blueprint / accessibility system | #250 taxonomy; source completion #251 | `docs/ui/`, `ui_truth.json`, Desktop/PWA/native surfaces | navigation described by current product; settings accessibility where implemented | D:P W:P A:P I:P | PARTIAL | 63/63 source-present but strict visual, behavior, accessibility, error/offline acceptance remains unfinished |

## Current canonical owner navigation

### Desktop
`Home` → `Conversation` → `Memory` → `Knowledge` → `Activities` → `Dashboard` → `Apps & Tools` → `Our Products` → `Settings`.

The executable desktop shell is `CanonicalMainWindow`. Projects, Live Work, Inbox and several detailed owner surfaces still have stronger PWA coverage than desktop coverage.

### PWA / Web
The PWA is the broadest owner surface. The canonical mental model is:

- **Talk with me:** Home / Conversation
- **What I remember:** Memory
- **What I know:** Knowledge
- **What I am doing:** Today / Inbox / Activity / Live Work / Projects
- **What I can access:** Apps & Tools / Capabilities
- **Where I can operate:** Devices / Computer Control / Sensorium
- **Where your data lives:** Data & Storage
- **What you control:** Settings / Security / Recovery / Providers

### Android and iPhone/iPad
The native companions are intentionally narrower. They concentrate on OS-bound work—create/connect/restore, passkeys, device trust, capabilities where supported, Sensorium permissions, recovery and provisioning—and rely on the trusted PWA for the broad owner product rather than duplicating every screen natively.

## Historical/superseded implementations that must not be counted twice

1. **Personal AI branding/source boundary** — PR #1 imported the earlier Personal AI snapshot; later branding/product work made Vishnu the canonical product name.
2. **Early stacked PWA reference branches (#7–#18)** — many were closed/unmerged or integrated through later main-bound UI work such as #19; they are provenance, not separate current products.
3. **Older agent planner/tool contracts (#97/#98 and related E-series branches)** — converged/superseded by the E9 integration in #111.
4. **Capability Forge V1/V2 (#185/#186)** — evolved into V3 (#187); older versions are lineage, not three separate current capability systems.
5. **REA draft #223** — superseded by merged canonical #224.
6. **Voice provider runtime draft #238** — superseded by canonical #239 and integration #240.
7. **UI audits #248/#249** — closed drafts; useful changes were reconciled into the merged 63-screen blueprint #250 and source-completion #251.
8. **Historical architecture snapshots (`ARCHITECTURE.md`, `ARCHITECTURE_V4.md`, `ARCHITECTURE_V5.md`)** — retained history; current authority is `docs/audit/CURRENT_ARCHITECTURE.md` / `docs/architecture/CURRENT.md`.

## Open work not on current `main`

PR **#252**, `feat/owner-capabilities-directory`, is the only open PR at audit time. It is a draft that adds a searchable owner-facing capability guide and an explicit PWA route. It is **not** counted as a current Vishnu capability until merged. Recommended action: continue, exact-head qualify, then merge if its guide remains truthful against this audit.

## Evidence and claim boundary

The existing source-derived audit at PR #245 examined 58 top-level subsystems, 2,407 reachable commits, all 240 PRs then present, 818 static API-style route declarations, 647 Python test modules, platform test suites and workflows. Current `main` is 52 commits ahead of that audited baseline, producing **2,459 reachable commits**. Current PR accounting is **247 total: 207 merged, 39 closed-unmerged, 1 open draft**. The post-baseline UI lineage has been reconciled here. Presence, tests and CI remain distinct from real providers, physical devices, signed distribution, live production state and strict rendered acceptance.