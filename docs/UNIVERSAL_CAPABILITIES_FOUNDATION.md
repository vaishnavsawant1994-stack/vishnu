# Universal Capabilities release tracker

Status reviewed 2026-10-12 for Vishnu PR #183 (`feature/universal-capabilities-foundation`).

This work extends Vishnu's existing integration registry, permission checks, tool registry, approval manager, encrypted vault, audit store, and agent execution path. The catalog remains inert until an owner connects and approves an operation. It does not create a second connector authority.

## Implemented on the PR head

- Public API catalog and OpenAPI operation discovery with unsupported schemas left inert.
- Owner controlled OpenAPI GET execution and explicitly approved bounded POST, PUT, PATCH, and DELETE operations.
- MCP Streamable HTTP initialization, tool discovery, owner risk review, and governed calls.
- Encrypted bearer token and API key header storage, credential rotation, revocation, and redacted connection metadata.
- Durable single-use write approvals bound to exact parameters and execution context.
- Rehydration of approved capabilities into the existing shared Vishnu tool registry after restart.
- Responsive web capability console and desktop/Android entry points.
- Isolated self-signed localhost HTTPS bridge tests for the API and MCP paths, including failure cases.

## Additional hardening in this change

- Resolve external destinations at dispatch and pin the TCP socket to a validated public IP. TLS SNI and certificate validation continue to use the approved hostname.
- Reject mixed public/private DNS answers and disable environment proxy routing for these requests.
- Record a provider's response as `accepted`, not `succeeded`; successful HTTP or MCP response alone is not proof of persisted side effects. OpenAPI writes remain unverified without an independent provider verification contract.

## Qualification evidence and limits

| Requirement | Status | Evidence or blocker |
|---|---|---|
| CI, Reliability and Security, qualification, release authority, Android companion/instrumentation, responsive checks, and macOS/Ubuntu/Windows packages | Passed on baseline `7ec36a7831f443cd0104ef900caad648f7087677` | GitHub Actions runs associated with that exact commit all report success. The new hardening commit still requires fresh CI. |
| Local HTTPS OpenAPI and MCP bridge regression | Implemented; baseline fixture checks reported passing | Uses a local self-signed fixture with test-only credentials; this is not public-provider evidence. |
| DNS validation and DNS-rebinding resistance | Socket pinning implemented here; fresh CI/adversarial qualification pending | This workspace cannot independently demonstrate an externally controlled public DNS rebinding environment. |
| Public CA-trusted OpenAPI and MCP qualification | Blocked | Requires a controlled public HTTPS service, public DNS, reachable egress, and disposable credentials. |
| OpenAPI write persistence verification | Incomplete | Requires provider-specific read-after-write contracts. Writes are one-shot and reported unverified until then. |
| OAuth authorization-code/PKCE and token lifecycle | Incomplete | No generic provider registration/redirect configuration is available in this task environment. |
| Complete native desktop, Android, and iOS lifecycle screens | Incomplete | Current desktop and Android entry points open the responsive web console; iOS management screens and native lifecycle flows are absent. |
| Full agent/workflow cancellation, restart recovery, and live capability qualification | Partial | Approved-tool rehydration is implemented; full workflow pause/cancel/recovery evidence remains outstanding. |
| Independent security/release review, merge, and production deployment | Not completed | PR must remain draft and unmerged until mandatory evidence and human review are available. No deployment has been performed. |

## Current verification record

- Prior baseline head: `7ec36a7831f443cd0104ef900caad648f7087677`.
- Hardening head: `7c594026495df8b0d267aa9e889c684ca59d253e`.
- Required GitHub workflows on the hardening head: CI (including full `pytest -q`), Reliability and Security, Qualification Evidence Closure, Governed Release Authority, Android Companion, Android Instrumentation, responsive checks, and macOS/Ubuntu/Windows Package Validation all passed on 2026-10-12.
- Local static verification for the hardening change: `python -m compileall -q integrations/discovery tests/test_capability_openapi_execution.py tests/test_capability_discovery_mcp.py` and `git diff --check` pass.
- Local pytest execution was unavailable in this workspace because its configured Python runtimes did not have `pytest` installed; the exact-head GitHub CI run executed and passed the full suite.

## Release decision

Keep PR #183 draft and unmerged. Do not deploy. Public-provider, provider-side write verification, OAuth, native interface, full agent/workflow, and independent review gates still require implementation or evidence. A green automated baseline is not a release certification.
