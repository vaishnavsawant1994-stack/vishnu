# Vishnu OS Screens 21–25 — first functional continuation

**Status:** Partial implementation on top of draft Screens 16–20 foundation (PR #255). Not merged, not deployed, not cross-platform qualified.

**Base:** PR #255 head `721fbe0664ede9fb6325bfabeaf34adb0d2910b9`; that branch is not merged into `main`.

This change extends the authenticated PWA Workspace shell. It does not create a second Project, Work, Agent, Resource or Approval runtime. Visual references are the five owner-approved composite desktop/iPhone images for Screens 21–25, which are design targets, not screenshots from running products.

## Feature truth ledger

| Screen | Real functionality in this slice | Material gaps / not claimed |
|---|---|---|
| 21 — Spatial View | Responsive GPU/WebGL rendering of Project-node geometry sourced only from verified linked canonical Projects; mouse/touch orbit and pinch/wheel zoom; accessible DOM object controls, Project links, reset and degraded fallback | **Not the approved character-production 3D scene.** WebGL currently renders only Project primitives, not the missing character source mesh, rig, animation or renders. No complete camera presets, saved spatial views or full 3D compare. Preview intentionally labeled. |
| 22 — Team / Agents | Reads canonical global Agent catalogue with search, selection, identity/role/description Inspector, opens existing Agent manager | Workspace membership, Agent grants, real per-Workspace active assignments, local permission mutations, Agent creation and collaborator invites not provided by current Workspace API. No fake values shown. |
| 23 — Files & Assets | Authorized GET of each linked canonical Project and aggregation of its real files/deliverables; search, source/deliverable/pinned filters, selection, metadata Inspector, deep link to Project Files; no fabricated asset state | Workspace file/artifact link creation and Workspace-level Resource listing still unavailable. The displayed grid is limited to existing linked Projects' files, not arbitrary 3D resources; true thumbnails, Workspace upload, version comparisons, storage availability and on-demand retrieval are not qualified. |
| 24 — Workspace Settings | Real owner-authorized Workspace name/description PATCH with persistence, favorite toggle PATCH, archive/restore PATCH with confirmation; responsive settings index and preview | Data policy, capability grants, invitation sharing, module preferences, cover uploads, delete impact and Workspace-specific intelligence settings require canonical API support. Unsupported categories explicitly marked. |
| 25 — Today | Cross-Workspace canonical Work + Attention GET projections, local time greeting, attention and Work drill-through, refresh, truthful empty/error states | Full calendar, persisted personal continuation, recommendation engine, accurate global assigned-agent counts and native notification integration unavailable in these APIs. |

## Security/truth boundaries

- All mutations use the existing owner-authenticated Workspace API and inherited trusted-device checks.
- Agent listing is explicitly called **global Agent catalogue**, not Workspace team membership.
- Linked Project assets are verified from authorized canonical GET /projects/{id}; no fake screenshot artifacts or file locations/sync states are guessed.
- Today reads canonical read-only Work/Attention projections and does not execute privileged actions.
- Archive only changes Workspace status and preserves related canonical resources.
- The 3D character in the reference is not a real linked mesh. WebGL Project-node geometry is genuine but does not qualify the requested character scene. Do not advertise Screen 21 as complete.

## Next backend integration tasks

1. Design authorized WorkspaceResource query/link endpoints that check actual Resource permission for every listed resource. Preserve local-first metadata vs full-source availability.
2. Add WorkspaceAgentAssignment scoped read/mutation routes using canonical Agent, capability, approval and Work authorities; do not duplicate agent tables.
3. Implement shared spatial WebGL renderer and asset import with actual approved GLB/GLTF/rig/textures and hardware qualification.
4. Add versioned Workspace module, data-policy, notification and inheritance settings only after authority review.
5. Add canonical schedule/calendar/continuation and Today personalization adapters.
6. Reconcile PR #255, complete end-to-end live owner tests, visual screenshot comparisons, and Android/iOS/native desktop embedding.
7. Do not merge or deploy before exact-head required CI and owner approval.

## QA

The existing `tests/vishnu_os_workspaces_browser.mjs` now exercises navigation for Screens 21–25 and Settings persistence using an explicit isolated transport fixture at mobile, tablet and desktop widths.

Browser fixture tests do **not** prove real owner authorization, WebGL behavior, Android/iOS native parity, visual pixel fidelity, local-first data plane or production readiness.
