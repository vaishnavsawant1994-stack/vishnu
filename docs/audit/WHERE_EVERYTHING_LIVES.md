# Where Everything Lives in Vishnu

**Audited main:** `5e2b88bff46bca2d4d212731ddad37fe59a7e88a`

This map identifies canonical source ownership. A path is not proof that a feature is reachable; UI/navigation truth is listed separately.

## Runtime and composition

| Area | Canonical paths | Notes |
|---|---|---|
| Desktop startup | `app/main.py`, `desktop/`, `ui/` | Desktop composition and PyQt owner product |
| Hosted runtime | `server/hosted_runtime.py`, `server/cloud_app.py`, `cloud_runtime/` | Hosted/cloud composition differs from desktop |
| PWA owner product | `server/iphone_pwa.py`, `server/cloud_app.py`, `pwa/` | Broadest current owner surface |
| Android | `android-companion/app/src/main/` | Native companion, OS-bound features |
| iOS/iPadOS | `ios-companion/PersonalAICompanion/` | Native companion, OS-bound features |
| Web companion | `web-companion/` | Secondary companion/control surface |
| Dashboard | `dashboard/` | Operational/control UI family |

## Intelligence and interaction

| Feature | Runtime/service | API/exposure | UI/current owner path |
|---|---|---|---|
| Conversation | `agent/`, model/runtime composition | conversation handlers in `server/iphone_pwa.py` and related routers | Desktop Conversation; PWA Home/composer/history |
| Models/providers | `models/` | owner/provider APIs under `server/` | Settings → AI Models & Providers |
| Adaptive intelligence | `agent/`, intelligence routing/config | runtime/provider APIs | conversation/runtime behavior; configuration-dependent |
| Persistent agents | `agent/`, durable work/evidence code | agent/work APIs | Advanced Agents / Work surfaces |
| Agent Workforce | agent/workforce modules | workforce/agent APIs | PWA Advanced/Agents; work delegation |
| Visual intelligence | `visual_intelligence/` | visual/owner APIs | Create/visualization pathways |
| Training | `training/` | qualification/model release APIs | Advanced/admin; experimental |
| Intelligence Lab | `intelligence_lab/` | lab APIs | Advanced/Labs; experimental |
| Evolution | `evolution/`, `future_intelligence/` | governed engineering/qualification APIs | engineering/qualification only |

## Memory, Knowledge and files

| Feature | Runtime/storage | API | UI |
|---|---|---|---|
| Memory | `memory/`, shared SQLite | `server/owner_product_memory.py`, `server/memory_governance_api.py` | Home → Memory → search/detail |
| Knowledge | `knowledge/`, shared SQLite | owner Knowledge/content APIs | Home → Knowledge → source/upload |
| File intelligence | `file_intelligence/` | `server/content_ingestion_api.py` and related content routes | Knowledge/Add Source; conversation attachment paths |
| Vision | `vision/` + Sensorium bridges | governed capture/observation APIs | permissioned visual input/native Sensorium |

Memory and Knowledge are deliberately separate authorities.

## Voice

| Feature | Paths | Exposure | Owner surface |
|---|---|---|---|
| Voice Intelligence | `voice/` | conversation/voice/provider APIs | Conversation voice + Settings → Voice |
| Optional STT/TTS runtime | `voice/` provider runtime modules | composed only when enabled/configured | mostly automatic/configuration-driven |
| OpenVoice | voice conversion adapter sources | governed optional adapter | advanced voice configuration |
| VoiceStudio | VoiceStudio adapter/integration + MCP projection | Universal Capabilities / configured local service | Voice Studio / advanced capability use |
| Voice Lab | Voice Lab/evidence/benchmark code | lab/telephony endpoints | owner/admin Voice Lab; experimental |

## Identity, security, devices and recovery

