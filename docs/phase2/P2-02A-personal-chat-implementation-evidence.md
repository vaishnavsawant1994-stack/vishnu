# Vishnu 2.0 — P2-02A Personal / General Chat implementation ledger

**State:** PWA implementation committed; qualification and visual acceptance pending.
**Base:** P2-01 Home branch at c5ac4d697a3116cdd79d21a55450a84528c3818c. Stacked draft PR #278.
**Visual authority:** Owner P2-02A design specification. The actual P2-02A screenshot was not available for calibrated image comparison in this turn. Do not claim pixel accuracy.

## Canonical integration map

| UI | Authoritative source | Claim |
| --- | --- | --- |
| Main sidebar, Chats history and CRUD | Existing appDrawer, conversationDrawer and owner-scoped conversation APIs | Reused, not duplicated |
| Context switcher | Canonical vContextChip, existing project chooser/permissions | Explicit user choice; does not silently migrate |
| Personal greeting and AI availability | Authenticated /iphone/api/status | Never hardcodes owner identity or an AI-ready state |
| New Chat and drafts | Canonical createConversation and sendTurn, transient per-conversation memory map | Drafts are not claimed durable across process restart |
| Messages, Markdown, source previews and reactions | Existing renderMessages, Markdown sanitizer, chat-experience | Does not introduce raw HTML from AI |
| AI response and continuity | Existing /voice/turn and conversation continuity | No extra backend or transcript store |
| Structured plan | Recognizable rows in persisted assistant messages | No fake schedule, calendar writes or progress |
| Follow-ups | Original editable composer | No automatic external action |
| Model indicator | Canonical status + Settings | Read-only readiness, NOT individual provider/model switching |
| Plus/attachments | Existing Knowledge upload, explicit consent dialog | Conversation-only attachment binding unavailable |
| Voice | Existing microphone/speech feature and OS permissions | No automatic recording |
| Mobile navigation | P2-02A scoped presenter | Home, Chat, Today, Work and More |
| Visual Core | Existing neural Canvas, canonical Core asset | No duplicate runtime-state engine |
| Work and project isolation | Canonical context label and original server scopes | Personal design disabled for verified Project context |

## Changes

pwa/p202-personal-chat.js and pwa/p202-personal-chat.css are scoped presentation additions. pwa/index.html imports them. pwa/sw.js caches them in shell v62. tests/p202_personal_chat_browser.mjs extends browser qualification. The existing chat and P2-01 test cases remain registered in .github/workflows/pwa-mobile-preview.yml; test_project_autonomy_ui_contract.py retains a strict shell-version assertion updated for the v62 upgrade.

## Qualification commands

Serve the PWA at http://127.0.0.1:4173/iphone/ before running:

    node tests/chat_experience_browser.mjs
    node tests/p202_personal_chat_browser.mjs
    node tests/vishnu_home_responsive.mjs
    node tests/p2_01_home_browser.mjs

The P2-02A fixture tests user identity, real API contract shaping, persisted conversation display, source-derived plan card, guided follow-ups, model/attachment availability explanation, new conversation creation, Project context guard and responsiveness across 320–1920px. They use deterministic API fixtures, not a real AI provider. Browser screenshots are not reference pixel-difference proof. Exact-head CI, Voice Lab, PWA preview, security and responsive conclusions must be verified before merging.

## Remaining / configuration dependent

- Pixel-difference review against the actual P2-02A image; accessible contrast and native screenshots.
- Conversation-scoped file preview/removal and attachment send, distinct from Knowledge persistence.
- Governed per-conversation provider selector; present control currently explains actual routing instead.
- Streaming cancellation when supported by canonical backend; genuine provider end-to-end qualification.
- Restart-persistent privacy-policy-compliant drafts, browser back/forward, keyboard on physical phones and cross-device sync.
- Native Windows/macOS/Linux/Android/iOS parity; real microphone, attachment picker and full accessibility acceptance.
- Generalized typed assistant response cards beyond schedule detection.

**Do not merge or deploy automatically.** Maintain this PR as draft until exact-head checks pass, user-visible actions are reviewed and missing functionality is either implemented or explicitly accepted as unavailable.