# Vishnu visual page catalog

**Audited baseline:** `4ec735de327f2bab6dccb774e2a9c28ef4fc44af`

CI screenshots were generated and four web-companion views were manually inspected. The artifact is available from [PR #248 responsive run 38940576760](https://github.com/vaishnavsawant1994-stack/vishnu/actions/runs/38940576760) under `personal-ai-design-system-web-companion`. These screenshots are companion subviews only, not full-page evidence for all Vishnu screen implementations. The catalog links available evidence without copying binary screenshots into the repository.

## ONB-001 — Connect / first run

- Purpose: Create or join a Vishnu runtime
- Platform: desktop: not verified., pwa: partial, android: partial, ios: partial
- Route / navigation: Launch → signed-out state → enroll/connect/restore.
- Status: partial
- Primary actions: Create/connect, scan or enter pairing code, configure name, retry.
- Backend: PWA owner enrollment APIs; Android ConnectActivity; iOS ConnectOnboardingView.
- Visual direction: Short guided steps; clear create/connect/restore choices; no provider jargon.
- Missing work: Prove each platform’s complete creation/join path and persistence; screenshot authenticated and error states.
- Screenshot: `web-companion-control-phone-390.png` from CI artifact run [38940576760](https://github.com/vaishnavsawant1994-stack/vishnu/actions/runs/38940576760); companion subview manually inspected, full canonical page remains NOT VERIFIED.

## AUTH-001 — Sign-in and session recovery

- Purpose: Authenticate the owner and recover expired sessions
- Platform: desktop: not verified., pwa: partial, android: partial, ios: partial
- Route / navigation: Launch → access gate; expired/unauthorized API response → sign-in/re-auth.
- Status: partial
- Primary actions: Authenticate, retry, choose recovery, cancel.
- Backend: PWA identity APIs; Android native OAuth/PKCE exchange; iOS companion owner flow.
- Visual direction: Trust-focused, minimal form; explain passkey/password/recovery choices.
- Missing work: Execute auth, expiry, reauthentication, recovery and deep-link return on each supported platform.
- Screenshot: NOT CAPTURED in this campaign.

## REC-001 — Restore Vishnu

- Purpose: Restore encrypted owner data and trusted access
- Platform: desktop: not verified., pwa: partial, android: partial, ios: partial
- Route / navigation: Signed-out access → Restore Vishnu or platform recovery action.
- Status: partial
- Primary actions: Select package, authenticate, restore, retry/cancel.
- Backend: PortableRecoveryActivity / PortableRecoveryView; PWA recovery APIs.
- Visual direction: Step-by-step restore with explicit data/device distinction.
- Missing work: Run isolated restore and interrupted restore on desktop/web and native targets; verify revocation and persistence.
- Screenshot: NOT CAPTURED in this campaign.

## HOME-001 — Home

- Purpose: Provide a calm starting point for conversation and attention
- Platform: desktop: partial, pwa: partial, android: N/A companion, ios: N/A companion.
- Route / navigation: Launch after authentication; primary Home navigation.
- Status: partial
- Primary actions: Start/continue chat, voice, attach file, select context, open recent item.
- Backend: PWA conversation/status APIs and desktop runtime/event bus.
- Visual direction: Vishnu identity and status, primary message composer, immediate attention, optional recent continuation.
- Missing work: Verify authenticated UI, live API behavior, all home actions, error and offline visuals.
- Screenshot: `web-companion-phone-390.png`, `web-companion-phone-320.png`, `web-companion-desktop-1440.png`, `web-companion-wide-2560.png` from CI artifact run [38940576760](https://github.com/vaishnavsawant1994-stack/vishnu/actions/runs/38940576760); companion subview manually inspected, full canonical page remains NOT VERIFIED.

## CHAT-001 — Conversation

- Purpose: Exchange messages and review governed actions/results
- Platform: desktop: partial, pwa: partial, android: partial via Safari, ios: partial via Safari.
- Route / navigation: Home composer or conversation navigation.
- Status: partial
- Primary actions: Send, stop/retry, copy/share where present, attach, voice, approve/deny.
- Backend: /iphone conversation API and desktop runtime; approvals/tool execution paths.
- Visual direction: Readable transcript, unobscured composer, clear tool/approval cards and response provenance.
- Missing work: Exercise real response and mock/tool approval lifecycle with persistence and failure states.
- Screenshot: NOT CAPTURED in this campaign.

## CHAT-002 — Conversation history and search

- Purpose: Find and resume previous conversations
- Platform: desktop: partial, pwa: partial, android: via web session partial., ios: verified
- Route / navigation: Home → history/sidebar → conversations or timeline.
- Status: partial
- Primary actions: Search, select/resume, rename, archive/delete where supported.
- Backend: Conversation APIs; PWA drawer/timeline JS.
- Visual direction: Searchable list with clear date labels and source timeline.
- Missing work: Verify history queries and every visible action against persistence and reload.
- Screenshot: NOT CAPTURED in this campaign.

## MEM-001 — Memory

- Purpose: Inspect, review and control personal memories
- Platform: desktop: partial, pwa: partial, android: N/A, ios: N/A.
- Route / navigation: Home feature card / More / Settings shortcut → Memory.
- Status: partial
- Primary actions: Search/filter, approve/dismiss, exclude source, export/settings.
- Backend: Memory APIs and MemoryStore; distinct from Knowledge.
- Visual direction: Overview with ambient review queue and switchable tree/graph detail.
- Missing work: Verify edit/delete/export/review persistence, source provenance and privacy toggles.
- Screenshot: `web-companion-memory-phone-390.png` from CI artifact run [38940576760](https://github.com/vaishnavsawant1994-stack/vishnu/actions/runs/38940576760); companion subview manually inspected, full canonical page remains NOT VERIFIED.

## KNW-001 — Knowledge and files

- Purpose: Add, find and manage indexed sources/documents
- Platform: desktop: partial, pwa: partial, android: partial via web, ios: partial via web.
- Route / navigation: Home shortcut / More → Knowledge; file attachment can add to Knowledge.
- Status: partial
- Primary actions: Upload, open, search, export, delete, connect source.
- Backend: /knowledge APIs and KnowledgeStore; parser/index pipeline.
- Visual direction: Source list, indexing status, upload/search and source detail with provenance.
- Missing work: Execute supported-format ingestion, citation retrieval, delete/index removal and failure paths.
- Screenshot: NOT CAPTURED in this campaign.

## ACT-001 — Activities

- Purpose: Review recent work and product events
- Platform: desktop: partial, pwa: partial, android: verified, ios: verified
- Route / navigation: More/app drawer → Activities; activity-source links deep into feature.
- Status: partial
- Primary actions: Search, filter, open source, inspect event.
- Backend: Activities API/event store.
- Visual direction: Chronological list with filters and source-context panel.
- Missing work: Confirm event sources and source deep-links resolve and redact sensitive fields.
- Screenshot: NOT CAPTURED in this campaign.

## WRK-001 — Workflows and active work

- Purpose: Inspect and control governed long-running work
- Platform: desktop: partial, pwa: partial, android: partial, ios: partial.
- Route / navigation: More → Workflows / work attention; project detail and owner controls.
- Status: partial
- Primary actions: Open, approve, cancel, retry/resume where service supports.
- Backend: Workflow and agent work APIs.
- Visual direction: Queue summary and readable detail with progress, approvals and result.
- Missing work: Validate start→approval→execution→completion and cancel/restart durability from UI.
- Screenshot: NOT CAPTURED in this campaign.

## PRJ-001 — Projects

- Purpose: Group work, context and files around a project
- Platform: desktop: partial, pwa: partial, android: web-mediated partial., ios: verified
- Route / navigation: Home recent projects → See all / project card; project deep link.
- Status: partial
- Primary actions: Create/edit/pause/resume, add tasks/files/discussion, ask Vishnu.
- Backend: Projects workspace APIs and persistence.
- Visual direction: Overview with project purpose, next work, plan, files, chat and activity tabs.
- Missing work: Exercise create/edit/task/file/work persistence with auth and failure handling.
- Screenshot: NOT CAPTURED in this campaign.

## APP-001 — Apps & Tools

- Purpose: Review connected services and available tools
- Platform: desktop: partial, pwa: partial, android: partial, ios: partial.
- Route / navigation: Sidebar/More → Apps & Tools; settings shortcut.
- Status: partial
- Primary actions: Inspect, connect/disconnect/reconnect, open capability details.
- Backend: Tools API and ToolRegistry.
- Visual direction: Connected services first; permissions and risk in detail; clear connection status.
- Missing work: Verify each listed tool registration, connection state and revoke mutation.
- Screenshot: NOT CAPTURED in this campaign.

## CAP-001 — Capability management

- Purpose: Import, govern and revoke OpenAPI/MCP capabilities
- Platform: desktop: partial, pwa: partial, android: partial, ios: blocked for cloud control by build configuration.
- Route / navigation: Apps & Tools → capabilities/import; native Manage Universal Capabilities.
- Status: partial
- Primary actions: Import, inspect, configure credential, test, approve/revoke.
- Backend: OpenAPI/MCP owner APIs and ToolRegistry.
- Visual direction: Guided import; review operations and permissions before enabling.
- Missing work: Prove import→credential→approval→fixture execution→audit→revoke. Record iOS internal-build restriction.
- Screenshot: NOT CAPTURED in this campaign.

## DEV-001 — Trusted devices

- Purpose: Inspect, enroll and revoke devices
- Platform: desktop: partial, pwa: partial, android: partial, ios: partial.
- Route / navigation: More / Apps & Tools / Settings → Devices; pairing action.
- Status: partial
- Primary actions: Enroll, approve/deny, inspect, revoke/mark lost if available.
- Backend: Device owner APIs and DeviceRegistry.
- Visual direction: Device list with current-device marker and detail/permissions/revoke.
- Missing work: Run enrollment approval and revoke in isolated test environment, then verify device can no longer act.
- Screenshot: NOT CAPTURED in this campaign.

## DAT-001 — Data & Storage

- Purpose: Understand and control data location/synchronization
- Platform: desktop: partial, pwa: partial, android: partial, ios: partial.
- Route / navigation: PWA Settings → Data & Storage; companion local-data sections are separate.
- Status: partial (PWA connected; other platform parity and visual execution not verified)
- Primary actions: Inspect aggregate storage/provider status; change default policy for newly governed objects.
- Backend: `GET /iphone/api/data-plane/overview`, `PUT /iphone/api/data-plane/settings`; canonical `UnifiedDataPlane`.
- Visual direction: Single Data & Storage area with policy, location, sync status and export/recovery links.
- Missing work: Trace each supported policy from UI mutation through storage/reload/sync on each intended platform.
- Screenshot: NOT CAPTURED in this campaign.

## MOD-001 — Models & AI providers

- Purpose: Choose active model/provider and understand data routing
- Platform: desktop: partial, pwa: partial, android: N/A, ios: partial via companion/cloud description.
- Route / navigation: Settings → AI & Models / owner controls model shortcut.
- Status: partial
- Primary actions: Select model/provider, configure/validate credential, retry.
- Backend: Model routing and provider APIs.
- Visual direction: Current model summary with provider, data routing and configure/test controls.
- Missing work: Verify settings persist after reload and actual model routing reflects selected provider.
- Screenshot: NOT CAPTURED in this campaign.

## VOC-001 — Voice

- Purpose: Configure voice and operate voice sessions
- Platform: desktop: partial, pwa: partial, android: partial, ios: partial.
- Route / navigation: Home microphone action; Settings → Voice; native companion voice section.
- Status: partial
- Primary actions: Start/stop, interrupt, choose voice/settings, grant permission.
- Backend: Voice APIs; Android AudioService; iOS SensoriumAudioFeatures.
- Visual direction: Visible session state with large start/stop and clear permission explanation.
- Missing work: Run supported automated voice path; capture physical device/microphone qualification separately.
- Screenshot: NOT CAPTURED in this campaign.

## SEC-001 — Security & approvals

- Purpose: Review identity/device protections and decide sensitive actions
- Platform: desktop: partial, pwa: partial, android: partial, ios: partial.
- Route / navigation: Settings → Security/Approvals; conversation approval card.
- Status: partial
- Primary actions: Approve once, deny/cancel, manage auth/device permission, revoke.
- Backend: Security owner APIs and per-capability approval services.
- Visual direction: Central security sections plus context approval card with risk and consequence.
- Missing work: Exercise approve/deny/expiry/revocation and confirm exact action scope is enforced.
- Screenshot: `web-companion-control-phone-390.png` from CI artifact run [38940576760](https://github.com/vaishnavsawant1994-stack/vishnu/actions/runs/38940576760); companion subview manually inspected, full canonical page remains NOT VERIFIED.

## PRI-001 — Privacy & data controls

- Purpose: Manage memory, conversation, telemetry and account data controls
- Platform: desktop: partial, pwa: partial, android: partial, ios: partial.
- Route / navigation: Settings → Privacy & Data.
- Status: partial
- Primary actions: Change, export, clear history, delete account with reauthentication.
- Backend: Privacy APIs and owner profile storage.
- Visual direction: Privacy summary and grouped memory/history/data controls.
- Missing work: Resolve or explicitly label each disabled control and verify delete/export persistence.
- Screenshot: NOT CAPTURED in this campaign.

## NOT-001 — Notifications

- Purpose: Control notification preferences and understand alerts
- Platform: desktop: partial, pwa: partial, android: partial, ios: partial.
- Route / navigation: Settings → Notifications; OS permission prompts.
- Status: partial
- Primary actions: Toggle preferences, request permission, open notification target.
- Backend: Preference API; Android/iOS native notifications.
- Visual direction: Category controls with OS permission and delivery-health explanation.
- Missing work: Verify preference persistence and actual local/provider delivery or clearly mark unavailable.
- Screenshot: NOT CAPTURED in this campaign.

## SYS-001 — Dashboard

- Purpose: Review aggregate system health and active components
- Platform: desktop: partial, pwa: partial, android: verified, ios: verified
- Route / navigation: Main navigation → Dashboard; Home shortcut.
- Status: partial
- Primary actions: Inspect component, refresh, navigate to owning settings page.
- Backend: Dashboard APIs; runtime health owner.
- Visual direction: Health cards with degraded reasons and direct remediation routes.
- Missing work: Verify every dashboard claim against source service and stale/error state.
- Screenshot: `web-companion-dashboard-tablet-768.png` from CI artifact run [38940576760](https://github.com/vaishnavsawant1994-stack/vishnu/actions/runs/38940576760); companion subview manually inspected, full canonical page remains NOT VERIFIED.

## SYS-002 — System status

- Purpose: Inspect runtime/model/tool service availability
- Platform: desktop: partial, pwa: partial, android: N/A, ios: N/A.
- Route / navigation: More/owner navigation → System Status.
- Status: partial
- Primary actions: Refresh, open configured service settings, copy safe diagnostics if implemented.
- Backend: System status API.
- Visual direction: System summary with last check and actionable linked remediation.
- Missing work: Exercise live failure and ensure status matches actual dependency availability.
- Screenshot: NOT CAPTURED in this campaign.

## SET-001 — Settings

- Purpose: Reach all owner configuration in a coherent hierarchy
- Platform: desktop: partial, pwa: partial, android: partial, ios: partial.
- Route / navigation: Primary nav or account menu → Settings.
- Status: partial
- Primary actions: Select section and persist supported settings.
- Backend: PWA renderSettings; desktop settings panel.
- Visual direction: Searchable/sectioned settings, grouped by intent with explicit unavailable states.
- Missing work: Derive final section list from real working controls; test save/reload and authorization.
- Screenshot: NOT CAPTURED in this campaign.

## OWN-001 — Owner profile and account

- Purpose: Inspect owner identity and account-level controls
- Platform: desktop: partial, pwa: partial, android: partial, ios: partial.
- Route / navigation: Account menu → owner/profile.
- Status: partial
- Primary actions: Edit supported fields, sign out, open security.
- Backend: Owner APIs and profile preferences.
- Visual direction: Compact owner menu leading to profile, settings and sign-out.
- Missing work: Verify each account action against owner API and persist edits.
- Screenshot: NOT CAPTURED in this campaign.

## ADV-001 — Advanced diagnostics

- Purpose: Expose owner-useful diagnostics without burdening daily screens
- Platform: desktop: partial, pwa: partial, android: N/A, ios: N/A.
- Route / navigation: Settings → Advanced or qualification route.
- Status: partial
- Primary actions: Run supported checks, export evidence, copy safe IDs.
- Backend: Qualification/readiness/recovery APIs.
- Visual direction: Advanced section with concise checks and safe export, separated from daily tasks.
- Missing work: Verify gated routes, evidence links and redaction; split developer-only internals from owner diagnostics.
- Screenshot: NOT CAPTURED in this campaign.

## SEN-001 — Sensorium permissions

- Purpose: Control temporary sensor access on a trusted companion
- Platform: desktop: N/A, pwa: N/A, android: partial, ios: partial.
- Route / navigation: Native companion → Sensorium section or consent prompt.
- Status: partial
- Primary actions: Allow once/session, deny, stop session, inspect privacy status.
- Backend: Android Sensorium activities/services; iOS Sensorium views/session bridge.
- Visual direction: Sensor permission overview with temporary session controls and clear data-use statement.
- Missing work: Verify consent→session→stop/revoke on real device; do not infer physical support from simulator.
- Screenshot: NOT CAPTURED in this campaign.

## UPD-001 — About and updates

- Purpose: Check version, update status and release identity
- Platform: desktop: partial, pwa: missing, android: partial, ios: partial.
- Route / navigation: Settings → About/Updates expected; no verified active route.
- Status: missing
- Primary actions: Check, review, install/restart only where supported.
- Backend: Updates/package APIs.
- Visual direction: About section with version, build, notices and update status; install control only when updater is active.
- Missing work: Add a small About/update surface only if owner must check/update supported installation; connect to verified updater.
- Screenshot: NOT CAPTURED in this campaign.

## TOD-001 — Today

- Purpose: See a date-scoped agenda of tasks, commitments and plans.
- Platform: desktop: Not verified, pwa: Partial, android: N/A, ios: N/A
- Route / navigation: Home → Today entry point/sidebar → Today screen.
- Status: PARTIAL
- Primary actions: Change date, jump to timeline, create item, open source, start chat.
- Backend: pwa/reference-pages.js loadToday uses /everyday/timeline and /projects/timeline; create/edit dialogs in pwa/index.html.
- Visual direction: Date-first timeline with clear separation of task/commitment/plan and source context.
- Missing work: Execute day changes, create/edit persistence, source jumps and error states.
- Screenshot: NOT CAPTURED in this campaign.

## VIZ-001 — Visualize

- Purpose: Explore generated architecture, workflow, lifecycle, sequence and dataflow visualizations.
- Platform: desktop: Not verified, pwa: Partial, android: N/A, ios: N/A
- Route / navigation: Sidebar → Visualize (entry injected by pwa/visualize-workspace.js).
- Status: PARTIAL
- Primary actions: Open gallery item, choose type/view, filter layers, inspect nodes, navigate to source module.
- Backend: /iphone/api/visualizations and visualization workspace service.
- Visual direction: Scrollable graph canvas with textual summary and accessible alternative; avoid shrinking labels.
- Missing work: Run gallery and API-backed visualization through source navigation; screenshot wide and narrow canvas.
- Screenshot: NOT CAPTURED in this campaign.

## LAB-001 — Labs & Workspaces

- Purpose: Central route to the existing project, agent, product, visualization and advanced capability-development workspaces.
- Platform: PWA implemented; desktop NOT VERIFIED; Android/iOS companion surfaces N/A.
- Route / navigation: Authenticated PWA sidebar → Explore → Labs & workspaces.
- Status: PARTIAL; this turn's implementation is source- and contract-tested, but local browser rendering was blocked by the missing Playwright Chromium binary.
- Primary actions: Open Projects, Agents, Products, Visualize, Capability Forge, production readiness and Advanced Settings.
- Backend: Existing destination APIs and services; the hub itself creates no state.
- Visual direction: Group everyday workspaces separately from owner-controlled advanced labs.
- Missing work: Run the mobile/desktop browser suite, inspect destinations and capture screenshots.
- Screenshot: NOT CAPTURED in this campaign.
