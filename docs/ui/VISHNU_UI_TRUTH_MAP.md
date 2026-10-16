# Vishnu UI Truth Map

**Repository:** `vaishnavsawant1994-stack/vishnu`  
**Audited baseline:** `main` at `4ec735de327f2bab6dccb774e2a9c28ef4fc44af`  
**Campaign:** complete UI, screen, navigation, accessibility and visual product blueprint  
**Production deployment:** none

## 1. Executive result

This audit derives the owner-visible Vishnu product from the existing Product Truth Map and current Desktop/PWA/Android/iOS source. It does not count files as screens and it does not turn backend folders into navigation.

A **canonical logical screen** is a distinct owner question or durable task, even when a platform implements it as a settings subsection, tabbed workspace, responsive drawer, sheet or native navigation destination.

| Measure | Result |
|---|---:|
| Canonical logical screens required | **63** |
| Canonical screens with some source implementation | **57** |
| COMPLETE under the strict visual/E2E definition | **0** |
| PARTIAL | **52** |
| EXPERIMENTAL | **5** |
| MISSING | **6** |
| Proven ORPHANED canonical screens | **0** |
| Proven DISCONNECTED canonical screens | **0** |
| Proven production PLACEHOLDER canonical screens | **0** |
| Desktop/PWA/Android/iOS platform slots classified | **252** |
| Source-proven platform implementation instances | **113** |
| Secondary dialog/sheet/drawer/prompt families | **34** |
| Major visual-state types | **14** |
| Canonical screens visually verified at this exact SHA | **0** |
| Canonical screens still not visually verified | **63** |

`0 COMPLETE` is intentional claim discipline. Many screens are real, reachable and backend-connected. A whole screen is not promoted to COMPLETE without exact-SHA rendered visual evidence plus behavioral/accessibility acceptance for its declared scope.

The machine authority for these counts is [`ui_truth.json`](ui_truth.json), validated by `scripts/validate_ui_truth.py` and `tests/test_ui_truth_artifacts.py`.

## 2. Counting model

The audit separates four quantities:

1. **Canonical screens** — unique owner concepts such as Device Detail or Work Detail.
2. **Platform implementations** — Desktop, PWA, Android and iOS implementations of those concepts.
3. **Secondary UI** — confirmations, approvals, credential prompts, pairing flows, imports, dialogs, sheets and drawers.
4. **Visual states** — initial, loading, empty, populated, editing, saving, success, error, offline, permission denied, approval required, disabled, revoked/expired and degraded.

Tabs that are alternate views of one owner task do not inflate the canonical count. Desktop Memory's Overview/Tree/Graph/Timeline/Why Retrieved remain one Memory workspace plus its detail concept. A responsive WorkOrder drawer can implement Work Detail without becoming another page.

## 3. Finished owner information architecture

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

Primary navigation should emphasize Home, Conversation, Memory, Knowledge and current work/attention. Projects, Automations, Apps & Tools and Devices are secondary destinations. Security-sensitive controls belong in deliberate owner-control flows. Diagnostics, Sensorium provider evidence, Voice Lab, Forge and product-building remain Advanced.

## 4. Current platform navigation truth

### Desktop

The executable entrypoint launches `CanonicalMainWindow`. Its active top-level navigation has **9 destinations**:

`Home`, `Conversation`, `Memory`, `Knowledge`, `Activities`, `Dashboard`, `Apps & Tools`, `Our Products`, `Settings`.

Several destinations compose deeper surfaces rather than standing alone: Memory opens Second Brain views; Dashboard opens Owner Control Center; Apps & Tools opens automation/integration/plugin/capability management; Settings launches storage/device/security/model controls.

### PWA / web

The PWA is the broadest owner product:

- Workspace: Home, Projects, Today, Inbox
- Personal: Conversations, Memory, Knowledge
- System: Live work, Activity, Tools, Workflows
- Account: Owner controls, Settings, Trusted devices, System status
- Injected advanced/product entries: Agents and Our Products

A P1 navigation ambiguity remains: **Live work** and **Workflows** currently resolve through the same `workflows` module key and need executable interaction verification before either label is removed or rewired.

