# Vishnu 2.0 P2-08 — Command Center implementation and evidence

Reference: Owner-supplied 1536×1024 Command Center desktop/mobile design. This is a reference-led implementation, **not** an automatic claim of pixel accuracy or production readiness.

## Git baseline and authority
- Base branch: `feat/p2-07-notifications-alerts` at `67a83d34aa0fc4f97fe8910900db0c3e87d1b969`.
- Implemented on `feat/p2-08-command-center`, intended as stacked draft PR. No merge or deployment.
- Replaces the original smaller `pwa/command-center.js` and `pwa/command-center.css` palette **in place**, preserving `window.vishnuOpenCommandCenter` and existing `data-command-center-entry` triggers. It does not introduce a second command overlay.
- Responsive page uses shared PWA app shell, brand/sidebar/top bar, original Vishnu Core asset `assets/genesis/vishnu-core.png`, electric-blue/navy styling and safe-area-aware mobile adaptation.
- Ctrl/Cmd+K remains owned by P2-06 Global Search; Ctrl/Cmd+Shift+P opens Command Center, without duplicate shortcut registration.

## Structured client-side command registry
- Stable allowlisted IDs in the existing Command Center module.
- Navigation: Home, Chat, Today, Workspaces, Projects, Agents, Library, Tools, Devices, Settings, Global Search, Notifications.
- Creation: conversation, Project, Workspace, Task, Automation navigation, Note editor navigation, Knowledge file-picker entry.
- Work/Agent: summarize day/current conversation, extract proposed tasks, request governed research, inspect custom agents, schedule-meeting drafting, email drafting; open actual Work.
- Category filters: All, Navigate, Create, Work, Agents, Tools, Files, Devices, Settings.
- Desktop: hero, Core, example chips, six cards, four command panels, quick context, shortcuts.
- Phone: native viewport, compact core, 3×2 card grid, category scrolling, one primary command list. No rendered phone frame on desktop.
- Natural-language aliases accept exact safe navigation and named Project/Workspace requests. Named creation opens the existing canonical editor **prefilled but not auto-submitted**. Open named Workspace uses authenticated Workspace search; selection is never guessed if ambiguous. Unknown text requires owner confirmation before being passed as a normal Vishnu chat turn. No arbitrary command eval, direct shell or tool dispatch.
- Canonical creation entrypoints: `vishnuChatBridge.createConversation`; existing `data-project-action=new-project` wizard; existing `data-workspace-new` wizard; `vishnuTodayP203Bridge.create('task')` composer. Agent actions use actual Agent Workforce or owner-bound AI turn, governed by existing permissions/approval execution.

## Device-bound history
- New `server/command_center_api.py` is **only** a small authenticated history adapter, not a tool execution authority. `GET/POST/DELETE /iphone/api/command-center/recent` stores stable command ID and UTC timestamp in existing DeviceRegistry metadata under `command_center.history.v2`; no new database/migration.
- The server allowlists IDs, rejects extra fields and typed prompts, uses device token and `ai:chat` permission, limits history to 12 entries, deduplicates and supports clearing. Browser localStorage v1 labels are not replayed or treated as authoritative.
- A "recent" row is the successfully initiated navigation or editor entry, **not** proof that a downstream task/automation completed. No fake timestamps or completed Work.

## Known partial/deferred functions
- Automatic safe scheduling still requires the canonical task/automation form and owner selection; calendar email send, external scheduling and native app launch require appropriate connected services and governed confirmation.
- Research and content extraction are routed to ordinary authenticated conversation/agents; it does not directly create a Work Order until the authoritative service acts.
- Project creation and Workspace creation **open their canonical wizards**, rather than inserting directly into storage. Success requires the owner to submit the form.
- "New Note", upload, and analyze file route to Knowledge/Files; unsupported inputs are not invented. Some screens may need improved direct deep links.
- Workspace and Project current names are shown only when confirmed by existing runtime context; unresolved names show None selected. Project URL-based context is fetched again from the existing protected Projects API. No Workspace data crosses into Personal Chat.
- No new provider access, native push, production jobs, remote desktop execution, built-in audio microphone permission, or secret-bearing client history.

## Test and qualification contract
- `tests/test_p208_command_center.py`: auth, revocation, scope denial, deduplication, device separation, history clear, no injection/unknown command.
- `tests/p208_command_center_browser.mjs`: real headless Chromium against a controlled browser host for 1536×1024 desktop, 390×844 phone, 320×720 phone; 9 filter controls, 6 action cards, routed editor activation, safe NL alias, actual history call, keyboard shortcut, XSS-escaped content and no unexpected horizontal overflow.
- `.github/workflows/pwa-mobile-preview.yml` runs `node --check` and the browser fixture, with optional screenshots via `P208_SCREENSHOT_DIR`.
- **Do not call screenshots visually approved** until comparing real CI-produced desktop and phone output to the owner reference. Native Windows/macOS/Linux/Android/iOS and real-device acceptance remain independent gates.
- No destructive capability is approved or executed from a Command Center button; backend governance must remain authoritative.

## Review prerequisites
Exact-head CI green; inspect actual P2-08 screenshot artifacts; native flow/dependency checks; back-navigation, 200% scaling, accessibility focus/VoiceOver/TalkBack; ensure P2-05/06/07 stacked PRs are reconciled before integration. No merge/deploy without explicit authorization.

## Compatibility contract fix\n- The legacy P3 PWA asset smoke test previously required `cc-dialog` in the Command Center stylesheet; P2-08 is now a full-page `cc-page-mode` implementation, so its assertion checks that real supported layout contract instead. All other asset probes remain unchanged.\n
## Trusted-session and canonical routing follow-up
- Command history POST/DELETE now require a matching active TrustedRequestContext, not just a bearer cookie. Tests cover absent session context, mismatched device context, revoked devices and permission-denied reads.
- Today navigation opens the existing Today surface, task creation leaves Command Center before opening the canonical Today composer, New Note enters the existing Memory note editor, and Upload File targets the existing Knowledge file input.
- Ctrl/Cmd+/ focuses the command input when the page is active and no other editor owns focus. Creation through New Chat clears obsolete Command Center styling.
- This change is not evidence that reminder scheduling, Work execution, native launchers or calendar writes are independently complete.

## Canonical creation deep links
- New Automation invokes the actual existing `workflowAdd` workflow composer (no automated execution); New Note opens `openKnowledgeNoteEditor` from Knowledge Notes instead of a generic note fallback.
- Upload File targets the existing `knowledgeFile` picker without uploading automatically. The global Command Center launcher receives an active blue selected treatment while the page is open.
- Browser fixture exercises both creator entry points; exact-head CI and screenshot qualification are required.

## Verified Core asset in browser fixture
- Browser fixture serves and decodes the real `pwa/assets/genesis/vishnu-core.png` at the PWA URL. Screenshot capture no longer silently omits the neural Core image. Reference-level pixel approval remains pending.
