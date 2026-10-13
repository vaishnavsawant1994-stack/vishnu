from __future__ import annotations

import json
import os
import platform as host_platform
import re
import sqlite3
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Mapping


class NativeProvider(StrEnum):
    ANDROID_EMULATOR = "android_emulator"
    IOS_SIMULATOR = "ios_simulator"
    DESKTOP_VM = "desktop_vm"


class NativePlatform(StrEnum):
    ANDROID = "android"
    IOS = "ios"
    WINDOWS = "windows"
    MACOS = "macos"
    LINUX = "linux"


class NativeStatus(StrEnum):
    READY = "ready"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class NativeProviderProfile:
    provider: NativeProvider
    platforms: frozenset[NativePlatform]
    environment_kind: str
    read_only_probe: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider.value,
            "platforms": sorted(item.value for item in self.platforms),
            "environment_kind": self.environment_kind,
            "read_only_probe": self.read_only_probe,
            "physical_device": False,
            "execution_authority": False,
        }


PROFILES = {
    NativeProvider.ANDROID_EMULATOR: NativeProviderProfile(
        NativeProvider.ANDROID_EMULATOR,
        frozenset({NativePlatform.ANDROID}),
        "vendor_emulator",
    ),
    NativeProvider.IOS_SIMULATOR: NativeProviderProfile(
        NativeProvider.IOS_SIMULATOR,
        frozenset({NativePlatform.IOS}),
        "vendor_simulator",
    ),
    NativeProvider.DESKTOP_VM: NativeProviderProfile(
        NativeProvider.DESKTOP_VM,
        frozenset({NativePlatform.WINDOWS, NativePlatform.MACOS, NativePlatform.LINUX}),
        "hosted_vm",
    ),
}

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,191}$")
_SECRET_KEY = re.compile(r"(?:token|secret|password|passwd|authorization|bearer|cookie|credential|api[_-]?key)", re.I)
MAX_METADATA_BYTES = 16 * 1024
MAX_TEXT = 512


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _bounded(value: Any, *, name: str, limit: int = MAX_TEXT, allow_empty: bool = False) -> str:
    text = str(value or "").strip()
    if (not text and not allow_empty) or len(text) > limit:
        raise ValueError(f"{name} must contain {'0' if allow_empty else '1'}-{limit} characters")
    return text


def _identifier(value: Any, *, name: str) -> str:
    text = str(value or "").strip()
    if not _IDENTIFIER.fullmatch(text):
        raise ValueError(f"{name} must be a bounded identifier")
    return text


def _validate_metadata(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("metadata must be an object")

    def walk(item: Any) -> None:
        if isinstance(item, Mapping):
            for key, nested in item.items():
                if _SECRET_KEY.search(str(key)):
                    raise ValueError("native evidence metadata must not contain secret-bearing keys")
                walk(nested)
        elif isinstance(item, (list, tuple)):
            for nested in item:
                walk(nested)

    normalized = json.loads(json.dumps(dict(value), sort_keys=True, ensure_ascii=False))
    walk(normalized)
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if len(encoded) > MAX_METADATA_BYTES:
        raise ValueError("native evidence metadata is too large")
    return normalized


@dataclass(frozen=True, slots=True)
class NativeDeviceEvidence:
    provider: NativeProvider
    platform: NativePlatform
    target_id: str
    status: NativeStatus
    os_version: str
    architecture: str
    capabilities: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    observed_at: datetime = field(default_factory=_utc_now)
    source: str = "native-device-lab"
    schema_version: int = 1
    physical_device: bool = False
    execution_authority: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.provider, NativeProvider):
            object.__setattr__(self, "provider", NativeProvider(str(self.provider)))
        if not isinstance(self.platform, NativePlatform):
            object.__setattr__(self, "platform", NativePlatform(str(self.platform)))
        if not isinstance(self.status, NativeStatus):
            object.__setattr__(self, "status", NativeStatus(str(self.status)))
        if self.platform not in PROFILES[self.provider].platforms:
            raise ValueError("provider/platform combination is invalid")
        object.__setattr__(self, "target_id", _identifier(self.target_id, name="target_id"))
        object.__setattr__(self, "os_version", _bounded(self.os_version, name="os_version", limit=120))
        object.__setattr__(self, "architecture", _bounded(self.architecture, name="architecture", limit=80))
        object.__setattr__(self, "source", _identifier(self.source, name="source"))
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        object.__setattr__(self, "observed_at", self.observed_at.astimezone(timezone.utc))
        capabilities = tuple(sorted({_bounded(item, name="capability", limit=80) for item in self.capabilities}))
        if len(capabilities) > 64:
            raise ValueError("too many native capabilities")
        object.__setattr__(self, "capabilities", capabilities)
        object.__setattr__(self, "metadata", _validate_metadata(self.metadata))
        if self.physical_device:
            raise ValueError("native emulator/VM evidence cannot claim a physical device")
        if self.execution_authority:
            raise ValueError("native emulator/VM evidence cannot grant execution authority")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "provider": self.provider.value,
            "platform": self.platform.value,
            "target_id": self.target_id,
            "status": self.status.value,
            "os_version": self.os_version,
            "architecture": self.architecture,
            "capabilities": list(self.capabilities),
            "metadata": json.loads(json.dumps(self.metadata)),
            "observed_at": self.observed_at.isoformat(),
            "source": self.source,
            "physical_device": False,
            "execution_authority": False,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "NativeDeviceEvidence":
        timestamp = datetime.fromisoformat(str(value.get("observed_at") or ""))
        return cls(
            provider=NativeProvider(str(value["provider"])),
            platform=NativePlatform(str(value["platform"])),
            target_id=str(value["target_id"]),
            status=NativeStatus(str(value["status"])),
            os_version=str(value["os_version"]),
            architecture=str(value["architecture"]),
            capabilities=tuple(str(item) for item in value.get("capabilities") or ()),
            metadata=dict(value.get("metadata") or {}),
            observed_at=timestamp,
            source=str(value.get("source") or "native-device-lab"),
            schema_version=int(value.get("schema_version") or 1),
            physical_device=bool(value.get("physical_device", False)),
            execution_authority=bool(value.get("execution_authority", False)),
        )


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


