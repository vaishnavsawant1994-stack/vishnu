from __future__ import annotations

from types import SimpleNamespace

import pytest

from models.hardware_profile import (
    HardwareProfile,
    HardwareProfiler,
    ReadinessState,
    ResourceRequirement,
    build_offline_readiness,
)
from models.portable_intelligence import (
    ExecutionTarget,
    ModelTier,
    RuntimeCandidate,
)


_GIB = 1024 ** 3


def _disk(free_gb: int):
    return SimpleNamespace(total=2 * free_gb * _GIB, used=free_gb * _GIB, free=free_gb * _GIB)


def _cpu_candidate(*, minimum_ram_gb: float = 8) -> RuntimeCandidate:
    return RuntimeCandidate(
        runtime_id="local-cpu-small",
        model_ref="vishnu-small-q4",
        tier=ModelTier.SMALL,
        target=ExecutionTarget.LOCAL,
        minimum_ram_gb=minimum_ram_gb,
        minimum_vram_gb=0,
    )


def _gpu_candidate(*, minimum_vram_gb: float = 12) -> RuntimeCandidate:
    return RuntimeCandidate(
        runtime_id="local-gpu-medium",
        model_ref="vishnu-medium-q4",
        tier=ModelTier.MEDIUM,
        target=ExecutionTarget.LOCAL,
        minimum_ram_gb=16,
        minimum_vram_gb=minimum_vram_gb,
    )


def test_profiler_detects_largest_nvidia_gpu_without_network_probe():
    observed_commands = []

    def run(command):
        observed_commands.append(tuple(command))
        return "NVIDIA Small, 8192\nNVIDIA Large, 24576\n"

    profiler = HardwareProfiler(
        memory_reader=lambda: 64 * _GIB,
        command_runner=run,
        which=lambda name: "/usr/bin/nvidia-smi" if name == "nvidia-smi" else None,
        system_reader=lambda: "Linux",
        machine_reader=lambda: "x86_64",
        cpu_count_reader=lambda: 16,
        disk_usage_reader=lambda path: _disk(500),
    )

    profile = profiler.probe("/tmp", online=False)

    assert profile.ram_gb == 64
    assert profile.disk_free_gb == 500
    assert profile.cpu_logical_cores == 16
    assert profile.accelerator == "nvidia-cuda"
    assert profile.accelerator_name == "NVIDIA Large"
    assert profile.gpu_vram_gb == 24
    assert profile.online is False
    assert observed_commands == [
        (
            "/usr/bin/nvidia-smi",
            "--query-gpu=name,memory.total",
            "--format=csv,noheader,nounits",
        )
    ]


def test_profiler_marks_apple_silicon_as_shared_memory_without_fake_vram():
    profiler = HardwareProfiler(
        memory_reader=lambda: 32 * _GIB,
        which=lambda name: None,
        system_reader=lambda: "Darwin",
        machine_reader=lambda: "arm64",
        cpu_count_reader=lambda: 10,
        disk_usage_reader=lambda path: _disk(200),
    )

    profile = profiler.probe(online=False)

    assert profile.accelerator == "apple-metal-shared"
    assert profile.accelerator_name == "Apple Silicon"
    assert profile.shared_accelerator_memory is True
    assert profile.gpu_vram_gb == 0


def test_cpu_only_machine_can_be_offline_ready():
    profile = HardwareProfile(
        platform="linux",
        architecture="x86_64",
        cpu_logical_cores=8,
        ram_gb=32,
        disk_free_gb=300,
        online=False,
    )

    report = build_offline_readiness(profile, (_cpu_candidate(), _gpu_candidate()))

    assert report.ready is True
    assert report.runtime_selection is not None
    assert report.runtime_selection.candidate.runtime_id == "local-cpu-small"
    check = next(item for item in report.checks if item.name == "local_text_ai")
    assert check.state is ReadinessState.WARNING
    assert check.reason == "local_cpu_runtime_selected"


def test_offline_readiness_blocks_when_no_local_model_fits():
    profile = HardwareProfile(
        platform="linux",
        architecture="x86_64",
        cpu_logical_cores=4,
        ram_gb=8,
        disk_free_gb=100,
        online=False,
    )

    report = build_offline_readiness(
        profile,
        (_cpu_candidate(minimum_ram_gb=16), _gpu_candidate(minimum_vram_gb=12)),
    )

    assert report.ready is False
    assert report.runtime_selection is None
    assert report.blocked == ("local_text_ai",)
    with pytest.raises(RuntimeError, match="local_text_ai"):
        report.require_ready()


def test_gpu_machine_selects_stronger_feasible_local_runtime():
    profile = HardwareProfile(
        platform="linux",
        architecture="x86_64",
        cpu_logical_cores=16,
        ram_gb=64,
        disk_free_gb=800,
        accelerator="nvidia-cuda",
        accelerator_name="NVIDIA GPU",
        gpu_vram_gb=24,
        online=False,
    )

    report = build_offline_readiness(profile, (_cpu_candidate(), _gpu_candidate()))

    assert report.ready is True
    assert report.runtime_selection is not None
    assert report.runtime_selection.candidate.runtime_id == "local-gpu-medium"
    check = next(item for item in report.checks if item.name == "local_text_ai")
    assert check.state is ReadinessState.READY
    assert check.reason == "local_gpu_runtime_selected"


def test_required_offline_assets_fail_closed():
    profile = HardwareProfile(
        platform="linux",
        architecture="x86_64",
        cpu_logical_cores=8,
        ram_gb=32,
        disk_free_gb=300,
        online=False,
    )

    report = build_offline_readiness(
        profile,
        (_cpu_candidate(),),
        required_assets={"embeddings": True, "ocr": False},
    )

    assert report.ready is False
    assert "asset:ocr" in report.blocked
    assert "asset:embeddings" not in report.blocked


def test_training_resources_are_explicit_not_inferred_from_agent_count():
    profile = HardwareProfile(
        platform="linux",
        architecture="x86_64",
        cpu_logical_cores=12,
        ram_gb=64,
        disk_free_gb=1000,
        online=False,
    )

    report = build_offline_readiness(
        profile,
        (_cpu_candidate(),),
        requirements=(
            ResourceRequirement(
                name="qlora-training",
                minimum_ram_gb=32,
                minimum_vram_gb=16,
                accelerator_required=True,
                required=False,
            ),
        ),
    )

    assert report.ready is True
    training = next(item for item in report.checks if item.name == "qlora-training")
    assert training.state is ReadinessState.WARNING
    assert "vram<16GB" in training.reason
    assert "accelerator_missing" in training.reason