| Feature | Canonical paths | API | UI |
|---|---|---|---|
| Owner identity | `identity/`, `onboarding/` | `server/identity_api.py`, owner-product routes | Welcome/Create/Join/Restore |
| Authentication/sessions | `identity/`, `security/` | session/owner access APIs | Sign In/Unlock; Security |
| Passkeys | identity/native WebAuthn/passkey sources | passkey endpoints | Security setup / sign-in methods |
| Recovery | `recovery/`, identity recovery sources | recovery/restore APIs | Welcome → Restore; Settings → Recovery |
| Trusted devices | `devices/`, `trust_continuity/`, `continuity/` | device/owner/continuity APIs | Settings → Devices; native Connect/This Device |
| Device gateway | `devices/` and gateway integrations | device command/status surfaces | primarily automatic/advanced |
| Approvals | `approvals/` | approval center/action APIs | approval prompts / Approvals Center |
| Secrets | `security/`, SecretVault/RootKeyStore | internal service APIs where needed | no low-level normal UI required |
| Audit/security events | security/audit/evidence stores | owner audit/security routes | Settings → Security → Audit History |

## Tools, capabilities and external integrations

| Feature | Canonical paths | API | UI |
|---|---|---|---|
| ToolRegistry | `tools/` | governed tool layer | Apps & Tools indirectly |
| Apps & Tools | `apps_tools/` | owner tool/integration APIs | Apps & Tools |
| OpenAPI capabilities | `capabilities/`, `integrations/` | `server/capability_console_api.py` and related routers | Apps & Tools → Capabilities → Add → OpenAPI |
| MCP capabilities | `capabilities/`, MCP transports/integrations | capability console/tool layer | Apps & Tools → Capabilities → Add → MCP |
| Credentials | capabilities + `security/` vault | capability credential endpoints | Capability Detail → credential/rotate/revoke |
| Plugins | `plugins/` | plugin/integration APIs | Apps & Tools where surfaced |
| Browser control | `browser/` + computer-control adapters | governed control APIs | Settings/Advanced → Computer & Browser Control |
| Capability Forge | Forge V3 sources | advanced capability APIs | advanced/testing; primarily iOS subset |
| REA | integration configuration and MCP projection | Universal Capabilities/ToolRegistry | available when REA/Node environment is installed/configured |

## Data and storage

| Feature | Canonical paths | Exposure | UI |
|---|---|---|---|
| Shared SQLite | `core/sqlite.py` + per-domain migrations | internal | no dedicated UI required |
| Data Plane | `data_plane/` | owner policy/placement/transfer APIs | Settings → Data & Storage; first-run Data Placement |
| PWA offline cache | `pwa/data-plane-cache.js` and related PWA code | browser storage/data-plane bridge | automatic/offline behavior |
| Storage Fabric | `data_plane/storage_fabric.py` + providers | provider health/detail/transfer APIs and inspection tools | Data & Storage → provider detail |
| Encrypted transfer | `data_plane/` transport/envelope code | internal transfer boundary | automatic during governed transfer |
| Backup/restore | `recovery/`, DR/backup code | operational/recovery APIs/tools | Recovery and operational tooling |

Frozen policy names: `device_only`, `progress_only`, `sync_everywhere`, `on_demand`.

## Work, Projects, automation and attention

| Feature | Paths | API | UI |
|---|---|---|---|
| Canonical Work | work orchestration/evidence authorities under current work/future-intelligence composition | work-order/claim/evidence/recovery APIs | Live Work / Work Detail / Today |
| Projects | `projects/` | project/work APIs | Projects → Project Workspace |
| Automation | `automation/` | workflow/run/approval/recovery APIs | Automations / Workflows |
| Attention | attention/work projection modules | inbox/attention APIs | Inbox / Attention Center |
| Notifications | `notifications/` | notification preference/event APIs | Notification Settings / attention |
| Activities | `activities/`, `evidence/` | activity/evidence APIs | Activity timeline / Work Detail |
| Proactive | `proactive/` | background/owner-controlled services | mostly automatic; owner settings where surfaced |

