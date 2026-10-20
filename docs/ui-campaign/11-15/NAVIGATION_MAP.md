# Navigation map — Screens 11–15

| Intent | Existing PWA action/route |
|---|---|
| Home | Existing Home landing (`openModule('home')`) |
| Conversation | Existing `openConversation(id)` and conversation client state; server activation resolves canonical thread |
| Conversation History | Existing conversation drawer/list and `openModule('conversations')` where available |
| Live voice | Existing voice controls and same active conversation context; exact deep-link persistence not qualified |
| Global Search | New `openModule('search')` responsive PWA module; `Ctrl/Cmd+K` and Home global-search entry route here |
| Project result | Search opens existing Projects module and dispatches `vishnu:open-project` with canonical ID; target selection handling remains dependent on the existing project view |

The browser app's canonical address is `/web/`; previous internal routes redirect there. Native app entry points are separate from the browser surface.
