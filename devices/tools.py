from __future__ import annotations

from typing import Any

from devices.virtual_lab import VirtualDeviceLab
from tools.registry import Risk, Tool, VerificationResult


_STATUS_INPUT = {
    "type": "object",
    "required": ["device_id"],
    "properties": {"device_id": {"type": "string", "minLength": 1, "maxLength": 160}},
    "additionalProperties": False,
}

_EXECUTE_INPUT = {
    "type": "object",
    "required": ["device_id", "action"],
    "properties": {
        "device_id": {"type": "string", "minLength": 1, "maxLength": 160},
        "action": {"type": "string", "minLength": 1, "maxLength": 128},
        "parameters": {"type": "object"},
        "request_id": {"type": "string", "minLength": 1, "maxLength": 128},
    },
    "additionalProperties": False,
}

_RESULT_OUTPUT = {
    "type": "object",
    "required": ["request_id", "device_id", "action", "success", "code", "output", "simulated", "verified"],
    "properties": {
        "request_id": {"type": "string"},
        "device_id": {"type": "string"},
        "action": {"type": "string"},
        "success": {"type": "boolean"},
        "code": {"type": "string"},
        "output": {"type": "object"},
        "simulated": {"type": "boolean"},
        "verified": {"type": "boolean"},
    },
    "additionalProperties": False,
}


def register_virtual_device_tools(registry: Any, lab: VirtualDeviceLab) -> None:
    """Expose virtual devices through the same governed ToolRegistry boundary."""

    def status_handler(parameters: dict[str, Any]) -> dict[str, Any]:
        return lab.status(parameters["device_id"])

    def execute_handler(parameters: dict[str, Any]) -> dict[str, Any]:
        return lab.execute(
            parameters["device_id"],
            parameters["action"],
            parameters.get("parameters") or {},
            request_id=parameters.get("request_id"),
        )

    def verifier(parameters: dict[str, Any], result: dict[str, Any]) -> VerificationResult:
        request_id = str(result.get("request_id", ""))
        verified = lab.verify(parameters["device_id"], request_id)
        if verified is None:
            return VerificationResult(False, "virtual command result is missing", {"request_id": request_id})
        matches = (
            verified.success == bool(result.get("success"))
            and verified.code == str(result.get("code", ""))
            and verified.action == str(result.get("action", ""))
        )
        return VerificationResult(
            matches,
            "simulated runtime result matched durable in-memory evidence" if matches else "simulated runtime result did not match evidence",
            {"request_id": request_id, "mode": "simulated"},
        )

    registry.register(
        Tool(
            name="virtual_device_status",
            description="Inspect a virtual device in the local deterministic device lab",
            handler=status_handler,
            risk=Risk.READ_ONLY,
            input_schema=_STATUS_INPUT,
            idempotency_supported=True,
            verification_method="runtime status snapshot",
        )
    )
    registry.register(
        Tool(
            name="virtual_device_execute",
            description="Execute a bounded action against a simulated device only",
            handler=execute_handler,
            risk=Risk.REVERSIBLE,
            minimum_risk=Risk.REVERSIBLE,
            verifier=verifier,
            verification_required=True,
            input_schema=_EXECUTE_INPUT,
            output_schema=_RESULT_OUTPUT,
            idempotency_supported=True,
            verification_method="simulated runtime evidence lookup",
        )
    )
