"""Device evidence boundaries and native-lab bridge for Voice Lab qualification."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .evaluation import GateStatus, QualificationGate


class DeviceClass(str, Enum):
    ANDROID_EMULATOR = "android_emulator"
    IOS_SIMULATOR = "ios_simulator"
    DESKTOP_VM = "desktop_vm"
    PHYSICAL = "physical"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class DeviceQualificationEvidence:
    device_id: str
    device_class: DeviceClass
    os_name: str
    microphone_route: str = ""
    speaker_route: str = ""
    bluetooth_tested: bool = False
    echo_tested: bool = False
    noise_tested: bool = False
    route_switch_tested: bool = False
    acoustic_latency_ms: float | None = None
    attestation: str = ""


@dataclass(frozen=True, slots=True)
class NativeDeviceSoftwareEvidence:
    provider_type: DeviceClass
    device_id: str
    os_name: str
    identity_verified: bool
    software_probe_passed: bool
    evidence_reference: str


_NATIVE_PROVIDER_ALIASES = {
    "ANDROID_EMULATOR": DeviceClass.ANDROID_EMULATOR,
    "android_emulator": DeviceClass.ANDROID_EMULATOR,
    "IOS_SIMULATOR": DeviceClass.IOS_SIMULATOR,
    "ios_simulator": DeviceClass.IOS_SIMULATOR,
    "DESKTOP_VM": DeviceClass.DESKTOP_VM,
    "desktop_vm": DeviceClass.DESKTOP_VM,
    "LINUX_VM": DeviceClass.DESKTOP_VM,
    "WINDOWS_VM": DeviceClass.DESKTOP_VM,
    "MACOS_VM": DeviceClass.DESKTOP_VM,
}


def native_software_evidence(payload: dict[str, Any]) -> NativeDeviceSoftwareEvidence:
    """Translate bounded native-lab evidence without importing another branch/runtime."""
    source = str(payload.get("provider_type") or payload.get("provider") or payload.get("source") or "")
    provider_type = _NATIVE_PROVIDER_ALIASES.get(source, DeviceClass.UNKNOWN)
    return NativeDeviceSoftwareEvidence(
        provider_type=provider_type,
        device_id=str(payload.get("device_id") or payload.get("serial") or payload.get("udid") or ""),
        os_name=str(payload.get("os_name") or payload.get("platform") or payload.get("os") or ""),
        identity_verified=payload.get("identity_verified") is True,
        software_probe_passed=(payload.get("software_probe_passed") is True or payload.get("probe_passed") is True),
        evidence_reference=str(payload.get("evidence_reference") or payload.get("artifact") or ""),
    )


def native_software_gate(item: NativeDeviceSoftwareEvidence) -> QualificationGate:
    valid_class = item.provider_type in {
        DeviceClass.ANDROID_EMULATOR,
        DeviceClass.IOS_SIMULATOR,
        DeviceClass.DESKTOP_VM,
    }
    complete = bool(
        valid_class
        and item.device_id
        and item.os_name
        and item.identity_verified
        and item.software_probe_passed
        and item.evidence_reference
    )
    return QualificationGate(
        "native-device-software-qualification",
        GateStatus.PASS if complete else GateStatus.BLOCKED,
        notes="native software qualification evidence complete" if complete else "native software evidence incomplete or untrusted",
    )


def physical_acoustics_gate(item: DeviceQualificationEvidence) -> QualificationGate:
    if item.device_class is not DeviceClass.PHYSICAL:
        return QualificationGate(
            "physical-device-acoustics",
            GateStatus.BLOCKED,
            notes="emulator/simulator/VM evidence cannot satisfy real physical acoustics",
        )
    complete = bool(
        item.microphone_route
        and item.speaker_route
        and item.attestation
        and item.bluetooth_tested
        and item.echo_tested
        and item.noise_tested
        and item.route_switch_tested
        and item.acoustic_latency_ms is not None
    )
    return QualificationGate(
        "physical-device-acoustics",
        GateStatus.PASS if complete else GateStatus.BLOCKED,
        observed=item.acoustic_latency_ms,
        notes="physical device evidence complete" if complete else "physical device acoustic evidence is incomplete",
    )
