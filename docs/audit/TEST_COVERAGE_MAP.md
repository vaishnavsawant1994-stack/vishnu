# Test Coverage Map

Baseline: `a8d3310b4d9090a42800621b1b27cb6045443c1e`.

This map distinguishes test categories from production proof.

| Domain | Evidence located | Highest justified claim |
|---|---|---|
| ToolRegistry/approvals/security | Unit/integration/security/recovery tests plus assurance/release gates | Governed execution and durable approval behavior are strongly qualified in repository scope. |
| Work/Projects/Agents | Unit/integration plus dedicated consistency, performance, qualification and release workflows | Durable Work lifecycle qualified in CI scope. |
| OpenAPI/MCP capabilities | Catalog/import/discovery/execution/native-session/live-HTTPS fixture tests | Internal/test-fixture E2E; not every public API/MCP provider. |
| Device trust/continuity | Registry/gateway/recovery tests plus native/emulator work | Software + emulator/simulator scope; physical L4 separate. |
| Data Plane/storage | Data-plane workflow, security/recovery, transfer/provider tests | Local-first policy/encrypted transfer/storage-fabric scope; live provider fleet not universal. |
| Memory/Knowledge/shared SQLite | Migration, encryption, backup/restore, concurrency/fault work | Local datastore behavior strongly qualified; production-volume restore still separate. |
| Universal Content Intelligence | Parser/OCR/media/semantic tests and evidence gates | Supported fixture/runtime scope; advanced OCR real-world corpus remains bounded. |
| Sensorium | Sensorium qualification workflow, virtual/emulator/simulator/hosted-VM evidence | L1-L3 scope; no physical L4 claim. |
| Voice | Voice Lab workflow/provider-boundary tests | Software/loopback/test-provider scope; physical acoustics/real telephony separate. |
| Products/build | Product governance, platform-build/package/release workflows | Development/build artifact scope; production signing/store acceptance external. |
| Intelligence Lab/self-improvement | Phase workflows, ML/dependency/release evidence | Gated experimental/qualification scope; live real-world evidence still required where specified. |
| Architecture/release | architecture-invariants, assurance, dependency audit, SBOM/reproducibility/release-authority workflows | Repository architecture/release gates; not production acceptance. |

## Current main check truth

The exact audited main SHA had successful registered GitHub check-runs when inspected. That result is evidence for that exact SHA only.

## Coverage rule

A feature with unit tests only is not labelled end-to-end verified. Mocks/fixtures do not count as live-provider evidence. Emulator/simulator does not count as physical hardware. CI does not count as production deployment or store acceptance.

## Remaining coverage work

- Framework-native exhaustive route-to-test mapper: NOT VERIFIED.
- UI-control-to-handler/API automated reachability across all PWA/native screens: NOT VERIFIED.
- Physical Android/iOS Sensorium/voice/background/camera qualification: BLOCKED/NOT VERIFIED.
- Live external OAuth/API/MCP/telephony provider qualification: provider/owner dependent.
- Production mounted-volume backup/restore and running-production-SHA acceptance: external production task, not performed here.
