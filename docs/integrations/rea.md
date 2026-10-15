# REA reverse-engineering subsystem

Vishnu integrates the official [REA](https://github.com/morluto/rea) runtime as a bounded local reverse-engineering subsystem. Vishnu does not reimplement REA's analyzers, provider router, BinarySession, Evidence semantics, or target handling. It owns one long-lived stdio MCP process and projects REA's live tool catalog into Vishnu's existing `ToolRegistry`, so Vishnu's owner permissions, approvals, emergency stop, typed call boundary, and audit/recovery architecture remain authoritative around every call.

## Exact runtime contract

- Official package: `rea-agents`.
- Pinned version: **6.5.0**.
- Transport: stdio MCP using `rea mcp`, matching REA's published `server.json`.
- MCP revision requested by Vishnu: `2025-11-25`; Vishnu also accepts REA negotiating `2025-06-18` or `2025-03-26`.
- Vishnu rejects a server whose `serverInfo.version` is not exactly `6.5.0`.
- One long-lived REA process is retained so REA's active target, provider binding, Evidence ledger, snapshots, cleanup and session semantics persist across calls.
- `tools/list` is read from the live REA process. Every upstream operation is projected as `rea_<upstream_name>`.
- REA input JSON Schemas are enforced again at Vishnu's final `ToolRegistry.dispatch` boundary. REA remains the final authority for its complete schema semantics.
- Every upstream MCP `CallToolResult` field is preserved, including `content`, `structuredContent`, `isError`, Evidence references, limitations, and `_meta.provenance.untrusted_content`. Vishnu adds a separate `_vishnu_trust_boundary` marker so target-derived data stays explicitly classified as untrusted when projected into Vishnu's model-facing result path.
- `rea_catalog` exposes REA's authoritative live catalog. `rea_status` exposes the negotiated server identity and runtime state.

REA's MCP annotations determine the minimum Vishnu risk class. Explicit read-only tools remain `READ_ONLY`; tools marked destructive become `DESTRUCTIVE`; all other operations fail closed as `EXTERNAL_SIDE_EFFECT`. Calls then pass through the normal Vishnu permission/approval/emergency-stop authority.

## Installation

Vishnu installs REA into its own `.rea/` prefix rather than fetching code when a reverse-engineering request begins:

```text
python scripts/install_rea.py
```

The installer requires the Node.js range published by REA (`^22.19.0 || ^24.11.0 || >=26.0.0`), installs `rea-agents@6.5.0` with an exact version, and verifies the resulting `rea --version`. The normal macOS/Linux/Windows Vishnu source installers invoke this step.

Desktop package builds also install the exact REA package before freezing Vishnu and include the resulting `.rea/` payload in the DMG/MSI/DEB application files. Node.js remains a runtime prerequisite because the official REA executable is a Node application; Vishnu does not silently download or replace Node when the packaged application starts.

At runtime Vishnu prefers the bundled/repository-local `.rea/node_modules/.bin/rea` and falls back to `rea` on `PATH`. A deployment can override the executable with `VISHNU_REA_COMMAND`; the value is tokenized and passed directly to `subprocess.Popen` with `shell=False`.

Optional runtime bounds:

```text
VISHNU_REA_COMMAND=/absolute/path/to/rea mcp
VISHNU_REA_STARTUP_TIMEOUT_SECONDS=90
VISHNU_REA_REQUEST_TIMEOUT_SECONDS=120
VISHNU_REA_MAX_MESSAGE_BYTES=33554432
```

## Analysis engines

REA remains the authority for its provider support and prerequisites. Its Ghidra, Hopper, IDA/Hex-Rays, JADX/JEB/ADB, GDB/Rizin/Frida, firmware, browser, packet, signal, WASM/EVM and other providers retain the same prerequisites and behavior they have when REA is run directly. Vishnu does not replace or emulate those engines.

Commercial providers still require valid licenses. REA is local-first but **not a sandbox**: untrusted binaries, applications and runtime targets may be parsed or executed by a provider with the operating-system user's authority. Use a VM/container or other isolation appropriate to the target risk.

## Evidence and prompt-injection boundary

REA remains authoritative for reverse-engineering Evidence. Vishnu does not flatten REA Evidence into a weaker duplicate record. Evidence IDs/references and REA's confidence/authority/limitations remain in the MCP result.

Target-derived strings, symbols, decompiled code, page text, scripts, network data, logs and file content are untrusted data, not instructions. Vishnu preserves REA's `_meta.provenance.untrusted_content` marker and adds its own fixed trust-boundary marker/instruction alongside the upstream result. The projected tool descriptions repeat the same rule so embedded target text cannot legitimately grant execution authority, weaken approvals, or become an instruction merely because a model can read it.

## Updating REA

Do not float the package version in production. To update REA, change the pinned version, re-run the fake-MCP boundary tests and a real REA catalog/provider qualification lane, review upstream security/licensing changes, and only then advance the pin.
