# Vishnu 2.0 — P2-02B Work Conversation
## Bounded implementation evidence

**Approved visual target:** uploaded 1536 × 1024 desktop/mobile Work Conversation design board, 2026-10-22.  
**Base:** P2-02A integrated branch, dependent on P2-01; exact head and base SHA are recorded in PR #279.  
**Release policy:** review only, no production deployment and no merge to main.

### Scope and source-to-design map

| Visual component | Real source / implementation | Status |
| --- | --- | --- |
| Dark four-column desktop and single-column mobile | `pwa/p202b-work-conversation.css`, loaded after Personal CSS | Implemented, screenshot comparison still required |
| Global navigation / compact Core | Existing PWA app drawer, canonical neural Canvas, shared owner status | Reused; does not create a second canvas |
| Work mode and context selector | `pwa/p202b-work-conversation.js`, existing `#vContextChip` for Project switch | Work type persisted in canonical `continuity_threads.context_json`; same existing owner/device authorization |
| Saved conversation list, open / New Chat, transcript, send | Canonical `/iphone/api/conversations` and original PWA `#messageStream`/`#composer` | Connected; Work-only list filtered by authenticated `GET /conversations?kind=work` |
| Search in this conversation | Loaded canonical message events and scroll-to-message | Search limited to currently loaded messages; no indexed attachment search |
| Chat / Files / Tasks / Research / Code / Plans / More | Canonical chat plus opt-in linked Project resource previews, tasks and WorkPlan | Chat, Files, Tasks and linked Plans functional with limits; Research/Code remain prompt-led |
| Right Conversation Context | Persisted Work context and optional, confirmed `work_project_id` in existing continuity JSON | Implemented; canonical Project lookup required; explicit link/unlink, not an ACL |
| Files & Resources | Linked Project `GET /projects/{id}`, authorized file download/index, `POST /projects/{id}/files/upload` | Existing Project files, deliverables, preview/download and explicit upload; no standalone conversation attachment store |
| Tasks | Linked Project `POST /projects/{id}/tasks`, `PATCH /projects/{id}/tasks/{task_id}`; Today fallback | Existing Project task listing, creation and done/reopen mutations; unlinked Today tasks are separate |
| Active Work | Linked `GET /projects/{id}/work` or authenticated global `/work/summary` | Linked Project status when verified; otherwise unrelated global WorkOrders labeled **not attached** |
| WorkPlan cards and execution | Existing governed Project Work APIs for plan creation, status, pause/resume; Work module for full execution/evidence | Canonical Plan only after explicit Project link; governed execution details remain with existing Work runtime |
| Approvals | `GET /approvals-center` with trusted owner session, filtered by verified linked Project ID | Linked pending approvals read-only; decision/continuation remains in canonical approval authority |
| Quick actions | Editable prompts fed to the canonical composer | Prompts are not claims of tool execution, document creation or provider availability |
| Model routing | Existing model status `GET /iphone/api/status` | Status and settings only; per-chat provider selection not implemented |
| Voice / attachments / secure Markdown | Canonical PWA conversation and voice input | Existing behaviors reused, cross-device acceptance pending |
| Mobile navigation | Five actions Home/Chat/Today/Work/More | Responsive UI implemented, keyboard/physical-device qualification pending |

### Distinctions protected

- Standalone Work mode is **not** Project/Workspace context and does not automatically create a project.
- New Work conversations are created through the existing API with `context_type: work`, persisted in `continuity_threads.context_json`. The existing list endpoint supports `kind=work` and `kind=personal`; older untagged threads remain Personal. This is an organizational classification **within the same owner domain**, not a new sharing boundary. The Work list is presently bounded by the existing 200-thread continuity read; full cursor pagination remains future work.
- Existing `PUT /iphone/api/conversations/{id}/work-project` requires a signed-in device, active trusted owner session, `confirm:true`, a Work-type thread, and a real unarchived Project. It stores only `work_project_id` in the existing thread context, without granting new execution rights; unlink stores null.
- The Stage-3 production GET `/iphone/api/conversations` now honors the same `kind=work|personal` classification as the legacy compatibility endpoint.
- WorkPlans, files, text artifacts, tasks and approvals are read from the linked canonical Project/Work stores, not created as a second chat-specific system.
- Standalone conversation-only attachments and automatic AI-generated artifact associations are **not** implemented. A confirmed linked Project can store files and human-entered text deliverables in its existing Project store; Knowledge upload stays a separate choice.
- There is no optimistic completion state, fabricated percent, or fake output document.
- No schema migrations, new execution authorities, credentials or permissions were added. Existing Project write endpoints preserve trusted-session and approval enforcement.

### Qualification and controls

Tests added: `tests/p202b_work_conversation_browser.mjs` and `tests/test_p202b_work_context.py`. It is run as part of `.github/workflows/pwa-mobile-preview.yml` and uses a clearly deterministic mocked owner-scoped backend.

Covered assertions: existing message preservation, one canonical Core, Work-vs-Personal route isolation, seven tabs, six quick actions, owner-scoped Work read, no fabricated unlinked files/tasks, explicit Project link/unlink, linked task update, scoped approval filtering, linked plan projection, file preview, in-thread search, 320/375/390/430/768/1024/1280/1440/1920 responsiveness, single voice-turn transport, reload behavior, Project context isolation and new canonical chat creation. Tests must **actually pass on the final SHA** before being reported green.

Service worker version `personal-ai-iphone-v64` invalidates the previous P2-02B shell assets. Visual screenshots are output by CI into `artifacts/p202b/`; this is a browser visualization rather than a pixel-difference measurement against the owner's composite design board.

### Remaining work required for full acceptance

1. Extend canonical Work metadata filtering with cursor pagination and validate a full trusted cross-device sync journey. The core Work/Personal type now persists in the existing continuity JSON without a new database migration; UI session preference is not an authority.
2. Decide whether standalone, non-Project Work conversations need dedicated task/file/artifact associations; current implementation deliberately reuses an explicitly linked existing Project.
3. Qualify real attachment upload/preview/download and deliverable updates in a trusted running browser; automatic AI-generated artifact transformation and binding remains unavailable.
4. Extend linked Project WorkPlan views with governed execute/cancel per-step evidence and approval continuation without bypassing existing authority. Plan creation/pause/resume use existing trusted endpoints but require exact-head and real-session qualification.
5. Build additional canonical Research and Code ledgers where supported; today these tabs offer guided prompts and contextual information. The linked Plans tab reads Project steps.
6. Implement real configured-model choice with privacy/cost disclosure (if existing route supports it) or keep the selector informational.
7. Verify browser keyboard/safe-area accessibility, long conversations, screenshots and pixel comparisons.
8. Qualify Web/PWA, Windows/macOS/Linux shells, Android emulator and iOS simulator; physical-device and provider-side acceptance remains owner/environment dependent.
9. Resolve P2-01/P2-02A dependent PR CI before merging the feature series.

**Current status: partially implemented.** This PR does not qualify P2-02B as complete or production-ready.
