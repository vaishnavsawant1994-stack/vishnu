# Test evidence — Screens 11–15

## This turn

- `node --check pwa/global-search.js` — passed.
- `node --check tests/chat_experience_browser.mjs` — passed.
- `node tests/chat_experience_browser.mjs` — passed, including a new desktop search query/result/open-conversation journey and mobile empty-search/no-horizontal-overflow check. The test host is an existing stale static server, so the test explicitly injects the current local Search JS/CSS; APIs are mocked and this does not prove live-server integration.
- Existing authenticated API calls are reused; no backend code or endpoint was added.
- Native application builds, emulator/simulator journeys, physical-device tests, visual golden diffs, and full chat-to-voice end-to-end journeys were not run in this slice.

## Previously recorded baseline evidence

Prior local work recorded passing Genesis/UI contract tests, `tests/chat_experience_browser.mjs`, and responsive Home preview checks. Those are not a substitute for the Screens 11–15 native or screenshot comparison acceptance gates. Re-run after this change if time/tooling allows.
## Local demo preview follow-up

- `node tests/campaign_demo_live_browser.mjs` — passed against the local web app server on port 8770: `/web/campaign-demo` redirects into the preview, all five preview/Search assets return 200 without owner sign-in, the sample Home renders, and the canonical Core image loads.
- `node tests/campaign_demo_browser.mjs` — passed: five screen navigations at desktop width and all five at 390px mobile width, local sample composition without an API write, no-microphone safety notice, mobile bottom navigation, no horizontal overflow, and no uncaught page errors.
- Self-check captures: `artifacts/campaign-demo/home-desktop.png`, `conversation-desktop.png`, `history-desktop.png`, `search-desktop.png`, `voice-desktop.png`, plus matching `*-mobile.png` captures for all five screens.
- This is interaction/responsive evidence only, not a 100% reference-image visual match or native parity qualification.
