# Vishnu Page Specifications

**Baseline:** `4ec735de327f2bab6dccb774e2a9c28ef4fc44af`

This is the canonical owner-facing page specification. A "screen" may be implemented as a full page, workspace, settings subsection, native navigation destination or responsive detail surface. Transient prompts are specified separately and do not create extra canonical IDs.

## Shared acceptance contract

Every required screen inherits these criteria unless explicitly N/A:

- Owner can reach the surface from a documented path or a valid authenticated deep link.
- Read data comes from a real API/runtime authority, not a demo-only object in normal mode.
- Writes are permission checked, persisted and still correct after refresh/reload when persistence is expected.
- Security-sensitive writes use current owner/device/approval authorities; direct URL navigation never bypasses them.
- Loading, empty, error, offline/degraded and unauthorized states are intentional where applicable.
- Destructive actions explain impact and require proportionate confirmation.
- Desktop/web provides visible focus and logical keyboard order; native surfaces provide accessible names/semantics and adequate touch targets.
- Phone/tablet layouts do not clip primary actions or require horizontal scrolling for core work.
- COMPLETE additionally requires exact-SHA executable behavior and visual evidence. No screen meets that stricter condition in this audit.

---

## Onboarding & Authentication

### ONB-001 — Welcome / Create-Join-Restore
**Purpose / owner question:** "Am I creating a new Vishnu, joining mine, or restoring it?"  
**Contents:** Vishnu identity/brand, `Create my Vishnu`, `I already have Vishnu`, `Restore Vishnu`, concise local-first/security explanation.  
**Actions/data/backend:** choose flow; first-run coordinator / identity bootstrap and platform provisioning entrypoints. No owner data should be created until the chosen flow requires it.  
**Navigation:** application/browser/native first launch. Exit to the selected onboarding flow.  
**Platforms:** Desktop, PWA, iOS required and present; Android native first-device version is required but currently missing.  
**States:** ready, runtime unavailable, setup already initialized, resume interrupted setup.  
**Status:** PARTIAL. Visual behavior is not exact-SHA accepted.

### ONB-002 — Owner Identity
**Purpose:** establish the human owner independently of device identity.  
**Contents:** first name, last name, display name, optional avatar, explanation that Device 1 is not the owner identity.  
**Actions/backend:** validate/save identity through identity/preferences authority; idempotent retry.  
**Navigation:** Create → Owner Identity → Security.  
**Platforms:** Desktop/PWA/iOS present; Android native missing for universal first-device parity.  
**States:** editing, validation error, saving, retry/resume.  
**Status:** PARTIAL.

### ONB-003 — Security Setup
**Purpose:** secure the owner before enabling trusted actions.  
**Contents:** passkey/biometric where supported, owner password/fallback where retained, explanation of local credential handling.  
**Actions/backend:** create credential; never echo secrets; fail closed if secure storage is unavailable.  
**Navigation:** Owner Identity → Security → Privacy/Autonomy.  
**Platforms:** Desktop/PWA/iOS present with different native conventions; Android first-device surface missing.  
**States:** passkey available/unavailable, password fallback, credential creation failure.  
**Status:** PARTIAL.

### ONB-004 — Privacy & Autonomy
**Purpose:** tell Vishnu how much external AI/action authority the owner allows.  
**Contents:** model privacy policy, memory enablement, autonomy mode, plain-language consequences.  
**Actions/backend:** persist owner preferences and tool autonomy setting.  
**Navigation:** Security → Privacy & Autonomy → Data Placement.  
**Platforms:** Desktop/PWA/iOS present; Android missing.  
**States:** defaults, edited, save error.  
**Status:** PARTIAL.

### ONB-005 — Data Placement Policy
**Purpose:** answer "Where may my data live?" during creation.  
**Contents:** exactly four policies — `device_only`, `progress_only`, `sync_everywhere`, `on_demand` — with plain-language explanation, current device/location and cloud-optional statement.  
**Actions/backend:** save canonical Data Plane policy; changing the selection must not silently move existing owner data.  
**Navigation:** Privacy & Autonomy → Data Placement → AI Provider.  
**Platforms:** required wherever Vishnu can be created as Device 1.  
**States:** policy selected/unselected, remote storage unavailable, offline with local choices still usable.  
**Status:** MISSING, P1.

### ONB-006 — AI Provider Setup
**Purpose:** choose how Vishnu obtains model intelligence.  
**Contents:** local/configure-later plus supported providers such as OpenAI, Gemini, OpenRouter and other currently configured provider choices; active privacy routing explanation.  
**Actions/backend:** save default provider/model; secrets go to encrypted credential authority, never visible after save.  
**Navigation:** Data Placement → AI Provider → Recovery.  
**Platforms:** Desktop/PWA/iOS present; Android first-device surface missing.  
**States:** provider not configured, invalid credential, local-only, test/connection failure.  
**Status:** PARTIAL.

