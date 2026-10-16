# Vishnu current architecture and execution flows

**Audited SHA:** `a8d3310b4d9090a42800621b1b27cb6045443c1e` on `main`.

## System context

```mermaid
flowchart TB
  Owner[Owner] --> Surfaces[Desktop / PWA / Android / iOS]
  Surfaces --> Runtime[Vishnu runtime compositions]
  Runtime --> Governed[Identity / approvals / tools / capabilities]
  Runtime --> Data[SQLite / local-first data plane]
  Governed --> Devices[Trusted devices / Sensorium providers]
  Governed --> External[Models / MCP / OpenAPI / integrations]
  Data --> Storage[Local files / configured remote providers]
```

The system is single-owner by design in current documentation. The repo is public, but neither its current SQLite schema nor owner-scoped APIs are evidence of general tenant isolation. There are multiple server composition roots: desktop/local API, hosted runtime, cloud/PWA. Their routers and lifecycle wiring differ and must be compared when qualifying a feature.

## Runtime request path

```mermaid
flowchart LR
  Input[Owner input] --> Context[Conversation context]
  Context --> Router[Model / agent routing]
  Router --> Retrieve[Memory and Knowledge retrieval]
  Retrieve --> Decision[Tool or capability decision]
  Decision --> Gate[Permission / approval]
  Gate --> Execute[Governed execution]
  Execute --> Audit[Audit and evidence]
  Audit --> Reply[Response to surface]
```

Conversation, model routing, context retrieval and action exposure are spread across runtime compositions and client code; this diagram is the intended source-level relationship, not proof that every feature invokes every step. OpenAPI/MCP execution is governed by capability policy, ToolRegistry, approval and audit systems where the governed execution path is selected. Do not infer that all agent/tool operations share identical coverage from this diagram.

## Capability execution

```mermaid
flowchart LR
  UI[Owner capability UI] --> API[Capability owner API]
  API --> Service[Capability catalog/service]
  Service --> Approval[ApprovalManager / policy]
  Approval --> Secret[SecretVault credentials]
  Secret --> Registry[ToolRegistry]
  Registry --> Target[OpenAPI / MCP / integration]
  Target --> Audit[Audit result to owner]
```

The exact implementation varies by capability kind. Capability discovery and stored descriptors do not themselves grant execution. MCP user-added endpoints and internally configured loopback endpoints have separate transport rules. VoiceStudio's internal loopback exception is narrowly scoped and startup discovery remains inert (PR #242). Credential consent and third-party provider acceptance are external qualification items.

## Device path

```mermaid
flowchart LR
  Surface[Owner surface] --> Registry[DeviceRegistry]
  Registry --> Gateway[DeviceGateway]
  Gateway --> Trust[Trusted device / provider]
  Trust --> Action[Allowed action or sensor]
  Action --> Result[Response and evidence]
```

Device identity is distinct from owner identity. Native Android/iOS sources exist for pairing, passkeys, recovery, data-plane stores and Sensorium features, but coverage is uneven. Android Emulator, iOS Simulator and hosted VM evidence are not physical-device acceptance. Sensorium physical actions and L4 qualification are explicitly gated.

## Data path

```mermaid
flowchart LR
  State[Owner/runtime state] --> Policy[Data placement policy]
  Policy --> Local[Local SQLite / files]
  Policy --> Transfer[Explicit provider transfer]
  Transfer --> Envelope[Authenticated encrypted segments]
  Envelope --> Remote[Configured provider replica]
  Remote --> Reconcile[Read-only health reconciliation]
  Reconcile --> State
```

The local-first policy labels are `device_only`, `progress_only`, `sync_everywhere`, and `on_demand`. PR #245 adds a resumable provider transfer/storage fabric foundation, capability/health tracking, S3-compatible multipart/range paths, encryption reuse, placement planning and non-destructive reconciliation. The implementation does not silently move owner data or automatically repair cloud replicas. Live provider configuration, owner consent, and real transfer acceptance remain unverified.

## Authentication and enrollment

```mermaid
flowchart TD
  Start[Create / join / restore] --> Auth[Passkey / password / recovery]
  Auth --> OwnerId[Owner identity]
  OwnerId --> Session[Owner session]
  Session --> Device[Register device identity]
  Device --> Scope[Apply scopes and trust]
  Scope --> Ready[Product surface]
```

Owner identity is not the first device ID. The repository has server and native client code for creation, login, passkey, recovery, provisioning, and enrollment. A complete cross-platform flow depends on runtime provisioning and external hosting, and was not executed in a fresh device environment for this audit.

## Voice path

```mermaid
flowchart LR
  Audio[Microphone or browser input] --> Capture[Permissioned capture]
  Capture --> Speech[Configured STT / voice turn]
  Speech --> Runtime[Conversation and governed runtime]
  Runtime --> Synthesis[Optional configured TTS]
  Synthesis --> Output[Device audio output]
```

The current source separates Voice Intelligence policy from optional provider runtime and Voice Lab. The existing `VoicePlan` is adapted to model-agnostic synthesis; a provider runtime is disabled by default unless explicitly enabled and composed. Voice Lab and governed telephony are isolated, default-off research/qualification features. Real STT/TTS provider and physical-acoustics behavior are `NOT VERIFIED` here.

## Recovery path

```mermaid
flowchart TD
  Loss[Device or runtime loss] --> Reauth[Owner re-authentication]
  Reauth --> Recovery[Supported recovery package / backup]
  Recovery --> Verify[Validate integrity and restore state]
  Verify --> Reenroll[Re-enroll trusted device]
  Reenroll --> Revoke[Revoke lost device credentials]
```

Crash, database, vault rotation, portable backup/restore, continuity and durable-work recovery have dedicated code and tests. Those tests establish fixture behavior, not the existence of an up-to-date owner production backup or a successful production restore. Production recovery is therefore `BLOCKED / NOT VERIFIED` until an isolated restore is accepted from the actual intended data root.

## Runtime, data and release boundaries

- `Memory` and `Knowledge` remain distinct domains.
- `ToolRegistry`, `ApprovalManager`, `DeviceRegistry`, `DeviceGateway`, `SecretVault`/`RootKeyStore`, and audit are canonical authorities; integrations should adapt to them.
- `future_intelligence`, `intelligence_lab`, evolution/training and qualification surfaces are gated or experimental; their presence is not general autonomous authority.
- `render.yaml` currently describes a headless Render runtime and persistent disk with auto-deploy off. Older readiness records refer to a Railway deployment observed on 2026-10-15. Current live hosting, runtime SHA, health, volume contents, and backup state were not checked.
- No production deployment, migration, secret rotation, provider connection or live data operation was performed.
