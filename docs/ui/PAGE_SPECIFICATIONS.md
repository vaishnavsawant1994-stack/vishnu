# Vishnu page specifications

**Audited baseline:** `4ec735de327f2bab6dccb774e2a9c28ef4fc44af`
**Count basis:** canonical logical owner-facing destinations, not individual native views, tabs, dialogs, or loading states. See `VISHNU_UI_TRUTH_MAP.md` for counting limits.

## ONB-001 — Connect / first run

**Purpose:** Create or join a Vishnu runtime
**Owner question:** How do I create Vishnu, connect my device, or restore access?
**Required / exists / reachable / connected:** Yes / PWA and native enrollment surfaces exist; platform-specific creation/restore paths differ. / Yes / Partial
**Navigation:** Launch → signed-out state → enroll/connect/restore.
**Content:** Profile/device enrollment, pairing code/QR, consent, retry and completion.
**Actions:** Create/connect, scan or enter pairing code, configure name, retry.
**Data:** Enrollment state, runtime URL, device identity and connection state.
**Backend:** PWA owner enrollment APIs; Android ConnectActivity; iOS ConnectOnboardingView.
**Security:** Owner authentication, PKCE/OAuth or pairing gates; do not display bearer secrets.
**Platform status:** desktop: not verified., pwa: partial, android: partial, ios: partial
**States:** Loading, empty discovery, invalid code, network error, paired success.
**Responsive/visual direction:** Short guided steps; clear create/connect/restore choices; no provider jargon. Use clear progress and secure browser handoff; preserve retry state.
**Accessibility:** Labels, keyboard reachability, focus and native screen-reader validation required.
**Test/evidence:** Existing PWA/native onboarding tests; full fresh-install journey not verified. Evidence: pwa/first-run.js; Android ConnectActivity; iOS ConnectOnboardingView; Android manifest launcher.
**Status:** PARTIAL
**Required next work:** Prove each platform’s complete creation/join path and persistence; screenshot authenticated and error states.
**Acceptance criteria:**
- [ ] Fresh owner can reach a completion state.
- [ ] Existing owner can pair without creating a duplicate identity.
- [ ] Interrupted enrollment can retry safely.

## AUTH-001 — Sign-in and session recovery

**Purpose:** Authenticate the owner and recover expired sessions
**Owner question:** Why am I being asked to sign in, and how do I regain access?
**Required / exists / reachable / connected:** Yes / PWA passkey/password/recovery choices and native secure-browser sign-in are present. / Yes / Partial
**Navigation:** Launch → access gate; expired/unauthorized API response → sign-in/re-auth.
**Content:** Passkey, password fallback if enabled, recovery entry, session-expired messaging.
**Actions:** Authenticate, retry, choose recovery, cancel.
**Data:** Session status and safe error/recovery guidance; never token values.
**Backend:** PWA identity APIs; Android native OAuth/PKCE exchange; iOS companion owner flow.
**Security:** Session checks; secure token storage on native; route/API authorization still needs end-to-end checks.
**Platform status:** desktop: not verified., pwa: partial, android: partial, ios: partial
**States:** Unauthenticated, loading, expired, denied, offline, authenticated.
**Responsive/visual direction:** Trust-focused, minimal form; explain passkey/password/recovery choices. Explain next step and preserve intended return destination.
**Accessibility:** Native/browser handoff must announce status; keyboard and focus checks required.
**Test/evidence:** Auth/security tests exist; visual sign-in flow not fully executed in this campaign. Evidence: pwa/index.html#enrollPanel; Android ConnectActivity; iOS ConnectOnboardingView.
**Status:** PARTIAL
**Required next work:** Execute auth, expiry, reauthentication, recovery and deep-link return on each supported platform.
**Acceptance criteria:**
- [ ] Unauthorized owner data is never rendered.
- [ ] Sign-in failure is actionable and does not imply success.

## REC-001 — Restore Vishnu

**Purpose:** Restore encrypted owner data and trusted access
**Owner question:** How do I restore Vishnu on a replacement device?
**Required / exists / reachable / connected:** Yes / Portable recovery UI exists on Android/iOS and PWA access choices; complete restore parity is not established. / Yes / Partial
**Navigation:** Signed-out access → Restore Vishnu or platform recovery action.
**Content:** Package selection/import, validation, reauthentication, progress, result.
**Actions:** Select package, authenticate, restore, retry/cancel.
**Data:** Recovery package metadata and restore result without exposing key material.
**Backend:** PortableRecoveryActivity / PortableRecoveryView; PWA recovery APIs.
**Security:** Recovery authentication and encrypted package handling.
**Platform status:** desktop: not verified., pwa: partial, android: partial, ios: partial
**States:** No package, invalid package, decrypt failure, interrupted, restored.
**Responsive/visual direction:** Step-by-step restore with explicit data/device distinction. Show what is restored and what requires re-enrollment.
**Accessibility:** Accessible file chooser labels, progress announcement and confirmation.
**Test/evidence:** Recovery unit/integration coverage exists; cross-platform restore not verified. Evidence: Android PortableRecoveryActivity; iOS PortableRecoveryView; first-run access panel.
**Status:** PARTIAL
**Required next work:** Run isolated restore and interrupted restore on desktop/web and native targets; verify revocation and persistence.
**Acceptance criteria:**
- [ ] Invalid package fails safely.
- [ ] Successful restore reports restored data and next enrollment step.

## HOME-001 — Home