### Android

Android is currently a companion-oriented native surface, centered on pairing/connection and Universal Capabilities. The internal-testing build intentionally leaves production host/certificate configuration blank. Native capability management is therefore configuration-blocked for production acceptance, not proof of full native parity.

Android does not need native duplicates of every PWA page if general owner work intentionally uses the trusted PWA. Native screens are required where the OS boundary matters: identity/enrollment, secure credentials, recovery, permissions/sensors and intended native capability controls.

### iOS / iPadOS

The Swift companion has create/join/restore onboarding, passkey/session/recovery/runtime provisioning, Universal Capabilities, device status, Sensorium Privacy and Capability Forge V3. Sensorium Privacy is reachable and can grant/revoke temporary local sensor sessions or stop all sensing. Forge V3 is reachable but deliberately experimental/non-production and disabled without a configured non-production host.

## 5. Required screen count by domain

| Domain | Canonical screens |
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

## 6. Six missing canonical screens

### P1

1. **ONB-005 — Data Placement Policy** — first-run does not clearly ask the owner to choose among `device_only`, `progress_only`, `sync_everywhere`, and `on_demand`, even though those policies exist in the product architecture.
2. **ONB-008 — Setup Review & Completion** — first-run lacks a coherent final review of identity, first trusted device, selected data policy, recovery and active AI provider/model before entering Home.
3. **DAT-002 — Connected Storage Provider Detail** — storage/provider capability and health exist behind the product, but there is no complete owner surface proving destination, health, consent, transfer state and safe failure behavior.

### P2/P3

4. **SEN-002 — Sensorium Status & Providers** — Sensorium privacy/permissions exist, but a normal owner lacks one coherent advanced provider/status/evidence view that does not expose ADB/simctl internals.
5. **SYS-003 — Updates & Release** — release/update infrastructure exists without one normal owner surface for current version, update availability, release notes, verification, install/restart state and failure recovery.
6. **SYS-004 — About / Version / Notices** — version, proprietary-license posture and third-party notices need a discoverable owner page.

### Accessibility correction

**SET-005 — Accessibility is PARTIAL, not MISSING.** Desktop `SettingsPanel` already exposes and persists **Reduce motion** and **High contrast**. Reduced motion applies to the active pulse immediately; high-contrast changes are stored and documented as fully applying after restart. What remains is a coherent Accessibility subsection, PWA parity where appropriate, OS-managed native behavior documentation, and full accessibility acceptance testing.

## 7. Important source-present but partial areas

- **Home / Conversation:** real state presentation, conversation controls and a11y hooks exist, but this campaign did not execute exact-SHA end-to-end visual acceptance.
- **Memory:** Desktop Second Brain has Overview, Tree, Graph, Timeline and Why Retrieved views. They are views of one logical workspace, not five pages.
- **Projects:** PWA has a real project list plus project workspace with Overview, Chat, Work Plan, Files & Sources, Approvals, Discussions, Activity, Live Work and visual-status views. WorkOrder inspection is a secondary responsive drawer/full-screen shell.
- **Apps & Tools / Capabilities:** real governed API wiring exists, including credentials, risk, approvals and one-time write approval. Native configuration/external-provider qualification remain incomplete.
- **Devices:** trust/revocation authorities and owner navigation exist, but a complete overview→detail→lost/revoke acceptance journey is not yet visually qualified.
- **Data & Storage:** Desktop/PWA controls exist; first-run placement selection and provider-detail transparency remain incomplete.
- **Security / Recovery:** real controls exist but the owner mental model is split across onboarding, Settings, Owner Controls and Devices.
- **System:** Desktop Owner Control Center is operational but several tabs are raw JSON/text projections, so it is not the finished owner UX.
- **Accessibility:** Desktop owner controls exist and persist; cross-platform product organization and full a11y qualification remain partial.

## 8. Backend without adequate owner UI

