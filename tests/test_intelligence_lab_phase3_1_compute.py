from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from devices.trusted_compute import (
    ACTION,
    CAPABILITY,
    PROTOCOL,
    TrustedComputeRequest,
    TrustedComputeWorker,
    sanitize_compute_request,
)
from intelligence_lab.bootstrap import build_intelligence_lab
from intelligence_lab.config import CapabilityLevel, LabSettings
from tools.registry import Risk, ToolRegistry


class FakeEvents:
    def emit(self, *args, **kwargs):
        return None


class FakeDevices:
    def __init__(self, *, admin: bool = True):
        self.admin = admin

    def is_active(self, device_id):
        return device_id == "compute-box"

    def authorize(self, device_id, scope):
        if device_id != "compute-box":
            return False
        if scope == "device:admin":
            return self.admin
        return scope == "ai:chat"

    def list(self):
        return [
            {
                "id": "compute-box",
                "name": "Compute Box",
                "platform": "linux",
                "revoked": False,
                "permissions": ["ai:chat", "device:admin"],
                "metadata": {
                    "compute_enabled": "true",
                    "gpu": "NVIDIA RTX",
                    "memory_gb": "32",
                    "network": "ethernet",
                    "battery_percent": "100",
                },
            }
        ]


class FakeGateway:
    def __init__(self, *, capable: bool = True):
        self.capable = capable
        self.calls = []

    def capabilities(self, device_id):
        return (CAPABILITY,) if self.capable and device_id == "compute-box" else ()

    def request_sync(self, device_id, command, timeout=15):
        self.calls.append((device_id, command, timeout))
        return {
            "device_id": device_id,
            "type": "result",
            "request_id": command.request_id,
            "ok": True,
            "result": {
                "protocol": PROTOCOL,
                "content": "remote governed reasoning",
                "mode": command.parameters["mode"],
                "model_target": "local-worker-model",
                "latency_ms": 12.0,
                "verified": True,
                "worker_id": "worker-1",
            },
        }


class FakeExecutor:
    def __init__(self):
        self.calls = []

    def chat(self, text, **kwargs):
        self.calls.append((text, kwargs))
        return "core-replanned-result"


def tool_registry(tmp_path: Path) -> ToolRegistry:
    settings = SimpleNamespace(autonomy_mode="ask", data_dir=tmp_path / "stable")
    return ToolRegistry(settings)


def lab_settings(tmp_path: Path, level: CapabilityLevel) -> LabSettings:
    return LabSettings(
        enabled=True,
        level=level,
        data_dir=tmp_path / "lab",
        max_models=3,
        benchmark_variants=1,
        learning_window=100,
    )


def core_runtime(tmp_path: Path, *, level: CapabilityLevel = CapabilityLevel.PROPOSE, admin: bool = True, capable: bool = True):
    registry = tool_registry(tmp_path)
    devices = FakeDevices(admin=admin)
    gateway = FakeGateway(capable=capable)
    executor = FakeExecutor()
    core = {
        "settings": SimpleNamespace(data_dir=tmp_path / "stable"),
        "tools": registry,
        "device_registry": devices,
        "device_gateway": gateway,
        "agent_executor": executor,
    }
    lab = build_intelligence_lab(
        core_runtime=core,
        settings=lab_settings(tmp_path, level),
        use_core_model=False,
    )
    return lab, core, registry, gateway, executor


def valid_parameters():
    return {
        "device_id": "compute-box",
        "destination": "device:compute-box",
        "prompt": "Analyze the bounded task",
        "context": {"evidence": "known"},
        "mode": "smart",
        "sensitivity": "internal",
        "max_tokens": 1024,
        "timeout_seconds": 30,
    }


def test_phase31_registers_governed_compute_only_on_explicit_enabled_lab(tmp_path):
    lab, core, registry, gateway, executor = core_runtime(tmp_path)
    tool = registry.get("trusted_device_compute")
    assert tool.risk == Risk.EXTERNAL_SIDE_EFFECT
    assert tool.verification_required is True
    assert "secret" in tool.prohibited_data_classifications
    assert lab.phase3.status()["governed_distributed_compute_available"] is True
    assert lab.phase3.status()["device_gateway_bypass_added"] is False

    disabled_registry = tool_registry(tmp_path / "disabled")
    disabled_core = {
        "settings": SimpleNamespace(data_dir=tmp_path / "disabled-stable"),
        "tools": disabled_registry,
        "device_registry": FakeDevices(),
        "device_gateway": FakeGateway(),
    }
    build_intelligence_lab(
        core_runtime=disabled_core,
        settings=LabSettings(enabled=False, data_dir=tmp_path / "disabled-lab"),
        use_core_model=False,
    )
    assert all(tool.name != "trusted_device_compute" for tool in disabled_registry.all())