### ONB-007 — Recovery Code Setup
**Purpose:** ensure the owner can recover without a lost first device.  
**Contents:** one-time codes, copy/save/download options, acknowledgement and warning not to store them insecurely.  
**Actions/backend:** generate one-time recovery material and record acknowledgement without silently uploading it.  
**Navigation:** AI Provider → Recovery Codes → Review.  
**Platforms:** Desktop/PWA/iOS present; Android missing.  
**States:** codes visible once, acknowledged, copy/download failure.  
**Status:** PARTIAL.

### ONB-008 — Setup Review & Completion
**Purpose:** answer "What did I just create and where is it secured?" before Home.  
**Contents:** owner identity, first trusted device, authentication method, recovery readiness, selected data policy, active model/provider, any configuration still deferred.  
**Actions/backend:** Finish/Enter Vishnu; resume setup instead of duplicating identity on retry.  
**Navigation:** Recovery Codes → Review → Home.  
**Platforms:** all first-device creation platforms.  
**States:** ready, unresolved required item, deferred provider, failed finalization.  
**Status:** MISSING, P1.

### AUTH-001 — Sign In / Unlock
**Purpose:** authenticate an existing owner without repeating onboarding.  
**Contents:** passkey/biometric, password fallback where permitted, session/device context, safe recovery link.  
**Actions/backend:** owner session creation/rotation with secure token handling.  
**Navigation:** protected entry/deep link → Sign In → requested destination/Home.  
**Platforms:** PWA/iOS source-present; desktop/native Android owner-unlock experience is incomplete.  
**States:** signed out, expired, revoked, failed, locked/degraded.  
**Status:** PARTIAL.

### AUTH-002 — Join Existing Vishnu / Device Enrollment
**Purpose:** make a new device trusted without making it the owner identity.  
**Contents:** existing Vishnu address/identity, QR or short-lived pairing, requested scopes, existing-device approval where available.  
**Actions/backend:** authenticate owner, create per-device credential, register trust/scopes, audit enrollment.  
**Navigation:** Welcome → Already have Vishnu → enrollment → Home/companion.  
**Platforms:** all four families have some source path; desktop explicitly falls back to secure PWA for some second-desktop authority.  
**States:** pending approval, denied, expired pairing, revoked, offline.  
**Status:** PARTIAL.

### AUTH-003 — Restore Access
**Purpose:** recover owner access when trusted devices/runtime are lost.  
**Contents:** recovery code/package, backup path where supported, passphrase/key, destination/runtime explanation.  
**Actions/backend:** verify recovery, restore safely, establish new trusted device, lead to lost-device revocation.  
**Navigation:** Welcome/Sign In → Restore Vishnu → review → Home.  
**Platforms:** Desktop/PWA/iOS source-present; Android native restore parity is missing.  
**States:** invalid/used code, incompatible/corrupt backup, restore pending/restart required.  
**Status:** PARTIAL.

---

## Home & Conversation

### HOME-001 — Home
**Purpose:** answer "What is Vishnu doing and what needs me now?" without becoming an admin dashboard.  
**Contents:** Vishnu presence/core state (idle/listening/thinking/acting/remembering/retrieving/responding/needs approval), composer entry, important attention, recent continuation, concise local/offline health.  
**Actions/backend:** start/continue conversation, open pending attention/work, voice/attachment entry. Runtime state is read-only projection; UI must not invent semantic AI state.  
**Navigation:** primary destination after auth/setup.  
**Platforms:** Desktop/PWA; native companions may open trusted PWA rather than duplicate Home.  
**States:** idle, active, needs approval, background work, degraded/offline, error.  
**Status:** PARTIAL.

### CHAT-001 — Conversation Workspace
**Purpose:** conduct the main owner/Vishnu interaction.  
**Contents:** history, user/assistant messages, markdown/code, attachments, citations, tool activity, approval cards, model indicator, voice/file controls.  
**Actions/backend:** send, stream, cancel, retry, copy, attach, approve/deny governed action. Conversation/turn runtime owns state.  
**Navigation:** Home or Conversations → thread.  
**Platforms:** Desktop/PWA required; trusted mobile web serves phones/tablets.  
**States:** sending, thinking, tool running, approval, interrupted/resumed, failure/offline.  
**Status:** PARTIAL.

### CHAT-002 — Conversation History
**Purpose:** find and continue prior threads.  
**Contents:** thread list, search/date grouping, current thread, optional project association, archive/delete where supported.  
**Actions/backend:** open/continue, rename/archive/delete only when canonical conversation authority supports it.  
**Navigation:** Home/Conversation → history drawer/sidebar/page.  
**Platforms:** PWA source-present; desktop equivalent is incomplete.  
**States:** loading, empty, search-no-results, error/offline.  
**Status:** PARTIAL.

