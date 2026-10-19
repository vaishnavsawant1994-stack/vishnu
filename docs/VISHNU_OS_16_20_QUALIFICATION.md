# Vishnu OS Screens 16–20 — actual implementation and remaining qualification

**Status: draft foundation. Not complete. Not merged. Not deployed.**

This PR adds a real vertical slice for the supplied visual references. Reference images are targets, NOT screenshots of running software. A passing package build never proves visual parity.

## Architecture

- Web UI hooks into the canonical /iphone PWA shell, reusing the authenticated Vishnu conversation bridge.
- New owner-scoped, versioned SQLite Workspace registry stores organization metadata, validated Project links, and saved Studio layout references.
- Project authority remains the existing ProjectStore / ProjectWorkforceStoreAdapter. No duplicate Project, Agent, Work, approval, device, memory, knowledge or capability runtime is created.
- Read-only work and attention data come from the existing canonical projections.
- Command Center only navigates or initiates existing user interfaces. It does NOT parse and execute privileged arbitrary commands.
- Existing Genesis and earlier Vishnu screens remain the core application; one short-landscape Home layout fix is included.

## Feature truth table

| Screen | Implemented first slice | Missing / not qualified |
|---|---|---|
| 16 Command Center | Keyboard entry, responsive modal/sheet, command filtering, Workspace search, safe navigation | NLP intent and governed command execution, persisted recents, voice |
| 17 Workspaces Library | Owner-scoped listing, cards, query, pinned/status filters, select/inspect, pin/archive | Full resource graph, file/agent counts, images/covers, advanced search |
| 18 Workspace Creation | Nine templates, name/description, validated persistent create, idempotent request retry, contextual AI prompt | AI generated setup review/accept flow, auto module configuration, cover upload |
| 19 Workspace Overview | Linked real Projects; read-only canonical Work and Attention; context and navigation | Complete canonical Files, Agents, Knowledge and Activity per Workspace |
| 20 2D Studio | Panel reference layout, add/close/reorder/focus, saved view persistence, responsive layout | Real document/code/diagram editors, dock/drag/split, 3D preview and collaboration |

## Platform truth

- Web/PWA: actual code wired through the first-served /iphone shell; test with authenticated owner and real API.
- Windows/macOS/Linux desktop: existing product is PyQt6; canonical reference UI is NOT yet embedded. Native installation and screenshot qualification missing.
- Android: existing companion uses Chrome Custom Tabs. Full in-app Vishnu OS shell is NOT implemented.
- iOS: existing companion uses SwiftUI and Safari. Full in-app Vishnu OS shell is NOT implemented.
- Tablet/iPad: responsive design exists; device-specific screenshot qualification pending.

Do not drop authenticated pages into unrestricted WKWebView/Android WebView merely to say the design appears inside the native app. First define safe session/OAuth/passkey bridging, trusted origins, permission boundaries, cookie handling and lifecycle recovery. Preserve native Sensorium and DeviceGateway capabilities.

## Security gaps and merge gates

1. User authentication, trusted device and ai:chat scope are checked for Workspace API. Only existing canonical Project links may be added. Other link categories are intentionally blocked until authorization exists.
2. Workspace name/description currently live in a separate SQLite file. Complete classification, encryption-at-rest and backup/restore review before storing regulated or sensitive information.
3. Layouts reference bounded resource IDs; they are NOT independent resource read permissions. Every future panel must reauthorize actual content on open.
4. Implement data-plane placement policy before allowing Workspace metadata sync across devices. Local-runtime storage is not cross-device synchronization.
5. All visible placeholder/unsupported functions must indicate their unavailability rather than fake outputs.
6. Never merge until exact-head CI, security, responsive/browser, standalone API, and platform qualification all pass.
7. Compare screenshots of the real running UI to all approved desktop/mobile references. The current branch has NOT been fully visually compared.
8. Validate backup, restore, concurrent create, migration, keyboard/screen reader, offline/error states, session revocation and native installed paths.
9. Do not deploy or merge without owner approval.

## Acceptance evidence expected

Actual build screenshots at agreed viewport sizes, UI comparison ledger, working navigation/API contract screenshots, backend tests, owner auth and safety tests, browser E2E, Android emulator, iOS Simulator, Windows/macOS/Linux packaging and installed UI verification.

This is a FOUNDATION PR. Its open work should be continued in bounded follow-up PRs, not misreported as finished.