Runner = Callable[[tuple[str, ...], int], CommandResult]


def _default_runner(args: tuple[str, ...], timeout: int) -> CommandResult:
    completed = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    return CommandResult(completed.returncode, completed.stdout or "", completed.stderr or "")


def _checked(runner: Runner, args: tuple[str, ...], *, timeout: int = 15) -> str:
    result = runner(args, timeout)
    if result.returncode != 0:
        raise RuntimeError(f"native probe command failed: {args[0]}")
    return result.stdout.strip()


class AndroidEmulatorProbe:
    """Read-only Android Emulator probe. Physical adb serials are rejected."""

    def __init__(self, runner: Runner = _default_runner) -> None:
        self._runner = runner

    def probe(self, serial: str | None = None) -> NativeDeviceEvidence:
        devices = _checked(self._runner, ("adb", "devices"))
        candidates = [
            line.split()[0]
            for line in devices.splitlines()[1:]
            if line.strip() and len(line.split()) >= 2 and line.split()[1] == "device" and line.split()[0].startswith("emulator-")
        ]
        selected = str(serial or (candidates[0] if candidates else "")).strip()
        if not selected.startswith("emulator-") or selected not in candidates:
            raise RuntimeError("no Android Emulator target is available")

        def shell(*parts: str) -> str:
            return _checked(self._runner, ("adb", "-s", selected, "shell", *parts))

        qemu = shell("getprop", "ro.boot.qemu") or shell("getprop", "ro.kernel.qemu")
        if qemu.strip() != "1":
            raise RuntimeError("adb target is not an Android Emulator")
        release = shell("getprop", "ro.build.version.release") or "unknown"
        sdk = shell("getprop", "ro.build.version.sdk") or "unknown"
        model = shell("getprop", "ro.product.model") or "Android Emulator"
        abi = shell("getprop", "ro.product.cpu.abi") or "unknown"
        boot_completed = shell("getprop", "sys.boot_completed") == "1"
        battery_text = shell("dumpsys", "battery")
        match = re.search(r"^\s*level:\s*(\d+)\s*$", battery_text, re.M)
        battery = int(match.group(1)) if match else None
        return NativeDeviceEvidence(
            provider=NativeProvider.ANDROID_EMULATOR,
            platform=NativePlatform.ANDROID,
            target_id=selected,
            status=NativeStatus.READY if boot_completed else NativeStatus.UNAVAILABLE,
            os_version=f"Android {release} (API {sdk})",
            architecture=abi,
            capabilities=("device_info", "battery", "instrumentation", "screen_runtime"),
            metadata={
                "model": model[:120],
                "boot_completed": boot_completed,
                "battery_percent": battery,
                "qemu": True,
                "environment_kind": "vendor_emulator",
            },
            source="android-emulator-probe",
        )


class IOSSimulatorProbe:
    """Read-only CoreSimulator probe using fixed simctl list commands."""

    def __init__(self, runner: Runner = _default_runner) -> None:
        self._runner = runner

    def probe(self, udid: str | None = None) -> NativeDeviceEvidence:
        raw = _checked(self._runner, ("xcrun", "simctl", "list", "devices", "available", "--json"), timeout=60)
        payload = json.loads(raw)
        options: list[tuple[str, dict[str, Any]]] = []
        for runtime, devices in dict(payload.get("devices") or {}).items():
            for device in devices or []:
                if bool(device.get("isAvailable", True)):
                    options.append((str(runtime), dict(device)))
        requested = str(udid or "").strip()
        chosen: tuple[str, dict[str, Any]] | None = None
        if requested:
            chosen = next((item for item in options if str(item[1].get("udid")) == requested), None)
        if chosen is None:
            chosen = next((item for item in options if str(item[1].get("state")) == "Booted"), None)
        if chosen is None and options:
            chosen = options[0]
        if chosen is None:
            raise RuntimeError("no iOS Simulator target is available")
        runtime, device = chosen
        target = _identifier(device.get("udid"), name="target_id")
        state = str(device.get("state") or "Unknown")
        runtime_label = runtime.rsplit(".", 1)[-1].replace("-", " ")
        return NativeDeviceEvidence(
            provider=NativeProvider.IOS_SIMULATOR,
            platform=NativePlatform.IOS,
            target_id=target,
            status=NativeStatus.READY if state == "Booted" else NativeStatus.UNAVAILABLE,
            os_version=runtime_label,
            architecture=host_platform.machine() or "unknown",
            capabilities=("xcode_test", "simctl", "screen_runtime", "unsigned_app_build"),
            metadata={
                "name": _bounded(device.get("name") or "iOS Simulator", name="simulator_name", limit=120),
                "state": state[:40],
                "environment_kind": "vendor_simulator",
            },
            source="ios-simulator-probe",
        )