---

## Memory

### MEM-001 — Memory Overview & Search
**Purpose:** answer "What does Vishnu remember?"  
**Contents:** categories/overview, recent memories, search/filter, privacy explanation, relationship/timeline summary. Desktop Second Brain tabs remain views inside this workspace.  
**Actions/backend:** search/browse Memory authority; link to settings/retention where supported.  
**Navigation:** primary Personal → Memory.  
**Platforms:** Desktop/PWA.  
**States:** empty, populated, searching, memory disabled, error.  
**Status:** PARTIAL.

### MEM-002 — Memory Detail / Why Retrieved
**Purpose:** understand an individual memory and why it influenced a response.  
**Contents:** content/subject/type, source, confidence, timestamps, sensitivity, contradiction/supersession state, relationships and retrieval explanation/evidence.  
**Actions/backend:** inspect; edit/delete only if current authority supports it and with proportional confirmation.  
**Navigation:** Memory search/tree/timeline → selected memory.  
**Platforms:** Desktop/PWA.  
**States:** direct inspection, retrieval explanation available/unavailable, revoked/deleted/error.  
**Status:** PARTIAL.

---

## Knowledge & Files

### KNW-001 — Knowledge Overview / Sources
**Purpose:** answer "What has Vishnu indexed as knowledge?"  
**Contents:** collections/sources/files, indexing availability/status, search, add/upload entry, location/privacy.  
**Actions/backend:** create collection, upload/add source, search via Knowledge authority/content intelligence.  
**Navigation:** Personal → Knowledge.  
**Platforms:** Desktop/PWA; PWA is richer.  
**States:** empty, ingesting/indexing, available, failed, offline-local.  
**Status:** PARTIAL.

### KNW-002 — Knowledge Source Detail
**Purpose:** inspect/update/remove one knowledge source without inventing a separate Files product.  
**Contents:** source identity, type, storage/location, ingestion/index status, extracted metadata/citations, update time and errors.  
**Actions/backend:** refresh/update/remove/disconnect; ask/search within source where supported.  
**Navigation:** Knowledge Overview → source.  
**Platforms:** PWA source-present; desktop detail parity incomplete.  
**States:** processing, ready, failed, unavailable, removal confirmation.  
**Status:** PARTIAL.

---

## Activities, Attention & Work

### ACT-001 — Today
**Purpose:** show what matters today without exposing internal scheduler mechanics.  
**Contents:** due/upcoming work, recent continuation, important reminders/automation, attention items.  
**Actions/backend:** open source item, acknowledge/continue where supported.  
**Navigation:** Workspace → Today.  
**Platforms:** PWA.  
**States:** empty/quiet day, loading, offline, error.  
**Status:** PARTIAL.

### ATT-001 — Inbox / Attention Center
**Purpose:** one place for approvals, failed work, security/device/provider issues and meaningful notifications.  
**Contents:** grouped items with severity, source, reason, required owner decision and age.  
**Actions/backend:** open canonical approval/work/device/security destination; mark notification read.  
**Navigation:** Workspace → Inbox and Home attention entry.  
**Platforms:** PWA; desktop equivalent should be added via Activities/Home rather than a duplicate subsystem.  
**States:** zero attention, unread, approval required, degraded/error.  
**Status:** PARTIAL.

### ACT-002 — Activity Timeline
**Purpose:** answer "What has Vishnu done recently?"  
**Contents:** actions, work, automation, integration/device activity with filters for time/status/system/project. Security audit payloads remain separate.  
**Actions/backend:** filter/open related entity.  
**Navigation:** primary/secondary Activity destination.  
**Platforms:** Desktop/PWA.  
**States:** empty, loading, filtered/no-results, error.  
**Status:** PARTIAL.

### WRK-001 — Live Work Overview
**Purpose:** show running/queued/waiting/completed/failed governed work.  
**Contents:** objective, status/progress, owner attention, worker/tool summary, project association.  
**Actions/backend:** open work detail, cancel/pause only through canonical work runtime.  
**Navigation:** System/Work → Live Work.  
**Platforms:** PWA; desktop parity incomplete.  
**States:** no active work, running, waiting approval, recovery required, failed.  
**Status:** PARTIAL.

### WRK-002 — Work Detail
**Purpose:** inspect one WorkOrder and its proof/authority state.  
**Contents:** objective, milestone, worker, tool, dependencies, output/evidence contract, approvals/budgets, evidence/receipts, claims/review, recovery and safe next action.  
**Actions/backend:** read authoritative aggregate; mutations belong to canonical work controls, not an ungoverned detail UI.  
**Navigation:** Live Work/Project → selected work item. PWA currently uses responsive drawer/full-screen shell.  
**Platforms:** PWA.  
**States:** loading, running, waiting approval, failed, uncertain/recovery, completed.  
**Status:** PARTIAL.

