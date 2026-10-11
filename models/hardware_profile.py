from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import ctypes
import os
from pathlib import Path
import platform as platform_module
import shutil
import subprocess
from typing import Callable, Iterable, Mapping, Sequence

from models.intelligence_restore import RestorePreflight
from models.portable_intelligence import (
    DeviceCapabilities,
    ExecutionTarget,
    RuntimeCandidate,
    RuntimeSelection,
    select_runtime,
)


_GIB = 1024 ** 3


def _gb(value: int | float) -> float:
    return round(float(value) / _GIB, 3)


def _default_memory_bytes() -> int:
    """Read physical memory without adding a mandatory psutil dependency."""

    if os.name == "nt":
        class MemoryStatusEx(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatusEx()
        status.dwLength = ctypes.sizeof(status)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            raise OSError("unable to read Windows physical memory")
        return int(status.ullTotalPhys)

    page_size = os.sysconf("SC_PAGE_SIZE")
    pages = os.sysconf("SC_PHYS_PAGES")
    total = int(page_size) * int(pages)
    if total <= 0:
        raise OSError("unable to read physical memory")
    return total


def _default_command_runner(command: Sequence[str]) -> str:
    completed = subprocess.run(
        list(command),
        check=True,
        capture_output=True,
        text=True,
        timeout=3,
        shell=False,
    )
    return completed.stdout


def _parse_nvidia_smi(output: str) -> tuple[str, float] | None:
    """Return the largest visible NVIDIA device by VRAM.

    `nvidia-smi` reports memory in MiB for the query used by HardwareProfiler.
    Multiple GPUs are not summed: one model process cannot assume it may pool
    unrelated devices unless a higher-level runtime explicitly supports that.
    """

    best: tuple[str, float] | None = None
    for raw_line in str(output or "").splitlines():
        line = raw_line.strip()
        if not line or "," not in line:
            continue
        name, raw_mib = line.rsplit(",", 1)
        try:
            gib = float(raw_mib.strip()) / 1024.0
        except ValueError:
            continue
        if gib <= 0:
            continue
        candidate = (name.strip() or "NVIDIA GPU", round(gib, 3))
        if best is None or candidate[1] > best[1]:
            best = candidate
    return best


@dataclass(frozen=True)
class HardwareProfile:
    platform: str
    architecture: str
    cpu_logical_cores: int
    ram_gb: float
    disk_free_gb: float
    accelerator: str = "none"
    accelerator_name: str = ""
    gpu_vram_gb: float = 0.0
    shared_accelerator_memory: bool = False
    online: bool = False

    def __post_init__(self) -> None:
        if self.cpu_logical_cores <= 0:
            raise ValueError("cpu_logical_cores must be positive")
        if self.ram_gb <= 0:
            raise ValueError("ram_gb must be positive")
        if self.disk_free_gb < 0 or self.gpu_vram_gb < 0:
            raise ValueError("hardware capacity cannot be negative")

    def device_capabilities(self, *, online: bool | None = None) -> DeviceCapabilities:
        return DeviceCapabilities(
            ram_gb=self.ram_gb,
            gpu_vram_gb=self.gpu_vram_gb,
            online=self.online if online is None else bool(online),
            accelerator=self.accelerator,
            platform=self.platform,
        )

    def public(self) -> dict[str, object]:
        return {
            "platform": self.platform,
            "architecture": self.architecture,
            "cpu_logical_cores": self.cpu_logical_cores,
            "ram_gb": self.ram_gb,
            "disk_free_gb": self.disk_free_gb,
            "accelerator": self.accelerator,
            "accelerator_name": self.accelerator_name,
            "gpu_vram_gb": self.gpu_vram_gb,
            "shared_accelerator_memory": self.shared_accelerator_memory,
            "online": self.online,
        }


class HardwareProfiler:
    """Dependency-light host profiler used before local/offline model selection.

    Network state is supplied by the caller. Profiling hardware must never make
    an external request merely to decide whether Vishnu can work offline.
    """

    def __init__(
        self,
        *,
        memory_reader: Callable[[], int] | None = None,
        command_runner: Callable[[Sequence[str]], str] | None = None,
        which: Callable[[str], str | None] | None = None,
        system_reader: Callable[[], str] | None = None,
        machine_reader: Callable[[], str] | None = None,
        cpu_count_reader: Callable[[], int | None] | None = None,
        disk_usage_reader: Callable[[str | os.PathLike[str]], object] | None = None,
    ) -> None:
        self._memory_reader = memory_reader or _default_memory_bytes
        self._command_runner = command_runner or _default_command_runner
        self._which = which or shutil.which
        self._system_reader = system_reader or platform_module.system
        self._machine_reader = machine_reader or platform_module.machine
        self._cpu_count_reader = cpu_count_reader or os.cpu_count
        self._disk_usage_reader = disk_usage_reader or shutil.disk_usage

    def _accelerator(self, *, system: str, machine: str) -> tuple[str, str, float, bool]:
        nvidia_smi = self._which("nvidia-smi")
        if nvidia_smi:
            try:
                result = _parse_nvidia_smi(
                    self._command_runner(
                        (
                            nvidia_smi,
                            "--query-gpu=name,memory.total",
                            "--format=csv,noheader,nounits",
                        )
                    )
                )
            except (OSError, subprocess.SubprocessError):
                result = None
            if result is not None:
                return "nvidia-cuda", result[0], result[1], False

        normalized_machine = machine.lower().replace("_", "-")
        if system.lower() == "darwin" and normalized_machine in {"arm64", "aarch64"}:
            # Apple Silicon uses unified memory rather than dedicated VRAM. We
            # intentionally keep gpu_vram_gb=0 so CUDA-style VRAM requirements
            # are not falsely satisfied by all system RAM.
            return "apple-metal-shared", "Apple Silicon", 0.0, True

        return "none", "", 0.0, False

    def probe(self, path: str | Path = ".", *, online: bool = False) -> HardwareProfile:
        system = str(self._system_reader() or "unknown")
        machine = str(self._machine_reader() or "unknown")
        cores = int(self._cpu_count_reader() or 1)
        memory_bytes = int(self._memory_reader())
        disk = self._disk_usage_reader(str(Path(path).expanduser()))
        free_bytes = int(getattr(disk, "free"))
        accelerator, accelerator_name, gpu_vram_gb, shared = self._accelerator(
            system=system,
            machine=machine,
        )
        return HardwareProfile(
            platform=system.lower(),
            architecture=machine.lower(),
            cpu_logical_cores=max(1, cores),
            ram_gb=_gb(memory_bytes),
            disk_free_gb=_gb(free_bytes),
            accelerator=accelerator,
            accelerator_name=accelerator_name,
            gpu_vram_gb=gpu_vram_gb,
            shared_accelerator_memory=shared,
            online=bool(online),
        )


class ReadinessState(str, Enum):
    READY = "ready"
    WARNING = "warning"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class ReadinessCheck:
    name: str
    state: ReadinessState
    reason: str


@dataclass(frozen=True)
class ResourceRequirement:
    name: str
    minimum_ram_gb: float = 0.0
    minimum_vram_gb: float = 0.0
    minimum_disk_free_gb: float = 0.0
    accelerator_required: bool = False
    required: bool = True

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("resource requirement name is required")
        if min(self.minimum_ram_gb, self.minimum_vram_gb, self.minimum_disk_free_gb) < 0:
            raise ValueError("resource requirements cannot be negative")


@dataclass(frozen=True)
class OfflineReadinessReport:
    profile: HardwareProfile
    ready: bool
    checks: tuple[ReadinessCheck, ...]
    runtime_selection: RuntimeSelection | None

    @property
    def blocked(self) -> tuple[str, ...]:
        return tuple(check.name for check in self.checks if check.state is ReadinessState.BLOCKED)

    def require_ready(self) -> None:
        if not self.ready:
            raise RuntimeError(f"offline readiness blocked: {', '.join(self.blocked) or 'unknown'}")

    def public(self) -> dict[str, object]:
        selection = self.runtime_selection
        return {
            "ready": self.ready,
            "profile": self.profile.public(),
            "selected_runtime": selection.candidate.runtime_id if selection else None,
            "selected_model_ref": selection.candidate.model_ref if selection else None,
            "checks": [
                {"name": check.name, "state": check.state.value, "reason": check.reason}
                for check in self.checks
            ],
            "blocked": list(self.blocked),
        }


def _assess_requirement(profile: HardwareProfile, requirement: ResourceRequirement) -> ReadinessCheck:
    failures: list[str] = []
    if profile.ram_gb < requirement.minimum_ram_gb:
        failures.append(f"ram<{requirement.minimum_ram_gb:g}GB")
    if profile.gpu_vram_gb < requirement.minimum_vram_gb:
        failures.append(f"vram<{requirement.minimum_vram_gb:g}GB")
    if profile.disk_free_gb < requirement.minimum_disk_free_gb:
        failures.append(f"disk<{requirement.minimum_disk_free_gb:g}GB")
    if requirement.accelerator_required and profile.accelerator == "none":
        failures.append("accelerator_missing")
    if not failures:
        return ReadinessCheck(requirement.name, ReadinessState.READY, "resource_requirement_satisfied")
    state = ReadinessState.BLOCKED if requirement.required else ReadinessState.WARNING
    return ReadinessCheck(requirement.name, state, ";".join(failures))


def build_offline_readiness(
    profile: HardwareProfile,
    runtime_candidates: Iterable[RuntimeCandidate],
    *,
    restore_preflight: RestorePreflight | None = None,
    required_assets: Mapping[str, bool] | None = None,
    requirements: Iterable[ResourceRequirement] = (),
) -> OfflineReadinessReport:
    """Describe whether this host is prepared for a network-disconnected session.

    Absence of a dedicated GPU is not itself a failure. If a CPU-capable local
    runtime fits RAM, Vishnu remains offline-ready and reports a warning that
    neural inference will use CPU/shared-memory execution. Model-specific
    training requirements can be supplied explicitly through `requirements`.
    """

    checks: list[ReadinessCheck] = []
    offline_device = profile.device_capabilities(online=False)
    local_candidates = tuple(
        candidate for candidate in runtime_candidates if candidate.target is ExecutionTarget.LOCAL
    )
    selection: RuntimeSelection | None = None
    try:
        selection = select_runtime(local_candidates, offline_device, local_only=True)
    except RuntimeError:
        checks.append(
            ReadinessCheck(
                "local_text_ai",
                ReadinessState.BLOCKED,
                "no_feasible_local_runtime",
            )
        )
    else:
        if selection.candidate.minimum_vram_gb > 0:
            reason = "local_gpu_runtime_selected"
            state = ReadinessState.READY
        elif profile.accelerator == "none":
            reason = "local_cpu_runtime_selected"
            state = ReadinessState.WARNING
        elif profile.shared_accelerator_memory:
            reason = "local_cpu_or_shared_memory_runtime_selected"
            state = ReadinessState.WARNING
        else:
            reason = "local_runtime_selected"
            state = ReadinessState.READY
        checks.append(ReadinessCheck("local_text_ai", state, reason))

    if restore_preflight is not None:
        if restore_preflight.ready:
            checks.append(ReadinessCheck("restore_assets", ReadinessState.READY, "required_artifacts_local"))
        else:
            checks.append(
                ReadinessCheck(
                    "restore_assets",
                    ReadinessState.BLOCKED,
                    "missing_required_artifacts:" + ",".join(restore_preflight.blocked_required),
                )
            )

    for asset_name, available in sorted(dict(required_assets or {}).items()):
        checks.append(
            ReadinessCheck(
                f"asset:{asset_name}",
                ReadinessState.READY if available else ReadinessState.BLOCKED,
                "local_asset_available" if available else "local_asset_missing",
            )
        )

    for requirement in requirements:
        checks.append(_assess_requirement(profile, requirement))

    return OfflineReadinessReport(
        profile=profile,
        ready=not any(check.state is ReadinessState.BLOCKED for check in checks),
        checks=tuple(checks),
        runtime_selection=selection,
    )