**Purpose:** Provide a calm starting point for conversation and attention
**Owner question:** What can I do next, and does Vishnu need my attention?
**Required / exists / reachable / connected:** Yes / PWA Home and desktop Home exist; native companions show connection/control form rather than equivalent Home. / Yes / Partial
**Navigation:** Launch after authentication; primary Home navigation.
**Content:** Presence state, composer, voice/attachment entry, recent work, pending attention.
**Actions:** Start/continue chat, voice, attach file, select context, open recent item.
**Data:** Runtime/presence, recent projects/conversations and pending attention.
**Backend:** PWA conversation/status APIs and desktop runtime/event bus.
**Security:** Owner session; approval summary must link to approval authority.
**Platform status:** desktop: partial, pwa: partial, android: N/A companion, ios: N/A companion.
**States:** Idle, loading, no recent work, offline, provider degraded, approval needed.
**Responsive/visual direction:** Vishnu identity and status, primary message composer, immediate attention, optional recent continuation. Reflow cards/composer; avoid dashboard density; safe-area composer on mobile.
**Accessibility:** Focus order across shortcuts/composer; live state announcements; 44px targets.
**Test/evidence:** PWA responsive workflow + desktop unit tests; authenticated live screenshot not captured here. Evidence: pwa/index.html Home markup and openModule; ui/main_window.py _home_page.
**Status:** PARTIAL
**Required next work:** Verify authenticated UI, live API behavior, all home actions, error and offline visuals.
**Acceptance criteria:**
- [ ] Text conversation entry is primary and keyboard-operable.
- [ ] Status never claims action success before runtime confirmation.

## CHAT-001 — Conversation

**Purpose:** Exchange messages and review governed actions/results
**Owner question:** Can I talk to Vishnu and understand what it is doing?
**Required / exists / reachable / connected:** Yes / PWA and desktop conversation implementations; native companions hand off to Safari/web session. / Yes / Partial
**Navigation:** Home composer or conversation navigation.
**Content:** Messages, streaming state, citations/attachments where supported, tool action, approval/result.
**Actions:** Send, stop/retry, copy/share where present, attach, voice, approve/deny.
**Data:** Conversation events, status, source references and action results.
**Backend:** /iphone conversation API and desktop runtime; approvals/tool execution paths.
**Security:** Owner session; action-specific approval; output must distinguish pending/failure/success.
**Platform status:** desktop: partial, pwa: partial, android: partial via Safari, ios: partial via Safari.
**States:** Sending, streaming, tool running, approval, error, offline, interrupted, resumed.
**Responsive/visual direction:** Readable transcript, unobscured composer, clear tool/approval cards and response provenance. Transcript scroll, composer safe areas and long content; mobile keyboard qualified in workflow.
**Accessibility:** Message semantics, announcements, keyboard send/stop, accessible composer required.
**Test/evidence:** PWA conversation lifecycle/responsive tests; live provider/tool completion not verified. Evidence: pwa chat experience modules; ui/main_window.py _conversation_page; web-companion app.js.
**Status:** PARTIAL
**Required next work:** Exercise real response and mock/tool approval lifecycle with persistence and failure states.
**Acceptance criteria:**
- [ ] User message reaches runtime.
- [ ] Cancel and retry produce accurate state.
- [ ] Failure remains visible after refresh.

## CHAT-002 — Conversation history and search

**Purpose:** Find and resume previous conversations
**Owner question:** Where is my prior conversation?
**Required / exists / reachable / connected:** Yes / PWA conversation drawer, search and timeline are present; desktop history reachability not exhaustively verified. / Yes / Partial
**Navigation:** Home → history/sidebar → conversations or timeline.
**Content:** Conversation list, date grouping, search, selected item/timeline, rename/delete controls.
**Actions:** Search, select/resume, rename, archive/delete where supported.
**Data:** Conversation metadata and timeline events.
**Backend:** Conversation APIs; PWA drawer/timeline JS.
**Security:** Owner session; destructive actions confirmation.
**Platform status:** desktop: partial, pwa: partial, android: via web session partial., ios: verified
**States:** Loading, empty, no search results, stale/deleted thread, offline.
**Responsive/visual direction:** Searchable list with clear date labels and source timeline. Drawer/sheet on narrow screens; list and reading area on wide screens.
**Accessibility:** Search label, selected item announcement, keyboard navigation.
**Test/evidence:** PWA interaction tests exist; all history mutations not verified. Evidence: pwa/index.html conversation/timeline drawer; chat-experience.js.
**Status:** PARTIAL
**Required next work:** Verify history queries and every visible action against persistence and reload.
**Acceptance criteria:**
- [ ] Selecting a conversation restores the correct thread.
- [ ] Delete/rename results persist after reload.

## MEM-001 — Memory

**Purpose:** Inspect, review and control personal memories
**Owner question:** What does Vishnu remember about me?
**Required / exists / reachable / connected:** Yes / PWA Memory with ambient suggestions/tree/graph; desktop Memory panel. / Partial / Partial
**Navigation:** Home feature card / More / Settings shortcut → Memory.
**Content:** Saved memories, pending suggestions, tree/graph views, provenance, review/settings controls.
**Actions:** Search/filter, approve/dismiss, exclude source, export/settings.
**Data:** Memory records, source, timestamps and privacy settings.
**Backend:** Memory APIs and MemoryStore; distinct from Knowledge.
**Security:** Owner authorization; review-before-save and deletion confirmation where applicable.
**Platform status:** desktop: partial, pwa: partial, android: N/A, ios: N/A.
**States:** Loading, empty, suggestions pending, populated, error, offline.
**Responsive/visual direction:** Overview with ambient review queue and switchable tree/graph detail. Graph scroll region; tree/card views; mobile one-column.
**Accessibility:** Readable graph alternative, review button labels, status announcements.
**Test/evidence:** Memory UI tests and API coverage exist; complete owner workflow not verified. Evidence: pwa/memory-experiences.js; ui/memory_panel.py; MemoryStore APIs.
**Status:** PARTIAL
**Required next work:** Verify edit/delete/export/review persistence, source provenance and privacy toggles.
**Acceptance criteria:**
- [ ] Memory is clearly distinguished from Knowledge.
- [ ] Review and dismiss actions update canonical memory state.

## KNW-001 — Knowledge and files

