# Vishnu UI Truth Map

**Repository:** `vaishnavsawant1994-stack/vishnu`  
**Audited baseline:** `main` at `4ec735de327f2bab6dccb774e2a9c28ef4fc44af`  
**Campaign:** UI, screen, navigation, accessibility and visual product blueprint  
**Production operations:** none

## 1. Executive result

This audit derives the visible product from the existing Product Truth Map and current UI source. It does not count files as screens and does not turn backend folders into navigation.

The finished Vishnu owner product requires **63 canonical logical screens/surfaces** under the counting rule below. A canonical screen is a distinct owner question or durable task (for example `Device Detail` or `Work Detail`) even when a platform implements that concept as a responsive drawer, sheet, settings subsection, tabbed workspace or full page.

Current canonical status at the audited SHA:

| Status | Count | Meaning |
|---|---:|---|
| COMPLETE | 0 | No canonical screen is promoted to COMPLETE because this campaign could not obtain exact-SHA rendered screenshot evidence plus full behavioral/a11y qualification for that screen. |
| PARTIAL | 51 | A meaningful implementation exists on at least one intended surface, but visual, platform, behavioral, failure-state, persistence or accessibility proof is incomplete. |
| EXPERIMENTAL | 5 | Deliberately advanced/lab/product-building UI: Agent Workforce, Our Products overview/detail, Capability Forge V3 and Voice Lab. |
| MISSING | 7 | Required owner UI is not represented sufficiently by the current visible product. |
| ORPHANED | 0 proven | No required canonical screen was proven unreachable after tracing the active desktop composition, PWA injection/navigation and native links. |
| DISCONNECTED | 0 proven | No required canonical screen was conclusively proven presentation-only. Individual controls remain NOT VERIFIED until interaction tests prove mutation/persistence. |
| PLACEHOLDER | 0 proven | PWA demo records are explicitly gated by preview/demo mode and labeled as sample-only; they are not counted as production placeholders. |

Therefore:

- **Canonical logical screens required:** 63
- **Canonical logical screens with some implementation:** 56
- **Fully complete under this campaign's strict definition:** 0
- **Partial:** 51
- **Experimental:** 5
- **Missing:** 7
- **Proven orphaned:** 0
- **Proven disconnected:** 0
- **Platform implementation slots classified:** 252 (63 × Desktop/PWA/Android/iOS implementation families)
- **Source-proven implementation instances:** 96
- **Secondary transient UI families inventoried:** 34
- **Major visual-state types:** 14
- **Visually verified at this exact SHA by runtime screenshot evidence:** 0
- **Still not visually verified:** 63 canonical screens

`0 COMPLETE` is intentional claim discipline, not a statement that the UI is unusable. Many screens have real navigation, real APIs and tests. The missing ingredient for COMPLETE is exact-SHA executable visual/behavior proof across the declared scope.

## 2. Counting rule

The audit separates four quantities:

1. **Canonical logical screens** — unique owner concepts. One `Device Detail` concept counts once.
2. **Platform implementations** — Desktop, PWA, Android and iOS implementations of a canonical concept. iPhone and iPad coverage is classified separately in acceptance notes but shares the Swift implementation family.
3. **Secondary UI** — approvals, confirmations, credential prompts, pairing flows, import dialogs, create/edit dialogs, drawers/sheets and other transient interaction shells.
4. **Visual states** — initial, loading, empty, populated, editing, saving, success, error, offline, permission-denied, approval-required, disabled, revoked and expired/degraded. States do not inflate page count.

## 3. Current product information architecture

The finished IA should preserve Vishnu's existing progressive-disclosure pattern instead of mirroring backend modules.

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

### Navigation principle

- **Primary:** Home, Conversation, Memory, Knowledge, Today/Activity.
- **Secondary:** Projects, Live Work, Automations, Apps & Tools, Devices.
- **Settings:** models/providers, voice, data/storage, notifications, privacy, security, recovery, appearance/language/accessibility.
- **Security-sensitive:** passkeys/sessions, recovery, credentials, device revocation, destructive data movement, capability approvals and audit.
- **Advanced:** Sensorium provider/evidence details, diagnostics, Voice Lab, Agent Workforce, Capability Forge and product-building/release surfaces.

Home must remain conversational and attention-focused; administrative systems should not be promoted to Home merely because their backend exists.

## 4. Current platform navigation truth

### Desktop

The executable entrypoint launches `CanonicalMainWindow`. Its active primary navigation contains **9 destinations**:

`Home`, `Conversation`, `Memory`, `Knowledge`, `Activities`, `Dashboard`, `Apps & Tools`, `Our Products`, `Settings`.