def test_governed_compute_tool_requires_admin_live_capability_and_verified_response(tmp_path):
    lab, core, registry, gateway, executor = core_runtime(tmp_path)
    tool = registry.get("trusted_device_compute")
    params = valid_parameters()
    result = registry.dispatch(tool, dict(params))
    assert result["verified"] is True
    assert result["device_id"] == "compute-box"
    assert result["protocol"] == PROTOCOL
    assert result["content"] == "remote governed reasoning"
    assert len(gateway.calls) == 1
    verification = registry.verify_result(tool, params, result)
    assert verification.verified is True

    denied_lab, denied_core, denied_registry, _, _ = core_runtime(tmp_path / "denied", admin=False)
    denied_tool = denied_registry.get("trusted_device_compute")
    with pytest.raises(PermissionError, match="device:admin"):
        denied_registry.dispatch(denied_tool, valid_parameters())

    missing_lab, missing_core, missing_registry, _, _ = core_runtime(tmp_path / "missing", capable=False)
    missing_tool = missing_registry.get("trusted_device_compute")
    with pytest.raises(PermissionError, match="advertised"):
        missing_registry.dispatch(missing_tool, valid_parameters())


def test_remote_compute_rejects_sensitive_secret_and_destination_mismatch():
    with pytest.raises(PermissionError, match="public/internal"):
        sanitize_compute_request({**valid_parameters(), "sensitivity": "sensitive"})
    with pytest.raises(ValueError, match="destination"):
        sanitize_compute_request({**valid_parameters(), "destination": "device:other"})
    with pytest.raises(ValueError, match="prompt"):
        sanitize_compute_request({**valid_parameters(), "prompt": "x" * 12001})


def test_device_worker_is_bounded_and_uses_injected_reasoner_only():
    calls = []

    def reasoner(request: TrustedComputeRequest):
        calls.append(request)
        return {"content": f"handled:{request.mode}", "model_target": "existing-vishnu-router"}

    worker = TrustedComputeWorker(reasoner, worker_id="box-1")
    result = worker.handle(ACTION, valid_parameters())
    assert result["protocol"] == PROTOCOL
    assert result["content"] == "handled:smart"
    assert result["worker_id"] == "box-1"
    assert result["verified"] is True
    assert len(calls) == 1
    with pytest.raises(ValueError, match="unsupported"):
        worker.handle("shell", valid_parameters())


def test_phase31_proposal_uses_live_compute_target_but_does_not_dispatch(tmp_path):
    lab, core, registry, gateway, executor = core_runtime(tmp_path, level=CapabilityLevel.PROPOSE)
    proposal = lab.phase3.distributed_compute_proposal(
        "Analyze this workload",
        context={"evidence": "bounded"},
        mode="smart",
        sensitivity="internal",
    )
    assert proposal["selected"]["id"] == "compute-box"
    assert proposal["proposal"]["action"] == "trusted_device_compute"
    assert proposal["executed"] is False
    assert proposal["core_reapproval_required"] is True
    assert gateway.calls == []
    assert executor.calls == []


def test_phase31_execution_returns_to_agent_executor_not_gateway(tmp_path):
    lab, core, registry, gateway, executor = core_runtime(
        tmp_path,
        level=CapabilityLevel.GOVERNED_EXECUTION,
    )
    result = lab.phase3.execute_distributed_compute(
        "Analyze this workload",
        context={"evidence": "bounded"},
        sensitivity="internal",
        owner_id="owner",
        device_id="requesting-device",
    )
    assert result == "core-replanned-result"
    assert len(executor.calls) == 1
    instruction = executor.calls[0][0]
    assert "trusted_device_compute" in instruction
    assert "untrusted advisory data" in instruction
    # FakeExecutor does not execute Core tools; this proves Phase 3 itself did
    # not bypass AgentExecutor and call DeviceGateway directly.
    assert gateway.calls == []


def test_phase31_standalone_service_still_has_no_execution_endpoint(tmp_path):
    lab, core, registry, gateway, executor = core_runtime(tmp_path)
    from intelligence_lab.phase3_service import create_phase3_app

    app = create_phase3_app(lab)
    paths = {route.path for route in app.routes}
    assert "/phase3/execute" not in paths
    assert "/phase3/compute/execute" not in paths
    assert "/phase3/tool-dispatch" not in paths
