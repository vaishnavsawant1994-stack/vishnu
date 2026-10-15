from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping

from tools.registry import Risk, Tool, ToolRegistry

from .runtime import REAMCPRuntime, REAUnavailableError


@dataclass(frozen=True, slots=True)
class REARegistration:
    available: bool
    tool_count: int
    public_names: tuple[str, ...]
    error: str | None = None


def _public_tool_name(upstream_name: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_]+", "_", upstream_name).strip("_")
    if not normalized:
        raise ValueError("REA advertised an unusable tool name")
    return f"rea_{normalized}"


def _risk_from_annotations(descriptor: Mapping[str, Any]) -> Risk:
    annotations = descriptor.get("annotations")
    annotations = annotations if isinstance(annotations, Mapping) else {}
    if annotations.get("destructiveHint") is True:
        return Risk.DESTRUCTIVE
    if annotations.get("readOnlyHint") is True:
        return Risk.READ_ONLY
    # REA intentionally marks additive Evidence/session recording as non-read-only.
    # When destructiveHint remains false, map that bounded local mutation to
    # Vishnu's reversible class rather than inventing a stronger external effect.
    return Risk.REVERSIBLE


def _tool_handler(runtime: REAMCPRuntime, upstream_name: str):
    def handler(parameters: dict[str, Any]) -> dict[str, Any]:
        return runtime.call_tool(upstream_name, parameters)

    return handler


def _status_tool(runtime: REAMCPRuntime) -> Tool:
    return Tool(
        name="rea_status",
        description="Inspect Vishnu's local REA reverse-engineering MCP runtime, negotiated protocol, server identity, diagnostics and recent notifications.",
        handler=lambda _parameters: runtime.status(),
        risk=Risk.READ_ONLY,
        connector_id="rea",
        capability="reverse_engineering:status",
        input_schema={"type": "object", "additionalProperties": False},
    )


def _catalog_tool(runtime: REAMCPRuntime) -> Tool:
    return Tool(
        name="rea_catalog",
        description="Return REA's authoritative live MCP tool catalog exactly as advertised by the connected REA runtime.",
        handler=lambda _parameters: {"tools": runtime.list_tools(), "runtime": runtime.status()},
        risk=Risk.READ_ONLY,
        connector_id="rea",
        capability="reverse_engineering:catalog",
        input_schema={"type": "object", "additionalProperties": False},
    )


def register_rea_tools(registry: ToolRegistry, runtime: REAMCPRuntime) -> REARegistration:
    """Project the live REA MCP catalog into Vishnu's governed ToolRegistry.

    Input schemas and descriptions come directly from REA. Handler results stay
    as complete MCP CallToolResult objects so Evidence references, structured
    content, errors, and untrusted-content provenance survive unchanged.
    """
    registry.register(_status_tool(runtime))
    try:
        descriptors = runtime.list_tools()
    except (REAUnavailableError, OSError, RuntimeError, ValueError) as exc:
        return REARegistration(False, 0, ("rea_status",), str(exc))

    registry.register(_catalog_tool(runtime))
    names = ["rea_status", "rea_catalog"]
    upstream_seen: set[str] = set()
    public_seen = set(names)
    for descriptor in descriptors:
        upstream_name = descriptor.get("name")
        if not isinstance(upstream_name, str) or not upstream_name:
            raise ValueError("REA advertised a tool without a valid name")
        if upstream_name in upstream_seen:
            raise ValueError(f"REA advertised duplicate tool {upstream_name}")
        upstream_seen.add(upstream_name)
        public_name = _public_tool_name(upstream_name)
        if public_name in public_seen:
            raise ValueError(f"REA tool name collision after Vishnu projection: {public_name}")
        public_seen.add(public_name)
        description = descriptor.get("description")
        if not isinstance(description, str) or not description.strip():
            description = f"REA reverse-engineering operation {upstream_name}."
        input_schema = descriptor.get("inputSchema")
        if input_schema is not None and not isinstance(input_schema, Mapping):
            raise ValueError(f"REA tool {upstream_name} advertised an invalid input schema")
        annotations = descriptor.get("annotations")
        annotations = annotations if isinstance(annotations, Mapping) else {}
        risk = _risk_from_annotations(descriptor)
        registry.register(
            Tool(
                name=public_name,
                description=f"REA `{upstream_name}` — {description}",
                handler=_tool_handler(runtime, upstream_name),
                risk=risk,
                requires_reauth=risk >= Risk.DESTRUCTIVE,
                connector_id="rea",
                capability=f"reverse_engineering:{upstream_name}",
                input_schema=dict(input_schema) if input_schema is not None else None,
                output_schema=None,
                idempotency_supported=annotations.get("idempotentHint") is True,
                verification_method="rea_evidence" if risk > Risk.READ_ONLY else None,
            )
        )
        names.append(public_name)
    return REARegistration(True, len(descriptors), tuple(names), None)