**Purpose:** Add, find and manage indexed sources/documents
**Owner question:** What documents can Vishnu use, and where did an answer come from?
**Required / exists / reachable / connected:** Yes / PWA Knowledge page supports upload/search/export/delete; desktop surface and mobile web path. / Yes / Partial
**Navigation:** Home shortcut / More → Knowledge; file attachment can add to Knowledge.
**Content:** Recent sources, indexed status, supported file picker, search/filter, detail/citation.
**Actions:** Upload, open, search, export, delete, connect source.
**Data:** Document metadata, processing state, provenance and citations.
**Backend:** /knowledge APIs and KnowledgeStore; parser/index pipeline.
**Security:** Owner authorization; deletion confirmation; content upload limits.
**Platform status:** desktop: partial, pwa: partial, android: partial via web, ios: partial via web.
**States:** Loading, empty, indexing, populated, unsupported file, permission, offline.
**Responsive/visual direction:** Source list, indexing status, upload/search and source detail with provenance. Responsive cards/list; filename wraps; detail may be drawer/modal.
**Accessibility:** File picker label, progress announcements, citation semantics.
**Test/evidence:** Knowledge UI/API tests exist; real-format end-to-end ingestion not verified in this campaign. Evidence: pwa/index.html loadKnowledge/uploadKnowledge; pwa/knowledge-notes.js.
**Status:** PARTIAL
**Required next work:** Execute supported-format ingestion, citation retrieval, delete/index removal and failure paths.
**Acceptance criteria:**
- [ ] Uploaded content persists and is searchable after reload.
- [ ] Unsupported format reports a clear reason.

## ACT-001 — Activities

**Purpose:** Review recent work and product events
**Owner question:** What has Vishnu done recently?
**Required / exists / reachable / connected:** Yes / PWA Activities screen with search/range/source navigation. / Partial / Partial
**Navigation:** More/app drawer → Activities; activity-source links deep into feature.
**Content:** Time-ordered activity, filters, status and source links.
**Actions:** Search, filter, open source, inspect event.
**Data:** Safe activity metadata and timestamps; no secrets.
**Backend:** Activities API/event store.
**Security:** Owner authorization; sensitive payload redaction.
**Platform status:** desktop: partial, pwa: partial, android: verified, ios: verified
**States:** Loading, empty, populated, source deleted, offline.
**Responsive/visual direction:** Chronological list with filters and source-context panel. Filter controls wrap; timeline scroll.
**Accessibility:** Status conveyed in text/icons; keyboard filter navigation.
**Test/evidence:** test_work_attention_center_ui and activity API tests; runtime visual flow not verified. Evidence: pwa/reference-pages.js bindActivities.
**Status:** PARTIAL
**Required next work:** Confirm event sources and source deep-links resolve and redact sensitive fields.
**Acceptance criteria:**
- [ ] Every activity link opens its originating record or explains it is unavailable.

## WRK-001 — Workflows and active work

**Purpose:** Inspect and control governed long-running work
**Owner question:** What is running, waiting, complete, or failed?
**Required / exists / reachable / connected:** Yes / PWA Workflows/Work attention; agent workforce pages; native capability/work UI is internal-testing oriented. / Yes / Partial
**Navigation:** More → Workflows / work attention; project detail and owner controls.
**Content:** Runs, queued/running/approval/failure status, progress, result, cancel/resume.
**Actions:** Open, approve, cancel, retry/resume where service supports.
**Data:** Durable work state, checkpoints, action/event summaries.
**Backend:** Workflow and agent work APIs.
**Security:** Owner identity and per-action approval; cancellation authority.
**Platform status:** desktop: partial, pwa: partial, android: partial, ios: partial.
**States:** Queued, running, waiting approval, completed, failed, offline.
**Responsive/visual direction:** Queue summary and readable detail with progress, approvals and result. Progress/detail sections; confirmation for cancellation.
**Accessibility:** Status updates announced; cancel confirmation keyboard accessible.
**Test/evidence:** Work attention / project autonomy tests; full restart recovery UI not verified. Evidence: pwa/work-attention-center.js; pwa/agents-workforce.js; workorder-detail.js.
**Status:** PARTIAL
**Required next work:** Validate start→approval→execution→completion and cancel/restart durability from UI.
**Acceptance criteria:**
- [ ] UI status matches durable backend state after refresh.

## PRJ-001 — Projects

**Purpose:** Group work, context and files around a project
**Owner question:** How do I continue work on a project?
**Required / exists / reachable / connected:** Yes / PWA project workspace exists; desktop has Products panel, not proven equivalent. / Partial / Partial
**Navigation:** Home recent projects → See all / project card; project deep link.
**Content:** Project list/detail tabs for overview, plan, files, chat, live/activities.
**Actions:** Create/edit/pause/resume, add tasks/files/discussion, ask Vishnu.
**Data:** Project/task/milestone/file metadata and activity.
**Backend:** Projects workspace APIs and persistence.
**Security:** Owner authorization; approvals for action-bearing work.
**Platform status:** desktop: partial, pwa: partial, android: web-mediated partial., ios: verified
**States:** Empty, populated, loading, saving, failed action, offline.
**Responsive/visual direction:** Overview with project purpose, next work, plan, files, chat and activity tabs. Detail tabs adapt to cards/menu on mobile; avoid wide tables.
**Accessibility:** Tabs and project actions keyboard/semantics; progress announced.
**Test/evidence:** Project UI contract/browser tests exist; all action/persistence paths not verified. Evidence: pwa/projects-workspace.js and projects-workspace-views.js.
**Status:** PARTIAL
**Required next work:** Exercise create/edit/task/file/work persistence with auth and failure handling.
**Acceptance criteria:**
- [ ] New project appears after reload.
- [ ] Project-specific context remains scoped.

## APP-001 — Apps & Tools

