# Endpoint matrix — Screens 11–15

| Screen/control | Existing source | Authentication/authority | Status in this slice |
|---|---|---|---|
| 11 Home greeting / recent conversations | Web app existing conversation and activity loaders; `/web/api/conversations` | Existing owner session | Existing integration; per-reference visual parity not qualified |
| 11 Home composer | Existing PWA create/send conversation flow | Existing owner session/runtime | Existing integration; smoke tests available |
| 12 Chat list/detail/voice | `server/conversation_voice_api.py`: `GET /web/api/conversations`, `GET /web/api/conversations/{id}`, voice endpoints under the same API router | `require_owner()` and canonical continuity/runtime | Existing integration; qualification scope is limited |
| 13 History search | Existing conversation-list query `GET /web/api/conversations?q=…`; web timeline/drawer | Existing owner session | Existing search/history; management varies by operation |
| 14 Voice | `server/conversation_voice_api.py` (`POST /web/api/voice/turn`, `/voice/barge`, `/voice/client-event`) plus web capture/client state | Existing owner session, explicit browser microphone permission | Existing path; physical-device/browser interoperability not established here |
| 15 Conversations | `GET /web/api/conversations?q={query}&limit=100` | Existing owner session | Implemented in `pwa/global-search.js` |
| 15 Projects | `GET /web/api/projects?q={query}&status=all&sort=recent` | Existing project device/owner auth | Implemented in `pwa/global-search.js` |
| 15 Workspaces, Work, Files, Agents, Memory, Knowledge, Artifacts, Devices | No federated global-search endpoint verified in this slice | Must follow each resource's own scope and authorization | Not indexed here; UI states the limited source coverage |

The Search module uses `window.api` and the existing list handlers. It introduces no backend route, search index, sample data, or broad unauthenticated query. API behavior must still be verified against a running authenticated server for deployment-specific configurations.
