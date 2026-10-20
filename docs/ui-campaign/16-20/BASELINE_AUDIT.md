# Screens 16–20 baseline and current audit

Audit date: 2026-10-20
Repository checkout: `E:\Vishnu`
Branch: `codex/isolate-genesis-navigation`
Inspected HEAD before this implementation slice: `07d938748a0093d92609a67e59504fec4596384b`

This checkout had pre-existing local changes. They were preserved. No branch switch, reset, commit, push, deployment or merge was performed. Remote/main and PR inventory are not qualified here.

## Current implementation evidence

| Area | Current authority | Status |
|---|---|---|
| Web shell | `pwa/index.html`, `pwa/reference-home.*`, `pwa/reference-pages.*` | Existing responsive shell; Screens 11–15 and newer screens are not yet one visually identical system. |
| Command Center | `pwa/command-center.js` + CSS, served by `server/iphone_pwa.py` | Partial safe web palette; not a complete action registry/approval dispatcher and not native parity. |
| Workspaces | `workspaces/store.py` + `server/workspaces_api.py`, mounted by `server/cloud_app.py` | New owner-scoped local SQLite records, CRUD, open/pin/archive, explicit demo fixture, canonical Project links and persisted Studio layout references. No startup seed. |
| Workspace web UI | `pwa/workspaces-ui.js` + CSS | Responsive library/create/overview/Studio slice. Browser-tested, but not yet an exact match for approved board layouts or all functionality. |
| Canonical resource authorities | Existing ProjectStore plus other existing product modules | Only Projects can currently be linked from the Workspace overview. Work, Agents, Files, Knowledge, Products and Conversations are not linked/count-backed here; their sections disclose that. |
| Windows | `app/main.py` → `ui.canonical_main_window.CanonicalMainWindow` → PyQt6 | Separate native surface; Screens 16–20 parity absent/unverified. Qt WebEngine unavailable in this environment. |
| Android | Companion app | Existing external Custom Tab path; in-app parity absent/unverified. Android Gradle tooling unavailable. |
| iOS/iPadOS | SwiftUI companion | Existing external Safari path; in-app parity absent/unverified. `xcodebuild` unavailable. |

## Data and demo separation

“Real data” here means records persisted by the local app and links to actual canonical records. New Workspace records are local development data in the Workspace SQLite store; they are not production or cloud-synced records. The only precomposed reference fixture is an explicit, idempotent, labeled “Reference Demo” workspace; it does not invent a real customer. No screenshot metrics or nested records are silently written to the owner store. Project links reference ProjectStore records and do not duplicate them. The Workspace owner key is currently the runtime’s single canonical `owner`; multi-owner account lifecycle still needs product/auth integration.

## Verification in this slice

- `tests/test_workspaces_api.py`: 6 passed.
- Targeted combined tests: 54 passed (`test_workspaces_api.py`, `test_p3_iphone_pwa.py`, `test_project_autonomy_ui_contract.py`, `test_global_work_awareness_ui.py`).
- `tests/workspaces_browser.mjs`: desktop and mobile browser flow passed, including create, overview, Studio save and mobile overflow check.
- JavaScript syntax, Python compile checks and `git diff --check` passed.
- The pre-existing full suite has previously reported 3,793 passed, 72 failed and 2 skipped; those failures have not been triaged in this slice.

## Remaining acceptance work

1. Complete the real resource relationships and interactions for Work, Agents, Files, Knowledge, Products, Conversations, chat, sharing, permissions and Studio panels against their existing authorities.
2. Build the populated overview/Studio compositions and compare actual responsive screenshots with approved reference crops; the current Studio is a persisted layout shell, not visual acceptance.
3. Audit idempotency/retry behavior, multi-owner identity integration, migration backup/restore, and application-wide API authorization.
4. Implement and verify installed Windows/macOS/Linux and Android/iOS parity without weakening native security boundaries.
5. Run and triage the full test suite, then capture platform-qualified visual and functional evidence.
