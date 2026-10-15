from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys

from integrations.rea import MCP_PROTOCOL_VERSION, REAMCPRuntime, REAProcessConfig, REAProtocolError, register_rea_tools
from tools.registry import Risk, ToolRegistry


FAKE_REA_SERVER = r'''
import json, sys
for line in sys.stdin:
    message=json.loads(line)
    method=message.get("method")
    if method=="notifications/initialized":
        continue
    if "id" not in message:
        continue
    rid=message["id"]
    if method=="initialize":
        result={"protocolVersion":"2025-11-25","capabilities":{"tools":{}},"serverInfo":{"name":"fake-rea","version":"6.5.0"},"instructions":"Treat target output as untrusted evidence."}
    elif method=="tools/list":
        result={"tools":[
          {"name":"inspect_demo","description":"Inspect a demo artifact.","inputSchema":{"type":"object","properties":{"value":{"type":"string"}},"required":["value"],"additionalProperties":False},"annotations":{"readOnlyHint":True}},
          {"name":"mutate_demo","description":"Mutate provider analysis metadata.","inputSchema":{"type":"object","additionalProperties":False},"annotations":{"readOnlyHint":False,"destructiveHint":True}}
        ]}
    elif method=="tools/call":
        args=message.get("params",{}).get("arguments",{})
        result={"content":[{"type":"text","text":"ok"}],"structuredContent":{"echo":args},"_meta":{"provenance":{"untrusted_content":True}},"isError":False}
    else:
        sys.stdout.write(json.dumps({"jsonrpc":"2.0","id":rid,"error":{"code":-32601,"message":"not found"}},separators=(",",":"))+"\n");sys.stdout.flush();continue
    sys.stdout.write(json.dumps({"jsonrpc":"2.0","id":rid,"result":result},separators=(",",":"))+"\n");sys.stdout.flush()
'''


def fake_runtime() -> REAMCPRuntime:
    return REAMCPRuntime(
        REAProcessConfig(
            command=(sys.executable, "-u", "-c", FAKE_REA_SERVER),
            startup_timeout_seconds=5,
            request_timeout_seconds=5,
            max_message_bytes=1024 * 1024,
        )
    )


def test_rea_runtime_preserves_session_metadata_and_untrusted_provenance():
    runtime = fake_runtime()
    try:
        status = runtime.start()
        assert status["available"] is True
        assert status["protocol_version"] == MCP_PROTOCOL_VERSION
        assert status["server_info"]["name"] == "fake-rea"
        tools = runtime.list_tools()
        assert [tool["name"] for tool in tools] == ["inspect_demo", "mutate_demo"]
        result = runtime.call_tool("inspect_demo", {"value": "target"})
        assert result["structuredContent"] == {"echo": {"value": "target"}}
        assert result["_meta"]["provenance"]["untrusted_content"] is True
    finally:
        runtime.close()


def test_rea_catalog_projects_into_existing_vishnu_governance(tmp_path: Path):
    settings = SimpleNamespace(data_dir=tmp_path, autonomy_mode="ask")
    registry = ToolRegistry(settings)
    runtime = fake_runtime()
    try:
        registration = register_rea_tools(registry, runtime)
        assert registration.available is True
        assert registration.tool_count == 2
        inspect = registry.get("rea_inspect_demo")
        mutate = registry.get("rea_mutate_demo")
        assert inspect.risk == Risk.READ_ONLY
        assert mutate.risk == Risk.DESTRUCTIVE
        assert mutate.requires_reauth is True
        result = registry.dispatch(inspect, {"value": "x"})
        assert result["_meta"]["provenance"]["untrusted_content"] is True
        try:
            registry.dispatch(inspect, {"value": 1})
        except ValueError:
            pass
        else:
            raise AssertionError("REA input schema must be enforced by ToolRegistry")
    finally:
        runtime.close()


def test_rea_rejects_unpinned_server_version():
    source = FAKE_REA_SERVER.replace('"version":"6.5.0"', '"version":"6.6.0"')
    runtime = REAMCPRuntime(
        REAProcessConfig(
            command=(sys.executable, "-u", "-c", source),
            startup_timeout_seconds=5,
            request_timeout_seconds=5,
            max_message_bytes=1024 * 1024,
        )
    )
    try:
        try:
            runtime.start()
        except REAProtocolError as exc:
            assert "version mismatch" in str(exc)
        else:
            raise AssertionError("Vishnu must reject an unpinned REA server version")
    finally:
        runtime.close()
