# Vishnu UI Truth Map

**Repository:** `vaishnavsawant1994-stack/vishnu`  
**Audited baseline:** `main` at `4ec735de327f2bab6dccb774e2a9c28ef4fc44af`  
**Campaign:** UI, screen, navigation, accessibility and visual product blueprint  
**Production operations:** none

## Executive result

This audit derives the visible Vishnu product from the existing Product Truth Map and current UI source. It does not count files as screens and does not mirror backend folders into navigation.

A **canonical logical screen** is a distinct owner question or durable task, even when one platform implements it as a settings subsection, tabbed workspace, responsive drawer, sheet or native navigation destination.

| Measure | Result |
|---|---:|
| Canonical logical screens required | **63** |
| Canonical screens with some source implementation | **56** |
| COMPLETE under the strict visual/E2E definition | **0** |
| PARTIAL | **51** |
| EXPERIMENTAL | **5** |
| MISSING | **7** |
| Proven ORPHANED canonical screens | **0** |
| Proven DISCONNECTED canonical screens | **0** |
| Proven production PLACEHOLDER canonical screens | **0** |
| Desktop/PWA/Android/iOS platform slots classified | **252** |
| Source-proven platform implementation instances | **112** |
| Secondary dialog/sheet/drawer/prompt families | **34** |
| Major visual-state types | **14** |
| Canonical screens visually verified at this exact SHA | **0** |
| Canonical screens still not visually verified | **63** |

`0 COMPLETE` is intentional claim discipline. Many screens are real, reachable and backend-connected. The campaign cannot promote a whole screen to COMPLETE without exact-SHA rendered visual evidence plus behavioral/accessibility acceptance for the declared scope.

The machine authority for these counts is [`ui_truth.json`](ui_truth.json), validated by `scripts/validate_ui_truth.py` and `tests/test_ui_truth_artifacts.py`.

## Counting model

The audit reports four separate things:

1. **Canonical screens** — unique owner concepts such as Device Detail or Work Detail.
2. **Platform implementations** — Desktop, PWA, Android and iOS implementations of those concepts. iPhone/iPad share the Swift implementation family but have separate responsive acceptance expectations.
3. **Secondary UI** — confirmations, approvals, credential prompts, pairing flows, imports, dialogs, sheets and drawers.
4. **Visual states** — initial, loading, empty, populated, editing, saving, success, error, offline, permission denied, approval required, disabled, revoked/expired and degraded.

Tabs that are alternate views of one owner task do not inflate the canonical screen count. For example, Desktop Memory's Overview/Tree/Graph/Timeline/Why Retrieved remain one Memory workspace plus detail concept. A responsive WorkOrder drawer can implement the canonical Work Detail concept without becoming another page.

## Finished information architecture

```text
VISHNU
├── First Run
│   ├── Welcome / Create / Join / Restore
│   ├── Owner Identity
│   ├── Security
│   ├── Privacy & Autonomy
│   ├── Data Placement
│   ├── AI Provider
│   ├── Recovery Codes
│   └── Review & Finish
├── Home
│   ├── Conversation
│   └── Conversation History
├── Personal
│   ├── Memory
│   └── Knowledge
├── Work
│   ├── Today
│   ├── Inbox / Attention
│   ├── Activity
│   ├── Live Work
│   ├── Automations
│   └── Projects
├── Apps & Tools
│   ├── Connected Services
│   └── Capabilities
├── Devices
├── Settings
│   ├── General & Profile
│   ├── Appearance
│   ├── Language & Region
│   ├── Accessibility
│   ├── AI Models & Providers
│   ├── Voice
│   ├── Data & Storage
│   ├── Notifications
│   ├── Privacy
│   ├── Security
│   └── Recovery
├── Status
│   ├── Dashboard
│   └── System Status / Diagnostics
└── Advanced
    ├── Sensorium
    ├── Computer & Browser Control
    ├── Security / Audit History
    ├── Voice Studio / Voice Lab
    ├── Agent Workforce
    ├── Capability Forge V3
    └── Our Products
```

Home remains conversational and attention-focused; administrative and technical systems stay in secondary navigation, Settings or Advanced.

## Current platform truth

### Desktop

The executable application launches `CanonicalMainWindow`. Its active primary navigation contains **9 destinations**: Home, Conversation, Memory, Knowledge, Activities, Dashboard, Apps & Tools, Our Products and Settings. Several are composition entry points: Memory opens the Second Brain workspace; Dashboard opens Owner Control Center; Apps & Tools opens automation/integration/plugin/capability management; Settings launches deeper data-storage and pairing controls.

### PWA / web

The PWA is the broadest owner surface:

- Workspace: Home, Projects, Today, Inbox
- Personal: Conversations, Memory, Knowledge
- System: Live work, Activity, Tools, Workflows
- Account: Owner controls, Settings, Trusted devices, System status
- Injected advanced/product entries: Agents and Our Products