## Sensorium

| Feature | Paths | API | UI |
|---|---|---|---|
| Sensorium core | `sensorium/` | Sensorium/context/world APIs | native privacy/sensor controls; advanced status |
| Native Device Lab | Sensorium provider/evidence code + workflows | read-only owner evidence/status APIs | Settings/Advanced → Sensorium Status |
| Android Emulator | workflows/qualification + Sensorium provider | evidence only | qualification |
| iOS Simulator | workflows/qualification + Sensorium provider | evidence only | qualification |
| Hosted desktop VMs | workflows/qualification + provider evidence | evidence only | qualification |

No normal-product adb/simctl/shell console is canonical.

## Products, packaging and release

| Feature | Paths | API | UI |
|---|---|---|---|
| Our Products | `products/` | product composer/build/distribution APIs | Our Products → Product Detail/Build |
| Packaging | `packaging/` | build/package tooling | release/engineering |
| Installer | `installer/` | installation tooling | platform-specific |
| Updates | `updates/` | governed release/update status | Settings → About / Updates |
| Deploy | `deploy/`, deployment manifests such as `render.yaml` | release/deployment integrations | release/owner tooling |
| Qualification | `qualification/`, `readiness/` | CI/evidence APIs/tools | owner/admin/CI |
| Evidence | `evidence/` | evidence/claim/release artifacts | Activity/Work/qualification views where applicable |
| SBOM/reproducibility | workflows/scripts/lockfiles/docs | CI artifacts | release evidence; internal |

## Canonical owner navigation

### Desktop executable shell

`CanonicalMainWindow` currently exposes these top-level destinations:

1. Home
2. Conversation
3. Memory
4. Knowledge
5. Activities
6. Dashboard
7. Apps & Tools
8. Our Products
9. Settings

Desktop is not currently the most complete surface for Projects, Inbox, Live Work and several detailed owner views.

### PWA / Web

The PWA is the broadest owner product. Current goal-oriented locations include:

- Conversation: Home → composer; History → thread
- Memory: Home → Memory → Search → Detail
- Knowledge: Home → Knowledge → source / Add Source
- Attention: Home → Inbox/Attention
- Work: Home → Live Work → Work Detail
- Projects: Home → Projects → Project Workspace
- Automations: More/System → Automations
- Integrations/capabilities: Apps & Tools → Capabilities
- Devices: Settings/More → Devices
- Data: Settings → Data & Storage
- AI providers: Settings → AI Models & Providers
- Voice: Settings → Voice
- Security: Settings → Security
- Recovery: Settings → Recovery
- Diagnostics: Settings/Account → System Status
- Version/release: Settings → About / Updates

### Native companions

Android and iOS intentionally concentrate on OS-bound tasks. Their canonical role is not to duplicate the entire PWA. Native paths include create/connect/restore, device trust, passkeys/provisioning, selected capability management, Sensorium privacy/sensors and recovery, plus opening the trusted PWA for broad owner work.

## Internal systems that should not receive duplicate owner pages

The following are implementation authorities and are not UI gaps by themselves:
- SQLite connection/migration mechanics
- Root key derivation/storage details
- SecretVault envelope/AAD/nonce internals
- ToolRegistry registration internals
- one-use approval durability internals
- event transport/bus mechanics
- conflict-resolution algorithms
- leases/replay-protection internals
- encrypted transport framing
- retry/backoff machinery
- audit hash-chain mechanics
- qualification/evidence persistence mechanics

## Historical paths/docs that are not current architecture authority

`ARCHITECTURE.md`, `ARCHITECTURE_V4.md`, `ARCHITECTURE_V5.md` are retained historical snapshots. Use `docs/audit/CURRENT_ARCHITECTURE.md` and `docs/architecture/CURRENT.md` as the current architecture references. Older UI taxonomies on closed PRs #248/#249 are also superseded by the 63-screen truth from #250/#251.