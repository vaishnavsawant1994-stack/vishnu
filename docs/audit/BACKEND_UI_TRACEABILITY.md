# Backend to UI traceability

**Baseline SHA:** `a8d3310b4d9090a42800621b1b27cb6045443c1e`.

This trace maps key domains and marks what was not proven. It does not infer wiring from a similarly named component.

| Domain | Backend/runtime owner | Exposure | Client/UI evidence | User path | Result |
|---|---|---|---|---|---|
| Owner identity/setup | `identity/`, `server/identity_api.py`, hosted and cloud composition | identity/session API; PWA/native handlers | PWA first-run; Android/iOS access, passkey, provisioning and recovery sources | first run / connect / restore | **PARTIAL**; no full fresh-install path executed across all platforms |
| Device trust | `devices/`, `trust_continuity/`, `continuity/` | device and continuity APIs | owner devices page; native connect and Sensorium screens | settings/owner controls or native companion | **PARTIAL**; physical-device and end-to-end approval/revocation not tested in this audit |
| Conversation/model | `agent/`, `models/`, `server/iphone_pwa.py`, runtime composition | conversation and provider APIs | PWA Home/chat; desktop conversation | Home → message | **PARTIAL**; no live model provider exercised here |
| Memory | `memory/`, `server/memory_governance_api.py`, product inspection APIs | memory API and tool/context integration | PWA Memory; desktop memory panel | Memory / Home context | **PARTIAL**; complete mutation/retrieval/UI lifecycle not browser-executed here |
| Knowledge/files | `knowledge/`, `file_intelligence/`, ingestion API | ingestion/search/content APIs | PWA notes/archives and file/knowledge UI | Knowledge / attach or ingest | **PARTIAL**; parser/provider-by-format evidence is not consolidated into a live UI run |
| Capability/OpenAPI/MCP | `capabilities/`, `integrations/`, capability console and ToolRegistry | owner capability APIs; governed tool layer | PWA capability console; native ForgeV3 subset | Apps & Tools / Advanced / native Forge | **PARTIAL**; fixture security tests exist; live third-party consent blocked |
| Data plane | `data_plane/`, `core/sqlite.py`, `continuity/` | policy, transfer, placement and inspection APIs/tools | PWA data policy/cache; native data stores | Settings/data controls | **PARTIAL/BLOCKED**; provider transfer and full cross-client placement not externally verified |
| Projects/work | `projects/`, `automation/`, `future_intelligence/work_orchestration` | project, work-order, workflow, attention APIs | PWA Projects/Work and owner workflow screens | Home → Projects/Work/More | **PARTIAL**; many focused tests, no complete live work journey run for this audit |
| Voice | `voice/`, Voice Intelligence, optional provider runtime | conversation voice, provider, Voice Lab and telephony endpoints | PWA voice controls; native voice/Sensorium code; Owner Control Center | conversation / Voice Lab | **PARTIAL/EXPERIMENTAL/BLOCKED** depending on provider and device; live provider/acoustics not verified |
| Sensorium | `sensorium/`, API routers, DeviceGateway | owner/internal APIs, native consent and qualification | selected native Sensorium screens; lab/evidence consoles | settings/consent/qualification | **INTERNAL/EXPERIMENTAL/PARTIAL**; no real physical device test |
| Product composition/distribution | `products/`, `packaging/`, product APIs | product composer, runners, distribution and release APIs | PWA Our Products and owner qualification UI | Products / owner release | **PARTIAL/EXPERIMENTAL**; actual signing and external distribution blocked |

## Reverse UI trace

Source uses many event handlers and client wrappers. This audit has not executed every button, form, toggle, optimistic update, error state, or rollback path. Therefore disconnected/no-op UI conclusions are not made globally. The highest risk areas to verify with browser/native instrumentation are the connection between API routers and per-surface controls, disabled configuration states that still render, and provider/data error recovery. Keep such entries `NOT VERIFIED` until a test exercises the interaction and asserts persistent backend state and displayed outcome.