**Purpose:** Review connected services and available tools
**Owner question:** What can Vishnu access or act through?
**Required / exists / reachable / connected:** Yes / PWA tools manager and settings links; native has capability manager/Forge internal test controls. / Yes / Partial
**Navigation:** Sidebar/More → Apps & Tools; settings shortcut.
**Content:** Connected/available tools, status, scopes/permissions, credentials state, activity.
**Actions:** Inspect, connect/disconnect/reconnect, open capability details.
**Data:** Integration metadata and secret-present state only.
**Backend:** Tools API and ToolRegistry.
**Security:** Owner auth; capability policy and approval; secret vault.
**Platform status:** desktop: partial, pwa: partial, android: partial, ios: partial.
**States:** Loading, none connected, connected, auth required, unavailable, revoked.
**Responsive/visual direction:** Connected services first; permissions and risk in detail; clear connection status. Search/filter and detail view; no secret values; mobile cards.
**Accessibility:** Clear read/write badges and screen-reader labels.
**Test/evidence:** tool/capability tests exist; external live integrations not verified. Evidence: pwa openModule tools → loadTools; NativeCapabilitiesView; ui/capability_manager.py.
**Status:** PARTIAL
**Required next work:** Verify each listed tool registration, connection state and revoke mutation.
**Acceptance criteria:**
- [ ] Unavailable integration is never represented as connected.

## CAP-001 — Capability management

**Purpose:** Import, govern and revoke OpenAPI/MCP capabilities
**Owner question:** Which APIs or MCP tools can act on my behalf?
**Required / exists / reachable / connected:** Yes / PWA tools and native capability surfaces exist; provider/account sign-in is disabled in iOS internal-testing build. / Yes / Partial
**Navigation:** Apps & Tools → capabilities/import; native Manage Universal Capabilities.
**Content:** Import/spec validation, operation list, credential status, scopes, approvals, audit.
**Actions:** Import, inspect, configure credential, test, approve/revoke.
**Data:** Capability ID, operations, source and state; never secret value.
**Backend:** OpenAPI/MCP owner APIs and ToolRegistry.
**Security:** Owner-only; write operations governed; network restrictions and secret vault.
**Platform status:** desktop: partial, pwa: partial, android: partial, ios: blocked for cloud control by build configuration.
**States:** Invalid spec, collision, credential required, approval, revoked, unavailable.
**Responsive/visual direction:** Guided import; review operations and permissions before enabling. Wizard steps and operation review; destructive revoke confirmation.
**Accessibility:** Form labels, schema errors, risk/read-write indication accessible.
**Test/evidence:** Capability security/UI tests exist; live provider and native cloud path not verified. Evidence: pwa loadTools; ui/capability_manager.py; Android ForgeV3Activity; iOS NativeCapabilities.swift.
**Status:** PARTIAL
**Required next work:** Prove import→credential→approval→fixture execution→audit→revoke. Record iOS internal-build restriction.
**Acceptance criteria:**
- [ ] No credential is re-rendered after save.
- [ ] Revocation prevents subsequent execution.

## DEV-001 — Trusted devices

**Purpose:** Inspect, enroll and revoke devices
**Owner question:** Which devices are trusted, and how can I stop one?
**Required / exists / reachable / connected:** Yes / PWA trusted devices management; native companion connects/enrolls itself; full cross-platform owner management parity not verified. / Partial / Partial
**Navigation:** More / Apps & Tools / Settings → Devices; pairing action.
**Content:** Device identity, platform, trust, online/last-seen, scopes, pending enrollment.
**Actions:** Enroll, approve/deny, inspect, revoke/mark lost if available.
**Data:** Device metadata, trust, requested scopes and audit status.
**Backend:** Device owner APIs and DeviceRegistry.
**Security:** Owner authorization; device identity distinct from owner; revocation auditable.
**Platform status:** desktop: partial, pwa: partial, android: partial, ios: partial.
**States:** Empty, pending approval, online, offline, revoked, API error.
**Responsive/visual direction:** Device list with current-device marker and detail/permissions/revoke. Cards on mobile; table/detail on desktop; confirm revoke.
**Accessibility:** Offline/trust status in text; destructive action confirmation.
**Test/evidence:** Device tests exist; owner enrollment/revoke UI execution not verified. Evidence: pwa loadDevices; native ConnectActivity / ConnectOnboardingView.
**Status:** PARTIAL
**Required next work:** Run enrollment approval and revoke in isolated test environment, then verify device can no longer act.
**Acceptance criteria:**
- [ ] Revoked device is not presented active after refresh.

## DAT-001 — Data & Storage

**Purpose:** Understand and control data location/synchronization
**Owner question:** Where does my data live and what syncs?
**Required / exists / reachable / connected:** Yes / PWA Data & Storage settings page exists. / Reachable in PWA; native parity is not verified. / PWA overview and policy update connect to the canonical Data Plane owner API.
**Navigation:** PWA Settings → Data & Storage. Companion local-data screens remain platform-specific.
**Content:** Current location, policy choice, sync status, remote availability, conflict/recovery.
**Actions:** Inspect provider and aggregate status; set default policy for newly governed data. Existing object policies and data movement are not changed here.
**Data:** Policy, local/remote state and sync health.
**Backend:** `UnifiedDataPlane` through `data_plane.runtime.get_data_plane`; `GET /iphone/api/data-plane/overview`, `PUT /iphone/api/data-plane/settings`.
**Security:** Owner authorization; explicit confirmation before data movement; no silent sync.
**Platform status:** desktop: partial, pwa: partial, android: partial, ios: partial.
**States:** Local-only, syncing, offline queue, conflict, provider unavailable, error.
**Responsive/visual direction:** Single Data & Storage area with policy, location, sync status and export/recovery links. Plain language for policy; current location/status visible before mutation.
**Accessibility:** Policy choices explained; status announced; touch-safe controls.
**Test/evidence:** Owner API tests verify authorization, summary redaction and persisted policy update; data-plane readiness tests pass. PWA visual/E2E and native parity are not verified. Evidence: `server/data_plane_owner_api.py`, `server/cloud_app.py`, `pwa/index.html`, `tests/test_data_plane_owner_api.py`.
**Status:** PARTIAL
**Required next work:** Capture signed-in PWA desktop/mobile evidence; verify `device:admin` through the live owner session; decide native policy-control parity and qualify any object-level migration flows separately.
**Acceptance criteria:**
- [ ] UI never promises remote availability unless confirmed by data plane.

