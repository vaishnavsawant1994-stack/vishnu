# REA reverse-engineering subsystem

Vishnu integrates the official [REA](https://github.com/morluto/rea) runtime as a bounded local reverse-engineering subsystem. Vishnu does not reimplement REA's analyzers or flatten its Evidence model. It owns a long-lived stdio MCP process and projects REA's live tool catalog into the existing `ToolRegistry` so Vishnu's approvals, emergency stop, permission model and audit path remain authoritative around calls.

## Runtime contract

- REA package pin: `rea-agents@6.5.0`.
- Default command: `npx -y rea-agents@6.5.0 mcp`.
- MCP handshake revision requested by Vishnu: `2025-11-25` (the client also accepts REA negotiating `2025-06-18` or `2025-03-26`).
- One long-lived REA process is retained for the Vishnu runtime so REA's active target, provider binding, Evidence ledger, snapshots and cleanup semantics persist across calls.
- `tools/list` is read from the live REA process. Each upstream operation is projected as `rea_<upstream_name>`.
- REA input JSON Schemas are enforced at Vishnu's final `ToolRegistry.dispatch` boundary.
- Complete MCP `CallToolResult` objects are returned unchanged. Vishnu therefore preserves `content`, `structuredContent`, `isError`, Evidence references and `_meta.provenance.untrusted_content` rather than rewriting target-derived data.
- `rea_catalog` exposes REA's authoritative live catalog. `rea_status` exposes negotiated server/runtime diagnostics.

REA's MCP tool annotations determine the Vishnu risk class without weakening REA's own effect model. Explicit read-only tools remain `READ_ONLY`; non-read-only but non-destructive operations such as additive Evidence/session recording map to `REVERSIBLE`; tools marked destructive become `DESTRUCTIVE`. They then pass through the normal Vishnu owner-approval and emergency-stop authority.

## Configuration

The integration is enabled by the application runtime. The command and bounds can be changed with:

```text
VISHNU_REA_COMMAND=npx -y rea-agents@6.5.0 mcp
VISHNU_REA_STARTUP_TIMEOUT_SECONDS=90
VISHNU_REA_REQUEST_TIMEOUT_SECONDS=120
VISHNU_REA_MAX_MESSAGE_BYTES=33554432
```

`VISHNU_REA_COMMAND` is tokenized without shell execution. Production images may install/pin REA ahead of time and set this value to an absolute/local `rea mcp` command to avoid first-use npm acquisition.

## Analysis engines

REA remains the authority for its provider support and prerequisites. Ghidra, Hopper, IDA, JADX, JEB, ADB, Binwalk/Unblob, Frida and other engines retain their own installation and licensing requirements. Vishnu does not silently install commercial engines or grant licenses for them.

REA is local-first but **not a sandbox**. Untrusted binaries and runtime targets are still parsed or executed by the selected local provider with the operating-system user's authority. Use VM/container isolation when the target risk requires it.

## Updating REA

Do not float the package version in production. Update `REA_PACKAGE_VERSION`, qualify the new live catalog and representative real-provider lanes, confirm licensing/security changes, and only then advance the pin.
