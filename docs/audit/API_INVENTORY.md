# API Inventory

Baseline: `a8d3310b4d9090a42800621b1b27cb6045443c1e`.

The live API is modular FastAPI code under `server/`, not a single route file. Discovered modules include primary `api.py` plus activities, agent continuity/work requests/workforce, approvals/approval center, Apps & Tools/capabilities and additional owner/device/product/data/Sensorium/voice/runtime routes.

## Security classes

- **Owner** — authenticated trusted owner/device context; sensitive operations may require `device:admin` plus recent reauthentication.
- **Device** — trusted device session/scope boundary.
- **Loopback/internal** — runtime-local/provider-specific endpoints with explicit trust assumptions.
- **Health/readiness** — operational status only; must not leak secrets.
- **Qualification/debug** — must remain non-production or explicitly gated.

## Source-verified capability route family

`server/apps_tools_api.py` exposes the Apps & Tools/capability family under `/iphone/api/apps-tools`, including tool/app listing/detail, capability search/detail/history/audit, OpenAPI import, MCP server listing/add/discovery and MCP capability approval/connection lifecycle. The implementation verifies active trusted device state/scopes, requires recent owner reauthentication for sensitive imports/connections, bounds request sizes, stores credential references through SecretVault, audits lifecycle events and rehydrates approved capabilities into the shared ToolRegistry after restart.

## Exhaustive-route status

An exact method/path/consumer count for **every** server route is `NOT VERIFIED` in this audit PR. The repository is large and an AST/framework-native route generator has not yet been committed. This is intentionally not replaced with a regex-derived or guessed count.

## Required per-route fields for the follow-up generator

`method, path, module, handler, auth, authorization/scope, approval, input schema, output schema, state modified, external effect, UI/native/internal consumers, tests, lifecycle status`.

## Current risks checked conceptually

Sensitive owner operations must not be anonymous; write/destructive actions must not bypass canonical approval/policy; capability credentials must remain references/redacted; revoked devices/connections must fence future execution; debug/qualification routes must not silently become production authority. Any exhaustive unused/duplicate/nonexistent-endpoint result remains `NOT VERIFIED` until generated from the current AST/router graph.