## MOD-001 — Models & AI providers

**Purpose:** Choose active model/provider and understand data routing
**Owner question:** Which model is answering, and where does my request go?
**Required / exists / reachable / connected:** Yes / PWA Settings renders AI/provider configuration; provider credential and live validity pathways require verification. / Partial / Partial
**Navigation:** Settings → AI & Models / owner controls model shortcut.
**Content:** Active provider/model, modality, local/cloud label, credential status, fallback.
**Actions:** Select model/provider, configure/validate credential, retry.
**Data:** Model metadata and non-secret credential presence.
**Backend:** Model routing and provider APIs.
**Security:** Owner auth; secrets via vault; disclose remote data routing.
**Platform status:** desktop: partial, pwa: partial, android: N/A, ios: partial via companion/cloud description.
**States:** No provider, invalid credential, unavailable, fallback, offline.
**Responsive/visual direction:** Current model summary with provider, data routing and configure/test controls. Simple default first; advanced model details progressive.
**Accessibility:** Provider and local/cloud labels must be textual, not color-only.
**Test/evidence:** Provider/unit tests exist; real-provider roundtrip not verified. Evidence: pwa/index.html renderSettings(models); owner-controls.js; server model APIs.
**Status:** PARTIAL
**Required next work:** Verify settings persist after reload and actual model routing reflects selected provider.
**Acceptance criteria:**
- [ ] Selection persists and actual runtime reports selected model.

## VOC-001 — Voice

**Purpose:** Configure voice and operate voice sessions
**Owner question:** Can I speak to Vishnu and control microphone/output behavior?
**Required / exists / reachable / connected:** Yes / PWA voice entry/settings; native Sensorium/voice session controls; hardware qualification is external. / Partial / Partial
**Navigation:** Home microphone action; Settings → Voice; native companion voice section.
**Content:** Mic permission, listening/speaking/session state, voice preferences and errors.
**Actions:** Start/stop, interrupt, choose voice/settings, grant permission.
**Data:** Session state and consent/permission; no raw audio retained unless documented.
**Backend:** Voice APIs; Android AudioService; iOS SensoriumAudioFeatures.
**Security:** Explicit platform mic permission and session gate; indicator while active.
**Platform status:** desktop: partial, pwa: partial, android: partial, ios: partial.
**States:** Permission denied, listening, transcribing, responding, speaking, interrupted, offline.
**Responsive/visual direction:** Visible session state with large start/stop and clear permission explanation. Voice state remains visible; one-handed start/stop; background behavior explicit.
**Accessibility:** Announce state and permission; keyboard shortcut alternatives on desktop.
**Test/evidence:** Voice qualification tests exist; physical mic/device behavior not verified. Evidence: pwa micButton/voicePanel; Android SensoriumAudioService; iOS SensoriumAudioFeatures.
**Status:** PARTIAL
**Required next work:** Run supported automated voice path; capture physical device/microphone qualification separately.
**Acceptance criteria:**
- [ ] Stopping voice stops capture and updates state.

## SEC-001 — Security & approvals

**Purpose:** Review identity/device protections and decide sensitive actions
**Owner question:** What is protected, and what is Vishnu asking permission to do?
**Required / exists / reachable / connected:** Yes / PWA Settings security/approvals and in-conversation approval panel; native passkey/consent screens. / Partial / Partial
**Navigation:** Settings → Security/Approvals; conversation approval card.
**Content:** Passkeys/session state, approvals pending/history, device links, emergency stop if enabled.
**Actions:** Approve once, deny/cancel, manage auth/device permission, revoke.
**Data:** Risk, target, effects, duration, audit event; redact secrets.
**Backend:** Security owner APIs and per-capability approval services.
**Security:** Owner/session enforcement, exact scope, explicit confirmation, audit.
**Platform status:** desktop: partial, pwa: partial, android: partial, ios: partial.
**States:** Pending, expired, denied, allowed, session expired, unavailable.
**Responsive/visual direction:** Central security sections plus context approval card with risk and consequence. Approval prompt names action, target, impact and one-time vs persistent scope.
**Accessibility:** Dialog focus trap/Escape; announce urgency and risk; large touch actions.
**Test/evidence:** Security/capability tests exist; every approval presentation not UI-tested. Evidence: pwa approval panel and settings/approvals; native passkey/sensor consent.
**Status:** PARTIAL
**Required next work:** Exercise approve/deny/expiry/revocation and confirm exact action scope is enforced.
**Acceptance criteria:**
- [ ] Approval cannot be confused with a durable grant.
- [ ] Secrets never appear in approval history.

## PRI-001 — Privacy & data controls

**Purpose:** Manage memory, conversation, telemetry and account data controls
**Owner question:** What is saved or shared, and how can I change it?
**Required / exists / reachable / connected:** Yes / PWA settings includes privacy page with explicit disabled/unavailable options. / Partial / Partial
**Navigation:** Settings → Privacy & Data.
**Content:** Memory toggle, review controls, retention, export, connected services, account delete.
**Actions:** Change, export, clear history, delete account with reauthentication.
**Data:** Persisted privacy settings and data export state.
**Backend:** Privacy APIs and owner profile storage.
**Security:** Owner auth/fresh verification for destructive actions; fail closed for unsupported options.
**Platform status:** desktop: partial, pwa: partial, android: partial, ios: partial.
**States:** Saved, unavailable/disabled, saving, error, destructive confirmation.
**Responsive/visual direction:** Privacy summary and grouped memory/history/data controls. Disabled unavailable features have clear reason; no fake toggle.
**Accessibility:** Switch labels/state and destructive warnings are accessible.
**Test/evidence:** Privacy page source says some controls disabled and certain services absent; complete mutations not verified. Evidence: pwa/index.html privacy settings renderer.
**Status:** PARTIAL
**Required next work:** Resolve or explicitly label each disabled control and verify delete/export persistence.
**Acceptance criteria:**
- [ ] Disabled controls state why and do not imply a setting changed.

