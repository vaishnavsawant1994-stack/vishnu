# Vishnu 2.0 — P2-04 Live Voice implementation / qualification ledger

**Design source:** owner-provided 1536 × 1024 desktop/mobile composite, 22 October 2026.
**Branch:** `feat/p2-04-live-voice`, stacked on `feat/p2-03-today-daily-assistant` PR #282 @ `78592b717eae3773d5248e10d0bdd51ecfc584d2`.
**PR:** draft, no merge to main, no deployment.

## Actual architecture

This is a new PWA presentation and session capture adapter, **not a second AI, approval, tool or conversation backend**. Existing authorities:
- Browser capture: secure-context `getUserMedia({audio:true})`, browser `SpeechRecognition` where supported. Owner must press Start Voice and acknowledge the browser provider disclosure; there is **no capture when opening the screen**.
- Final recognized text and typed messages: `POST /iphone/api/voice/turn` using the same canonical request_id, conversation ID, session and ApprovalManager/executor as other PWA conversation entry points.
- Canonical history: `GET /iphone/api/conversations/{id}`, or Project/Workspace-scoped conversation GET. No transcript data store is introduced.
- General/Work: existing `POST /iphone/api/conversations` with actual personal/work classification. Project: existing `POST /iphone/api/projects/{project_id}/conversations` with ProjectStore validation. Workspace: existing `POST /iphone/api/workspaces/{workspace_id}/conversations` with existing owner-scoped WorkspaceStore validation. Switching context starts a distinct conversation, rather than leaking old transcript content into another scope.
- The canonical turn handler also verifies that a Project-scoped thread still links to a nonarchived Project, using a short **server-sourced** Project name/goal as grounding. The existing Workspace scoping check is preserved.
- Optional speech output: browser `speechSynthesis` once an actual canonical reply is received. Playback interruption uses `POST /iphone/api/voice/barge`; in-flight cancellation uses `POST /iphone/api/voice/operation/cancel`. Durable Work remains governed separately.
- Live audio visual: lightweight CSS orb plus WebAudio input analyzer bars (where supported), rendered only when actual microphone capture has begun. Session time starts on actual recognition startup; frame rendering stops on release.
- Local, owner-initiated Screen Share uses `getDisplayMedia`. **Screen content is NOT sent to AI and does not provide vision/screen analysis** in this slice; sharing ends on End or track loss.
- Today's Key Items: bounded reads from existing `/work/attention` and `/everyday/timeline`. These are real records; no screenshot sample content is inserted.

## PWA files and routes

- `pwa/p204-live-voice.js`, `pwa/p204-live-voice.css`: desktop and responsive mobile Voice stage, Focus/Expanded mode, owner-scoped context picker, canonical transcripts, status, microphone, mute, timer, End, barge, voice/text input, honest disabled/unavailable advanced controls.
- `pwa/index.html`: Vishnu sidebar Live Voice entry point and bridge into existing PWA routing and session. Existing Chat/Home microphone remains available and is not replaced.
- `server/iphone_pwa.py`: static routes for the two P2-04 assets; no new voice data route.
- `pwa/sw.js`: v68 bounded UI-only cache update; no owner API caching.
- `server/conversation_voice_api.py`: additional safe, server-authored Project context and reject archived Project voice conversation. Existing Workspace logic is unchanged.
- `tests/test_stage3_conversation_voice.py`: tests Project association/archival response.
- `tests/p204_live_voice_browser.mjs`: Playwright 390/1440px mock canonical service and mocked permission/test media. Includes no automatic capture, focus, actual state/mute, canonical text, distinct Workspace context, End cleanup and layout overflow check.
- `.github/workflows/pwa-mobile-preview.yml`: syntax check, browser scenario and screenshot output `artifacts/live-voice-p204/`.

## Reference image mapping

Desktop: Vishnu sidebar/header; Live Voice title/controls; central cyan/blue/purple orb with waveform, context selectors and three session controls; focus/expanded modes; right Conversation/Transcript/Tools & Activity/Context tabs; Today's Key Items and text composer. Mobile: single-column orb, two-by-two contexts, mute/end/text, key-items panel and five-destination bottom navigation. The live image is **not** a hardcoded raster screenshot.

## Security guarantees and constraints

- No microphone or screen capture on screen open. Browser permission prompt and explicit owner gesture are required. The capture stream is stopped between submitted voice turns, on tab hide, page unload, End and local track revocation.
- One canonical final transcript maps to one logical request, and stale, late replies cannot restart output after session End.
- Project/Workspace context is checked via server source-of-truth associations before the canonical turn. Choosing a UI tab grants **no new filesystem, tool, agent, Memory, Knowledge or provider access**.
- Tool execution, approvals, one-use tickets and emergency stop stay under existing governed services.
- No raw voice recordings, screen frames or temporary partial transcripts are persisted by this PWA voice UI.
- Browser STT may use external processing. The capture consent text says so; environment/provider behavior must be acceptance-qualified.

## Still required for complete acceptance

1. **Native and physical-device qualification:** Windows/macOS/Linux microphone devices, Android runtime audio permissions, iOS AVAudioSession, headset/Bluetooth routing, background restrictions and native UI parity are unverified.
2. **Provider qualification:** Local/native STT, TTS, configured model, true low-latency streaming and full-duplex/automatic turn resume are not demonstrated. The browser UI uses turn-based STT → canonical turn → optional browser TTS, and requires explicit restart between voice turns.
3. **Advanced capabilities:** AI-visible screen-share frames, live screen understanding, durable notes/artifact creation from audio, voice-local device switching, genuine voice-driven tool status cards and in-screen approval ticket decisions are not implemented. Corresponding actions disclose limitations or navigate to the authoritative module.
4. **Context intelligence:** Despite server-authoritative scope associations, independently verifying broad executor Memory/Knowledge retrieval isolation and contextual tool grants remains a release blocker inherited from P2-02D.
5. **Visual and accessibility:** Exact desktop/mobile pixel overlays, screenshot review, 320–1920px large-font/VoiceOver/TalkBack/keyboard acceptance and motion reduction require further evidence.
6. **Resilience:** Reconnection, cross-device session persistence, active microphone source switching, provider failure matrices and full cancellation race tests need real-runtime qualification. A completed backend turn during a lost request may require status recovery before retry.
7. **Permissions/persistence:** Scope selection is in-memory for this UI session; per-owner preference migration and cross-device Focus preference are not claimed.

**Status:** integrated first web/PWA implementation in source, not release-ready, not visually certified, not native-device-qualified, not deployed. Keep draft until exact final commit checks and screenshots have been reviewed.
