# Vishnu Current Architecture

Canonical baseline: `a8d3310b4d9090a42800621b1b27cb6045443c1e`.

This is the current engineering reference. Root `ARCHITECTURE.md`, `ARCHITECTURE_V4.md` and `ARCHITECTURE_V5.md` remain useful historical documents but do not override live code.

## System context

```mermaid
flowchart LR
  O[Owner] --> S[Desktop / PWA / Android / iOS]
  S --> API[Owner + Device APIs]
  API --> R[Vishnu Runtime]
  R --> I[Identity / Security]
  R --> A[Agent / Work / Automation]
  R --> M[Memory]
  R --> K[Knowledge + Content Intelligence]
  R --> T[ToolRegistry]
  R --> D[DeviceRegistry + DeviceGateway]
  R --> DP[Local-first Data Plane]
  R --> SE[Sensorium]
  T --> C[OpenAPI / MCP / Apps / Tools]
  T --> CC[Computer + Browser Control]
  D --> N[Trusted devices / emulator / simulator / hosted VM]
  DP --> LS[Local stores]
  DP --> PS[Optional provider storage]
  C --> X[External systems]
```

## Runtime flow

```mermaid
flowchart LR
  U[User input] --> CX[Conversation/context]
  CX --> MR[Model/router/reasoning]
  MR --> AG[Agent/Work decision]
  M[Memory] --> CX
  K[Knowledge] --> CX
  AG --> TR[ToolRegistry]
  TR --> PG[Policy/risk gateway]
  PG --> AP[ApprovalManager when required]
  AP --> EX[Governed execution]
  EX --> AU[Audit/evidence]
  EX --> CX
  CX --> OUT[Response/UI]
```

## Identity and security

- Owner identity is separate from device identity.
- Trusted devices are owned by the canonical `DeviceRegistry`; communication/dispatch belongs to `DeviceGateway`.
- Sessions/request context must resolve to an active trusted device with appropriate scope for owner/device APIs.
- Sensitive owner changes can require recent reauthentication.
- `ToolRegistry` is the canonical governed action boundary. Risk, permission, destination and classification rules are evaluated before execution.
- `ApprovalManager` is the durable approval authority. Approval tickets bind execution/tool/parameters/owner/device/session/security epoch and bounded use count; uncertain dispatch is fenced for recovery.
- `SecretVault`/root-key systems own secrets and credential references. APIs should not return raw credentials.
- Emergency stop/autonomy controls and security epochs are durable.
- Audit/evidence records are part of the execution contract, not optional UI telemetry.

## Action/capability architecture

```mermaid
flowchart LR
  UI[Apps & Tools / Context UI] --> OA[Owner API]
  OA --> CAT[Capability catalog]
  CAT --> CR[Credential reference / SecretVault]
  CAT --> APP[Owner risk/approval]
  APP --> TR[Shared ToolRegistry]
  TR --> OAPI[OpenAPI executor]
  TR --> MCP[MCP runtime]
  TR --> IT[Internal tools/integrations]
  OAPI --> AUD[Audit]
  MCP --> AUD
  IT --> AUD
```

Universal Capabilities lives under `integrations/discovery/*` and `server/apps_tools_api.py`. The top-level `capabilities/` directory is evaluation/benchmark code and must not be treated as the capability catalog authority.

Approved OpenAPI/MCP operations are attached to the existing ToolRegistry; restart rehydration reconstructs approved registrations while live connection rows/revocation still fence execution. Capability discovery is distinct from executable approval.

## Device and Sensorium architecture

```mermaid
flowchart LR
  UI[Owner/agent request] --> DR[DeviceRegistry]
  DR --> DG[DeviceGateway]
  DG --> TD[Trusted device/provider]
  TD --> RES[Observation/result]
  RES --> EV[Evidence]
  EV --> UI
  SEN[Sensorium] --> DR
  SEN --> DG
```

Sensorium is a sensing/observation/world-model authority, not an action-authority bypass. Virtual simulation, Android Emulator, iOS Simulator and hosted Linux/Windows/macOS VM providers can qualify hardware-free paths. Physical-device L4 is a distinct evidence boundary.

## Data architecture

```mermaid
flowchart LR
  C[Runtime/UI] --> P{Storage policy}
  P -->|device_only| L[Local store]
  P -->|progress_only| L
  P -->|sync_everywhere| L
  P -->|on_demand| L
  L --> LEASE[Lease + authorization]
  LEASE --> ENC[Envelope/segmented encryption]
  ENC --> REM[Trusted remote/provider storage]
  REM --> SYNC[Progress/conflict/tombstone/recovery]
  SYNC --> L
```

