from __future__ import annotations

import json
import uuid
from typing import Any, Mapping

from devices.gateway import DeviceCommand
from devices.trusted_compute import ACTION, CAPABILITY, PROTOCOL, sanitize_compute_request, validate_compute_result
from tools.registry import Risk, Tool, VerificationResult


INPUT_SCHEMA = {
    "type": "object",
    "required": ["device_id", "destination", "prompt"],
    "properties": {
        "device_id": {"type": "string", "minLength": 1, "maxLength": 200},
        "destination": {"type": "string", "minLength": 8, "maxLength": 220},
        "prompt": {"type": "string", "minLength": 1, "maxLength": 12000},
        "context": {"type": "object"},
        "mode": {"type": "string", "enum": ["fast", "smart", "deep"]},
        "sensitivity": {"type": "string", "enum": ["public", "internal"]},
        "max_tokens": {"type": "integer", "minimum": 1, "maximum": 8192},
        "timeout_seconds": {"type": "number", "minimum": 1, "maximum": 120},
        "task_id": {"type": "string", "maxLength": 200},
    },
    "additionalProperties": False,
}

OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["protocol", "device_id", "request_id", "content", "mode", "verified"],
    "properties": {
        "protocol": {"type": "string", "enum": [PROTOCOL]},
        "device_id": {"type": "string", "minLength": 1, "maxLength": 200},
        "request_id": {"type": "string", "minLength": 16, "maxLength": 160},
        "content": {"type": "string", "minLength": 1, "maxLength": 64000},
        "mode": {"type": "string", "enum": ["fast", "smart", "deep"]},
        "model_target": {"type": "string", "maxLength": 300},
        "latency_ms": {"type": "number", "minimum": 0},
        "worker_id": {"type": "string", "maxLength": 200},
        "verified": {"type": "boolean"},
    },
    "additionalProperties": False,
}


def _has_compute_capability(gateway: Any, device_id: str) -> bool:
    getter = getattr(gateway, "capabilities", None)
    if not callable(getter):
        return False
    return CAPABILITY in set(getter(device_id))


def register(registry, device_registry, device_gateway):
    """Register the only Core authority allowed to dispatch Lab compute remotely.

    The tool requires an active trusted device with the existing owner-grade
    `device:admin` permission and a live v1 compute capability advertisement.
    ToolRegistry still controls owner approval, emergency stop, data-class risk,
    verification and audit through the normal AgentExecutor path.
    """
    existing = [tool for tool in registry.all() if getattr(tool, "name", "") == "trusted_device_compute"]
    if existing:
        return existing[0]

    def validate_input(parameters: Mapping[str, Any]):
        clean = sanitize_compute_request(parameters)
        device_id = str(parameters.get("device_id") or "")
        if not device_registry.is_active(device_id):
            raise PermissionError("trusted compute target device is inactive")
        if hasattr(device_registry, "authorize") and not device_registry.authorize(device_id, "device:admin"):
            raise PermissionError("trusted compute target requires device:admin permission")
        if not _has_compute_capability(device_gateway, device_id):
            raise PermissionError("trusted compute target has not advertised intelligence_compute_v1")
        # Prove JSON size/shape now; the sanitized form is reconstructed by the
        # handler so arbitrary caller-only fields are never sent to the device.
        json.dumps(clean, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        return True

    def handler(parameters: dict[str, Any]):
        clean = sanitize_compute_request(parameters)
        device_id = str(parameters["device_id"])
        if not device_registry.is_active(device_id):
            raise PermissionError("trusted compute target device is inactive")
        if hasattr(device_registry, "authorize") and not device_registry.authorize(device_id, "device:admin"):
            raise PermissionError("trusted compute target requires device:admin permission")
        if not _has_compute_capability(device_gateway, device_id):
            raise PermissionError("trusted compute target is offline or compute capability is unavailable")
        request_id = f"compute-{uuid.uuid4().hex}"
        timeout = float(clean.pop("timeout_seconds"))
        command = DeviceCommand(
            action=ACTION,
            parameters={
                **clean,
                "device_id": device_id,
                "destination": f"device:{device_id}",
            },
            request_id=request_id,
        )
        envelope = device_gateway.request_sync(device_id, command, timeout=timeout)
        if not isinstance(envelope, Mapping):
            raise RuntimeError("trusted compute device returned an invalid envelope")
        if str(envelope.get("request_id") or "") != request_id or str(envelope.get("device_id") or "") != device_id:
            raise RuntimeError("trusted compute response identity mismatch")
        if not bool(envelope.get("ok", False)):
            raise RuntimeError("trusted compute device reported failure")
        result = validate_compute_result(envelope.get("result"))
        if not result["verified"]:
            raise RuntimeError("trusted compute result is not verified by the worker")
        return {
            "protocol": PROTOCOL,
            "device_id": device_id,
            "request_id": request_id,
            "content": result["content"],
            "mode": result["mode"],
            "model_target": result["model_target"],
            "latency_ms": result["latency_ms"],
            "worker_id": result["worker_id"],
            "verified": True,
        }

    def verifier(parameters, result):
        expected_device = str(parameters.get("device_id") or "")
        verified = bool(
            isinstance(result, Mapping)
            and result.get("verified") is True
            and result.get("protocol") == PROTOCOL
            and result.get("device_id") == expected_device
            and str(result.get("request_id") or "").startswith("compute-")
            and bool(result.get("content"))
        )
        return VerificationResult(
            verified=verified,
            reason="trusted compute response is bound to device/request/protocol" if verified else "trusted compute verification failed",
            evidence={
                "device_id": expected_device,
                "request_id": str(result.get("request_id") or "") if isinstance(result, Mapping) else "",
                "protocol": PROTOCOL,
                "worker_verified": bool(result.get("verified")) if isinstance(result, Mapping) else False,
            },
        )

    tool = Tool(
        "trusted_device_compute",
        "Execute a bounded AI reasoning task on an explicitly trusted compute-capable device",
        handler,
        Risk.EXTERNAL_SIDE_EFFECT,
        verifier=verifier,
        verification_required=True,
        prohibited_data_classifications=("secret", "sensitive", "restricted"),
        capability="trusted_device_compute",
        minimum_risk=Risk.EXTERNAL_SIDE_EFFECT,
        input_schema=INPUT_SCHEMA,
        output_schema=OUTPUT_SCHEMA,
        input_validator=validate_input,
        idempotency_supported=False,
        verification_method="device-request-protocol-binding",
    )
    registry.register(tool)
    return tool
