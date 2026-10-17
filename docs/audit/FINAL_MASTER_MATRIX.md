# Vishnu Definitive Feature Matrix

**Audited main:** `5e2b88bff46bca2d4d212731ddad37fe59a7e88a`

This table is the compact development view. Detailed lineage, usage and caveats are in `WHAT_VISHNU_HAS.md`, `FEATURE_PROVENANCE.md`, `WHERE_EVERYTHING_LIVES.md`, `VISHNU_CURRENT_COMPLETENESS.md` and `docs/OWNER_GUIDE.md`.

`Introduced` names a merged/current-main entry point, not a closed draft. Closed-unmerged predecessors remain recorded in `CLOSED_UNMERGED_PR_INVENTORY.md` and `feature_history.json` lineage.

Legend: D desktop, W PWA/web, A Android, I iOS/iPadOS. `P` partial, `E` experimental, `B` externally blocked, `N/A` deliberate non-native surface. Tests are summarized as `focused`, `broad CI`, `platform CI`, or `internal`; none implies production acceptance.

| ID | Domain | Feature | Introduced | Current path | API/service | UI / how to use | D | W | A | I | Test/evidence | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| CORE-RUNTIME | Core | Runtime composition | #1 / typed #207 | `app/`, `server/`, `cloud_runtime/` | composition roots | automatic | P | P | P | P | broad CI | PARTIAL |
| CONVERSATION | Conversation | Conversation lifecycle | #1 | `agent/`, `pwa/`, `desktop/` | conversation handlers | Home/Conversation → send | P | P | companion | companion | broad CI | PARTIAL |
| MODEL-ROUTING | Models | Model/provider routing | #1; major #114 | `models/` | provider/router APIs | Settings → AI Models & Providers | P | P | P | P | provider contracts | PARTIAL |
| ADAPTIVE-INTELLIGENCE | Agent | STANDARD/SMART/DEEP/RESEARCH/AUTO | #117 | `agent/` | routing policy | conversation/runtime config | P | P | N/A | N/A | focused | PARTIAL |
| PERSISTENT-AGENTS | Agent | Durable agent identity/execution | #99 | `agent/` | agent/work APIs | Advanced Agents/Work | P | P | N/A | N/A | recovery/concurrency | PARTIAL |
| AGENT-WORKFORCE | Agent | Specialist agents/teams | #114 | `agent/`, `future_intelligence/agent_workforce/` | workforce APIs | Advanced/Agents | gap | E | N/A | N/A | focused | PARTIAL |
| VISUAL-INTELLIGENCE | Intelligence | Visualize | #116 | `visual_intelligence/` | visual APIs | Create/visualization | P | P | N/A | N/A | focused | PARTIAL |
| TRAINING | Intelligence | Training/self-improvement | #119 | `training/` | training/qualification | Advanced/admin | E | E | N/A | N/A | qualification | EXPERIMENTAL |
| INTELLIGENCE-LAB | Intelligence | Intelligence Lab | #231 | `intelligence_lab/` | lab APIs | Advanced/Labs | E | E | E | E | dedicated CI | EXPERIMENTAL |
| EVOLUTION | Engineering | Evolution/code autonomy research | #142 | `evolution/`, `future_intelligence/` | governed engineering | engineering only | E | E | N/A | N/A | qualification | EXPERIMENTAL |
| MEMORY | Memory | Memory | #1 | `memory/` | owner Memory/governance APIs | Memory → search/detail | P | P | N/A | N/A | broad/fault/DR | PARTIAL |
| MEMORY-GOV | Memory | Governance/at-rest protection | #199/#205 | `memory/`, `security/` | governance/storage | Memory/Privacy | P | P | N/A | N/A | security/fault | PARTIAL |
| KNOWLEDGE | Knowledge | Knowledge | #1 | `knowledge/` | Knowledge APIs | Knowledge → source | P | P | P | P | broad | PARTIAL |
| FILE-INTELLIGENCE | Knowledge | File/content intelligence | #165 | `file_intelligence/` | content-ingestion APIs | Knowledge → Add Source | P | P | P | P | format/qualifier | PARTIAL |
| VISION | Vision | Permissioned vision | #227 | `vision/` | capture/observation APIs | governed visual input | P | P | P | P | focused | PARTIAL |
| SENSORIUM-VISION | Sensorium | Visual Sensorium | #227 | `sensorium/`, `vision/` | Sensorium APIs | native privacy/sensors | P | P | P | P | platform/focused | PARTIAL |
| SENSORIUM-WORLD | Sensorium | Context/world model | #228 | `sensorium/` | world/context APIs | Advanced Sensorium | E | E | P | P | focused | EXPERIMENTAL |
| SENSORIUM-CAUSAL | Sensorium | Causal/procedural intelligence | #229 | `sensorium/` | causal/task APIs | advanced/internal | E | E | E | E | benchmark/focused | EXPERIMENTAL |
| SENSORIUM-NATIVE | Sensorium | Native provider/evidence layer | #191 | `sensorium/`, `qualification/` | read-only evidence/status | Sensorium Status/native privacy | qualification | P | P | P | emulator/simulator/VM | PARTIAL |
| VOICE | Voice | Voice conversation | #1 | `voice/` | voice/conversation APIs | microphone / Settings → Voice | P | P | P | P | voice CI | PARTIAL |
| VOICE-INTELLIGENCE | Voice | Director/personas/lexicon | #237 | `voice/` | voice planning | Voice/Voice Studio | P | P | N/A | N/A | focused | PARTIAL |
| VOICE-RUNTIME | Voice | Optional STT/TTS provider runtime | #239 | `voice/` | provider protocols/runtime | configured provider | B | B | B | B | contracts | BLOCKED |
| OPENVOICE | Voice | OpenVoice conversion | #236 | `voice/` | optional adapter | advanced voice setup | B | N/A | N/A | N/A | focused | BLOCKED |
| VOICESTUDIO | Voice | VoiceStudio | #241 | `voice/`, `capabilities/` | provider/MCP | Voice Studio/capability | P | N/A | N/A | N/A | capability tests | PARTIAL |
| VOICE-LAB | Voice | Voice Lab/telephony | #243 | `voice/`, `qualification/` | lab/telephony | Voice Lab | E | N/A | N/A | N/A | voice-lab CI | EXPERIMENTAL |
| IDENTITY | Identity | Owner identity/first run | #192 | `identity/`, `onboarding/` | identity APIs | Welcome → Create | P | P | P | P | identity/recovery | PARTIAL |
| AUTH | Identity | Auth/sessions | #1 | `identity/`, `security/` | session APIs | Sign In/Security | gap | P | gap | P | security | PARTIAL |
| PASSKEY | Identity | Passkeys | #220 | identity/native sources | passkey/WebAuthn | Security → Sign-in Methods | P | P | P | P | platform source/tests | PARTIAL |
| RECOVERY | Recovery | Restore/recovery | #192 | `recovery/`, `identity/` | recovery APIs | Restore Vishnu / Recovery | P | P | gap | P | DR/recovery | PARTIAL |
| TRUSTED-DEVICES | Devices | Trusted devices | #1; expanded #183/#220 | `devices/`, continuity dirs | device owner APIs | Settings → Devices | P | P | P | P | emulator/simulator/focused | PARTIAL |
| DEVICE-GATEWAY | Devices | Gateway/connectivity | #1; native lab #191 | `devices/` | DeviceGateway | Add Device/native Connect | P | P | P | P | native lab | PARTIAL |
| CONTINUITY | Devices | Continuity/trust continuity | #108 | `continuity/`, `trust_continuity/` | continuity APIs | automatic/recovery/work | P | P | P | P | recovery/concurrency | PARTIAL |
| APPROVALS | Security | ApprovalManager | #1 | `approvals/` | approval APIs | prompts/Approvals Center | gap | P | P | P | security/focused | PARTIAL |
| SECRET-VAULT | Security | Vault/root-key rotation | #200 | `security/` | internal | no dedicated UI | internal | internal | internal | internal | rotation/fault | COMPLETE |
| AUDIT | Security | Security/audit events | #1 | `security/`, `evidence/` | audit APIs | Security → Audit History | gap | P | N/A | N/A | assurance | PARTIAL |
| CYBER-ASSURANCE | Security | Cybersecurity assurance | #226 | `qualification/`, workflows | evidence | CI/admin | internal | internal | internal | internal | exact-SHA workflow | INTERNAL |
| TOOL-REGISTRY | Tools | ToolRegistry/Apps & Tools | #1 | `tools/`, `apps_tools/` | tool layer | Apps & Tools | P | P | N/A | N/A | broad | PARTIAL |
| CAP-OPENAPI | Capabilities | OpenAPI import/execution | #183 | `capabilities/`, `integrations/` | capability console | Capabilities → Add OpenAPI | P | P | P | P | TLS/security fixtures | PARTIAL |
| CAP-MCP | Capabilities | MCP discovery/execution | #183 | `capabilities/`, integrations | capability/tool layer | Capabilities → Add MCP | P | P | P | P | security/schema fixtures | PARTIAL |
| CAP-CREDENTIALS | Capabilities | Credential rotation/revoke | #183 | capabilities + `security/` | credential APIs | Capability Detail | P | P | P | P | security/focused | PARTIAL |
| CAP-FORGE | Capabilities | Capability Forge V3 | #185→#187 | capability/native Forge | advanced APIs | iOS Advanced/Forge | N/A | N/A | N/A | E | focused | EXPERIMENTAL |
| REA | Integrations | REA 6.5.0 stdio MCP | #224 | integrations/capabilities | MCP/ToolRegistry | Apps & Tools when installed | P | P | N/A | N/A | catalog/integration | PARTIAL |
| COMPUTER-CONTROL | Control | Browser/computer control | #1 | `browser/`, device adapters | control APIs | Desktop Advanced | P | gap | N/A | N/A | focused/security | PARTIAL |
| INTEGRATIONS | Integrations | Plugins/integrations | #1 | `plugins/`, `integrations/` | service-specific | Apps & Tools | P | P | N/A | N/A | adapter-specific | PARTIAL |
| SQLITE | Data | Shared SQLite/migrations | #203 | `core/sqlite.py` + domains | internal | no UI | internal | internal | internal | internal | migration/concurrency/fault | INTERNAL |
| DATA-PLANE | Data | Local-first policies | #195 | `data_plane/` | owner data APIs | Data & Storage / first run | P | P | gap | N/A | data-plane CI | PARTIAL |
| DATA-TRANSPORT | Data | Encrypted transfer | #196 | `data_plane/` | internal transfer | automatic | internal | internal | internal | internal | security/transport | INTERNAL |
| STORAGE-FABRIC | Data | Remote providers/storage fabric | #197; expanded #245 | `data_plane/storage_fabric.py` | provider/detail/transfer | Provider Detail | gap | P | N/A | N/A | fixture/security | BLOCKED |
| DISASTER-RECOVERY | Recovery | Backup/DR foundation | #216 | `recovery/`, `readiness/` | operational | Recovery | B | B | B | B | DR/fault | BLOCKED |
| CANONICAL-WORK | Work | WorkPlan/WorkOrder/Evidence | #62 | work/project/evidence code | work APIs | Live Work/Work Detail | gap | P | N/A | N/A | extensive | PARTIAL |
| PROJECTS | Work | Projects | #46 | `projects/` | project/work APIs | Projects → Workspace | gap | P | N/A | N/A | focused | PARTIAL |
| AUTOMATION | Automation | Workflows/automation | #1 | `automation/` | workflow APIs | Automations/Workflows | P | P | N/A | N/A | focused/recovery | PARTIAL |
| ATTENTION | Work | Inbox/Attention | #73 | work/activity projection | attention APIs | Inbox/Attention | gap | P | N/A | N/A | focused | PARTIAL |
| NOTIFICATIONS | Work | Notifications | #77 | `notifications/` | notification APIs | Notification Settings | P | P | P | P | focused | PARTIAL |
| ACTIVITIES | Work | Activity/evidence | #76 | `activities/`, `evidence/` | activity APIs | Activities/Activity | P | P | N/A | N/A | focused | PARTIAL |
| PROACTIVE | Automation | Proactive systems | #1 | `proactive/` | background services | automatic/settings | P | P | P | P | focused | PARTIAL |
| PRODUCTS | Products | Product Composer/runners | #150 | `products/`, `packaging/` | product/build APIs | Our Products | E | E | target | target | product-runner CI | EXPERIMENTAL |
| DESKTOP-UI | Platform | Desktop owner product | #1 | `desktop/`, `ui/`, `app/main.py` | local/owner APIs | CanonicalMainWindow | P | N/A | N/A | N/A | package/UI tests | PARTIAL |
| PWA | Platform | Web/PWA owner product | #3 | `pwa/`, `server/iphone_pwa.py` | owner PWA routes | browser owner product | N/A | P | N/A | N/A | browser/responsive | PARTIAL |
| ANDROID | Platform | Android companion | #1 | `android-companion/` | owner/device/capability APIs | native Connect/Trust | N/A | N/A | P | N/A | emulator/instrumentation | PARTIAL |
| IOS | Platform | iOS/iPadOS companion | #1 | `ios-companion/` | owner/device/capability APIs | native Create/Trust/Sensorium | N/A | N/A | N/A | P | simulator/build | PARTIAL |
| WEB-COMPANION | Platform | Web companion/dashboard | #1 | `web-companion/`, `dashboard/` | secondary APIs | configured companion | N/A | P | N/A | N/A | responsive/focused | PARTIAL |
| UNIVERSAL-ONBOARDING | Identity | Any-platform Device 1 | #192; universalized #220 | onboarding/identity/platform clients | identity/provisioning | Welcome → Create/Join/Restore | P | P | P | P | platform/focused | PARTIAL |
| PACKAGING | Release | Packages/installers | #96 | `packaging/`, `installer/` | build tooling | engineering/release | P | N/A | target | target | package validation | PARTIAL |
| UPDATES | Release | Updates/release authority | #96 | `updates/`, release code | release/status | About / Updates | P | P | platform | platform | release authority | PARTIAL |
| SUPPLY-CHAIN | Release | SBOM/locks/repro/license | #212 | workflows/scripts/docs | CI evidence | internal | internal | internal | internal | internal | SBOM/repro CI | INTERNAL |
| DEPLOYMENT | Release | Governed deploy/canary | #143 | `deploy/`, manifests | deployment integrations | release tooling | N/A | hosted B | N/A | N/A | preview/release CI | BLOCKED |
| QUALIFICATION | Qualification | Evidence/qualification | #80 | `qualification/`, `readiness/`, `evidence/` | evidence tooling | CI/admin | internal | internal | internal | internal | many workflows | INTERNAL |
| NATIVE-LAB | Qualification | Emulator/simulator/VM lab | #191 | Sensorium/qualification/workflows | evidence/status | qualification | VM | read-only status | emulator | simulator | platform CI | INTERNAL |
| UI-BLUEPRINT | UI | 63-screen taxonomy/a11y system | #250 | `docs/ui/` + product UIs | machine truth | product-wide | P | P | P | P | validator/source tests | PARTIAL |

## Matrix interpretation

- **0 user-facing rows are promoted to strict COMPLETE.**
- The one COMPLETE row is a narrowly scoped internal security behavior.
- A green test/evidence cell does not mean production, provider or physical-device acceptance.
- Native `N/A` is not a bug: many broad owner tasks intentionally use the PWA.
- The current UI machine authority reports 63 canonical screens, all source-present, 58 partial, 5 experimental, 0 missing concepts and 0 strict complete.