### WRK-003 — Agent Workforce
**Purpose:** advanced visibility/control for explicit worker/agent orchestration, not normal chat.  
**Contents:** workforce state, active work, worker allocations/detail and governed controls.  
**Actions/backend:** use workforce APIs only; avoid exposing implementation internals as ordinary settings.  
**Navigation:** injected advanced PWA navigation.  
**Platforms:** PWA.  
**States:** disabled/unconfigured, no workers, active, degraded.  
**Status:** EXPERIMENTAL.

---

## Automations

### AUT-001 — Automations / Workflows Overview
**Purpose:** manage owner-created recurring/conditional work.  
**Contents:** active/paused/upcoming workflows, schedule/condition, last/next run and attention.  
**Actions/backend:** create, pause/resume, open detail; AutomationEngine/workflow authority persists state.  
**Navigation:** Apps & Tools/System → Workflows/Automations.  
**Platforms:** Desktop/PWA.  
**States:** empty, active, paused, failure, scheduler unavailable.  
**Status:** PARTIAL.

### AUT-002 — Automation Detail & Run History
**Purpose:** understand and control one automation.  
**Contents:** instruction, trigger/schedule, permissions, next run, run history, outputs/errors.  
**Actions/backend:** edit, pause/resume, run where allowed, delete with confirmation.  
**Navigation:** Automations Overview → automation.  
**Platforms:** Desktop/PWA.  
**States:** active/paused, executing, success, failed, approval needed.  
**Status:** PARTIAL.

---

## Projects

### PRJ-001 — Projects Overview
**Purpose:** organize sustained owner work.  
**Contents:** active/paused/review/completed/archived projects, search/filter/sort, progress and continue card.  
**Actions/backend:** create, open, edit metadata, archive/restore via project API.  
**Navigation:** Workspace → Projects.  
**Platforms:** PWA; desktop parity is missing.  
**States:** loading, empty, preview mode clearly labeled, filtered/no-results, error.  
**Status:** PARTIAL.

### PRJ-002 — Project Workspace
**Purpose:** one coherent workspace for a project's context and governed work.  
**Contents:** Overview, Chat, Work Plan, Files & Sources, Approvals, Discussions, Activity, Live Work and optional visual status/structure views.  
**Actions/backend:** converse in project context, manage tasks/files/discussions, inspect approvals/work.  
**Navigation:** Projects Overview → project.  
**Platforms:** PWA.  
**States:** loading, empty sections, offline, backend error, archived/completed.  
**Status:** PARTIAL.

---

## Products

### PRD-001 — Our Products Overview
**Purpose:** advanced product-building overview for Vishnu-created products, not a general consumer Home feature.  
**Contents:** product family/hierarchy, requests, reusable components, lifecycle/build state.  
**Actions/backend:** open/create/inspect supported product records through existing product authority.  
**Navigation:** Desktop `Our Products`; injected PWA entry.  
**Platforms:** Desktop/PWA.  
**States:** empty, building, ready, failed, blocked by qualification.  
**Status:** EXPERIMENTAL.

### PRD-002 — Product Detail / Build Lifecycle
**Purpose:** inspect a product's specification, artifacts and governed release/build lifecycle.  
**Contents:** manifest/spec, components, targets, stages, artifacts, qualification/release state.  
**Actions/backend:** initiate permitted development build/qualification; production signing/release remains separately governed.  
**Navigation:** Our Products → product.  
**Platforms:** Desktop/PWA.  
**States:** draft/building/qualified/failed/blocked.  
**Status:** EXPERIMENTAL.

---

## Apps, Tools & Capabilities

### APP-001 — Apps & Tools Overview
**Purpose:** answer "What can Vishnu access?"  
**Contents:** connected/available apps, internal tools, integrations, capability entry, connection/permission status.  
**Actions/backend:** open integration/capability, connect/reconnect/revoke where governed.  
**Navigation:** primary secondary destination Apps & Tools.  
**Platforms:** Desktop/PWA.  
**States:** empty/unconfigured, connected, degraded, revoked.  
**Status:** PARTIAL.

### APP-002 — Connected Service / Integration Detail
**Purpose:** inspect one service connection without exposing secret values.  
**Contents:** service name, status, scopes/permissions, credential status, available actions, recent safe activity/error.  
**Actions/backend:** authenticate/test/reconnect/revoke through integration/OAuth/credential authorities.  
**Navigation:** Apps & Tools → service.  
**Platforms:** Desktop/PWA.  
**States:** disconnected, connecting, connected, invalid/expired credential, provider unavailable.  
**Status:** PARTIAL.

