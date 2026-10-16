# Repository Inventory

Audited baseline: `a8d3310b4d9090a42800621b1b27cb6045443c1e`.

Status here describes the subsystem's role, not universal production readiness.

| Path | Purpose / current interpretation | Primary owner/exposure | Audit status |
|---|---|---|---|
| `activities/` | Activity/event domain backing owner activity history. | Server Activities API, desktop/PWA Activities. | Active |
| `agent/` | Agent planning/execution/context/durable task behavior. | Conversation, Work, ToolRegistry. | Active |
| `android-companion/` | Native Android trusted-device companion. | Device/session/pairing/capability/Sensorium/data-plane surfaces. | Active; physical device not fully verified |
| `app/` | Application/runtime composition and launch plumbing. | Product runtime. | Active |
| `approvals/` | Approval-related product/runtime helpers distinct from canonical durable security authority. | Approval UI/services. | Active/delegating |
| `apps_tools/` | Apps & Tools projections/product model. | Owner Apps & Tools UI/API. | Active |
| `automation/` | Schedules/cron/background automation engine. | Work/tools/owner APIs. | Active |
| `browser/` | Browser-related runtime/control support. | Agent/computer-control. | Active |
| `capabilities/` | Capability evaluation/benchmark code. **Not** the Universal Capabilities catalog authority. | Evaluation/qualification. | Active/internal |
| `cloud_runtime/` | Optional hosted/cloud runtime plumbing. | Runtime/deployment. | Active/conditional |
| `config/` | Runtime/environment configuration. | All runtimes. | Active |
| `continuity/` | Process/device/agent continuity support. | Agent/device/recovery. | Active |
| `core/` | Shared core/runtime primitives. | Cross-cutting. | Active |
| `dashboard/` | Dashboard models/services. | Desktop/PWA/API. | Active |
| `data_plane/` | Local-first data policies, transport, leases, encryption, providers/storage fabric. | Owner storage settings/runtime. | Active/canonical |
| `deploy/` | Deployment definitions/helpers. | Non-production/prod configuration boundary. | Active; deployment not executed by audit |
| `desktop/` | Desktop platform/runtime integration. | Native app/packaging. | Active |
| `devices/` | Canonical DeviceRegistry and DeviceGateway plus device support. | Trusted-device APIs/companions/Sensorium. | Active/canonical |
| `docs/` | Architecture, security, qualification and product documentation. | Engineering. | Mixed current/historical |
| `evidence/` | Evidence/receipt lifecycle and qualification/action evidence. | Persistent agents/security/qualification. | Active |
| `evolution/` | Governed self-improvement/evolution logic. | Intelligence Lab/owner controls. | Active/gated |
| `file_intelligence/` | File parsing/retrieval/grounding support. | Knowledge/UCI. | Active |
| `future_intelligence/` | Future/advanced intelligence research domain. | Advanced/gated paths. | Experimental/internal |
| `identity/` | Owner identity/authentication/recovery concepts. | Onboarding/security. | Active |
| `installer/` | Install/bootstrap support. | Distribution. | Active |
| `integrations/` | Connector state, OAuth, gateway and **Universal Capabilities** discovery/execution under `integrations/discovery/`. | Apps & Tools, ToolRegistry, SecretVault. | Active/canonical |
| `intelligence_lab/` | Governed research/autonomy/optimization laboratory. | Advanced owner controls/qualification. | Experimental/gated |
| `ios-companion/` | Native iOS trusted-device companion. | Device/session/pairing/capability/Sensorium/data-plane surfaces. | Active; simulator verified, physical device bounded |
| `knowledge/` | User/source knowledge store, retrieval/indexing. | Knowledge API/UI and UCI. | Active/canonical |
| `memory/` | Personal memory store/context retrieval. | Memory API/UI and agent context. | Active/canonical; separate from Knowledge |
| `models/` | Model routing/provider/artifact logic. | Conversation/intelligence/training. | Active |
| `notifications/` | Notification domain/providers/hooks. | Attention/proactive/native. | Active/externally conditional |
| `onboarding/` | First-run/create/existing/restore orchestration. | Desktop/PWA/native. | Active |
| `packaging/` | Package/build artifact logic. | Release/product build. | Active |
| `personal-ai/` | Legacy/product package namespace retained in repository. | Historical/runtime compatibility depending file. | Mixed; requires per-file classification |
| `playbooks/` | Qualified reusable plans/playbooks. | Agent/Work. | Active |
| `plugins/` | Plugin/integration extension logic. | Tool/integration layer. | Active |
| `proactive/` | Proactive preferences/suggestions/behavior. | Dashboard/notifications. | Active |
| `products/` | Our Products manifests/runtime/build domain. | Products UI/API/build. | Active |
| `projects/` | Project domain linked to Work. | Projects UI/API/Work. | Active |
| `pwa/` | Web/PWA product surface and assets. | Browser/mobile web. | Active |
| `qualification/` | Qualification/evidence harnesses. | CI/release gates. | Active/internal |
| `readiness/` | Production/readiness evidence and status. | Release/owner. | Active/internal |
| `recovery/` | Recovery/restore/DR orchestration. | Identity/data/work/device recovery. | Active |
| `scripts/` | Build/qualification/migration/audit utilities. | Engineering/CI. | Active/internal |
| `security/` | Approval, request-context, sessions, secrets and security authorities. | All sensitive runtime paths. | Active/canonical |
| `sensorium/` | Sensor/provider abstraction, evidence, world/observation systems. | Agent/device owner APIs. | Active; physical L4 bounded |
| `server/` | FastAPI/owner/device/PWA API modules and runtime composition. | All clients. | Active |
| `tests/` | Unit/integration/security/recovery/qualification tests. | CI. | Active |
| `tools/` | Canonical ToolRegistry plus internal/governed tool implementations. | Agent/Work/capabilities. | Active/canonical |
| `training/` | Governed training/model workflows. | Intelligence/self-improvement. | Active/gated |
| `trust_continuity/` | Trust/recovery continuity components. | Identity/device/recovery. | Active |
| `ui/` | Native desktop PyQt UI and focused dialogs/panels. | Desktop. | Active |
| `updates/` | Update/release update logic. | Product/release. | Active |
| `vision/` | Vision processing/provider logic. | Sensorium/conversation. | Active |
| `visual_intelligence/` | Visual workspace/intelligence analysis. | Visualize/agent. | Active |
| `voice/` | Voice runtime/providers/personas/director/telephony boundaries. | Conversation/Sensorium/Apps & Tools. | Active; some provider paths gated |
| `web-companion/` | Browser companion/trusted web-device support. | Web/device path. | Active |