Data movement is policy-governed. The architecture does not permit silent movement merely because remote storage is available. The current provider/storage fabric adds resumability, ranges/multipart, provider health/capabilities and placement/replica metadata without changing that rule.

Canonical data domains remain separate:

- MemoryStore: personal conversational/behavioral memory.
- Knowledge: user/source knowledge and UCI ingestion/retrieval.
- DeviceRegistry: trust/device state.
- Capability/connector state: external capability metadata and credential references.
- Work/Projects/Products: durable domain state.
- Approval/execution controls: governed action state.
- Audit/evidence: security/qualification/action evidence.

Shared SQLite/versioned migrations are the production datastore foundation for migrated local stores. Sensitive data is encrypted where its domain classification requires it.

## Memory and Knowledge

Memory and Knowledge are deliberately separate authorities. Memory captures/retrieves owner interaction context; Knowledge ingests sources/files and provides grounded retrieval/citations. Architecture tests prohibit silently collapsing these domains into one store.

Universal Content Intelligence feeds Knowledge/content graphs using native parsing, OCR/visual extraction, media transcription where dependencies are available, and semantic extraction. Advanced OCR/HTR components must retain their current evidence boundaries; the repository does not justify a general foundation-model claim.

## Work/agent architecture

User intent can become a Work/agent lifecycle with planning, tool selection, approval, durable execution, cancellation, retries, evidence, completion judging and restart recovery. Projects and Work are linked but remain explicit domain concepts. Attention/notification surfaces project important state back to the owner.

Intelligence Lab and self-improvement systems are governed/gated. They do not receive a second action executor: real-world actions still flow through canonical tools/policy/approvals.

## Voice and vision

Voice and Vision are input/output/sensing capabilities integrated with conversation and Sensorium. Provider-specific systems such as OpenVoice/VoiceStudio are isolated provider boundaries. VoiceStudio MCP is projected through Universal Capabilities instead of bypassing ToolRegistry. Real carrier/provider and physical-acoustic qualification remain separate from software/loopback CI.

## Product/build architecture

The Products domain owns product manifests/runtime composition and governed build/qualification paths. Development artifacts can be produced for multiple platforms. Production signing, notarization, store acceptance and other external release credentials remain external gates and are not inferred from successful development builds.

## Product surfaces

### Desktop
Primary navigation verified in `ui/main_window.py`:

Home; Conversation; Memory; Knowledge; Activities; Dashboard; Apps & Tools; Settings.

Additional focused UI modules include first run, capability management, native auth, mobile pairing, memory detail, products and control/settings panels.

### PWA
PWA exposes conversation/context, Work/agents and progressive-disclosure owner controls. Infrastructure subsystems do not automatically receive top-level navigation; Settings/Advanced/More/contextual surfaces are valid exposure locations.

### Android/iOS
Native companions are trusted-device/product surfaces, not replacements for the canonical server/runtime authorities. Emulator/simulator qualification must not be restated as physical-device qualification.

## Authentication / first-device flow

```mermaid
flowchart LR
  W[Welcome] --> C{Create / Existing / Restore}
  C --> O[Owner identity]
  O --> AU[Auth method / passkey/password where supported]
  AU --> RC[Recovery acknowledgement]
  RC --> TD[First trusted device]
  TD --> SP[Storage policy]
  SP --> MP[Model/provider setup]
  MP --> H[Home]
```

Identity creation, trusted-device enrollment, runtime provisioning and data location are separate concepts. A browser/device enrollment must not be described as hosting a full runtime unless code actually provisions one.

## Recovery flow

```mermaid
flowchart LR
  LOSS[Loss/process/device failure] --> RA[Recovery authority]
  RA --> OA[Owner reauthentication]
  OA --> DS[Restore durable state/data]
  DS --> TD[Reconstruct trusted-device access]
  TD --> RV[Revoke lost/compromised device]
  RV --> CONT[Continue permitted work]
```

## Release boundary

Current CI includes general CI plus architecture, assurance, data-plane, capability, intelligence, work, Sensorium, Voice, dependency, package/platform, release and reproducibility evidence. Exact-SHA CI is evidence for that SHA only. It is not production acceptance.

## Intentional limitations / external gates

- No production deployment is performed by this audit.
- External OAuth/provider consent and callbacks must be configured and verified separately.
- Physical-device L4, physical acoustics/camera/background behavior and store distribution require real hardware/platform evidence.
- Production signing/notarization/store credentials are owner/external inputs.
- Live telephony and paid provider behavior require approved real accounts.
- Simulator/emulator/mock/fixture evidence must remain labelled as such.
