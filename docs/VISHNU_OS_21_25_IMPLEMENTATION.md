# Vishnu OS Screens 21–25 — first functional continuation

**Status:** Partial implementation on top of draft Screens 16–20 foundation (PR #255). Not merged, not deployed, not cross-platform qualified.

**Base:** PR #255 head `721fbe0664ede9fb6325bfabeaf34adb0d2910b9`; that branch is not merged into `main`.

This change extends the authenticated PWA Workspace shell. It does not create a second Project, Work, Agent, Resource or Approval runtime. Visual references are the five owner-approved composite desktop/iPhone images for Screens 21–25, which are design targets, not screenshots from running products.

## Feature truth ledger

| Screen | Real functionality in this slice | Material gaps / not claimed |
|---|---|---|
| 21 — Spatial View | Responsive spatial Project-object preview populated solely from verified linked canonical Projects; object selection opens the real Project; layout rotation/reset and accessible object buttons | **Not a genuine WebGL/mesh spatial engine.** No approved character source mesh, asset adapters, rig/animation/renders, true orbit camera, saved spatial views or full 3D compare. Preview intentionally labeled. |
| 22 — Team / Agents | Reads canonical global Agent catalogue with search, selection, identity/role/description Inspector, opens existing Agent manager | Workspace membership, Agent grants, real per-Workspace active assignments, local permission mutations, Agent creation and collaborator invites not provided by current Workspace API. No fake values shown. |
| 23 — Files & Assets | Honest Workspace resource-link view and links to canonical Projects/Knowledge, no simulated resource cards | Workspace API currently rejects file/artifact link creation and does not provide authorized Resource listing/versions/availability/upload. Cannot produce reference card grid honestly. |
| 24 — Workspace Settings | Real owner-authorized Workspace name/description PATCH with persistence, favorite toggle PATCH, archive/restore PATCH with confirmation; responsive settings index and preview | Data policy, capability grants, invitation sharing, module preferences, cover uploads, delete impact and Workspace-specific intelligence settings require canonical API support. Unsupported categories explicitly marked. |
| 25 — Today | Cross-Workspace canonical Work + Attention GET projections, local time greeting, attention and Work drill-through, refresh, truthful empty/error states | Full calendar, persisted personal continuation, recommendation engine, accurate global assigned-agent counts and native notification integration unavailable in these APIs. |

## Security/truth boundaries

- All mutations use the existing owner-authenticated Workspace API and inherited trusted-device checks.
- Agent listing is explicitly called **global Agent catalogue**, not Workspace team membership.
- Assets are not fabricated from approved reference images and no file locations/sync state are guessed.
- Today reads canonical read-only Work/Attention projections and does not execute privileged actions.
- Archive only changes Workspace status and preserves related canonical resources.
- The 3D character in the reference is not a real linked mesh, so this UI must not be advertised as finished Screen 21.

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
