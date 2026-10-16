# Current Architecture Audit

Exact baseline: `a8d3310b4d9090a42800621b1b27cb6045443c1e`.

The canonical long-term architecture is `docs/architecture/CURRENT.md`. This audit-facing document records the evidence/reconciliation decisions behind it.

## Current runtime layers

1. **Product surfaces** — PyQt desktop, PWA/web, Android companion, iOS companion, owner/admin/qualification surfaces, installers/packages.
2. **Identity/security** — owner identity, sessions/request context, trusted-device state, recovery/WebAuthn paths, SecretVault/root-key systems, ApprovalManager, audit/evidence and emergency/autonomy controls.
3. **Intelligence** — conversation/context, model routing/reasoning, agents, Work, Memory, Knowledge, file/content intelligence, vision/visual intelligence, voice, proactive/intelligence-lab systems.
4. **Actions/capabilities** — ToolRegistry, internal tools, Apps & Tools, OpenAPI, MCP, integrations/plugins, computer/browser control, Capability Forge.
5. **Devices/sensing** — DeviceRegistry, DeviceGateway, native companions, Sensorium, virtual/emulator/simulator/hosted-VM providers and explicit physical-device boundary.
6. **Data** — versioned SQLite stores, Memory/Knowledge/product/device stores, SecretVault, local-first Data Plane, encrypted leases/transport, conflicts/tombstones/recovery, optional provider storage.
7. **Release** — desktop/native/PWA packaging, product builders, CI, security/qualification evidence and governed release gates.

## Reconciliation findings

- Root `ARCHITECTURE.md` is historical and materially under-describes current Vishnu.
- `ToolRegistry` remains the canonical action executor; Capability Forge, REA, VoiceStudio MCP, automation and agents must project into/delegate to that authority rather than bypass it.
- `ApprovalManager` in `security/approvals.py` is the durable exact-use approval authority.
- Device identity/trust (`DeviceRegistry`) and device transport/dispatch (`DeviceGateway`) are intentionally separate responsibilities.
- Memory and Knowledge are intentionally separate authorities and architecture tests enforce that boundary.
- Universal Capabilities lives in `integrations/discovery/*` + `server/apps_tools_api.py`; top-level `capabilities/` is not that authority.
- Sensorium is observation/sensing/world state, not a second action authority.
- Data Plane/storage fabric follows explicit owner policy and must not silently move/copy/repair owner data.

## Required flows

The canonical diagrams for system context, runtime/tool, capability, device, data, authentication and recovery flows are in `docs/architecture/CURRENT.md`.

## Current evidence boundaries

`COMPLETE` architecture claims are limited to code paths/fixtures/CI actually located on the audited SHA. Physical-device L4, real external provider consent, production signing/notarization/store acceptance, real telephony/acoustics and production deployment remain separately blocked/not verified.
