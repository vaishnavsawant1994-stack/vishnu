# Screens 16–20 readiness

Status is limited to this checkout and evidence captured on 2026-10-20. “Partial” means an implementation slice exists; it does not imply screenshot-level acceptance or complete functionality.

| Screen | Web/PWA | Windows | macOS/Linux | Android | iPhone/iPad | Live authority |
|---|---|---|---|---|---|---|
| 16 Command Center | PARTIAL; browser-tested safe navigation and conversation action | MISSING | MISSING | MISSING | MISSING | Existing modules/conversation creation; no unified command resolver or governed action dispatch |
| 17 Workspaces Library | PARTIAL; searchable/filterable persisted Workspace records, pin/archive, explicit reference-demo import | MISSING | MISSING | MISSING | MISSING | Owner-scoped SQLite WorkspaceStore/API |
| 18 Create Workspace | PARTIAL; template, name/type/description creation persists locally | MISSING | MISSING | MISSING | MISSING | WorkspaceStore; no live template recommender |
| 19 Workspace Overview | PARTIAL; saved metadata and actual canonical Project references; other resource sections are honest empty states | MISSING | MISSING | MISSING | MISSING | WorkspaceStore + existing ProjectStore references; no other resource-family links yet |
| 20 Workspace Studio | PARTIAL; saves bounded panel layout/reference metadata; not the full populated interactive reference canvas | MISSING | MISSING | MISSING | MISSING | WorkspaceStore Studio view persistence |

Approved reference boards remain the acceptance target. Exact screenshot comparison has not passed; desktop/mobile browser captures are implementation evidence only. Native parity is unverified: this checkout has no usable Qt WebEngine, Android Gradle toolchain/wrapper, or iOS `xcodebuild`.

Only the explicit “Import reference demo” action creates `Rudra Health Care · Reference Demo`, marked illustrative and not a real customer. Other reference metrics, Projects, agents, files and activities are not silently seeded as owner data. See `BASELINE_AUDIT.md` and `WORKSPACE_DATA_AND_UI_STAGE.md`.