One P1 ambiguity remains: `Live work` and `Workflows` currently use the same `workflows` module key. Browser interaction must determine whether this is an intentional alias or a navigation defect before code is changed.

### Android

Android is currently a companion-oriented native surface rather than full owner-product parity. Source-proven native UI centers on connection/pairing and Universal Capabilities. The internal-testing build intentionally leaves production server/certificate configuration blank. Broad Home/conversation/work can remain the trusted PWA; native screens are required where the OS boundary matters, such as first-device identity/trust, recovery, secure credentials, local permissions/sensors and intended native capability controls.

### iOS / iPadOS

The Swift companion has create/join/restore onboarding, passkey/session/recovery/runtime provisioning, Universal Capabilities, connection/device status, Sensorium Privacy and Capability Forge V3. Sensorium Privacy can grant/revoke temporary local sensor sessions and stop all sensing. Forge V3 is deliberately experimental/non-production and remains disabled without a configured non-production host.

## Required screen count by domain

| Domain | Count |
|---|---:|
| Onboarding & Auth | 11 |
| Home & Conversation | 3 |
| Memory | 2 |
| Knowledge & Files | 2 |
| Activities & Work | 6 |
| Automation | 2 |
| Projects | 2 |
| Products | 2 |
| Apps & Tools | 2 |
| Capabilities | 3 |
| Devices | 2 |
| Data & Storage | 2 |
| Models & Providers | 2 |
| Voice | 3 |
| Sensorium & Control | 3 |
| Security & Privacy | 5 |
| Recovery | 1 |
| Notifications | 1 |
| System & Status | 4 |
| Settings | 5 |
| **Total** | **63** |

The no-blank master table is in [`CURRENT_REQUIRED_SCREEN_MATRIX.md`](CURRENT_REQUIRED_SCREEN_MATRIX.md). Detailed contents/actions/backends/states/acceptance criteria for every screen are in [`PAGE_SPECIFICATIONS.md`](PAGE_SPECIFICATIONS.md).

## Seven missing canonical screens

### P1

1. **ONB-005 — Data Placement Policy** — first-run must explicitly choose among `device_only`, `progress_only`, `sync_everywhere`, `on_demand`.
2. **ONB-008 — Setup Review & Completion** — final owner review of identity, trusted device, recovery readiness, data policy and model/provider before Home.
3. **DAT-002 — Connected Storage Provider Detail** — provider destination/capability/health/encryption/transfer/retry/disconnect owner surface.
4. **SET-005 — Accessibility** — coherent owner surface for supported reduce-motion/high-contrast and platform-following behavior.

### P2/P3

5. **SEN-002 — Sensorium Status & Providers** — advanced provider availability/evidence status without exposing low-level ADB/simctl execution.
6. **SYS-003 — Updates & Release** — installed version/update/release-notes/verification/restart/failure-recovery surface.
7. **SYS-004 — About / Version / Notices** — build identity, proprietary-license notice and third-party notices.

See [`MISSING_SCREEN_REPORT.md`](MISSING_SCREEN_REPORT.md) for implementation recommendations.

## Important partial/experimental truth

- **Home / Conversation:** strong source structure, runtime-state projection and accessibility hooks; exact-SHA visual journey not accepted here.
- **Memory:** real Desktop Second Brain and PWA Memory, but platform and mutation/privacy lifecycle remain uneven.
- **Knowledge:** real ingestion/search/source UI, with desktop detail parity incomplete.
- **Projects:** real PWA overview and rich project workspace; WorkOrder detail is an authoritative responsive detail shell.
- **Apps & Tools / Capabilities:** real governed APIs, credentials, approvals, history and revocation; native/external-provider qualification remains partial.
- **Devices:** navigation and trust/revocation authorities exist; complete enroll/detail/revoke/lost-device journey still needs accepted executable evidence.
- **Data & Storage:** real desktop/PWA controls exist, while first-run placement and storage-provider transparency are incomplete.
- **Security / Recovery:** real controls exist but are fragmented across onboarding, Settings, Owner Controls and Devices.
- **System:** Desktop Owner Control Center is connected but several tabs are JSON/text runtime projections, so it is a diagnostic partial rather than the finished owner UX.
- **Experimental:** Agent Workforce, Our Products overview/detail, Capability Forge V3 and Voice Lab remain isolated advanced/lab/product-building experiences.

## Backend without adequate UI

The most important owner-manageable backend gaps are first-run data placement, setup review, storage-provider detail, Accessibility, advanced Sensorium provider status, Updates/About, consolidated sessions/security and recovery/lost-device guidance. The detailed mapping is in [`BACKEND_WITHOUT_UI.md`](BACKEND_WITHOUT_UI.md).