See [`BACKEND_WITHOUT_UI.md`](BACKEND_WITHOUT_UI.md). Highest-value gaps are first-run data placement, storage-provider detail/health/movement, consolidated session/sign-in management, self-update/release UI, advanced Sensorium provider status, recovery/lost-device guidance and cross-platform accessibility organization.

Low-level registries, migrations, crypto envelopes, SQLite connection logic, conflict resolution, lease internals, event buses and transport primitives correctly remain internal.

## 9. UI without backend / placeholder truth

See [`UI_WITHOUT_BACKEND.md`](UI_WITHOUT_BACKEND.md).

No production canonical screen was conclusively proven fake. PWA demo datasets are explicitly gated/labeled preview data rather than normal persisted owner data. The Live work/Workflows duplicate module mapping is a navigation semantics defect candidate, not evidence that the backend is fake.

Individual controls remain behaviorally NOT VERIFIED until click/type/submit/save/reload/failure/restart tests prove the complete path.

## 10. Secondary UI and visual-state model

The blueprint inventories **34 transient UI families**: approvals, fresh-owner reauthentication, destructive confirmation, credentials, provider connection/testing, OpenAPI/MCP setup, one-time write approval, pairing, pending-device approval, lost-device/revoke confirmation, recovery-code handling, restore/backup/data-movement confirmation, sync conflict resolution, knowledge/memory actions, project/work/automation dialogs, conversation/history/attachment shells, sensor permission prompts, Voice Studio/Lab consent, passkey removal and emergency stop.

The shared visual state vocabulary has **14 major state types**:

`initial`, `loading`, `empty`, `populated`, `editing`, `saving`, `success`, `error`, `offline`, `permission denied`, `approval required`, `disabled`, `revoked/expired`, `degraded`.

Local-first UX must distinguish **offline but locally usable** from **unavailable**.

## 11. Accessibility truth

Source/tests already prove important primitives such as accessible labels for core chat controls, approval-dialog semantics/focus return, live/error announcements, reduced-motion styling, responsive rules and Desktop Reduce Motion/High Contrast persistence.

Still not qualified as whole-product accessibility:

- complete keyboard tab order for every Desktop/PWA screen;
- screen-reader journeys across major workflows;
- physical-device VoiceOver/TalkBack acceptance;
- Dynamic Type/text scaling across native UI;
- physical touch-target acceptance;
- complete contrast certification;
- keyboard reachability of every custom control.

See [`ACCESSIBILITY_RESPONSIVE_DESIGN_AUDIT.md`](ACCESSIBILITY_RESPONSIVE_DESIGN_AUDIT.md).

## 12. Responsive and visual evidence truth

PWA source contains narrow-phone/tablet breakpoints, safe-area handling, mobile composer/home chrome, drawer adaptations, focus-visible styling and reduced-motion handling. Projects and WorkOrder detail include explicit mobile layouts. Desktop uses shared semantic presentation tokens and screen-fitting helpers.

That is source evidence, not screenshot acceptance. This campaign obtained **0 accepted exact-SHA runtime screenshots**, so visual verification remains open for all 63 canonical screens. Required viewport acceptance is narrow phone, standard phone, large phone, tablet portrait, tablet landscape, laptop, desktop and wide desktop.

See [`VISUAL_PAGE_CATALOG.md`](VISUAL_PAGE_CATALOG.md).

## 13. Design-system direction

Vishnu already has a consistent dark semantic direction. The finished cross-platform system should preserve:

- semantic background/surface/text/accent/danger/status tokens;
- consistent type hierarchy and 4px-based spacing;
- 44px minimum interactive targets;
- consistent focus treatment;
- consistent active/offline/degraded/blocked/revoked badges;
- one approval vocabulary and one destructive-action vocabulary;
- progressive disclosure of technical identifiers;
- native platform conventions without changing Vishnu's owner mental model.

## 14. Internal systems correctly requiring no dedicated screen

Infrastructure that should remain internal includes migration engines, key/encryption-envelope internals, registry mechanics, durable-approval internals, event buses, conflict-resolution internals, lease/token transport, encrypted segment framing, retry/backoff mechanics, audit-chain internals and low-level emulator/simulator adapter mechanics. Their owner-relevant status may be projected into Diagnostics/Security, but the implementation machinery itself should not become normal navigation.

