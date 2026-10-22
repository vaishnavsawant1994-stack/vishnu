# Vishnu 2.0 — P2-06 Global Search implementation/evidence ledger

Reference: owner-supplied 1536×1024 desktop/mobile composite (22 October 2026). This file records *source implementation*, not visual or release acceptance.

## Branch and architecture

Feature branch `feat/p2-06-global-search` is stacked on `feat/p2-05-conversation-history` PR #284, head `8ec5cb7e7238e62dea544d77ab843ac9bb8bfa87`. P2-05 and earlier Phase 2 PRs are unmerged into main at the starting baseline. No deployment or main merge authorized.

- Continue extending **`pwa/global-search.js` and `pwa/global-search.css`**, not another detached UI.
- One search router `server/global_search_api.py` is registered in the existing `server/cloud_app.py`. It owns **no search database** and only queries canonical stores through bounded read adapters.
- Endpoint `GET /iphone/api/search` supports query, category, Workspace/Project, tag, UTC date range, ranking, limit and offset with type-specific facets and per-source coverage. `GET /iphone/api/search/result/{type}/{id}` returns a separately authorized source-derived detail. `GET /iphone/api/search/status` reports availability.
- Canonical sources: ContinuityService Conversation History, ProjectStore Projects/Tasks/File Index, owner WorkspaceStore, KnowledgeStore documents and notes, normal-sensitivity MemoryStore, Agent Workforce templates. Work tasks are distinguished from active Work execution; the search results must not imply an Agent is working merely because its template is available.
- Owner authentication uses existing trusted PWA device cookie/token with DeviceRegistry authorization. Memory and Knowledge require their additional read scopes. Denied/unavailable sources are reported in the `coverage` model and not incorrectly portrayed as no matches.
- Search returns sanitized **metadata/excerpts only**, never SecretVault entries, provider credentials, raw file bytes or secret/sensitive memory contents. Memory search excludes non-normal sensitivity and never-store; private Knowledge follows the existing per-device `knowledge:private` capability.
- UI is a dark, glowing reference-inspired three-column desktop search with mobile list and result-detail view; category facets, filters, search, clear, result cards, preview, real related IDs, open-source actions and bounded session-only Recent Searches. The existing Search/Command Center separation is retained.
- `pwa/sw.js` cache changed to v70 for asset refresh, not owner API caching.

## Coverage and deliberately limited features

**Supported:** lexical titles, persisted conversation messages, project title/goal, canonical workspace metadata, ProjectStore task titles/descriptions, indexed Project files, KnowledgeStore title/filename/chunks, authorized normal Memory subjects, agent catalog metadata, source-specific detail revalidation, source-first navigation, Project task creation with explicit confirmation.

**Supported contextual mutations:** explicit owner-confirmed conversation summary through the canonical voice/turn service and Project organization through the existing authorized conversation organize route; model/provider outcomes remain subject to actual availability. Authenticated private app deep links are revalidated on open.\n\n**Not guaranteed:** global semantic/vector ranking, arbitrary PDF image OCR, FTS coverage of unindexed binaries, true global work-order/approval/execution-evidence search (current Work results represent canonical Project tasks), project-to-workspace search beyond the primary WorkspaceStore, conversation-specific files not linked in canonical schema, native device parity, AI summarization of arbitrary search results, direct in-search destructive file/task/agent mutations, stable cursor pagination under concurrent updates, locale-aware calendar day boundaries or cross-device recent-search persistence.

`GET /search` scans a documented capped number of records per source. Facet counts describe the scanned search set, and the response marks known truncation with `count_is_lower_bound`. A category can report **unavailable/restricted/partial** rather than falsely reporting full coverage.

**Recent Searches** are deliberately held in memory for this UI session only. No private query is written to persistent unencrypted localStorage, a new database or analytics. Clear All erases the session list; a future opt-in persisted history should require an explicit retention/privacy design.

**Search result actions** open authorized owning modules; Copy Link copies a private in-app reference, not a public sharing grant. Only resource-appropriate actions are enabled. Arbitrary AI summarization of non-conversation resources, file open/download and direct destructive file/agent operations are not falsely claimed complete; conversation summarization and Project organization are supported through their existing authorities.

## Test paths and evidence required

- `tests/test_p206_global_search.py`: real canonical store fixtures, eight source categories, facets, Project/Workspace scoping, native SQL search, work details, permission denial, restricted Knowledge/Memory, secret exclusion and source failure.
- `tests/p206_global_search_browser.mjs`: desktop 1536×1024 and phone 390×844 Playwright route fixture, search, filters, selected result, preview, mobile detail, clear and screenshot artifacts.
- `.github/workflows/pwa-mobile-preview.yml` includes the new browser test and screenshots under `artifacts/global-search-p206`.

**Separate acceptance gates:** exact-head CI, security, screenshot diffs against the supplied board, keyboard/screen-reader, 320–1920 viewport matrix, huge data/performance, real native desktop/Android/iOS runtime and physical device acceptance. Mark untested gates as unverified, not passed.

No production deployment. Proprietary repository license unchanged.

## Follow-up hardening, October 22
- Reject whitespace-only API search queries rather than running a broad query on all canonical sources.
- Desktop/mobile advanced filters include an explicit custom UTC date interval using the existing validated API date range. Calendar days are UTC in the backend, not owner-timezone-aware civil dates.

## Source completeness hardening
- Bounded Project, Workspace, Agent, Memory and Knowledge scans now disclose `partial` coverage instead of claiming complete facet counts after the scan cap.
- Explicit Project filters resolve the canonical Project directly, even when that Project is older than the first 100 listed Projects.
- Added an isolated 105-Project regression verifying lower-bound facets and authorized filtered recall. Full exact-head qualification must be rerun after this change.

## Canonical Conversation lifecycle from search preview
- Search offers a More menu for canonical Conversation results only: move existing original thread to a Workspace with explicit confirmation, secure JSON export, archive, or permanent delete with two owner confirmations. Other resource types do not receive these operations.
- All mutations call the owning Conversation API. Export returns a real authorized bundle, and browser download is initiated only after its receipt. Archive/delete refresh Search only after backend confirmation; no resource-cloning or fake success.
- Browser qualification adds Workspace move, real export result and archive disappearance. Desktop screenshot capture occurs with populated results and selected preview; mobile screenshot capture occurs with results visible, before destructive action. These are fixtures, not physical native-device or pixel-diff evidence.

## Stale-result preview protection
- Fresh queries and facet/filter changes invalidate outstanding source-detail requests before rendering a new result set. An earlier delayed, authorized preview cannot reactivate an obsolete selection.
- The P2-06 browser fixture now holds a Conversation detail response while switching to the Projects facet and verifies that the stale preview remains absent at desktop and mobile viewport sizes.
- This commit requires fresh exact-head CI qualification; no native-device or exact pixel-match claim is made.

## Memory opt-out enforced on every search route
- Memory-disabled state now blocks direct Search result previews as well as list queries; source availability accurately reports Memory as unavailable when disabled.
- A canonical-memory fixture verifies that an accessible result becomes unpreviewable after the owner disables Memory. Errors reading the toggle fail closed.
- This is Search-route enforcement only, not a claim that all other Memory UI/features are disabled. Requires new exact-head tests.
