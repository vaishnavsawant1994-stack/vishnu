# Vishnu 2.0 — P2-02D Workspace Conversation architecture / qualification

**Reference:** Owner-approved deep-navy Workspace Conversation desktop/mobile composite (22 October 2026, 1536×1024).
**Repository:** vaishnavsawant1994-stack/vishnu.
**Stacked base:** P2-02C PR #280 (`d8b8dbaae87a090ef27aa78d0f956108a2060614`).
**Development branch:** `feat/p2-02d-workspace-conversation`.
**Pull request:** draft PR #281, targeting the P2-02C branch, not `main`.
**Deployment:** none.

## Selected authorities

The authenticated `/iphone/api/workspaces` routes and `workspaces/store.py:WorkspaceStore` in `workspaces.sqlite3` are the canonical **P2-02D** Workspace source. They own Workspace identity, lifecycle and Project links. `projects/store.py:ProjectStore` owns linked Project records; `devices/continuity.py:ContinuityService` and canonical turn runtime own conversations and events; `ToolRegistry`, `ApprovalManager` and existing Work runtime remain in control of execution.

The older `/iphone/api/os/workspaces` path and `os-workspaces.sqlite3` are still used by the Vishnu OS Workspace shell. They **are not reconciled in this PR**. Legacy records are not deleted, copied, renamed or silently promoted; this is a release-blocking architecture dependency. A future owner-reviewed, idempotent migration plan must map IDs and Project links, preserve OS Studio layouts, identify duplicates/conflicts, qualify rollback and safely convert old clients.

## Backend delta

- `server/workspace_conversation_api.py`: owner-session-validated, Project-data-backed **GET /workspaces/{id}/summary**, **GET /workspaces/{id}/conversations**, **POST /workspaces/{id}/conversations** and **GET /workspaces/{id}/conversations/{conversation_id}**.
- `devices/continuity.py`: SQL-filter `workspace_id` before LIMIT, require `conversation_kind=workspace`, exclude Workspace threads from Personal filtering; Workspace append operations do not take over the device's Personal active context.
- `core/personal_ai_runtime.py`: continuing a Workspace chat does not mark it as the device's Personal-active conversation.
- `server/conversation_voice_api.py`: bounded additive `workspace_id` turn parameter. Before any AI execution, check that the requested conversation's persisted owner/Workspace association matches, and that the Workspace is active. Build a bounded model reference from WorkspaceStore and **actually linked** Project names; reject forged, missing or mismatched associations with 404/409.
- Canonical conversation IDs, messages, archive/rename/export and AI approvals are not duplicated in a Workspace-specific message database.

## Screen-to-feature map

| Visual area | Implementation and data | Qualification caveat |
|---|---|---|
| Global navigation / Workspace library | Existing `workspaces-ui.js` and shared PWA shell | Existing shell differs somewhat from reference |
| Workspace identity and dropdown | WorkspaceStore-backed opened record | Workspace switching returns to verified library |
| Summary chips / overview | Server summary from linked Projects, tasks and Project files | Members/Workspace-agent counts deliberately unavailable |
| Tabs | Chat / Projects / Files / Tasks / Agents / Plans / Research / Code / Knowledge / More | Advanced areas route to real modules or explicit unsupported disclosure |
| Left Workspace Chats | Scoped canonical list/create/open, recent history | First page max 100; pin/restore not added |
| Linked Projects list | WorkspaceStore Project links -> ProjectStore IDs | No copied Project content or fake progress |
| Main Chat | Verified Workspace thread and existing `/voice/turn` | No claim of streaming or per-Workspace model routing |
| Workspace context inspector | Authenticated metadata, counts, linked Projects | Inclusion-policy editor not complete |
| Active Projects | Canonical status and completed/total task ratio | No invented attention counts |
| Agents | Canonical Agents destination with honest unavailable Workspace assignment | No fabricated human membership or live agent presence |
| Tools / composer | Read-only destinations and explicitly prepared prompts | Attachment-to-Workspace ingestion and generated-artifact binding not yet supported |
| Mobile | Mobile five-tab layout, Workspace chat picker, bottom destinations, safe-area sizing | Requires real device and screenshot review |

## Data protection

Workspace IDs are validated server-side and owner session/device scope is required by the new API. Cross-Workspace conversation read and turn submission fail closed. Workspace records stay owner-scoped. Chats are stored in the existing ContinuityService with `context.conversation_kind=workspace` and `context.workspace_id`.

**Open security boundary:** the shared AgentExecutor still performs broader Memory/Knowledge retrieval by default, outside the Workspace Project-link projection. Therefore do **not** claim strict AI-context isolation or fully source-scoped tool access for Workspace conversations. Consequential tool execution continues to use existing approval governance; this PR does not relax it.

## Qualification / evidence

- `tests/test_workspace_conversation_api.py`: owner auth, multiple durable threads, retry, cross-Workspace 404, SQL query filtering before pagination, Project summary source, archival, restart, Personal exclusion.
- `tests/test_stage3_conversation_voice.py`: forged Workspace ID, missing scope, Personal-thread confusion and server-grounded Project names.
- `tests/p202d_workspace_conversation_browser.mjs`: independent browser mock for desktop/mobile composition, summary, New Chat, canonical /voice/turn, mobile tabs.
- `.github/workflows/pwa-mobile-preview.yml`: executes P2-02D JS syntax and browser tests. Verify exact final-commit workflow statuses before claiming success.
- PWA cache v66 loads both new P2-02D assets while API requests remain excluded from offline CacheStorage.

### Release-blocking work

1. Finish and qualify migration/compatibility of existing canonical/OS Workspace SQLite stores without loss.
2. Enforce resource-specific AI context retrieval and tool-bound source isolation beyond the Workspace association guard.
3. Complete Workspace-only file, Knowledge and Agent links; real per-Workspace agent availability and owner context-policy editor.
4. Full CRUD, pin/unpin, restored archive, and robust cross-process idempotency/pagination for hundreds of chats.
5. Visual overlay comparison against supplied desktop/mobile composite and QA at 320–1920px, text zoom, keyboard/screen readers.
6. Native Windows/macOS/Linux, Android emulator/physical and iOS simulator/physical qualification.
7. Real owner session, configured AI model and storage-policy acceptance.

**Status:** implemented first slice in source; not fully qualified, visually certified, native-qualified or released. Keep PR #281 draft; no merge or deployment.