## Canonical authority decisions

- Governed actions: `tools/registry.py` (`ToolRegistry`).
- Durable action approvals: `security/approvals.py` (`ApprovalManager`).
- Trusted devices: `devices/registry.py` (`DeviceRegistry`).
- Device transport/dispatch: `devices/gateway.py` (`DeviceGateway`).
- Universal Capabilities: `integrations/discovery/*` + `server/apps_tools_api.py` + product UIs.
- Secrets/credentials: SecretVault/root-key authorities; capability/connector stores hold references, not raw secret authority.
- Memory: `memory/` domain/store.
- Knowledge: `knowledge/` domain/store; intentionally separate from Memory.
- Local-first movement/sync: `data_plane/`.
- Sensing/observation: `sensorium/`; does not replace ToolRegistry as action authority.

## Architecture-document reconciliation

- `ARCHITECTURE.md`: historical V2, materially incomplete for current code.
- `ARCHITECTURE_V4.md`, `ARCHITECTURE_V5.md`: historical evolution references; current claims must be verified against source.
- `docs/architecture/CURRENT.md`: canonical current architecture created by this audit.
- `docs/audit/VISHNU_PRODUCT_TRUTH_MAP.md`: canonical implementation/status evidence map.

## Known inventory limitations

This first audit PR classifies every top-level subsystem and the major nested authorities, but does not claim a manually verified import graph for every individual source file. Per-file orphan/import/API-consumer generation is a follow-up automated-analysis item and remains `NOT VERIFIED` rather than being inferred from file presence.