Several are compositional entry points rather than independent full implementations. Memory opens the Second Brain panel; Dashboard opens Owner Control Center; Apps & Tools opens automation/integration/plugin/capability management; Settings contains configuration tabs and launches Data & Cloud Storage / mobile pairing.

### PWA / web

The PWA is the broadest owner product. Its live navigation is grouped rather than matching desktop one-for-one:

- Workspace: Home, Projects, Today, Inbox
- Personal: Conversations, Memory, Knowledge
- System: Live work, Activity, Tools, Workflows
- Account: Owner controls, Settings, Trusted devices, System status
- Injected advanced/product entries: Agents and Our Products

This composition is directionally correct. It reflects owner intent, not backend folder names.

**Navigation ambiguity:** `Live work` and `Workflows` currently use the same `workflows` module key in the root PWA navigation. That is a P1 information-architecture ambiguity and must be interaction-tested before either label is removed or rewired.

### Android

Android is currently a **companion-oriented native surface**, not full owner-product parity. Source-proven native UI centers on connection/pairing and Universal Capabilities. The internal-testing build intentionally leaves private production server/certificate configuration blank. Native capability management is therefore configuration-blocked for production acceptance.

The finished architecture should not require Android-native duplicates of every PWA page if the supported mobile product intentionally opens the trusted PWA for general conversation/work. Native screens are required where the OS boundary matters: first-device identity/enrollment, secure credentials, recovery, local permissions/sensors and native capability controls where intended.

### iOS / iPadOS

The Swift companion is richer than Android but remains a companion. It has create/join/restore onboarding, passkey/session/recovery/runtime provisioning, Universal Capabilities, Capability Forge V3, connection/device status and Sensorium Privacy. `Sensorium Privacy` is directly reachable and can grant/revoke temporary local sensor sessions or stop all sensing. Forge V3 is directly reachable but explicitly non-production and disabled without a configured non-production host.

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

The detailed IDs and status are in `ui_truth.json` and `PAGE_SPECIFICATIONS.md`.

## 6. Seven missing canonical screens

### P0/P1

1. **ONB-005 — Data Placement Policy** — first-run lacks a clear choice among `device_only`, `progress_only`, `sync_everywhere`, `on_demand` even though these are canonical data policies.
2. **ONB-008 — Setup Review & Completion** — owner needs a final review of Vishnu identity, first trusted device, storage policy and active model/provider before entering Home.
3. **SET-005 — Accessibility** — reduce-motion/high-contrast preferences exist in runtime/control projections, but there is no coherent owner-facing accessibility settings surface.
4. **DAT-002 — Connected Storage Provider Detail** — storage-fabric/provider capability/health exists in backend architecture, but there is no complete owner-facing provider detail/control experience proving destination, health, consent, transfer and failure state.

### P2/P3

5. **SEN-002 — Sensorium Status & Providers** — current native Sensorium privacy is strong for permissions; a normal owner lacks one coherent advanced status page for provider availability/evidence without exposing ADB/simctl internals.
6. **SYS-003 — Updates & Release** — update/release infrastructure exists, but the normal owner product lacks a coherent current-version/update/release-notes/install/recovery surface.
7. **SYS-004 — About / Version / Notices** — version, proprietary license posture and third-party notices should have a discoverable owner page rather than being scattered through release files.

## 7. Important partial screens

The following exist but should not be called complete yet:

- **Home / Conversation:** strong source structure, state presentation and a11y hooks, but no exact-SHA visual journey was executed in this campaign.
- **Memory:** Desktop Second Brain has Overview, Tree, Graph, Timeline and Why Retrieved; those are views within one logical workspace, not five pages. Full mutation/privacy lifecycle remains uneven by platform.
- **Projects:** PWA has a real overview plus a substantial project workspace with Overview, Chat, Work Plan, Files & Sources, Approvals, Discussions, Activity, Live Work and visual-status tabs. WorkOrder detail is an authoritative responsive drawer/full-screen projection.
- **Apps & Tools / Capabilities:** real governed API wiring exists; credentials, approvals and writes are protected. Native parity/configuration and external-provider proof remain incomplete.
- **Devices:** owner navigation exists and backend trust/revocation authority exists, but complete overview/detail/pending-approval/lost-device interaction evidence is not yet captured as a single accepted journey.
- **Data & Storage:** desktop storage dialog and PWA/admin data controls exist; first-run placement selection and provider-detail transparency are incomplete.
- **Security/Recovery:** many real controls exist, but the owner mental model is fragmented across Settings, Owner Controls, onboarding and device surfaces.
- **System:** Desktop Owner Control Center is a real operational view, but it currently renders several tabs as JSON/text projections and should not be mistaken for the finished owner UX.

