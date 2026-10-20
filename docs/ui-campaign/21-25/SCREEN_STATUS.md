# Screens 21–25 implementation status

Audit date: 2026-10-20 · local checkout `E:\Vishnu` · branch `codex/isolate-genesis-navigation`.

This is a stage report, not a completion certificate. Approved screenshots remain the visual acceptance authority. No exact-image comparison has passed.

| Screen | Web/PWA | Windows | macOS/Linux | Android | iOS/iPadOS | Data / current gap |
|---|---|---|---|---|---|---|
| 21 Workspace 3D Spatial View | MISSING; reference inspected, no genuine renderer/scene or canonical character/asset source integrated | MISSING | MISSING | MISSING | MISSING | Supplied board is a composite, not a usable mesh/asset. No production-quality spatial engine or source model located in the targeted PWA search. |
| 22 Workspace Team / Agents / Access | PARTIAL: local Agent catalog and summary API + memberships from linked Projects; read-only Workspace view | MISSING | MISSING | MISSING | MISSING | Actual workforce counts/membership; grant editing, invites, Workspace-level scopes, work reassignment and governed pause/remove are not integrated here. Browser UI test uses explicitly test-only responses. |
| 23 Workspace Files & Assets | PARTIAL: shows file metadata returned by linked canonical Projects | MISSING | MISSING | MISSING | MISSING | Not the global typed Resource/Artifact system; no upload, thumbnail/preview, version comparison, asset provenance, 3D models/materials/renders, or storage-policy state. |
| 24 Workspace Settings | PARTIAL: save/reload-capable local General profile fields (name, description, type, pin) | MISSING | MISSING | MISSING | MISSING | Other ten settings categories, sharing/access, remote sync, icon/cover, module preferences and archive/delete governance remain unimplemented. |
| 25 Today / Personal Command View | PARTIAL: new responsive full-page command dashboard follows the supplied composition; reads owner Everyday timeline, Operations, canonical Work summary and attention, Projects, Workspaces, and audited Activity. Per-source failures remain visible; preview rows are isolated and labeled. | MISSING | MISSING | MISSING | MISSING | No exact screenshot overlay/difference pass. Calendar, suggested actions and some dashboard sections are navigation-only, not new authorities. No real-time refresh/push aggregation. |

## Verification in this slice

- `tests/workspaces_browser.mjs`: desktop 1440px and mobile 390px mocked browser journeys cover create, settings save, Agent view, Asset empty state, Studio save and overflow. This harness does not exercise the full Today route.
- `tests/today_command_browser.mjs`: renders the Today dashboard’s shared renderer at desktop/mobile sizes with explicitly labeled browser-only fixtures; verifies priority ordering, no horizontal overflow and Workspace navigation. It does not call the real API runtime.
- Targeted API/UI contracts: 54 passed. All 15 inline PWA scripts passed JavaScript parse checks; Python compile and `git diff --check` passed.
- The requested local PWA URL did not respond during this check, so no live runtime screenshot or end-to-end Today browser journey could be captured.
- Browser responses for Agent catalog/summary are test fixtures only; no native application, physical device, live production-like data, WebGL scene, or screenshot-difference qualification was performed.
- Local changes only. No commit, push, merge or deployment.

## Data policy

Workspace and Project authorities persist genuine owner-created local records. The optional Screen17–20 reference Workspace remains clearly labeled demo data. The five new reference images themselves do not prove that their sample project, people, agents, models or file data exist. No fake records were inserted into canonical Agent, Project or file databases for this stage. A controlled, isolated development fixture set for Screens 21–25 remains future work.

## Blockers to the supplied master acceptance

1. Obtain/recover the approved character model, reference renders, thumbnails, textures/materials, rig and animation assets; a composite screenshot is not a substitute.
2. Select and implement one maintainable 3D engine, then qualify model loading, selection, camera, layers, version comparison, mobile gestures/accessibility and resource limits.
3. Define Workspace-scoped, authorization-checked relationships to canonical agents, work, assets, settings and activity; expose only real backend records.
4. Finish integration of Workspace settings/assets/team actions against their authorities; finish remaining Today controls and qualify all data-source edge cases.
5. Capture matching viewport screenshots and run overlays/difference review at reference desktop/mobile sizes.
6. Build and test every claimed native platform. This local environment has not provided native parity evidence.
