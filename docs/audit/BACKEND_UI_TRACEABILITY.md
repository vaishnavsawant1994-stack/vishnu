# Backend <-> UI Traceability

Baseline: `a8d3310b4d9090a42800621b1b27cb6045443c1e`.

| Domain | Backend authority | Exposure | Product surface | Truth |
|---|---|---|---|---|
| Governed actions | `tools/registry.py` | Internal tool calls / server action APIs | Approval/context UI | Correctly internal core; user controls appear at action/approval points. |
| Approvals | `security/approvals.py` | Approval APIs/Work integration | Approval/Attention surfaces | Connected; durable exact-use authority. |
| Devices | `devices/registry.py`, `devices/gateway.py` | Device/owner APIs | Pairing, Settings/devices, native companions | Connected; physical L4 separately unverified. |
| Memory | `memory/` | Memory owner APIs/context | Desktop Memory + PWA/context | Backend and desktop UI present; exhaustive mobile management parity not verified. |
| Knowledge | `knowledge/`, UCI | Knowledge/content APIs | Knowledge/file surfaces | Backend/UI present; per-format/mobile UX parity varies. |
| Work/Projects | agent/work/project runtimes | Work/Projects APIs/events | Projects/Work/Attention/Agents | Connected and extensively qualified. |
| Universal Capabilities | `integrations/discovery/*` | `server/apps_tools_api.py` | Apps & Tools, `ui/capability_manager.py`, native managers | Connected. OpenAPI/MCP execution attaches to shared ToolRegistry; live external OAuth/provider proof remains separate. |
| Capability Forge | Forge runtime/services | Owner/capability APIs | Apps & Tools/advanced/native management | Present; production external providers/canaries can remain blocked. |
| Computer/browser control | computer/browser tools | Agent/action APIs | Contextual agent + approval feedback | Connected through governed execution; universal app/device behavior not claimed. |
| Data Plane | `data_plane/*` | owner/device/storage APIs | Storage settings/status | Connected policy/control model; provider-specific availability varies. |
| Sensorium | `sensorium/*` | read/owner APIs, agent context | Contextual/Advanced/native permissions | Correctly not a top-level action executor; physical evidence bounded. |
| Voice | `voice/*` | conversation/provider APIs | Conversation voice/settings/capabilities | Core software path present; physical/live-provider parity partial. |
| Products | `products/*` | Products/build APIs | Products UI | Connected; production signing/store external. |
| Intelligence Lab | `intelligence_lab/*` | owner/qualification paths | Advanced/lab controls | Intentionally gated/experimental. |

## Verified Universal Capabilities trace

`Apps & Tools / capability UI -> owner session/device scope -> server/apps_tools_api.py -> CapabilityCatalogStore -> SecretVault credential reference -> owner risk/approval -> attach approved operation/tool -> shared ToolRegistry -> OpenAPI/MCP runtime -> audit -> UI result/history`.

The API also rehydrates connected approved capabilities after restart while still reading live connection/revocation state before provider execution.

## Reverse-trace rules

For each interactive control the required path is:

`control -> handler -> service/client -> API/runtime -> authority -> state/external effect -> persistence/audit -> success/error -> UI refresh`.

No-op/TODO/local-only controls must be classified as disconnected/broken. This audit found no basis for declaring the entire multi-platform control set free of such cases; exhaustive static+runtime control tracing remains `NOT VERIFIED` pending automated inventory. The audit therefore does not issue a false zero-orphan/zero-fake-control claim.