## 8. Backend without adequate UI

See `BACKEND_WITHOUT_UI.md`. The most important areas are:

- first-run local-first placement policy;
- storage-fabric provider capability/health/transfer visibility;
- consolidated owner session/sign-in-method management;
- self-update/release owner flow;
- advanced Sensorium provider status/evidence;
- coherent Accessibility settings;
- complete recovery/lost-device guided flow;
- route-level diagnostics only where owner-actionable.

Low-level registries, migrations, crypto envelopes, SQLite connection logic, conflict resolution, lease internals, event buses and transport primitives correctly remain internal.

## 9. UI without backend / placeholder truth

See `UI_WITHOUT_BACKEND.md`.

No production page was conclusively proven fake. The PWA contains explicit `uiDemo=1` / demo-preview datasets for design/testing; those records are visibly labeled sample-only and are not saved. They remain developer preview behavior, not normal product data.

The PWA `Live work` / `Workflows` duplicate module mapping is a navigation semantics defect candidate, not evidence that either backend is fake.

Individual buttons still require behavioral instrumentation before the audit can assert there are no no-op callbacks or ignored API results across the entire UI.

## 10. Secondary UI inventory

The blueprint requires **34 transient surface families**, including:

- canonical action approval prompt;
- fresh-owner reauthentication prompt;
- destructive confirmation;
- credential entry;
- provider connection/test prompt;
- OpenAPI import/preview;
- MCP add/discover/approval;
- capability one-time write approval;
- capability revoke/disconnect confirmation;
- device pairing QR/code;
- pending-device approval;
- device revoke/lost-device confirmation;
- recovery-code copy/download acknowledgement;
- restore confirmation;
- backup create/import/export confirmation;
- data-movement confirmation;
- sync-conflict resolution;
- knowledge upload/add-source;
- knowledge remove/disconnect;
- memory delete/retention confirmation;
- new/edit project;
- new/edit project task;
- WorkOrder detail shell;
- new/edit automation;
- automation pause/delete;
- notification/account menu;
- conversation history drawer;
- attachment/file picker;
- conversation retry/cancel feedback;
- microphone/camera/sensor permission prompt;
- Voice Studio persona/authorization dialogs;
- Voice Lab telephony consent/approval;
- security key/passkey removal confirmation;
- emergency-stop confirmation.

Implementations may be dialog, sheet, drawer, popover or full-screen mobile presentation depending on platform.

## 11. Visual-state model

The shared state vocabulary contains **14 major visual state types**:

`initial`, `loading`, `empty`, `populated`, `editing`, `saving`, `success`, `error`, `offline`, `permission denied`, `approval required`, `disabled`, `revoked/expired`, `degraded`.

A page only needs the states relevant to its data/action model. Local-first screens must distinguish `offline but locally usable` from `unavailable`.

## 12. Accessibility truth

Existing automated contracts verify important primitives: accessible labels for chat controls, approval dialog semantics/focus return, live/error announcements, reduced-motion CSS behavior and responsive breakpoint expectations.

Still **NOT VERIFIED** as complete product accessibility:

- full desktop/web tab order for every screen;
- screen-reader journeys across all major flows;
- VoiceOver/TalkBack acceptance on physical devices;
- dynamic type/text scaling on all native screens;
- touch-target acceptance on physical phones/tablets;
- contrast certification across all states;
- keyboard reachability for every custom control.

`SET-005 Accessibility` is required to make owner-facing controls for supported accessibility preferences discoverable.

## 13. Responsive truth

PWA source includes phone/tablet breakpoints, safe-area handling, fixed mobile composer/home chrome, drawer behavior, 44px touch targets, focus-visible styling and reduced-motion rules. Projects and WorkOrder detail both contain explicit mobile adaptations.

Source is not visual proof. The exact audited SHA has **0 accepted runtime screenshots in this campaign**. Required viewport acceptance remains: narrow phone, standard phone, large phone, tablet portrait, tablet landscape, laptop, desktop and wide desktop.

## 14. Visual system

Vishnu already has a semantic dark visual direction across desktop and PWA. Desktop shared tokens include near-black background/surfaces, light text, muted secondary text, blue accent, red danger, 4/8/12/16/20/24/32/40 spacing, 44px control/touch targets and strong focus borders. PWA uses matching dark glass/surface semantics, blue/cyan status accents, rounded cards, safe-area spacing, focus-visible and reduced motion.