## NOT-001 — Notifications

**Purpose:** Control notification preferences and understand alerts
**Owner question:** Which events can interrupt me?
**Required / exists / reachable / connected:** Yes / PWA settings and native registration/notification paths; delivery service stage may be incomplete. / Partial / Partial
**Navigation:** Settings → Notifications; OS permission prompts.
**Content:** Categories, quiet hours, OS permission, delivery/registration state.
**Actions:** Toggle preferences, request permission, open notification target.
**Data:** Preference state and provider registration status.
**Backend:** Preference API; Android/iOS native notifications.
**Security:** Owner authorization and platform OS permission; no success claim before provider delivery.
**Platform status:** desktop: partial, pwa: partial, android: partial, ios: partial.
**States:** Denied permission, not configured, enabled, quiet, provider unavailable.
**Responsive/visual direction:** Category controls with OS permission and delivery-health explanation. Differentiate preference from OS/provider delivery state.
**Accessibility:** Native announcement and notification settings deep link behavior required.
**Test/evidence:** Notification API tests exist; real APNs/provider delivery not verified. Evidence: PWA renderSettings(notifications); iOS APNs registration notes; Android manifest.
**Status:** PARTIAL
**Required next work:** Verify preference persistence and actual local/provider delivery or clearly mark unavailable.
**Acceptance criteria:**
- [ ] Changing preference persists and state is accurate after restart.

## SYS-001 — Dashboard

**Purpose:** Review aggregate system health and active components
**Owner question:** Is Vishnu healthy right now?
**Required / exists / reachable / connected:** Yes / PWA Dashboard and desktop Dashboard exist; tests partly cover responsive. / Yes / Partial
**Navigation:** Main navigation → Dashboard; Home shortcut.
**Content:** Health summaries, active work, provider/device/sync status and alerts.
**Actions:** Inspect component, refresh, navigate to owning settings page.
**Data:** Aggregated runtime health and timestamps.
**Backend:** Dashboard APIs; runtime health owner.
**Security:** Owner-only; status must be sourced and timestamped.
**Platform status:** desktop: partial, pwa: partial, android: verified, ios: verified
**States:** Loading, healthy, degraded, unavailable, stale.
**Responsive/visual direction:** Health cards with degraded reasons and direct remediation routes. Operational density separate from calm Home; responsive grid.
**Accessibility:** Status text and timestamps; keyboard access to detail links.
**Test/evidence:** Dashboard APIs/tests exist; live page visual execution not performed. Evidence: pwa loadDashboard; ui/main_window Dashboard.
**Status:** PARTIAL
**Required next work:** Verify every dashboard claim against source service and stale/error state.
**Acceptance criteria:**
- [ ] Stale data is identified with last-updated time.

## SYS-002 — System status

**Purpose:** Inspect runtime/model/tool service availability
**Owner question:** Why is a system feature unavailable?
**Required / exists / reachable / connected:** Yes / PWA System Status module exists; desktop Dashboard summary is not equivalent. / Yes / Partial
**Navigation:** More/owner navigation → System Status.
**Content:** Runtime version, model/tool connectivity, service status, timestamp, safe diagnostics.
**Actions:** Refresh, open configured service settings, copy safe diagnostics if implemented.
**Data:** Health metadata and non-sensitive diagnostics.
**Backend:** System status API.
**Security:** Owner-only, redact secrets/host credentials.
**Platform status:** desktop: partial, pwa: partial, android: N/A, ios: N/A.
**States:** Loading, healthy, degraded, unavailable, unauthorized.
**Responsive/visual direction:** System summary with last check and actionable linked remediation. Compact grouped status; avoid raw logs in normal view.
**Accessibility:** Status uses text+icon; keyboard refresh.
**Test/evidence:** System tests exist; owner route/UI click not verified. Evidence: pwa openModule system → loadSystem.
**Status:** PARTIAL
**Required next work:** Exercise live failure and ensure status matches actual dependency availability.
**Acceptance criteria:**
- [ ] Unavailable components are not shown as healthy.

## SET-001 — Settings

**Purpose:** Reach all owner configuration in a coherent hierarchy
**Owner question:** How do I configure Vishnu?
**Required / exists / reachable / connected:** Yes / PWA settings has subsections; desktop Settings; native companion uses integrated control form. / Partial / Partial
**Navigation:** Primary nav or account menu → Settings.
**Content:** General, AI, voice, memory, data, apps, devices, notifications, privacy, security, advanced.
**Actions:** Select section and persist supported settings.
**Data:** Preference values, capability availability, save status.
**Backend:** PWA renderSettings; desktop settings panel.
**Security:** Owner-only; setting-specific authorization.
**Platform status:** desktop: partial, pwa: partial, android: partial, ios: partial.
**States:** Loading, saved, unavailable, error, session expired.
**Responsive/visual direction:** Searchable/sectioned settings, grouped by intent with explicit unavailable states. Desktop subnav; mobile section selector; no settings dump.
**Accessibility:** Heading hierarchy, current section, keyboard selection and status announcements.
**Test/evidence:** Responsive settings workflow tests; full setting persistence not verified. Evidence: pwa/index.html renderSettings; ui/settings_panel.py; native pairedHome Form.
**Status:** PARTIAL
**Required next work:** Derive final section list from real working controls; test save/reload and authorization.
**Acceptance criteria:**
- [ ] No inactive setting appears interactive.

