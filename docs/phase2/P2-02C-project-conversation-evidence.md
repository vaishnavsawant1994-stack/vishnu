# Vishnu 2.0 P2-02C — Project Conversation implementation evidence

**Reference:** owner-supplied 1536×1024 desktop/mobile composite design, 22 October 2026.
**Branch:** feat/p2-02c-project-conversation.
**Draft PR:** #280, stacked on P2-02B PR #279, which remains stacked on P2-02A/P2-01.
**Release constraint:** no merge to main, no production deployment.

## Source-of-truth design and implementation

The current ProjectStore (projects/store.py, via the ProjectWorkforceStoreAdapter in cloud_app.py) owns Projects, tasks, milestones, approvals, source files and deliverables. ContinuityService (devices/continuity.py) remains the only source for conversation identity, metadata and messages; canonical voice/turn transport remains the only chat execution path. No parallel engine, ProjectStore, workforce or approval mechanism was created.

### Backend changes

- GET /iphone/api/projects/{project_id}/conversations: requires trusted owner device and existing, unarchived Project; lists only Project-scoped canonical threads; global list pagination cannot evict older Project threads.
- POST /iphone/api/projects/{project_id}/conversations: requires active trusted owner session; creates one canonical project-type thread with project_id in existing continuity.context_json. Does not create a Project.
- GET /iphone/api/projects/{project_id}/conversations/{conversation_id}: requires owner authentication and checks the conversation's project_id, returning 404 on a foreign Project thread. Historic untagged primary Project conversations are accepted only when ProjectStore identifies them as that Project's primary.
- Legacy POST /iphone/api/projects/{project_id}/conversation remains supported, keeps the ProjectStore primary conversation_id, and upgrades an existing legacy primary's context on explicit reuse. All creation, message persistence and history still use existing authority, no new SQLite table or migration.

Known caveat: multiple SQLite stores are not updated as a single transaction when recording a new primary conversation, so crash reconciliation requires further design and acceptance. No multi-human Project ACL is provided by this single-owner system.

### Desktop/mobile source map

| Area | Source and behavior | Status |
|---|---|---|
| Dark navy layout, neon selection and 3-zone Project chat | pwa/p202c-project-conversation.css / js | Implemented in PWA, pixel comparison unverified |
| Header, breadcrumb, actual Project name/goal/status/target date and task progress | GET /projects/{id}; ProjectStore | Canonical data |
| Project Chats, create/open/reload | GET/POST /projects/{id}/conversations; scoped GET by id | Implemented, bounded first page (100) |
| Messages and composer | Existing canonical /voice/turn with validated request_id and same conversation ID | Connected; model/provider and real session acceptance pending |
| Project Files | Existing ProjectStore project.files, file index/download and confirmed upload to Project Files | Source-backed; no ephemeral chat-attachment lifecycle |
| Tasks | Existing GET Project, PATCH Project task state | Mutations wait for server response; assignment is not execution |
| Project Agents | Existing Agents module destination | No fake agent cards or unverified presence shown |
| Project WorkPlan/Progress | Existing Project plan and live modules | Navigation reuses canonical Work Engine |
| Project tools | Existing destinations or editable prompts | Prompt-only actions do not imply completed tool or artifact |
| Mobile chat list and five visible Project tabs | Responsive picker and nav | Implemented; physical-device keyboard checks pending |
| Private Share control | Private URL copy only | No invented collaboration grant |
| Model selector | Canonical route info | Per-chat switching unavailable |

### Qualification

Updated tests/test_projects_api.py for cross-Project 404, owner restrictions, legacy primary retention and >200 unrelated conversations. Extended tests/projects_workspace_browser.mjs for the owner-scoped mocked Project chat routes, ten desktop tabs, five mobile tabs, mobile new-chat picker and canonical transport. PWA mobile visual preview workflow produces screenshots for representative mobile/tablet/desktop browser viewports in artifacts/project-workspace.

PWA service worker now uses personal-ai-iphone-v65 to cache the two P2-02C presentation assets (never caches owner API data). Existing cache invariant tests were updated to require v65.

Tests must be inspected at the **exact final head SHA**, not inferred from earlier workflow runs. Success on a deterministic Playwright/mock-owner fixture does not establish real model acceptance or actual hardware parity.

### Known blocking gaps

- Supplied screenshot visual similarity not quantitatively verified: no owner-reference pixel overlay/difference evidence yet.
- Real Android/iOS and macOS/Windows/Linux native UI parity not demonstrated; Web/PWA is the implemented surface.
- Project context is supplied as bounded grounding text in the canonical turn, not an independently authenticated, server-built model-context channel; do not claim complete cross-Project AI-context isolation.
- No multi-user project sharing/permissions, no automatic generated-image/document artifact binding, no conversation-only upload lifecycle, no per-chat provider selection, no true research/code ledgers.
- Real workforce-assignment controls and live agent-status/approval cards require separate verified contracts; old canonical Agents/Work module remains available.
- No cursor pagination beyond first 100 Project threads, no pin/unpin, no selective cross-device draft sync, no comprehensive keyboard/SR/hardware qualification.
- WorkPlan execution remains under existing Project Work APIs and approvals; P2-02C tools currently navigate there rather than replicate governed execution in Chat.
- The Project message input is bounded at 1,800 characters to keep project context and request within canonical transport limits. Attachment upload persists to Project Files only with explicit owner consent.
- Exact-head CI/PWA preview must be green and visual evidence reviewed before upgrading this draft to production-ready.

**Status: partially implemented and not release-qualified. Keep PR #280 as draft.**
