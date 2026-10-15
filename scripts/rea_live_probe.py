from __future__ import annotations

import json

from integrations.rea import REA_PACKAGE_VERSION, REAMCPRuntime


def main() -> int:
    runtime = REAMCPRuntime.from_environment()
    try:
        status = runtime.start()
        tools = runtime.list_tools()
        if not status.get("available"):
            raise RuntimeError("REA MCP runtime did not become available")
        if status.get("server_info", {}).get("version") != REA_PACKAGE_VERSION:
            raise RuntimeError("REA MCP runtime did not report the pinned version")
        if not tools:
            raise RuntimeError("REA MCP runtime advertised no tools")
        if any(not isinstance(item, dict) or not isinstance(item.get("name"), str) for item in tools):
            raise RuntimeError("REA MCP runtime advertised an invalid tool descriptor")
        print(
            json.dumps(
                {
                    "rea_version": REA_PACKAGE_VERSION,
                    "protocol_version": status.get("protocol_version"),
                    "server_info": status.get("server_info"),
                    "tool_count": len(tools),
                },
                sort_keys=True,
            )
        )
        return 0
    finally:
        runtime.close()


if __name__ == "__main__":
    raise SystemExit(main())
