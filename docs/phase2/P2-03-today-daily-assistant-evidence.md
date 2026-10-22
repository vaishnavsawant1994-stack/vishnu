# Vishnu 2.0 — P2-03 Today / Daily Assistant

**Reference:** Owner-approved deep-navy Today desktop/mobile composite, 1536×1024, received 22 October 2026.
**Repository:** `vaishnavsawant1994-stack/vishnu`.
**Stacked base:** `feat/p2-02d-workspace-conversation` PR #281 @ `b836e44937070269711a7dc5b23eb0383e995f0c`.
**Branch:** `feat/p2-03-today-daily-assistant`.
**Delivery:** draft PR targeting P2-02D; no merge, production deployment or data change.

## Canonical authorities reused

Today presentation only. No Today data store, conversation engine, task authority, Project authority, Agent runner or approval authority added.

- Timeline: `GET /iphone/api/everyday/timeline?day=YYYY-MM-DD&timezone=IANA&limit=500` (existing).
- Detail / lifecycle: `GET /iphone/api/everyday/items/{id}`, `POST /iphone/api/everyday/{id}/complete|snooze|reschedule|cancel` (existing).
- Native item creation: `openTodayExistingCreate()` → existing `POST /iphone/api/everyday/items` (existing).
- Approval list/detail: `GET /iphone/api/approvals-center` and `/{id}`. An explicit review + confirmation precedes authority `POST /iphone/api/approval/{id}/approve|reject`.
- Attention: `GET /iphone/api/work/attention`, `/{id}` (read-only).
- Projects: `GET /iphone/api/projects`, link via existing `window.openProject`; progress shown **only** when verified canonical `progress_percent` exists.
- Agents: `GET /iphone/api/agents/summary`; `GET /iphone/api/agents` is definitions-only, **not** evidence of active execution.
- Work: `GET /iphone/api/work/summary`; not a second work executor.
- Recent Activity: `GET /iphone/api/activities`, `/{id}`.
- AI input: both Today composers share one draft and hand off to existing `sendTurn` and canonical `/voice/turn`. Today does not construct a new conversation ledger.
- Voice / attachments: existing `micButton` and `attachmentButton` only after leaving the Today overlay. File picker explicitly discloses that the existing upload path stores data in Knowledge.

The upper and bottom composers share a single draft in P2-03; no hidden second unsent draft is stored.

## UI and behavior

P2-03 replaces the fullscreen Today **presentation** using `pwa/p203-today.js` and `pwa/p203-today.css`, hosted through existing PWA routes. The previous inline Today renderer remains available when P2-03 is absent, and explicit `todayDemo` preview keeps its separately labeled fixture mode.

The Today layout now includes desktop navigation, top search/owner actions, reused neural Core, greeting, date controls, AI composer, four quick actions, four canonical counts, event timeline, Needs You, day summary, Projects, Agents, Activity, lower desktop composer, five-item mobile navigation.

- The selected local day is explicitly supplied to the authenticated Everyday timeline API; timezone defaults to the device IANA time zone and is disclosed.
- Next/previous day arithmetic uses the calendar date, not 24-hour offsets (works through daylight savings).
- Absent or failed sources display `—` or an actionable unavailable note, not a fabricated zero.
- Pending formal approvals are counted separately from Work attention.
- Approval decision is two-stage (detail + confirmation); only canonical Stage-2 authority executes.
- Installed Agent definitions are never labeled running.
- Progress bar is omitted when the Project has no verified progress percentage.
- Each Today item details its verified source/state and supports existing lifecycle calls.
- Date changes discard stale earlier-fetch responses. Independent source failures render independently.
- Mobile safe-area bottom navigation and responsive stacks are provided.

## Qualification evidence and limits

- `tests/p203_today_browser.mjs`: browser fixture at 320, 390 and 1440px, canonical API reads, source normalization, approval review + authority call, next-day/today navigation, draft synchronization, action links and mobile overflow.
- `.github/workflows/pwa-mobile-preview.yml`: `node --check pwa/p203-today.js` and dedicated browser test; optional screenshots `artifacts/today-p203/today-{320,390,1440}.png`.
- Service worker updated to a new cache revision to include both Today assets.
- Existing `tests/today_command_browser.mjs` continues to verify legacy fallback rendering.

**Do not mark as complete until exact-head workflows and screenshots are reviewed.**

### Remaining issues / scope boundaries

1. Pixel overlay with the approved composite has not been performed. In-app screenshot artifacts are browser tests, not a proof of pixel parity.
2. Native iOS/Android/desktop hardware behavior, voice permissions, on-device session renewal and passkeys require real-device qualification.
3. Owner timezone is currently the trusted device/browser setting; centralized per-owner timezone preferences need separate integration.
4. No calendar month/week page was added. View Calendar scrolls to the canonical day timeline, not an external calendar provider.
5. Approval decisions use existing confirmation and auth rules; fresh verification is decided by the server. Do not claim automatic approval for review-only attention records.
6. Global Activity and Agent definitions remain observable through existing owner modules. Detailed active Agent-instance rows require a qualified workforce projection.
7. Date-specific task count covers Everyday timeline records only; Project tasks are a separate authority until a source-aware normalized cross-system task count is qualified.
8. Text-first Today prompts use the existing canonical conversation context; strict AI retrieval source isolation is outside this screen's authority (P2-02D dependency).
9. For safety, Today does not autonomously create/commit Work Plans or send external messages on a quick-action click.

**Status:** substantial first implementation in source, not production-verified, visually certified, native-device-qualified or release-approved.
