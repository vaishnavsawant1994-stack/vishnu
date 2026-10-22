# Vishnu 2.0 — P2-07 Notifications & Alerts implementation and qualification ledger

Reference: owner-supplied desktop/mobile Notifications & Alerts composition, 1536 × 1024, October 22 2026. Reference is visual design authority; fixtures are not acceptance screenshots. This change is **draft** and must not merge or deploy without separate authorization.

## Branch and design
- Branch `feat/p2-07-notifications-alerts`, stacked on `feat/p2-06-global-search` at `dc55555d093d0813b5f55216533763e6e0a3c429`. Earlier Phase 2 screens are preserved as inherited changes; PR #285 remains an unmerged dependency.
- `pwa/p207-notifications.js` and `pwa/p207-notifications.css` extend the common PWA app shell and replace the sidebar Inbox destination with Notifications. The design uses dark navy, electric blue, category summary cards, tabs, filters, dated rows, selected detail, contextual owner actions and compact phone list/detail. Existing profile/navigation remain shared.
- Desktop and phone are actual responsive layout modes, not a phone-mockup background. The real owner name, category counts, timestamps and records come from runtime APIs.

## Canonical backend and security
- `notifications/service.py` remains the one persisted NotificationService. Additive schema **user_version=2** migration adds `pinned_at`, `dismissed_at`, `event_type`, `source_type`, `source_id`, `project_id`, `workspace_id` and `priority`. Existing rows and dedupe keys are retained. Fail closed for unsupported future schema versions.
- Existing generic notification events remain minimal and safe; known Work metadata IDs are bounded before insertion. No event parameters, external-provider tokens or secret bodies are copied to notifications.
- `server/notifications_center_api.py` provides device-bound `GET /iphone/api/notifications-center`, `GET /iphone/api/notifications-center/{id}`, `POST /iphone/api/notifications-center/read-bulk`, `POST /iphone/api/notifications-center/{id}/read`, `POST /iphone/api/notifications-center/{id}/pin` and `POST /iphone/api/notifications-center/{id}/dismiss`.
- Canonical `ApprovalsProjection` provides read-only pending approval rows and scope-checked details. Approve and Deny actions use **existing** `/iphone/api/approvals-center/{id}` to revalidate pending state then existing `/iphone/api/approval/{id}/approve|reject` to submit. This module never reimplements ApprovalManager, interprets reading an alert as approval, or creates a second approval table.
- Device/auth/session restrictions apply. Approval projections are only shown for the trusted current device and session; missing context reports approval source unavailable.
- Bulk read marks only persisted notifications for this trusted device. Approval items explicitly do not support read, pin or dismiss.

## Real functionality and honest coverage
- Actual category counts, unread/pending distinction; filtering by category, type, unread, priority, lexical text, project, workspace and UTC day; newest/oldest sort; bounded pagination. Counts refer to up to 200 persisted notifications and 100 pending approvals; coverage is marked partial at caps.
- Authoritative list/detail with source revalidation. Selection, mark read, mark all read, pin, dismiss, private copy link, approved linked Project navigation and existing Notification Settings. Workspace and Project options are drawn from existing APIs.
- Incremental foreground reconciliation through bounded authenticated polling every 20 seconds; no invented live events. No plaintext offline caching of private notifications; failures retain only the current in-memory last confirmed view and are visibly disclosed.
- **Sources currently producing in-app notifications:** existing Work completions/blockers/approval-required categories, configured workflow events, schedules and actual pending ApprovalManager tickets. Messages, standalone Projects, and Security category buttons show real zero counts until a canonical event producer is connected, rather than fabricated feed items.
- **Not implemented or deferred:** owner-authorized reminder scheduling/snooze, resource-to-Workspace linking and externally shareable links, persistent cross-device read-state sync, dedicated message/security notification producer adapters, end-to-end deep opening for all WorkOrders, active device push enrollment and native-companion parity. Disabled/absent capabilities are explained rather than falsely presented as working.
- Search uses literal metadata/content permitted to this device, not arbitrary hidden keys. P2-07 does not implement new global index/OCR/semantic search.
- Existing APNs generic lock-screen previews and notification settings service remain unchanged.

## Automated evidence
- `tests/test_p207_notifications.py`: real SQLite legacy migration, restart durability, bulk read idempotency, pin/dismiss behavior, device isolation/revocation, filtering, canonical ApprovalManager projection and cross-session denial.
- `tests/p207_notifications_browser.mjs`: Chromium fixture, desktop 1536×1024 and phone 390×844, category counters, selected detail, approve via canonical route, read/pin, bulk read and phone layout/back/filter checks. When `P207_SCREENSHOT_DIR` is set, captures implementation screenshots under `artifacts/notifications-p207`.
- `.github/workflows/pwa-mobile-preview.yml` runs the P2-07 browser test and `node --check`, in addition to retained Phase 2 checks.
- Exact-head CI and screenshot results must be verified **after the final branch push**. Native Android/iOS, desktop platform packaging and physical-device acceptance remain independent gates.

## Acceptance status
Source implementation is not equivalent to reference pixel parity. Mandatory follow-up includes full-resolution screenshot comparison, accessible focus/keyboard and dynamic-text review, 320–1920 px viewport coverage, large dataset/query performance, real provider/authenticated runtime integration, and user acceptance. No merge or production deployment authorized.

## Mobile action follow-up
- Mobile details include touch-accessible Read, Pin/Unpin, Dismiss and private Copy Link controls; desktop retains its right-side actions. Shared handlers use the canonical device-scoped service.
- Browser fixture uses visible-action targeting on 1536 px desktop and 390 px phone; visual and native acceptance remain unverified.

## Compatibility hardening
- Replace the obsolete exact `v70` cache assertion in the older Project Autonomy contract with a numeric minimum-version requirement and P2-07 asset presence checks. Keeps service-worker cache upgrades legal while still rejecting stale bundles.
- Preserve the historical Timeline attention counter separately from P2-07's unread-notifications counter (`p207UnreadCount`), and make the top Notifications shortcut open the P2-07 module. Neither count is fabricated.