## 15. Exact implementation priorities

### P0/P1

1. Implement **ONB-005 Data Placement Policy** using the existing canonical data-policy authority; do not invent a parallel preference store.
2. Implement **ONB-008 Setup Review & Completion** as the final first-run summary/commit step.
3. Implement **DAT-002 Connected Storage Provider Detail** only against the canonical provider/storage-fabric authority, including health, consent and movement evidence.
4. Resolve the PWA **Live work / Workflows** duplicate-module navigation ambiguity after executable interaction verification.
5. Consolidate **SET-005 Accessibility** into a discoverable settings subsection while retaining the existing working Desktop preferences rather than rebuilding them.

### P2/P3

6. Add Sensorium provider/status evidence UI without exposing raw ADB/simctl execution.
7. Add Updates & Release.
8. Add About / Version / Notices.
9. Continue native parity only where the native OS boundary requires it.
10. Run exact-SHA visual, responsive, keyboard, screen-reader and behavioral acceptance before promoting any screen to COMPLETE.

## 16. Companion documents

- [`CURRENT_REQUIRED_SCREEN_MATRIX.md`](CURRENT_REQUIRED_SCREEN_MATRIX.md) — required/existing/platform matrix.
- [`PAGE_SPECIFICATIONS.md`](PAGE_SPECIFICATIONS.md) — page-by-page purpose, contents, actions, backend, navigation, states and acceptance criteria.
- [`MISSING_SCREEN_REPORT.md`](MISSING_SCREEN_REPORT.md) — missing-screen implementation report.
- [`ORPHANED_AND_DISCONNECTED_SCREEN_REPORT.md`](ORPHANED_AND_DISCONNECTED_SCREEN_REPORT.md) — reachability/connectivity reconciliation.
- [`BACKEND_WITHOUT_UI.md`](BACKEND_WITHOUT_UI.md) — owner-manageable backend gaps.
- [`UI_WITHOUT_BACKEND.md`](UI_WITHOUT_BACKEND.md) — placeholder/no-op risk review.
- [`NAVIGATION_BLUEPRINT.md`](NAVIGATION_BLUEPRINT.md) — final IA and click paths.
- [`USER_JOURNEYS.md`](USER_JOURNEYS.md) — new-owner, join-device, lost-device, conversation, tool action, service connection and data-control journeys.
- [`SECONDARY_UI_INVENTORY.md`](SECONDARY_UI_INVENTORY.md) — dialog/sheet/drawer/prompt inventory.
- [`ACCESSIBILITY_RESPONSIVE_DESIGN_AUDIT.md`](ACCESSIBILITY_RESPONSIVE_DESIGN_AUDIT.md) — accessibility and viewport truth.
- [`VISUAL_PAGE_CATALOG.md`](VISUAL_PAGE_CATALOG.md) — source-derived visual catalog and missing runtime evidence.
- [`ui_truth.json`](ui_truth.json) — machine-readable authority.

## 17. Owner-facing conclusion

Vishnu should have **63 canonical logical screens/surfaces** under the evidence-derived counting rule.

Vishnu currently has **57 canonical concepts with meaningful source implementation**. **52 are PARTIAL**, **5 are deliberately EXPERIMENTAL**, and **6 are genuinely MISSING**. No canonical screen is claimed COMPLETE yet because exact-SHA visual/E2E/a11y acceptance has not been executed. No canonical screen was conclusively proven orphaned, disconnected or production-placeholder during this source audit.

The product direction is not to create dozens of extra administrative pages. It is to preserve one simple mental model:

```text
Talk with Vishnu
→ see what Vishnu remembers and knows
→ see what Vishnu is doing
→ control what Vishnu can access
→ control where Vishnu can operate
→ understand where your data lives
→ approve, stop, revoke or recover anything important
```

The next implementation work is therefore bounded: close the six real missing concepts by priority, consolidate partial owner controls instead of duplicating them, then run exact-SHA executable visual/functional qualification before making completion claims.