Low-level registries, migrations, crypto envelopes, SQLite mechanics, conflict resolution, lease internals, event buses, encrypted-segment framing and audit-chain implementation correctly remain internal.

## UI without backend / orphan truth

No required canonical screen was conclusively proven presentation-only or orphaned. PWA preview/demo datasets are explicitly gated and labeled sample-only; they are not counted as production placeholders. The Desktop Owner Control Center's JSON projections are connected diagnostics, not fake UI.

This does **not** prove repository-wide zero no-op callbacks. A future framework-aware trace must map `visible control → handler → API/runtime → authorization/approval → persistence/effect → returned result → UI success/error` before making that stronger claim. See [`UI_WITHOUT_BACKEND.md`](UI_WITHOUT_BACKEND.md) and [`ORPHANED_AND_DISCONNECTED_SCREEN_REPORT.md`](ORPHANED_AND_DISCONNECTED_SCREEN_REPORT.md).

## Accessibility and responsive truth

Existing source/tests prove useful primitives such as accessible labels for chat controls, approval-dialog focus semantics, live/error announcements, reduced-motion rules, responsive breakpoints, safe-area behavior and desktop 44px control/touch targets. They do not establish full screen-reader/keyboard/touch/contrast acceptance across the product.

Required executable follow-up includes complete tab order, VoiceOver/TalkBack journeys, native text scaling, physical touch behavior, contrast checks and representative phone/tablet/laptop/desktop layouts. See [`ACCESSIBILITY_RESPONSIVE_DESIGN_AUDIT.md`](ACCESSIBILITY_RESPONSIVE_DESIGN_AUDIT.md).

## Visual evidence

This connected-GitHub environment cannot launch the repository runtime, browser, Android Emulator or iOS Simulator, and no exact-SHA screenshot artifact was found during this source pass. Consequently all 63 canonical records have `visual_verified=false`; no design mock or `uiDemo=1` preview is promoted to runtime evidence.

[`VISUAL_PAGE_CATALOG.md`](VISUAL_PAGE_CATALOG.md) defines the screenshot acceptance plan and the evidence slot for every screen.

## Secondary UI and states

The blueprint inventories **34** transient UI families, including action approvals, reauthentication, destructive confirmations, credential prompts, OpenAPI/MCP flows, device pairing/revocation, recovery/backup, data movement/conflict, project/work/automation dialogs, sensor permissions, voice authorization and emergency stop.

The shared visual-state vocabulary contains **14** types: initial, loading, empty, populated, editing, saving, success, error, offline, permission denied, approval required, disabled, revoked/expired and degraded. See [`SECONDARY_UI_INVENTORY.md`](SECONDARY_UI_INVENTORY.md).

## Owner journey and navigation authority

The finished UX must let the owner answer:

- What is Vishnu doing? → Home / Live Work / Activity
- What does Vishnu remember? → Memory
- What does Vishnu know? → Knowledge
- What needs me? → Inbox / Approvals
- What can Vishnu access? → Apps & Tools / Capabilities
- Which devices belong to me? → Devices
- Where does my data live? → Data & Storage
- Which AI model/provider is active? → AI Models & Providers
- What can sense my environment? → Sensorium Privacy
- How do I stop/revoke something? → relevant detail + canonical confirmation
- How do I recover? → Recovery
- Is the system healthy? → Dashboard / System Status

Exact click paths and platform navigation are in [`NAVIGATION_BLUEPRINT.md`](NAVIGATION_BLUEPRINT.md); end-to-end owner journeys are in [`USER_JOURNEYS.md`](USER_JOURNEYS.md).

## Implementation priority

**P0:** no speculative redesign is justified by source audit alone. Any behavioral qualification that finds auth/recovery/data-loss/unauthorized-action failure becomes P0 immediately.

**P1:** implement ONB-005, ONB-008, DAT-002 and SET-005; resolve the Live Work/Workflows semantic ambiguity after executable confirmation; unify fragmented Security/Recovery without creating duplicate authorities; capture exact-SHA visual/interaction evidence for Home, Conversation, Memory, Knowledge, Apps & Tools, Devices and Data & Storage.

**P2:** Sensorium provider status, Work/Automation/Project parity refinements, owner-session management polish, offline/degraded/failure-state coverage.

**P3:** Updates/About, visual consistency refinements, broader screenshot catalog and low-frequency convenience UI.

## Final confidence statement

Vishnu's owner-facing product is now specified as a **63-screen canonical model**, separate from platform implementations, transient UI and visual states. Current source proves meaningful implementation for **56** concepts and **112** platform implementation instances, but no full canonical screen is promoted to COMPLETE without exact-SHA rendered behavior/visual acceptance. Seven required concepts are missing. No required canonical screen was proven orphaned or disconnected; unexecuted controls remain explicitly NOT VERIFIED rather than assumed correct.