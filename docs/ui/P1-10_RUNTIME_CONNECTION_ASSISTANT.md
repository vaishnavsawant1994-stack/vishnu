# Vishnu 2.0 · P1-10 Runtime Connection Assistant

Screen ID: P1-10. **Conditional, never tenth mandatory onboarding step.** Design reference supplied by owner: 1536×1024 cyan neural sphere, three runtime cards and holographic platform. P1-09 is an unmerged dependency; this branch is deliberately stacked on feat/p1-09-recovery-complete.

## Entry and resume

- The existing PWA first-run adapter calls the canonical same-origin \`/iphone/api/status\` and \`/iphone/api/access/options\` paths.
- After the existing \`check()\` cannot authenticate, P1-10 appears only when first-run options are unavailable **and** the canonical options probe fails on the network or reports HTTP 503. HTTP 401/403 is an owner-authentication state and must not be mislabeled as a missing runtime.
- Existing creation, login, joining, recovery and Home navigation are untouched on a responding runtime.
- A returning restored owner can enter P1-10 from P1-09 if session verification fails due to an unreachable runtime. Back uses the originating recovery result, not a hard-coded previous screen.
- The web PWA cannot launch when it has never been served and has no offline shell. Offline P1-10 therefore requires an installed/cached PWA shell or a separately packaged native client. Availability in a completely fresh, unreachable-host browser is impossible without preinstallation or another hosting origin.

## What works versus what does not

| Choice | Implemented in current PWA | Not claimed |
| --- | --- | --- |
| Existing Vishnu | Validates a user-typed HTTPS runtime origin (loopback HTTP only in local development), prohibits URL credentials, query parameters and fragments; explicitly confirms top-level navigation to \`/iphone/\`. That origin performs its own login and device-approval ceremony. No secrets transferred. | CORS-free cross-origin server identity proof, automatic QR scanning, LAN discovery, deep-link pairing, credential transfer. The address is **not** a connected or authenticated status. |
| This device | Checks the canonical same-origin \`/iphone/api/access/options\` route for an already running Vishnu. Links to checked-in Windows/local-dev startup instructions. Unsupported bare browser/device setup is clearly explained. | Installing Python/native dependencies from a web page; launching a process without owner permission; unrestricted Android/iOS local Python runtime. |
| Online | Links to the versioned \`render.yaml\` template and the hosting dashboard, gated by cost/consent acknowledgement. Owners return to the existing-runtime choice with their deployment's HTTPS address. | Provider account creation, billing, infrastructure provisioning, server deployment, hosted runtime auto-enrollment, a mandatory GPU or data sync. |

Server status remains authoritative. Client-side choice state is presentation-only and never marks runtime connected. The page shares the exact Phase 1 perspective-projected 3D node sphere (rotation, interactive pointer drag, reduced-motion and disposal) extracted from P1-09 into \`pwa/neural-sphere.js\`.

## Security boundaries

No plaintext password, recovery code, provider key, pairing token, server grant, or device credential is read or persisted. The browser's HttpOnly, SameSite cookies are scoped to their current origin. The flow refuses HTTP remote addresses and URL userinfo/query/fragment; a user must explicitly confirm address navigation. New-origin owner authentication and device trust are enforced by existing \`OwnerAccessStore\`, \`DeviceRegistry\`, \`PwaSessionMiddleware\`, and the canonical join/approval APIs.

The Render deployment template is existing infrastructure, not an API integration; hosted costs and geography require separate owner approval. Do not set \`canContinue\` or \`connected\` merely because navigation or a deployment guide was opened.

## Visual review and acceptance gates

Browser fixtures capture P1-10 at 1536×1024, 1920×1080, 1366×768, 820×1180, 390×844, 430×932 and 360×800. These are **preview fixtures**, not actual production-connected screenshots.

- \`node tests/runtime_assistant_browser.mjs\` validates all three mutually exclusive options, keyboard selection, Back origin, unsafe URL rejection, two-step address confirmation, offline probe and horizontal overflow.
- \`node tests/recovery_complete_browser.mjs\` guards reuse of the P1-09 core.
- \`python -m pytest tests/test_p3_iphone_pwa.py tests/test_project_autonomy_ui_contract.py tests/test_global_work_awareness_ui.py -q\` checks existing server and cache contracts.
- Validate exact-head UI, security, PWA mobile, package, release and CI gates before merging. Historical issue #267 documents certifi/Pillow audit blockers on the base branch.

## Deferred for platform-level work

The standalone native Windows/macOS/Linux installer, Android/iOS native provisioning screens, QR/deep-link flows, hosted provider authorization, durable runtime-target chooser and physical-device performance are *not* implemented by this bounded PWA change. Those must be qualified on supported real devices and backends before claiming universal P1-10 functionality. No production deployment is authorized.