### CAP-001 — Capabilities Overview
**Purpose:** view governed OpenAPI/MCP/other capabilities and risk/connection state.  
**Contents:** search/list, source/type, method/tool, risk, connection and revocation state.  
**Actions/backend:** import/discover entry, open detail, connect/approve.  
**Navigation:** Apps & Tools → Capabilities; native companion capability manager where intended.  
**Platforms:** Desktop/PWA/Android/iOS source-present; Android production host configuration is blocked.  
**States:** signed out, loading, empty, connected, revoked, server unavailable.  
**Status:** PARTIAL.

### CAP-002 — Capability Detail
**Purpose:** understand exactly what a capability can do before use.  
**Contents:** operation/tool schema, source/server, risk/read-write state, permission, credential status, history/audit and recent failure.  
**Actions/backend:** connect, risk approve, execute/test, rotate credential, disconnect/revoke; writes require exact one-time approval when policy demands it.  
**Navigation:** Capabilities Overview → capability.  
**Platforms:** Desktop/PWA/Android/iOS source-present with different depth.  
**States:** disconnected, approved read, write approval required, expired session, revoked/error.  
**Status:** PARTIAL.

### CAP-003 — Capability Forge V3
**Purpose:** advanced non-production capability creation/readiness/OAuth/canary rollout control.  
**Contents:** readiness, provider list, capability/version IDs, OAuth status, canary/promotion controls, provider verification result.  
**Actions/backend:** fresh-owner authenticated Forge V3 APIs; production activation is explicitly excluded.  
**Navigation:** iOS companion → Capability Forge V3.  
**Platforms:** iOS current implementation; no general owner parity required until Forge graduates from lab/advanced scope.  
**States:** host unconfigured, session expired, denied, request result.  
**Status:** EXPERIMENTAL.

---

## Devices

### DEV-001 — Trusted Devices Overview
**Purpose:** answer "Which devices belong to my Vishnu?"  
**Contents:** name/platform/type, current device, trust, online/offline/last-seen, scopes and pending/revoked distinction.  
**Actions/backend:** open device, start pairing/enrollment, review pending request.  
**Navigation:** Settings/More → Trusted Devices.  
**Platforms:** Desktop/PWA/native companions have some source representation.  
**States:** current-only empty-other-devices, online/offline, pending, revoked, API failure.  
**Status:** PARTIAL.

### DEV-002 — Device Detail
**Purpose:** inspect/control one trusted device.  
**Contents:** name, device ID where appropriate, platform/type, created/last seen, trust/scopes/security/continuity status, advanced metadata progressively disclosed.  
**Actions/backend:** rename/change permitted scopes if supported, revoke/mark lost with confirmation.  
**Navigation:** Devices → device.  
**Platforms:** PWA/iOS have meaningful detail/status; desktop/Android parity incomplete.  
**States:** online/offline, pending, revoked/lost, stale, unauthorized.  
**Status:** PARTIAL.

---

## Data & Storage

### DAT-001 — Data & Storage Overview / Policy
**Purpose:** answer "Where is my data and what will Vishnu sync?"  
**Contents:** current placement policy, local/remote locations, cloud master state, sync/remote availability, local-first explanation and recovery link.  
**Actions/backend:** change policy with clear consequences; no silent data movement; open provider detail/transfer only when configured.  
**Navigation:** Settings → Data & Storage.  
**Platforms:** Desktop/PWA source-present; native first-device policy selection is missing where needed.  
**States:** local-only, synced, offline, conflict, provider unavailable, movement confirmation.  
**Status:** PARTIAL.

### DAT-002 — Connected Storage Provider Detail
**Purpose:** make remote storage transparent and controllable.  
**Contents:** provider/account label, capabilities, health, destination/location, encryption statement, transfer/sync status, last error and consent.  
**Actions/backend:** connect/test/disconnect, permitted explicit transfer, retry/cancel; secrets never displayed.  
**Navigation:** Data & Storage → Connected Storage → provider.  
**Platforms:** Desktop/PWA.  
**States:** disconnected, healthy, degraded, offline, transferring, failed/retry.  
**Status:** MISSING, P1.

---

## Models & Providers

### MOD-001 — AI Models & Providers Overview
**Purpose:** answer "Which AI is Vishnu using and where does data go?"  
**Contents:** active/default model/provider, local/cloud indicator, available/configured providers, health and privacy routing.  
**Actions/backend:** select default, add/open provider, test availability.  
**Navigation:** Settings → AI & Models.  
**Platforms:** Desktop/PWA.  
**States:** local-only, configured, degraded/fallback, provider unavailable.  
**Status:** PARTIAL.

