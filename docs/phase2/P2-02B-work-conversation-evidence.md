# Vishnu 2.0 — P2-02B Work Conversation
## Bounded implementation evidence

**Approved visual target:** uploaded 1536 × 1024 desktop/mobile Work Conversation design board, 2026-10-22.  
**Base:** P2-02A integrated branch at `b0be85b53486920495d625de4406c85f52dc7eb2`, itself dependent on P2-01.  
**Release policy:** review only, no production deployment and no merge to main.

### Scope and source-to-design map

| Visual component | Real source / implementation | Status |
| --- | --- | --- |
| Dark four-column desktop and single-column mobile | `pwa/p202b-work-conversation.css`, loaded after Personal CSS | Implemented, screenshot comparison still required |
| Global navigation / compact Core | Existing PWA app drawer, canonical neural Canvas, shared owner status | Reused; does not create a second canvas |
| Work mode and context selector | `pwa/p202b-work-conversation.js`, existing `#vContextChip` for Project switch | Device-local **organizational view** only, not server-enforced Work scope |
| Saved conversation list, open / New Chat, transcript, send | Canonical `/iphone/api/conversations` and original PWA `#messageStream`/`#composer` | Connected; history lists all conversations with explicit disclosure; no Work-only false filtering |
| Search in this conversation | Loaded canonical message events and scroll-to-message | Search limited to currently loaded messages; no indexed attachment search |
| Chat / Files / Tasks / Research / Code / Plans / More | Read-only dialogs and existing canonical destinations | Chat working through original transport; advanced tabs partial |
| Right Conversation Context | Actual conversation ID/title; no invented project metadata | Implemented; shows Work view as device-local organizational label |
| Files & Resources | Existing Knowledge Library via explicit consent | No conversation-only attachment binding. Unavailable state, rather than fake attachments |
| Tasks | Existing Today task creation | No standalone Work-conversation task association. Creating a Today task does not imply a chat link |
| Active Work | Authenticated `GET /iphone/api/work/summary` | Real Project WorkOrders displayed **as unrelated global work** only |
| WorkPlan cards and execution | Original Project Work APIs and `pwa/workorder-detail.js` remain untouched | Not implemented for standalone Work chat without canonical link; no fake progress |
| Approvals | Existing Work Attention/ApprovalManager authority | Not bypassed; governed actions remain in canonical Work |
| Quick actions | Editable prompts fed to the canonical composer | Prompts are not claims of tool execution, document creation or provider availability |
| Model routing | Existing model status `GET /iphone/api/status` | Status and settings only; per-chat provider selection not implemented |
| Voice / attachments / secure Markdown | Canonical PWA conversation and voice input | Existing behaviors reused, cross-device acceptance pending |
| Mobile navigation | Five actions Home/Chat/Today/Work/More | Responsive UI implemented, keyboard/physical-device qualification pending |

### Distinctions protected

- Standalone Work mode is **not** Project/Workspace context and does not automatically create a project.
- The current server has canonical conversation persistence, but does **not** yet expose a dedicated Work-context metadata field to provide persisted cross-device Work-only filtering.
- The current Work summary is Project-based. No WorkPlan is linked to a Work chat unless a separate canonical association is created.
- Conversation-only attachment association and generated artifact linkage are not present in the verified backend. Uploading to Knowledge requires a separate explicit owner action.
- There is no optimistic completion state, fabricated percent, or fake output document.
- No schema migrations, execution authorities, credentials or permissions were changed.

### Qualification and controls

Test added: `tests/p202b_work_conversation_browser.mjs`. It is run as part of `.github/workflows/pwa-mobile-preview.yml` and uses a clearly deterministic mocked owner-scoped backend.

Covered assertions: existing message preservation, only one canonical Core, Work-vs-Personal route isolation, seven Work tabs, six quick actions, owner-scoped Work read, no unlinked file/task claims, in-thread search, 320/375/390/430/768/1024/1280/1440/1920 responsiveness, single voice-turn transport call, reload behavior, Project context isolation and new canonical conversation creation. Tests must **actually pass on the final SHA** before being reported green.

Visual screenshots are output by CI into `artifacts/p202b/`; this is a browser visualization rather than a pixel-difference measurement against the owner's composite design board.

### Remaining work required for full acceptance

1. Design a versioned, owner-scoped canonical Work-context association with proper privacy, migration, read/write APIs and cross-device sync policy. Do not rely on local view preference as authority.
2. Bind tasks, file attachments, generated documents and WorkPlan/WorkOrder IDs to the Work context explicitly and securely. Reuse existing backend authorities.
3. Create genuine file upload/preview/download, artifact transformations, and task editing/completion integrated with those associations.
4. Implement authorization-aware plan creation/start/pause/resume/cancel and per-step/evidence views for associated work without bypassing approvals.
5. Make Research/Code/Plans tabs provide the permitted real content, not just entry-point dialogs.
6. Implement real configured-model choice with privacy/cost disclosure (if existing route supports it) or keep the selector informational.
7. Verify browser keyboard/safe-area accessibility, long conversations, screenshots and pixel comparisons.
8. Qualify Web/PWA, Windows/macOS/Linux shells, Android emulator and iOS simulator; physical-device and provider-side acceptance remains owner/environment dependent.
9. Resolve P2-01/P2-02A dependent PR CI before merging the feature series.

**Current status: partially implemented.** This PR does not qualify P2-02B as complete or production-ready.
