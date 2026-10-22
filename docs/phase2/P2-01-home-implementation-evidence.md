# Vishnu 2.0 · P2-01 Home · Implementation evidence

**Design authority:** owner-supplied 1536×1024 desktop/mobile design board (October 22, 2026).  
**Base:** `63cc4bf7485b602d725c89a400008925560591f4` (`main`).  
**Scope:** a bounded, opt-in presentation enhancement of the existing `/iphone/` PWA Home. No owner-identity, database, auth, runtime-state, Work execution or native-app authority is replaced.

## Source-to-screen mapping

| Design area | Actual implementation / authority | Claim |
| --- | --- | --- |
| Background, cards, sidebar, hero, phone navigation | `pwa/p2-home.css` and `pwa/p2-home.js`; loaded by `pwa/reference-home.js` | Implemented in PWA; image-diff validation pending |
| Spherical Core and status animation | Existing `#neuralCanvas`, canonical `.core-stage`, `core/home_state_projection.py`, `core/runtime_state.py`; central owner glyph is decorative | Existing engine reused; runtime-state animation mapping and native parity not independently qualified |
| Greeting and owner label | Owner-scoped `GET /iphone/api/status`, display_name fields | No sample personal name |
| Time and date | `Date` with `Intl.DateTimeFormat(navigator.language)` | Local live time; no fabricated 9:41/2025 |
| AI label | Owner-scoped `/status` model state | Unknown/failed states do not display AI Ready; system health opens canonical System Status |
| Meeting and task summaries | `GET /iphone/api/everyday/active?limit=200` | Vishnu Today items only; **not an external calendar total** |
| Approval summary | `GET /iphone/api/work/attention` read-only projection | Approvals remain under their original approval authority |
| Work count and active WorkOrders | `GET /iphone/api/work/summary` read-only projection | No fabricated percentage or ETA; opens original Work/project views |
| Recent Activity | Existing conversation cache, `renderHomeRecent`, conversation system | Shows real recent conversations, not a union of unrelated records |
| Message composer | Original `#composer`, `/voice/turn`, conversation APIs | Existing transport, duplicate guards, voice and Knowledge-upload behavior preserved |
| Attachments | Existing `#attachmentInput` and Knowledge-upload flow | No new preview/cancel interaction is claimed; broader multimodal acceptance still open |
| Quick cards | Six P2-01 buttons reusing Today, Workflows, Labs, Knowledge and canonical Chat | Implemented in the PWA shell; each route requires browser confirmation |
| Quick Tools | Six safe prompt starters; optional local browser shortcut visibility preference | Not proof of tool execution/provider availability; actual execution uses original governance |
| Notifications | Existing Work Attention Center and Activities fallback | Full notification-inbox parity and unread count require further work |
| Weather | No provider accessed | **Intentionally absent** until a permissioned provider exists |
| Offline shell | `pwa/sw.js` includes P2-01 CSS and JS | Does not imply offline AI inference |

## Security and data policies

- All sensitive reads go through the existing same-origin, owner-scoped `/iphone/api` transport; the Home presentation neither approves Work nor executes tools.
- The presenter cancels in-flight reads on route changes, uses an eight-second timeout, ignores stale responses and renders unavailable/error states rather than false zeros.
- Local Quick Tools settings store **only shortcut names**, on this device; no secrets, personal messages or tool arguments.
- Existing Phase 1 enrollment, recovery, trust and session management are untouched.
- No precise location request, camera/microphone auto-start, production deployment, or provider authorization is introduced.

## Tests

The existing `tests/vishnu_home_responsive.mjs` still checks owner identity, project hydration, navigation drawer, conversation binding and send behavior, with layout assertions updated to six approved cards and scrollable phone Home. Separate `tests/p2_01_home_browser.mjs` validates Live Today, Work, approvals, status, mobile and desktop breakpoints, original neural canvas, guided tools, preserved conversation, backend failure, and locked UI.

The PWA preview GitHub workflow now runs **both** browser files under its HTTP fixture server. The workflow should capture PNG artifacts for 320, 390, and 1440 widths. These rendered screenshots are not pixel-difference proof against the owner's composite board, and should not be characterized as 100% accuracy.

Commands in the PWA preview job:

```bash
node tests/vishnu_home_responsive.mjs
node tests/p2_01_home_browser.mjs
```

Additional required verification: full PR exact-head CI, PWA screenshot review/cropping and image matching at comparable viewports, 393×852 and ultrawide review, cross-browser keyboard/safe-area tests, accessibility check, live owner-account flows, voice file chooser/permission matrix, tablet behavior and all native/real-device qualification.

## Acceptance status / known remaining work

**Implemented but not yet independently accepted:** desktop/mobile PWA Home design, six cards, P2 summaries, guided Quick Tools, responsive navigation, local clock, existing canonical composer and Core reuse.

**Dependent on configuration:** connected AI, actual WorkOrders, calendar/Today data, image creation/research tools.

**Not completed:** configured optional weather; full Notifications read/unread parity; a genuine persisted tool-governed launch workflow for each Quick Tool; pre-send attachment preview/cancel; independently measured runtime-to-Core animation state parity; pixel-difference comparisons; Android/iOS native screenshot/interaction parity; physical-device passkeys, joins, restore and full acceptance.

**Do not merge or declare complete** until mandatory checks pass on the exact current head. PR remains draft during qualification, and production deployment is out of scope.