### MOD-002 — Provider Detail / Credentials
**Purpose:** configure one provider securely.  
**Contents:** provider, models, connection status, credential-present indicator, data-routing disclosure, validation result.  
**Actions/backend:** save/rotate/revoke credential, test connection, choose model; never re-display secret.  
**Navigation:** Models & Providers → provider.  
**Platforms:** Desktop/PWA.  
**States:** unconfigured, validating, connected, invalid/expired credential, rate/provider error.  
**Status:** PARTIAL.

---

## Voice

### VOC-001 — Voice Settings
**Purpose:** configure normal voice interaction.  
**Contents:** microphone permission/status, speech output, listening/wake behavior if supported, interruption, selected authorized voice.  
**Actions/backend:** persist supported preferences, request OS permission only at point of use.  
**Navigation:** Settings → Voice.  
**Platforms:** Desktop/PWA; native permission/session UI remains platform specific.  
**States:** permission required/denied, available, provider unavailable, text-only degraded mode.  
**Status:** PARTIAL.

### VOC-002 — Voice Studio
**Purpose:** advanced owner management of personas/expression/pronunciation/authorized voices.  
**Contents:** persona/voice configuration, enrollment/authorization status, preview/management controls.  
**Actions/backend:** use Voice Intelligence/VoiceStudio governed runtime; sensitive enrollment requires explicit owner authority.  
**Navigation:** Desktop Dashboard/Owner Control Center → Voice Studio.  
**Platforms:** Desktop.  
**States:** provider unavailable, no authorized voice, configured, validation failure.  
**Status:** PARTIAL.

### VOC-003 — Voice Lab
**Purpose:** isolated research/qualification environment, not normal owner voice settings.  
**Contents:** benchmark/qualification candidates, evidence, optional governed telephony controls.  
**Actions/backend:** test/qualify/promote only through lab/release authority; telephony remains default-off and consent governed.  
**Navigation:** Desktop Owner Control Center → Voice Lab.  
**Platforms:** Desktop.  
**States:** disabled, candidate, testing, qualified/failed, provider/hardware blocked.  
**Status:** EXPERIMENTAL.

---

## Sensorium & Computer Control

### SEN-001 — Sensorium Privacy & Permissions
**Purpose:** let the device owner see/stop exactly which sensors are active.  
**Contents:** camera/voice plus microphone, screen, location, motion, environment, network, clipboard, wearable, document/OCR and spatial session state; retention/boundary explanations and recent local audit.  
**Actions/backend:** allow this session, stop individual session, STOP ALL SENSING. Sensor access never implies action authority.  
**Navigation:** iOS companion → Sensorium Privacy & Sensors; Android equivalent required.  
**Platforms:** iOS source-present, Android missing.  
**States:** OFF, session active with remaining time, denied/unavailable, emergency stop.  
**Status:** PARTIAL.

### SEN-002 — Sensorium Status & Providers
**Purpose:** advanced owner diagnostics for provider availability/evidence without exposing low-level ADB/simctl command execution.  
**Contents:** virtual/native provider type, availability/readiness, device association, last evidence timestamp and qualification level.  
**Actions/backend:** read status/evidence; no arbitrary provider command console.  
**Navigation:** Settings → Advanced → Sensorium.  
**Platforms:** Desktop/PWA advanced owner surfaces.  
**States:** available/unavailable/degraded/failed/not verified.  
**Status:** MISSING, P2.

### CTL-001 — Computer & Browser Control
**Purpose:** make governed computer/browser operating authority understandable.  
**Contents:** enabled/disabled, current device/profile, permission/risk boundary, stop state and link to activity history.  
**Actions/backend:** enable/disable supported control, approve proposed sensitive action through canonical approval UI; no unrestricted shell console.  
**Navigation:** Settings → Computer Control / Advanced.  
**Platforms:** Desktop source-present; PWA management parity is incomplete.  
**States:** disabled, enabled, action approval required, target unavailable, revoked/error.  
**Status:** PARTIAL.

---

## Security, Privacy & Approvals

### SEC-001 — Security Overview
**Purpose:** summarize whether owner identity, trusted devices, credentials and recovery are healthy.  
**Contents:** sign-in method status, trusted-device count, recovery readiness, credential/vault status, recent critical event links.  
**Actions/backend:** navigate to sign-in methods, devices, recovery, audit and emergency controls.  
**Navigation:** Settings → Security.  
**Platforms:** Desktop/PWA.  
**States:** healthy, warning/action needed, recovery incomplete, revoked/degraded.  
**Status:** PARTIAL.

