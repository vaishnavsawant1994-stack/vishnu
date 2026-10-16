"""Device evidence boundaries for Voice Lab qualification."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
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


def physical_acoustics_gate(item: DeviceQualificationEvidence) -> QualificationGate:
    if item.device_class is not DeviceClass.PHYSICAL:
        return QualificationGate("physical-device-acoustics", GateStatus.BLOCKED, notes="emulator/simulator/VM evidence cannot satisfy real physical acoustics")
    complete = bool(item.microphone_route and item.speaker_route and item.attestation and
                    item.bluetooth_tested and item.echo_tested and item.noise_tested and
                    item.route_switch_tested and item.acoustic_latency_ms is not None)
    return QualificationGate("physical-device-acoustics", GateStatus.PASS if complete else GateStatus.BLOCKED,
                             observed=item.acoustic_latency_ms,
                             notes="physical device evidence complete" if complete else "physical device acoustic evidence is incomplete")
