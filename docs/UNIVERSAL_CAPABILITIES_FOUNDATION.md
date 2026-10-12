# Universal Capabilities release tracker

Status reviewed 2026-10-12 for Vishnu PR #183 (`feature/universal-capabilities-foundation`). Current implementation commit: `1b3d91b18dab4df4a051182a02081e01da3b4343` (qualification still running).

This work extends Vishnu's existing integration registry, permission checks, tool registry, approval manager, encrypted vault, audit store, and agent execution path. The catalog remains inert until an owner connects and approves an operation. It does not create a second connector authority.

## Implemented on the PR head

- Public API catalog and OpenAPI operation discovery with unsupported schemas left inert.
- Owner controlled OpenAPI GET execution and explicitly approved bounded POST, PUT, PATCH, and DELETE operations.
- MCP Streamable HTTP initialization, tool discovery, owner risk review, and governed calls.
- Encrypted bearer token and API key header storage, credential rotation, revocation, and redacted connection metadata.
- Durable single-use write approvals bound to exact parameters and execution context.
- Rehydration of approved capabilities into the existing shared Vishnu tool registry after restart.
- Responsive web capability console.
- Android native capability management client: browser-based owner authorization with PKCE, hashed server session exchange, encrypted Android preferences, API scope enforcement, capability discovery/details, OpenAPI import, MCP discovery, connections, explicit write approval, execution testing, history/audit, credential rotation, disconnect, and logout.
- Isolated self-signed localhost HTTPS bridge tests for the API and MCP paths, including failure cases.

## Additional hardening in this change

- Resolve external destinations at dispatch and pin the TCP socket to a validated public IP. TLS SNI and certificate validation continue to use the approved hostname.
- Reject mixed public/private DNS answers and disable environment proxy routing for these requests.
- Record a provider's response as `accepted`, not `succeeded`; successful HTTP or MCP response alone is not proof of persisted side effects. OpenAPI writes remain unverified without an independent provider verification contract.

## Qualification evidence and limits

| Requirement | Status | Evidence or blocker |
|---|---|---|
| Scoped native session backend | Implemented; exact-head qualification pending | Commit `110e418791919fd40edd80bc153a66faef692078`; PKCE S256, one-time 90-second code, exact client/redirect binding, atomic exchange, hashed tokens, 8-hour TTL, rotation, logout, device revoke, and endpoint tests. Initial CI exposed five test-fixture/compatibility failures; fixes are in `1b3d91b18dab4df4a051182a02081e01da3b4343`; rerun underway. |
| Android native capability management | Implemented; Android build/instrumentation pending | Commit `1b3d91b18dab4df4a051182a02081e01da3b4343`; uses native API routes and encrypted session storage. Public App Link association/signing fingerprint and production redirect registration are not configured, so end-to-end authentication is blocked until infrastructure configuration. |
| CI, Reliability and Security, qualification, release authority, Android companion/instrumentation, responsive checks, and macOS/Ubuntu/Windows packages | Previously passed on `ab548340d16e1cc80268ebe354d2b55114145132`; exact-head rerun pending | The earlier green result predates the native-auth and Android changes and does not qualify the current head. |
| Local HTTPS OpenAPI and MCP bridge regression | Implemented; baseline fixture checks reported passing | Uses a local self-signed fixture with test-only credentials; this is not public-provider evidence. |
| DNS validation and DNS-rebinding resistance | Socket pinning implemented; automated tests passed | Public DNS rebinding against an externally controlled hostname was not run; hosted network qualification remains open. |
| Public CA-trusted OpenAPI and MCP qualification | Blocked | Requires a controlled public HTTPS service, public DNS, reachable egress, and disposable credentials. |
| OpenAPI write persistence verification | Incomplete | Requires provider-specific read-after-write contracts. Writes are one-shot and reported unverified until then. |
| OAuth authorization-code/PKCE and token lifecycle | Incomplete | No generic provider registration/redirect configuration is available in this task environment. |
| Native desktop and iOS lifecycle screens | Incomplete | Desktop and iOS management flows are not implemented. Android client is present, but App Link verification and exact-head qualification remain pending. |
| Full agent/workflow cancellation, restart recovery, and live capability qualification | Partial | Approved-tool rehydration is implemented; full workflow pause/cancel/recovery evidence remains outstanding. |
| Independent security/release review, merge, and production deployment | Not completed | PR must remain draft and unmerged until mandatory evidence and human review are available. No deployment has been performed. |

## Current verification record

- Prior baseline head: `7ec36a7831f443cd0104ef900caad648f7087677`.
- Hardening head: `7c594026495df8b0d267aa9e889c684ca59d253e`.
- Required GitHub workflows on the hardening head: CI (including full `pytest -q`), Reliability and Security, Qualification Evidence Closure, Governed Release Authority, Android Companion, Android Instrumentation, responsive checks, and macOS/Ubuntu/Windows Package Validation all passed on 2026-10-12.
- Native-session commit: `110e418791919fd40edd80bc153a66faef692078`. Its CI run reported 5 failures and 3,089 passes, including native test fixture assumptions and missing optional registry injection in older browser-only router tests.
- Android/auth fixes: `1b3d91b18dab4df4a051182a02081e01da3b4343`. Exact-head CI, security, Android build/instrumentation, and platform package workflows are currently in progress; do not treat as passed until completed.
- Local static verification for the hardening change: `python -m compileall -q integrations/discovery tests/test_capability_openapi_execution.py tests/test_capability_discovery_mcp.py` and `git diff --check` pass.
- Local pytest execution was unavailable in this workspace because its configured Python runtimes did not have `pytest` installed; the exact-head GitHub CI run executed and passed the full suite.

## Release decision

Keep PR #183 draft and unmerged. Do not deploy. Public-provider qualification, provider-side write verification, generic capability OAuth, native desktop/iOS management, Android verified-link setup, full agent/workflow cancellation and recovery, exact-head qualification, independent review, merge approval, and release/deployment gates remain open. A green automated baseline is not a release certification.
