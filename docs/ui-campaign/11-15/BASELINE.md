# Screens 11–15 baseline

Audit date: 2026-10-19
Local repository: `E:\Vishnu`
Branch: `codex/isolate-genesis-navigation`
Inspected HEAD: `07d938748a0093d92609a67e59504fec4596384b`

The worktree was already modified before this campaign (Genesis/PWA, Android, iOS, desktop, tests, and untracked `artifacts/`). Those changes are preserved. This turn did not fetch or switch branches, commit, push, deploy, or modify remote state. The pack's cited `main` SHA is a historical snapshot, not the current checked-out base. No related PR inventory or clean-main comparison was performed.

## Existing entry points

| Surface | Observed entry | Baseline reality |
|---|---|---|
| Web app | `pwa/index.html`, served as `/web/` | Responsive Home/chat, drawer-based conversation navigation/history, existing owner-authenticated APIs and voice client. Search was conversation-oriented rather than a dedicated federated results page. |
| Windows desktop | `app/main.py` → `ui.canonical_main_window.CanonicalMainWindow` → PyQt6 `MainWindow` | Separate native widgets and runtime. It does not render the supplied Screens 11–15 shell. “Open web app” opens the configured local browser surface. |
| Android | `android-companion` | Native companion/setup and device capabilities; primary “Open Vishnu” uses Chrome Custom Tab. It is not an embedded native rendering of Screens 11–15. |
| iOS/iPadOS | `ios-companion` | SwiftUI companion/device capabilities; “Open Vishnu” hands off to Safari. It is not an embedded rendering of Screens 11–15. |

## Relevant existing capabilities found

- `server/conversation_voice_api.py`: owner-authenticated conversation list/get and voice-turn/client-event handlers.
- `server/projects_api.py`: owner/device-authenticated project list with `q`, status, and sort filters.
- `server/activities_api.py`, `server/global_work_api.py`, `server/work_attention_api.py`: existing activity, work summary, and attention surfaces. These are not yet a federated search API.
- PWA owns chat creation, activation, conversation timeline/search, voice state/turn wiring, Home composer, and several other resource modules. The supplied composite references are concepts, not application assets or production data.

## Working-tree caution

Do not reset, clean, or overwrite the pre-existing worktree. No claim is made that the latest remote `main`, a native package, or a release build was tested in this audit.