## OWN-001 — Owner profile and account

**Purpose:** Inspect owner identity and account-level controls
**Owner question:** Which owner/account is active?
**Required / exists / reachable / connected:** Yes / PWA owner menu/controls and native owner sign-in state; full profile edit flow not verified. / Yes / Partial
**Navigation:** Account menu → owner/profile.
**Content:** Display name, identity status, sign-out, account links supported by API.
**Actions:** Edit supported fields, sign out, open security.
**Data:** Owner profile metadata and session state.
**Backend:** Owner APIs and profile preferences.
**Security:** Owner-only; reauthentication for sensitive identity changes.
**Platform status:** desktop: partial, pwa: partial, android: partial, ios: partial.
**States:** Loading, profile missing, session expired, save error.
**Responsive/visual direction:** Compact owner menu leading to profile, settings and sign-out. Account menu on narrow screens; profile separate from security controls.
**Accessibility:** Accessible account menu semantics and keyboard dismissal.
**Test/evidence:** Owner UI tests partly exist; all profile mutations not verified. Evidence: pwa owner-controls.js; native connection home.
**Status:** PARTIAL
**Required next work:** Verify each account action against owner API and persist edits.
**Acceptance criteria:**
- [ ] Sign-out clears local session and routes to access gate.

## ADV-001 — Advanced diagnostics

**Purpose:** Expose owner-useful diagnostics without burdening daily screens
**Owner question:** How can I troubleshoot or inspect qualification details?
**Required / exists / reachable / connected:** Yes / PWA advanced settings/evidence and qualification consoles; primarily owner/operator-gated. / Partial / Partial
**Navigation:** Settings → Advanced or qualification route.
**Content:** Safe diagnostic status, evidence links, version/schema, support bundle if available.
**Actions:** Run supported checks, export evidence, copy safe IDs.
**Data:** Qualification metadata and redacted diagnostic output.
**Backend:** Qualification/readiness/recovery APIs.
**Security:** Owner/operator authorization; redact secrets and personal content.
**Platform status:** desktop: partial, pwa: partial, android: N/A, ios: N/A.
**States:** Not configured, running, passed/failed, unauthorized.
**Responsive/visual direction:** Advanced section with concise checks and safe export, separated from daily tasks. Progressive disclosure; avoid raw debug output by default.
**Accessibility:** Keyboard focus; output copy labels; do not rely on color.
**Test/evidence:** Qualification tests are backend-heavy; actual diagnostics UI not clicked. Evidence: pwa advanced settings; qualification owner routes.
**Status:** PARTIAL
**Required next work:** Verify gated routes, evidence links and redaction; split developer-only internals from owner diagnostics.
**Acceptance criteria:**
- [ ] Sensitive values are redacted from displayed/exported diagnostics.

## SEN-001 — Sensorium permissions

**Purpose:** Control temporary sensor access on a trusted companion
**Owner question:** What sensors can a device use right now?
**Required / exists / reachable / connected:** Yes / Android/iOS consent/privacy and sensor session UI; intended as device-specific controls, not full owner PWA page. / Yes / Partial
**Navigation:** Native companion → Sensorium section or consent prompt.
**Content:** Sensor list, session scope/duration, privacy status, permission result.
**Actions:** Allow once/session, deny, stop session, inspect privacy status.
**Data:** Session and OS permission state; no sensor payload unless explicitly surfaced.
**Backend:** Android Sensorium activities/services; iOS Sensorium views/session bridge.
**Security:** Explicit per-session consent; OS permission and foreground restrictions.
**Platform status:** desktop: N/A, pwa: N/A, android: partial, ios: partial.
**States:** Permission request, denied, active, expired, stopped, unavailable.
**Responsive/visual direction:** Sensor permission overview with temporary session controls and clear data-use statement. Native per-platform patterns; visible active sensor indicator.
**Accessibility:** OS accessibility semantics; announce active session and stop action.
**Test/evidence:** Sensorium unit/native tests; physical sensors and hardware not verified. Evidence: Android SensoriumConsentActivity / PrivacyActivity; iOS SensoriumPrivacyView.
**Status:** PARTIAL
**Required next work:** Verify consent→session→stop/revoke on real device; do not infer physical support from simulator.
**Acceptance criteria:**
- [ ] Sensor session ends on stop/background/expiry as architecture specifies.

## UPD-001 — About and updates

**Purpose:** Check version, update status and release identity
**Owner question:** Which build am I using, and is an update available?
**Required / exists / reachable / connected:** Yes / PWA About & Updates page exists. / Reachable in PWA Settings. / Connected to authenticated safe release-identity metadata; signed update check/install is not connected.
**Navigation:** Settings → About & Updates.
**Content:** Product name, version/source, optional build revision, release channel and installation-managed update status.
**Actions:** Retry metadata load. No check/install control appears until a signed updater is connected.
**Data:** Safe build identity metadata; no secrets or filesystem paths. Signed update metadata is not currently returned.
**Backend:** `GET /iphone/api/about` in `server/about_api.py`; installed package/repository metadata and explicit build environment values.
**Security:** Active trusted device and `device:read`; no production update is performed or represented as available.
**Platform status:** desktop: not verified, pwa: partial, android: partial, ios: partial.
**States:** Current, available, downloading, verification failure, restart.
**Responsive/visual direction:** About section with version, build, notices and update status; install control only when updater is active. Clear version and verified update state; no false-ready status.
**Accessibility:** Button and progress announcements; destructive/restart confirmation.
**Test/evidence:** About API tests cover metadata and native scope. PWA visual/API execution and packaged build identity are not verified. Evidence: `server/about_api.py`, `pwa/index.html`, `tests/test_about_api.py`, `updates/`, `packaging/`.
**Status:** PARTIAL
**Required next work:** Verify PWA visual/accessibility states and packaged release identity; wire update actions only where signed update verification and recovery are fully connected.
**Acceptance criteria:**
- [ ] No update control shown unless actual update flow can verify and recover.