### SEC-002 — Sign-in Methods & Sessions
**Purpose:** control passkeys/password fallback and active owner sessions.  
**Contents:** registered methods, active/native/browser sessions where supported, created/last-used/device metadata without raw tokens.  
**Actions/backend:** add passkey, remove method with reauth, revoke session, rotate native session where supported.  
**Navigation:** Security → Sign-in Methods & Sessions.  
**Platforms:** Desktop/PWA; native flows exist but management is fragmented.  
**States:** no passkey, current session, expired/revoked, reauth required.  
**Status:** PARTIAL.

### SEC-003 — Security Events / Audit History
**Purpose:** answer "What sensitive actions happened?" without exposing secrets.  
**Contents:** timestamp, action/system, requesting device/session, outcome, approval/revocation context, redacted payload summary.  
**Actions/backend:** filter/search/open related entity; no mutation of immutable audit truth.  
**Navigation:** Security/Owner Controls → Audit History.  
**Platforms:** PWA source-present; desktop parity missing.  
**States:** empty, filtered, loading/error, unavailable audit store.  
**Status:** PARTIAL.

### APR-001 — Approvals Center
**Purpose:** provide one discoverable queue of pending governed decisions.  
**Contents:** what Vishnu wants to do, why, target/service/device, read/write/destructive classification, parameters/impact, one-time versus persistent distinction.  
**Actions/backend:** Allow once/Approve/Deny/Cancel using ApprovalManager and fresh owner reauth when required.  
**Navigation:** Inbox/Home attention → Approvals Center or contextual approval surface.  
**Platforms:** PWA strongest; desktop equivalent should be unified with Activities/Home.  
**States:** pending, approved/consumed, denied, expired, invalidated.  
**Status:** PARTIAL.

### PRI-001 — Privacy Controls
**Purpose:** explain/control memory, knowledge, telemetry/external AI and data-sharing/privacy behavior.  
**Contents:** local-first explanation, memory privacy, external-provider data flow, cloud/data policy links, sensor/device sharing boundaries.  
**Actions/backend:** persist supported preferences; link to Data & Storage and Sensorium for location/sensing-specific controls.  
**Navigation:** Settings → Privacy.  
**Platforms:** Desktop/PWA.  
**States:** local-only, external allowed, disabled control due unavailable feature.  
**Status:** PARTIAL.

---

## Recovery & Notifications

### REC-001 — Recovery Overview
**Purpose:** answer "Can I recover Vishnu if this device disappears?"  
**Contents:** recovery-code status, backup/recovery-package status, last accepted backup where known, lost-device guidance and restore entry.  
**Actions/backend:** regenerate codes only if supported with fresh reauth; create/export recovery package/backup; open restore; revoke lost device after recovery.  
**Navigation:** Settings → Recovery.  
**Platforms:** Desktop/PWA/iOS have parts; Android parity missing.  
**States:** ready, action required, no backup, package failure, recovery method revoked.  
**Status:** PARTIAL.

### NOT-001 — Notification Settings
**Purpose:** control which meaningful events interrupt the owner and through which available channels.  
**Contents:** approvals/work failures/device/security/automation categories, push/local availability, quiet behavior/summaries where supported.  
**Actions/backend:** persist notification preferences; reject channels unavailable in the installation.  
**Navigation:** Settings → Notifications.  
**Platforms:** Desktop/PWA.  
**States:** push unavailable, category unsupported, saved/error.  
**Status:** PARTIAL.

---

## System, Status & Settings

### SYS-001 — Dashboard / Operational Status
**Purpose:** operational overview distinct from conversational Home.  
**Contents:** runtime/model/device/integration/automation/data-sync/active-work health and actionable alerts.  
**Actions/backend:** refresh, open affected system; avoid duplicating daily conversation.  
**Navigation:** Desktop Dashboard; PWA operational dashboard/status link.  
**Platforms:** Desktop/PWA.  
**States:** healthy, degraded, warning, unavailable component.  
**Status:** PARTIAL; Desktop current Control Center exposes several JSON/text projections that need product-grade presentation.

### SYS-002 — System Status / Diagnostics
**Purpose:** advanced technical status for owner troubleshooting.  
**Contents:** version/runtime health, provider health, device/data status, diagnostics/evidence links, safe redacted error details.  
**Actions/backend:** refresh/export safe diagnostics where supported; never expose secrets or arbitrary execution.  
**Navigation:** Account/Settings → System Status / Advanced.  
**Platforms:** Desktop/PWA.  
**States:** healthy, degraded, failed, qualification not verified.  
**Status:** PARTIAL.

### SYS-003 — Updates & Release
**Purpose:** let owner understand/update the installed Vishnu safely.  
**Contents:** current version/build, update available, release notes, verification/signature status, install/restart state and failure recovery.  
**Actions/backend:** check/download/apply only through existing update/release authority; no silent production promotion.  
**Navigation:** Settings → Updates.  
**Platforms:** Desktop/PWA owner surface as appropriate to deployment.  
**States:** up to date, available, downloading/verifying, restart required, failed/rolled back.  
**Status:** MISSING, P3.