The finished cross-platform design system should standardize:

- semantic colors rather than hardcoded per-screen values;
- type scale and section hierarchy;
- 4px-based spacing;
- 10–16px standard radii;
- 44px minimum interactive target;
- one focus-ring treatment;
- consistent status badges for active/offline/degraded/blocked/revoked;
- consistent approval and destructive-action language;
- platform-native controls where appropriate while retaining Vishnu naming/status semantics.

## 15. Internal systems correctly requiring no dedicated UI

At least **12 infrastructure families** should remain internal and be surfaced only through owner-meaningful status/control where needed:

1. SQLite migration engine
2. RootKeyStore internals
3. SecretVault encryption envelope internals
4. ToolRegistry registry mechanics
5. Approval durability internals
6. event bus / signal transport
7. conflict resolver internals
8. lease/token transport internals
9. encrypted data-segment framing
10. retry/backoff engine
11. audit-chain/hash mechanics
12. qualification/evidence persistence mechanics

The owner needs controls/status/history around these systems where material; they do not need raw implementation screens.

## 16. Required owner answers

The final product IA must let the owner answer, without developer knowledge:

- What is Vishnu doing now? → Home / Live Work / Activity
- What does Vishnu remember? → Memory
- What does Vishnu know? → Knowledge
- What needs me? → Inbox / Approvals
- What can Vishnu access? → Apps & Tools / Capabilities / Permissions
- Which devices are trusted? → Devices
- Where does my data live? → Data & Storage
- Which AI provider is active? → AI Models & Providers
- What can sense my environment? → Sensorium Privacy
- How do I stop/revoke something? → relevant detail page plus canonical confirmation
- How do I recover? → Recovery
- Is the system healthy? → Dashboard / System Status

## 17. Click-path blueprint

- Add AI provider: `Home → Settings → AI Models & Providers → Add Provider`
- Revoke lost phone: `Home → Settings/More → Devices → Device Detail → Revoke/Mark Lost`
- Check data location: `Home → Settings → Data & Storage`
- Remove an API capability: `Home → Apps & Tools → Capabilities → Capability Detail → Disconnect/Revoke`
- Review pending approval: `Home → Inbox/Attention → Approval → Allow once / Deny`
- Inspect active work: `Home → Live Work → Work Detail`
- Restore Vishnu: `Welcome → Restore Vishnu → Verify recovery → Establish trusted device → Review → Home`
- Stop sensing on iPhone: `Companion → Sensorium Privacy → STOP ALL SENSING`
- Advanced capability rollout: `Companion → Capability Forge V3` only in explicitly configured non-production/testing context.

## 18. Priority implementation plan

### P0

No new P0 visual redesign is justified by this audit alone. Existing authentication, approval, credential, revoke and recovery authorities must not be weakened. Any discovered security/data-loss break from behavioral testing becomes P0 immediately.

### P1

1. ONB-005 Data Placement Policy
2. ONB-008 Setup Review & Completion
3. SET-005 Accessibility
4. DAT-002 Connected Storage Provider Detail
5. Resolve/clarify PWA `Live work` versus `Workflows` navigation semantics
6. Unify fragmented Security/Recovery controls without duplicating authorities
7. Add exact-SHA interaction + screenshot qualification for Home, Conversation, Memory, Knowledge, Apps & Tools, Devices and Data & Storage

### P2

- Sensorium status/provider presentation
- Work/Automation/Project parity refinements
- session/sign-in-method management polish
- failure/offline/degraded-state coverage

### P3

- Updates/About owner surfaces
- visual consistency refinements
- broader screenshot catalog and noncritical convenience UI

## 19. Visual evidence limitation

This environment can inspect and modify the connected GitHub repository but cannot clone/launch the repository runtime or emulator/simulator directly. No exact-SHA screenshot artifact was found during this source pass. Therefore `visual_verified=false` remains correct for every canonical screen. The follow-up qualification must capture real rendered screenshots; static source and demo previews are not accepted as visual evidence.

## 20. Final confidence statement

Vishnu's visible owner product is now defined as a **63-screen canonical product model**, separate from platform implementations, transient UI and visual states. Current source proves meaningful implementation for 56 concepts but does not justify calling any full canonical screen COMPLETE under the requested strict standard because runtime visual/behavior qualification remains outstanding. Seven required concepts are missing, the most important being first-run Data Placement, setup review/completion, Accessibility and connected-storage provider detail. No required canonical screen was proven orphaned or presentation-only; where reachability or individual control behavior is not executable in this environment it remains explicitly NOT VERIFIED.