## TOD-001 — Today

**Purpose:** See a date-scoped agenda of tasks, commitments and plans.
**Owner question:** What needs my attention today?
**Required / exists / reachable / connected:** Yes / PWA Today/Visualize destination is source-backed; complete interactive path not re-executed. / Yes / Partial
**Navigation:** Home → Today entry point/sidebar → Today screen.
**Content:** Date selector, tasks, meetings/commitments, plans, timeline and selected item details.
**Actions:** Change date, jump to timeline, create item, open source, start chat.
**Data:** Everyday timeline and project task metadata.
**Backend:** pwa/reference-pages.js loadToday uses /everyday/timeline and /projects/timeline; create/edit dialogs in pwa/index.html.
**Security:** Owner authorization; sensitive payload redaction.
**Platform status:** desktop: Not verified, pwa: Partial, android: N/A, ios: N/A
**States:** Loading, no items, populated, create/edit, API error, offline.
**Responsive/visual direction:** Date-first timeline with clear separation of task/commitment/plan and source context.
**Accessibility:** Date controls and timeline controls have labels; dialog focus/error semantics require runtime check.
**Test/evidence:** test_work_attention_center_ui and activity API tests; runtime visual flow not verified. Evidence: pwa/reference-pages.js loadToday/bindToday; Today dialog IDs in pwa/index.html.
**Status:** PARTIAL
**Required next work:** Execute day changes, create/edit persistence, source jumps and error states.

**Acceptance criteria:**
- [ ] Selected date controls returned data.
- [ ] Created item persists after reload.

## VIZ-001 — Visualize

**Purpose:** Explore generated architecture, workflow, lifecycle, sequence and dataflow visualizations.
**Owner question:** How does a system or project flow fit together?
**Required / exists / reachable / connected:** Yes / PWA Today/Visualize destination is source-backed; complete interactive path not re-executed. / Yes / Partial
**Navigation:** Sidebar → Visualize (entry injected by pwa/visualize-workspace.js).
**Content:** Visualization gallery, type selector, layer/view filters, detail canvas and export/share controls where supported.
**Actions:** Open gallery item, choose type/view, filter layers, inspect nodes, navigate to source module.
**Data:** Visualization payloads, node/edge metadata and source references.
**Backend:** /iphone/api/visualizations and visualization workspace service.
**Security:** Owner-only; status must be sourced and timestamped.
**Platform status:** desktop: Not verified, pwa: Partial, android: N/A, ios: N/A
**States:** Loading, empty gallery, populated graph, API error, invalid graph, offline.
**Responsive/visual direction:** Scrollable graph canvas with textual summary and accessible alternative; avoid shrinking labels.
**Accessibility:** Graph must have text alternative and keyboard-accessible detail navigation.
**Test/evidence:** Dashboard APIs/tests exist; live page visual execution not performed. Evidence: pwa/visualize-workspace.js ensureNavEntry/openWorkspace; visualize APIs.
**Status:** PARTIAL
**Required next work:** Run gallery and API-backed visualization through source navigation; screenshot wide and narrow canvas.

**Acceptance criteria:**
- [ ] Choosing an item renders its correct visualization.
- [ ] Graph is navigable or has an equivalent text outline.

## LAB-001 — Labs & Workspaces

**Purpose:** Give the owner one place to reach existing project workspaces, agent work, product work, visualization and advanced capability-development tools. This is a navigation page; it does not duplicate those systems or invent new lab behavior.
**Owner question:** Where can I continue workspace work, and which advanced development surfaces are available?
**Required / exists / reachable / connected:** Yes / Implemented in the main PWA / Yes through the authenticated sidebar / Partial; each card routes to its existing destination.
**Navigation:** Launch → Home → sidebar → Explore → Labs & workspaces.
**Content:** Workspaces section with Projects, Agents, Products and Visualize. Advanced labs section with Capability Forge and Qualification evidence. Forge is labeled advanced and explains its separate approval boundary.
**Actions:** Open Projects and Visualize in the existing PWA; navigate to Agents, Products, Forge or Forge readiness; open Advanced Settings for qualification evidence.
**Data:** No new data is read, modified or stored by the hub. Destination pages own their own data and state.
**Backend:** Existing project/workflow, agent workforce, product lifecycle, visualization, capability Forge and qualification services.
**Security:** Each destination retains its existing authentication and authorization controls. Forge activation remains separate from approval; the Forge cannot self-approve production activation.
**States:** Hub renders synchronously; destination loading, offline and errors are owned and displayed by each destination. No hub-level API status is implied.
**Responsive behavior:** Uses the existing PWA module layout and card grid. Narrow screens stack through the shared module CSS. Destination screens retain their own responsive behavior.
**Accessibility:** Native buttons and named section headings support keyboard focus. Screen-reader announcements, touch target measurements and contrast checks remain NOT VERIFIED.
**Platform differences:** PWA only. Android and iOS companion apps do not claim this workspace hub. Desktop is NOT VERIFIED.
**Tests:** `tests/test_labs_workspace_hub_contract.py`; PWA mobile browser test includes page rendering, existing destination links and responsive overflow assertions. The browser suite could not run locally because the Playwright Chromium binary is absent.
**Visual direction:** A compact directory rather than a dashboard. Separate everyday workspaces from advanced labs and avoid duplicating project, agent or product interfaces.
**Acceptance criteria:**
- [x] Sidebar entry opens the Labs & Workspaces hub.
- [x] Projects and Visualize actions route to their existing PWA modules.
- [x] Agents and Products actions open their existing routed pages.
- [x] Capability Forge and production readiness actions open existing routes.
- [x] Qualification evidence links to Advanced Settings.
- [x] Copy explains the separate Forge approval boundary.
- [ ] Run browser UI qualification and verify links/auth/failure states on supported browsers.
