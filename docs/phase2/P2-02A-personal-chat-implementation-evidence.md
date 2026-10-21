# Vishnu 2.0 — P2-02A Personal / General Chat

**Reference:** Owner-supplied desktop and mobile chat design board, October 22, 2026.  
**Base main SHA:** `63cc4bf7485b602d725c89a400008925560591f4`.  
**PR:** Bounded, review-only Personal Chat enhancement; no production deployment.

## Implementation map

| UI | Canonical source | P2-02A scope |
| --- | --- | --- |
| Owner and locked state | Owner-authenticated `/iphone/api/status`, `check()` in `pwa/index.html` | Read-only name, model readiness and initials; P2 features hide outside authenticated Chat |
| Chat navigation, desktop two sidebars, history | `#appDrawer`, `#conversationDrawer`, `renderConversationList`, `refreshConversationsDrawer` | Restyle; reuse all existing row event handlers and conversation IDs |
| New, open, rename, delete, share/export | `vishnuChatBridge` and existing conversation endpoints | Retained; new header action calls canonical `createConversation()`; native three-dot menu reused |
| Conversation title and context | `vishnuChatBridge.current`, `#vContextChip`, `chat-context-owner.js` | Read-only title; context selector delegates to canonical permission-gated picker, no silent reassignment |
| User and assistant messages | `renderMessages()`, `renderMessageMarkdown()`, `/voice/turn` | Original safely parsed Markdown and server persistence retained, P2 bubble styling scoped |
| Daily plan card | Canonical assistant `assistant_message.payload.text` | Only parse recognisable time rows from an actual response; extra visual representation, not a saved calendar |
| Follow-up buttons | Original `#message` plus `vishnuChatBridge.setDraft` | Editable prompt seeded within currently selected conversation; never mutates Today or calendar |
| Composer and voice | Existing `#composer`, `#micButton`, speech pipeline | Reuses submit, retry, authorization and permission boundaries; microphone visually restored |
| Model status | `GET /iphone/api/status` model property | "Vishnu AI" routing information dialog and Settings link. **No new provider-switching authority** |
| Attachments | Existing `attachmentInput` uses `uploadKnowledge()` | Explicit menu labels permanent Knowledge ingestion; conversation-only upload is reported unavailable, not silently persisted |
| Drafts | Shared composer | In-memory only per conversation, no new permanent storage of private text |
| Global search | Existing Global Search via canonical module | Search launcher opens existing Search |
| Notifications | Existing Work Attention Center or Activities module | Honest fallback, not a fabricated unread count |
| Responsive shell | `pwa/p202-personal-chat.css` | Desktop two-column navigation/history plus main thread, tablet, phone, mobile tabs, safe-area composer |
| Offline shell | `pwa/sw.js` | Cache-version bump with static P2-02A files; not proof of offline AI inference |

## Changed files

- `pwa/p202-personal-chat.js`: presentation-only controls, context delegation, genuine plan rendering, safe attachments, scoped mobile nav, owner and route lifecycle.
- `pwa/p202-personal-chat.css`: dark navy/cyan personal-chat layout and responsive breakpoints.
- `pwa/index.html`: imports exactly those assets after the canonical Chat layer.
- `pwa/sw.js`: includes assets in versioned shell cache.
- `tests/p202_personal_chat_browser.mjs`: browser/fixture acceptance for canonical message, structured plan, follow-up draft, attachment disclosures, breakpoints and Home isolation.
- `.github/workflows/pwa-mobile-preview.yml`: includes new test while retaining `tests/chat_experience_browser.mjs`.

## Qualification and exclusions

Run in the repository preview environment (HTTP server serving `pwa` at `/iphone/`):

```bash
node tests/chat_experience_browser.mjs
node tests/p202_personal_chat_browser.mjs
```

CI fixtures prove frontend contracts and deterministic backend-shaped responses **only**; they do not demonstrate external LLM provider acceptance. Browser screenshots are visual evidence for review, not pixel-accuracy metrics. Real-device/browser keyboard and safe-area tests, streaming/cancellation provider proof, server-backed Chat attachment lifecycle, model route selection, persistent per-conversation drafts under owner data policy, full Personal/Work/Project/Workspace privacy classification and native app parity remain explicit follow-up items.

The existing Project Chat context picker has been retained rather than replaced; the UI defaults to Personal Conversation only when project context is not indicated. No transcript copying between contexts happens automatically.

**Status:** Implementation awaiting exact-head CI, accessibility and visual-reference acceptance. Do not merge/ship solely based on source changes; no production deployment performed.