class DesktopVMProbe:
    """Probe the current desktop qualification host when it is explicitly VM-scoped."""

    def __init__(self, environment: Mapping[str, str] | None = None) -> None:
        self._environment = dict(os.environ if environment is None else environment)

    def probe(self) -> NativeDeviceEvidence:
        env = self._environment
        github_hosted = str(env.get("GITHUB_ACTIONS", "")).lower() == "true"
        explicitly_vm = str(env.get("VISHNU_DESKTOP_VM", "")).lower() in {"1", "true", "yes"}
        if not (github_hosted or explicitly_vm):
            raise RuntimeError("desktop native probe requires a declared VM/hosted-runner environment")
        system = host_platform.system().lower()
        mapping = {"windows": NativePlatform.WINDOWS, "darwin": NativePlatform.MACOS, "linux": NativePlatform.LINUX}
        native_platform = mapping.get(system)
        if native_platform is None:
            raise RuntimeError("unsupported desktop qualification platform")
        run_id = str(env.get("GITHUB_RUN_ID") or "local-vm")
        target_id = _identifier(f"desktop-{native_platform.value}-{run_id}", name="target_id")
        return NativeDeviceEvidence(
            provider=NativeProvider.DESKTOP_VM,
            platform=native_platform,
            target_id=target_id,
            status=NativeStatus.READY,
            os_version=f"{host_platform.system()} {host_platform.release()}",
            architecture=host_platform.machine() or "unknown",
            capabilities=("desktop_runtime", "package_smoke", "python_runtime"),
            metadata={
                "environment_kind": "github_actions_hosted_runner" if github_hosted else "declared_vm",
                "runner_os": str(env.get("RUNNER_OS") or host_platform.system())[:80],
                "virtualization_assertion": "qualification_runner",
            },
            source="desktop-vm-probe",
        )


class NativeDeviceLab:
    """Persistent qualification evidence for emulators, simulators and desktop VMs.

    It stores observation evidence only. It never accepts arbitrary commands and
    never grants ToolRegistry, Computer Control, or physical-device authority.
    """

    def __init__(self, path: str | Path, *, event_bus: Any | None = None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._event_bus = event_bus
        self._lock = RLock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS native_device_evidence (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                platform TEXT NOT NULL,
                target_id TEXT NOT NULL,
                status TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        self._db.commit()

    @staticmethod
    def profiles() -> list[dict[str, Any]]:
        return [PROFILES[key].to_dict() for key in NativeProvider]

    def record(self, evidence: NativeDeviceEvidence) -> dict[str, Any]:
        if not isinstance(evidence, NativeDeviceEvidence):
            raise TypeError("evidence must be NativeDeviceEvidence")
        snapshot = evidence.to_dict()
        encoded = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        with self._lock:
            cursor = self._db.execute(
                "INSERT INTO native_device_evidence(provider, platform, target_id, status, observed_at, payload_json) VALUES(?,?,?,?,?,?)",
                (
                    evidence.provider.value,
                    evidence.platform.value,
                    evidence.target_id,
                    evidence.status.value,
                    evidence.observed_at.isoformat(),
                    encoded,
                ),
            )
            self._db.commit()
            evidence_id = int(cursor.lastrowid)
        if self._event_bus is not None:
            self._event_bus.emit(
                "sensorium.native_device.evidence_recorded",
                evidence_id=evidence_id,
                provider=evidence.provider.value,
                platform=evidence.platform.value,
                target_id=evidence.target_id,
                status=evidence.status.value,
                physical_device=False,
                execution_authority=False,
            )
        return {"evidence_id": evidence_id, **snapshot}

    def list(self, *, limit: int = 100, provider: NativeProvider | str | None = None) -> list[dict[str, Any]]:
        if limit < 1 or limit > 500:
            raise ValueError("limit must be between 1 and 500")
        params: list[Any] = []
        where = ""
        if provider is not None:
            normalized = NativeProvider(provider)
            where = " WHERE provider=?"
            params.append(normalized.value)
        params.append(limit)
        with self._lock:
            rows = self._db.execute(
                f"SELECT id, payload_json FROM native_device_evidence{where} ORDER BY id DESC LIMIT ?",
                tuple(params),
            ).fetchall()
        result = []
        for row in rows:
            payload = json.loads(str(row["payload_json"]))
            result.append({"evidence_id": int(row["id"]), **payload})
        return result

    def close(self) -> None:
        with self._lock:
            self._db.close()
