# P2-05 Conversation History — implementation and qualification truth ledger

Reference: owner-provided Conversation History desktop/mobile composite, 1536 × 1024, 22 October 2026.

## Source and branch
- Base: `feat/p2-04-live-voice`, commit `431d76cf4c8c385b368a68eed5d42866000ce98c` (P2-04 PR #283, unmerged; Phase 2 code has not yet landed on main).
- Feature branch: `feat/p2-05-conversation-history` (stacked, no production deployment).
- No independent conversation database or chat engine.

## Canonical design
- `devices/continuity.py` remains source of truth for thread IDs, events, per-device continuity and context.
- Additive SQLite index and derived SQL history read model: bounded cursor pagination, title/message/metadata search, category, pinned, tags, Project/Workspace, UTC-calendar-date range and archive filters.
- History pin/tags/summary live in the existing `context_json` alongside existing context classification; metadata writes and organization changes use `ContinuityService` transactions. No copied event rows, no duplicated message store. These presentation metadata keys do not carry authorization.
- Organization is owner-confirmed: personal, work, Project and Workspace. Project and Workspace IDs are checked by canonical stores before the original thread context is rewritten. Old scope authority keys are removed. The original thread ID, history sequence and event payloads remain unchanged.
- Existing /iphone/api/conversations list, get, create, archive, export and delete remain in place. New `GET /iphone/api/conversations/history/search`, `GET /{id}/history-detail`, `PATCH /{id}/metadata`, `POST /{id}/restore`, `POST /{id}/organize`, `GET /{id}/related` extend existing router.
- Existing trusted owner session and device registry authorization are reused. No multi-user sharing grants.
- Browser `pwa/p205-conversation-history.js` and CSS present list/detail, actual canonical events, categories, date/type/source/tag filters, pins, archive/restore/rename/tags, organizational actions, export/delete, Summary request via canonical turn and optional saved summary, mobile navigation and desktop preview.
- The P2-05 composer sends `POST /iphone/api/voice/turn` through the existing protected canonical path. Workspace turns include the saved, validated workspace_id. The front end does not emit raw, third-party HTML from transcript content.
- PWA asset routes and cache version 69 integrated; Home See All and existing sidebar Conversations entry open the History surface.
- Playwright mocked-interface checks and backend API/integrity tests included; `pwa-mobile-preview.yml` captures 1440/390 screenshots under `artifacts/conversation-history-p205`.

## Deliberately honest gaps
- Full text search uses SQL LIKE over canonical title/context/event payload; there is **no global attachment OCR, embedding search, semantic relation index or Project/Workspace name indexing**. Tag and saved context filtering are real.
- Conversation-specific file and task linking are **not present in the canonical ledger**. The Files and Tasks tabs explain this instead of showing screenshot demo data. A canonical Project/Workspace association is shown in Related; it does not grant file/task access.
- Direct file preview/download and Use in Implementation from a conversation are not implemented without a trustworthy conversation-attachment authority. The interface routes to the appropriate authorized Library.
- Summary is generated via a canonical AI conversation turn; a metadata summary is saved only after an AI response is confirmed. The model needs to be configured; no fabricated summary.
- For Personal/Work, continuing Voice uses the existing Chat microphone. Reopening an exact saved Project/Workspace transcript in the dedicated P2-04 Voice UI is not yet supported, so the UI does not claim it.
- Direct scoped Project/Workspace new chats stay in History with their verified conversation IDs; no silent reclassification as Personal Chat.
- Date filter compares server-stored UTC date from `updated_at`, not yet an owner-timezone-calculated day. Custom date range and offline secure cache remain unimplemented.
- PWA responsive styling alone **does not establish native Windows/macOS/Linux/Android/iOS parity**. Pixel-diff, cross-device storage policy, real attachment indexing, migration qualification across all historic schemas and real-device acceptance are separate gates.
- Some specialized message result renderers (code/artifact/embedded media) remain plain escaped text in History. The canonical full Chat renderer is available to continue the thread.
- Existing thread-owner model is single-owner. No collaboration or external Workspace sharing is introduced.

## Security and data policies
- Consent required in the UI to reorganize a conversation between scopes; existing history isn't automatically shared or duplicated.
- All mutations require an existing trusted session and, when present, the canonical device's `ai:chat` permission.
- Export and deletion use existing authorized endpoints. Deletion requires two confirmations in the UI, and never deletes unrelated Project/Workspace source records.
- Search and metadata use parameterized SQL, bounded inputs, and no new transcript telemetry.
- Source content stays untrusted when displayed. Moving an old Personal conversation to a Workspace changes **organization only**, not external provider/tool grants. Security review of broad executor-side Memory/Knowledge isolation is still required.

Status: integrated draft source implementation; full test / screenshot / platform qualification must be verified on the exact PR head before completion or merge. No main merge and no production deployment.