### SYS-004 — About / Version / Notices
**Purpose:** provide stable product/legal/build identity.  
**Contents:** Vishnu version/build, proprietary license notice, third-party notices, links to Privacy/Security and update status.  
**Actions/backend:** copy version/build; open local notices.  
**Navigation:** Settings → About.  
**Platforms:** Desktop/PWA.  
**States:** normal; notices unavailable is a safe noncritical error.  
**Status:** MISSING, P3.

### SET-001 — Settings Hub
**Purpose:** coherent configuration map without becoming a dumping ground.  
**Contents:** General/Profile, Appearance, Language, Accessibility, AI & Models, Voice, Memory, Knowledge, Data & Storage, Apps & Tools, Devices, Notifications, Privacy, Security, Recovery, Updates, Advanced and About links.  
**Actions/backend:** navigate only; settings remain owned by their canonical domains.  
**Navigation:** primary secondary/account Settings.  
**Platforms:** Desktop/PWA.  
**States:** normal, feature unavailable entries clearly disabled/explained.  
**Status:** PARTIAL.

### SET-002 — General & Profile
**Purpose:** basic owner/app preferences.  
**Contents:** owner display/profile information, launch/startup and non-domain-specific preferences.  
**Actions/backend:** update profile/preferences with persistence and reload proof.  
**Navigation:** Settings → General.  
**Platforms:** Desktop/PWA.  
**States:** editing, saving, validation/error.  
**Status:** PARTIAL.

### SET-003 — Appearance
**Purpose:** visual preferences without changing product meaning.  
**Contents:** theme/appearance and supported presentation preferences. Accessibility-specific controls belong to SET-005.  
**Actions/backend:** persist per-owner/device UI preference as designed.  
**Navigation:** Settings → Appearance.  
**Platforms:** Desktop/PWA.  
**States:** preview, saved, unsupported option.  
**Status:** PARTIAL.

### SET-004 — Language & Region
**Purpose:** language/locale presentation preferences.  
**Contents:** supported language/region/time presentation controls; unavailable localization must not be falsely offered.  
**Actions/backend:** persist and safely apply supported preference.  
**Navigation:** Settings → Language & Region.  
**Platforms:** Desktop/PWA.  
**States:** supported, restart/reload required if applicable.  
**Status:** PARTIAL.

### SET-005 — Accessibility
**Purpose:** make supported accessibility preferences discoverable.  
**Contents:** reduce motion, high contrast and any future text/interaction accommodations actually supported by platform/runtime; explain OS-managed settings where Vishnu follows system behavior.  
**Actions/backend:** persist supported preferences and immediately update presentation where safe.  
**Navigation:** Settings → Accessibility.  
**Platforms:** Desktop/PWA; native apps should follow OS accessibility settings and expose app-specific controls only if needed.  
**States:** system-default, enabled, unsupported.  
**Status:** MISSING, P1.

---

## Screen-specific acceptance examples

### DEV-001 Devices Overview
- [ ] Owner reaches it from Settings/More.
- [ ] Current and other trusted devices are distinguished.
- [ ] Name/platform/trust/presence/last seen/scopes are safe and correct.
- [ ] Revoked devices never appear active.
- [ ] Selecting a device opens DEV-002.
- [ ] Empty-other-device and offline states are intentional.
- [ ] Refresh agrees with DeviceRegistry after revoke/enroll.

### CAP-002 Capability Detail
- [ ] Source/schema/risk/read-write state is visible before execution.
- [ ] Credential value is never redisplayed.
- [ ] Write/destructive execution cannot proceed without the canonical approval path.
- [ ] Revocation prevents future execution after refresh/restart.
- [ ] Invalid/expired owner session produces reauthentication guidance.

### DAT-001 Data & Storage
- [ ] Owner can identify current policy and current locations.
- [ ] Offline local capability is not presented as total Vishnu failure.
- [ ] Policy change persists after reload.
- [ ] UI never claims remote copy succeeded without data-plane evidence.
- [ ] Any explicit data movement states source, destination, encryption and confirmation.

### CHAT-001 Conversation
- [ ] Send/stream/cancel/retry states are distinguishable.
- [ ] Tool use and approval wait are visible.
- [ ] Attachment/citation results are tied to the correct turn.
- [ ] Session expiry and offline failure are actionable.
- [ ] Keyboard focus and live status announcements remain usable.

## Final page composition rule

Every finished screen must answer four things in its first viewport or accessible structure: **what am I looking at, what is its state, what can I do, and what should I do next?** Technical metadata is progressively disclosed. Daily-use owner needs must not be buried in Advanced merely because the underlying subsystem is complex.
