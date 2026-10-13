from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from threading import RLock
from typing import Any

from sensorium.models import DataClassification, DeviceState, SensorEvent, SensorKind, VirtualDevice
from sensorium.virtual_device_lab import VirtualDeviceLab


class VirtualPlatform(StrEnum):
    ANDROID = "android"
    IOS = "ios"
    WINDOWS = "windows"
    MACOS = "macos"
    LINUX = "linux"


class PermissionState(StrEnum):
    GRANTED = "granted"
    DENIED = "denied"
    PROMPT = "prompt"
    RESTRICTED = "restricted"


class NetworkType(StrEnum):
    WIFI = "wifi"
    CELLULAR = "cellular"
    ETHERNET = "ethernet"
    OFFLINE = "offline"


class VirtualFault(StrEnum):
    NETWORK_DROP = "network_drop"
    LOW_BATTERY = "low_battery"
    PERMISSION_REVOCATION = "permission_revocation"
    DISCONNECT_RECONNECT = "disconnect_reconnect"


@dataclass(frozen=True, slots=True)
class VirtualPlatformProfile:
    platform: VirtualPlatform
    device_class: str
    default_os_version: str
    capabilities: frozenset[SensorKind]
    default_permissions: dict[str, PermissionState]


@dataclass(slots=True)
class VirtualRuntimeState:
    battery_percent: int = 100
    charging: bool = False
    network_type: NetworkType = NetworkType.WIFI
    network_online: bool = True
    airplane_mode: bool = False
    signal_percent: int = 100
    locked: bool = False
    foreground_app: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    permissions: dict[str, PermissionState] = field(default_factory=dict)
    notification_count: int = 0
    last_fault: str | None = None

    def safe_dict(self) -> dict[str, Any]:
        return {
            "battery_percent": self.battery_percent,
            "charging": self.charging,
            "network": {
                "type": self.network_type.value,
                "online": self.network_online,
                "airplane_mode": self.airplane_mode,
                "signal_percent": self.signal_percent,
            },
            "locked": self.locked,
            "foreground_app": self.foreground_app,
            "location": {
                "available": self.latitude is not None and self.longitude is not None,
                "latitude": self.latitude,
                "longitude": self.longitude,
            },
            "permissions": {key: value.value for key, value in sorted(self.permissions.items())},
            "notification_count": self.notification_count,
            "last_fault": self.last_fault,
            "simulated": True,
            "execution_authority": False,
        }


_COMMON_PERMISSIONS = {
    "camera": PermissionState.PROMPT,
    "microphone": PermissionState.PROMPT,
    "location": PermissionState.PROMPT,
    "notifications": PermissionState.PROMPT,
    "clipboard": PermissionState.GRANTED,
    "screen": PermissionState.GRANTED,
}

_MOBILE_CAPABILITIES = frozenset(
    {
        SensorKind.SCREEN,
        SensorKind.CAMERA,
        SensorKind.MICROPHONE,
        SensorKind.CLIPBOARD,
        SensorKind.WINDOW,
        SensorKind.SYSTEM,
        SensorKind.LOCATION,
        SensorKind.NETWORK,
        SensorKind.CUSTOM,
    }
)

_DESKTOP_CAPABILITIES = frozenset(
    {
        SensorKind.SCREEN,
        SensorKind.CAMERA,
        SensorKind.MICROPHONE,
        SensorKind.CLIPBOARD,
        SensorKind.WINDOW,
        SensorKind.INPUT,
        SensorKind.SYSTEM,
        SensorKind.LOCATION,
        SensorKind.NETWORK,
        SensorKind.CUSTOM,
    }
)

PROFILES: dict[VirtualPlatform, VirtualPlatformProfile] = {
    VirtualPlatform.ANDROID: VirtualPlatformProfile(
        VirtualPlatform.ANDROID, "phone", "Android 16", _MOBILE_CAPABILITIES, dict(_COMMON_PERMISSIONS)
    ),
    VirtualPlatform.IOS: VirtualPlatformProfile(
        VirtualPlatform.IOS, "phone", "iOS 27", _MOBILE_CAPABILITIES, dict(_COMMON_PERMISSIONS)
    ),
    VirtualPlatform.WINDOWS: VirtualPlatformProfile(
        VirtualPlatform.WINDOWS, "desktop", "Windows 11", _DESKTOP_CAPABILITIES, dict(_COMMON_PERMISSIONS)
    ),
    VirtualPlatform.MACOS: VirtualPlatformProfile(
        VirtualPlatform.MACOS, "desktop", "macOS", _DESKTOP_CAPABILITIES, dict(_COMMON_PERMISSIONS)
    ),
    VirtualPlatform.LINUX: VirtualPlatformProfile(
        VirtualPlatform.LINUX, "desktop", "Linux", _DESKTOP_CAPABILITIES, dict(_COMMON_PERMISSIONS)
    ),
}


class VirtualDeviceFleet:
    """High-level, hardware-free Android/iOS/desktop simulation.

    The fleet is observation-only from Vishnu's authority perspective. It can
    mutate *simulated* device state and publish synthetic Sensorium events, but
    it cannot dispatch host keyboard/mouse, launch host apps, open URLs, install
    packages, or otherwise gain physical execution authority.
    """

    VERSION = "2"
    MAX_NOTIFICATION_TEXT = 4096
    MAX_FIXTURE_REF = 1000
    MAX_ANALYSIS = 20_000
    PERMISSIONS = frozenset(_COMMON_PERMISSIONS)

    def __init__(self, lab: VirtualDeviceLab) -> None:
        if not isinstance(lab, VirtualDeviceLab):
            raise TypeError("lab must be a VirtualDeviceLab")
        self._lab = lab
        self._states: dict[str, VirtualRuntimeState] = {}
        self._platforms: dict[str, VirtualPlatform] = {}
        self._lock = RLock()

    @staticmethod
    def profiles() -> list[dict[str, Any]]:
        return [
            {
                "platform": profile.platform.value,
                "device_class": profile.device_class,
                "default_os_version": profile.default_os_version,
                "capabilities": sorted(kind.value for kind in profile.capabilities),
                "permissions": {key: value.value for key, value in sorted(profile.default_permissions.items())},
                "simulated": True,
                "execution_authority": False,
            }
            for profile in PROFILES.values()
        ]

    def provision(
        self,
        *,
        device_id: str,
        platform: VirtualPlatform | str,
        name: str | None = None,
        os_version: str | None = None,
        controller_device_id: str | None = None,
    ) -> dict[str, Any]:
        normalized = VirtualPlatform(platform)
        profile = PROFILES[normalized]
        virtual = VirtualDevice(
            device_id=device_id,
            name=name or f"Virtual {normalized.value}",
            platform=f"virtual-{normalized.value}",
            capabilities=profile.capabilities,
            metadata={
                "virtual_fleet_version": self.VERSION,
                "device_class": profile.device_class,
                "os_version": str(os_version or profile.default_os_version)[:80],
                "simulated": True,
                "execution_authority": False,
            },
        )
        snapshot = self._lab.register_device(virtual, controller_device_id=controller_device_id)
        with self._lock:
            self._platforms[device_id] = normalized
            self._states[device_id] = VirtualRuntimeState(permissions=dict(profile.default_permissions))
        return {"device": snapshot, "runtime": self.snapshot(device_id, controller_device_id=controller_device_id)}

    def remove(self, device_id: str, *, controller_device_id: str | None = None) -> None:
        self._lab.remove_device(device_id, controller_device_id=controller_device_id)
        with self._lock:
            self._platforms.pop(device_id, None)
            self._states.pop(device_id, None)

    def _state(self, device_id: str) -> VirtualRuntimeState:
        with self._lock:
            state = self._states.get(device_id)
            if state is None:
                raise KeyError("virtual fleet device not found")
            return state

    def _platform(self, device_id: str) -> VirtualPlatform:
        with self._lock:
            platform = self._platforms.get(device_id)
            if platform is None:
                raise KeyError("virtual fleet device not found")
            return platform

    def snapshot(self, device_id: str, *, controller_device_id: str | None = None) -> dict[str, Any]:
        device = self._lab.get_device(device_id, controller_device_id=controller_device_id)
        state = self._state(device_id)
        platform = self._platform(device_id)
        return {
            "device_id": device_id,
            "platform": platform.value,
            "device_state": device["state"],
            "runtime": state.safe_dict(),
            "capabilities": list(device["capabilities"]),
            "simulated": True,
            "execution_authority": False,
        }

    def list(self, *, controller_device_id: str | None = None) -> list[dict[str, Any]]:
        # Authorize once through the canonical lab before exposing fleet metadata.
        self._lab.list_devices(controller_device_id=controller_device_id)
        with self._lock:
            ids = sorted(self._states)
        return [self.snapshot(device_id, controller_device_id=controller_device_id) for device_id in ids]

    def _inject(
        self,
        device_id: str,
        kind: SensorKind,
        payload: dict[str, Any],
        *,
        controller_device_id: str | None,
        classification: DataClassification = DataClassification.INTERNAL,
    ) -> dict[str, Any]:
        event = SensorEvent.create(
            device_id=device_id,
            kind=kind,
            payload=payload,
            data_classification=classification,
            source="virtual-device-fleet",
        )
        return self._lab.inject_event(event, controller_device_id=controller_device_id)

    def set_battery(
        self,
        device_id: str,
        percent: int,
        *,
        charging: bool = False,
        controller_device_id: str | None = None,
    ) -> dict[str, Any]:
        if isinstance(percent, bool) or not isinstance(percent, int) or not 0 <= percent <= 100:
            raise ValueError("battery percent must be an integer between 0 and 100")
        self._inject(
            device_id,
            SensorKind.SYSTEM,
            {"battery_percent": percent, "charging": bool(charging)},
            controller_device_id=controller_device_id,
        )
        state = self._state(device_id)
        with self._lock:
            state.battery_percent = percent
            state.charging = bool(charging)
        return self.snapshot(device_id, controller_device_id=controller_device_id)

    def set_network(
        self,
        device_id: str,
        network_type: NetworkType | str,
        *,
        online: bool | None = None,
        airplane_mode: bool = False,
        signal_percent: int = 100,
        controller_device_id: str | None = None,
    ) -> dict[str, Any]:
        normalized = NetworkType(network_type)
        if isinstance(signal_percent, bool) or not isinstance(signal_percent, int) or not 0 <= signal_percent <= 100:
            raise ValueError("signal percent must be an integer between 0 and 100")
        resolved_online = normalized != NetworkType.OFFLINE if online is None else bool(online)
        if airplane_mode:
            resolved_online = False
            normalized = NetworkType.OFFLINE
        self._inject(
            device_id,
            SensorKind.NETWORK,
            {
                "network_type": normalized.value,
                "online": resolved_online,
                "airplane_mode": bool(airplane_mode),
                "signal_percent": signal_percent,
            },
            controller_device_id=controller_device_id,
        )
        state = self._state(device_id)
        with self._lock:
            state.network_type = normalized
            state.network_online = resolved_online
            state.airplane_mode = bool(airplane_mode)
            state.signal_percent = signal_percent
        return self.snapshot(device_id, controller_device_id=controller_device_id)

    def set_permission(
        self,
        device_id: str,
        permission: str,
        state: PermissionState | str,
        *,
        controller_device_id: str | None = None,
    ) -> dict[str, Any]:
        name = str(permission).strip().lower()
        if name not in self.PERMISSIONS:
            raise ValueError("unsupported virtual permission")
        normalized = PermissionState(state)
        self._inject(
            device_id,
            SensorKind.CUSTOM,
            {"event": "permission_changed", "permission": name, "state": normalized.value},
            controller_device_id=controller_device_id,
        )
        runtime = self._state(device_id)
        with self._lock:
            runtime.permissions[name] = normalized
        return self.snapshot(device_id, controller_device_id=controller_device_id)

    def set_location(
        self,
        device_id: str,
        latitude: float,
        longitude: float,
        *,
        accuracy_meters: float = 10.0,
        controller_device_id: str | None = None,
    ) -> dict[str, Any]:
        lat = float(latitude)
        lon = float(longitude)
        accuracy = float(accuracy_meters)
        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise ValueError("location coordinates are invalid")
        if not 0 <= accuracy <= 100_000:
            raise ValueError("location accuracy is invalid")
        runtime = self._state(device_id)
        if runtime.permissions.get("location") != PermissionState.GRANTED:
            raise PermissionError("virtual location permission is not granted")
        self._inject(
            device_id,
            SensorKind.LOCATION,
            {"latitude": lat, "longitude": lon, "accuracy_meters": accuracy},
            controller_device_id=controller_device_id,
            classification=DataClassification.SENSITIVE,
        )
        with self._lock:
            runtime.latitude = lat
            runtime.longitude = lon
        return self.snapshot(device_id, controller_device_id=controller_device_id)

    def set_foreground_app(
        self,
        device_id: str,
        app_id: str,
        *,
        title: str | None = None,
        controller_device_id: str | None = None,
    ) -> dict[str, Any]:
        app = str(app_id).strip()
        if not app or len(app) > 200:
            raise ValueError("app_id must contain 1-200 characters")
        bounded_title = None if title is None else str(title)[:500]
        self._inject(
            device_id,
            SensorKind.WINDOW,
            {"foreground_app": app, "title": bounded_title},
            controller_device_id=controller_device_id,
            classification=DataClassification.SENSITIVE,
        )
        runtime = self._state(device_id)
        with self._lock:
            runtime.foreground_app = app
        return self.snapshot(device_id, controller_device_id=controller_device_id)

    def set_locked(
        self,
        device_id: str,
        locked: bool,
        *,
        controller_device_id: str | None = None,
    ) -> dict[str, Any]:
        self._inject(
            device_id,
            SensorKind.SYSTEM,
            {"locked": bool(locked)},
            controller_device_id=controller_device_id,
        )
        runtime = self._state(device_id)
        with self._lock:
            runtime.locked = bool(locked)
        return self.snapshot(device_id, controller_device_id=controller_device_id)

    def push_notification(
        self,
        device_id: str,
        *,
        title: str,
        body: str = "",
        app_id: str = "fixture.app",
        controller_device_id: str | None = None,
    ) -> dict[str, Any]:
        runtime = self._state(device_id)
        if runtime.permissions.get("notifications") != PermissionState.GRANTED:
            raise PermissionError("virtual notification permission is not granted")
        bounded_title = str(title)
        bounded_body = str(body)
        if not bounded_title or len(bounded_title) > 512 or len(bounded_body) > self.MAX_NOTIFICATION_TEXT:
            raise ValueError("virtual notification content is invalid")
        event = self._inject(
            device_id,
            SensorKind.CUSTOM,
            {"event": "notification_received", "app_id": str(app_id)[:200], "title": bounded_title, "body": bounded_body},
            controller_device_id=controller_device_id,
            classification=DataClassification.SENSITIVE,
        )
        with self._lock:
            runtime.notification_count += 1
        return {"event": event, "runtime": self.snapshot(device_id, controller_device_id=controller_device_id)}

    def publish_camera_fixture(
        self,
        device_id: str,
        *,
        fixture_ref: str,
        analysis: str = "",
        width: int = 1280,
        height: int = 720,
        controller_device_id: str | None = None,
    ) -> dict[str, Any]:
        runtime = self._state(device_id)
        if runtime.permissions.get("camera") != PermissionState.GRANTED:
            raise PermissionError("virtual camera permission is not granted")
        ref = str(fixture_ref).strip()
        if not ref or len(ref) > self.MAX_FIXTURE_REF:
            raise ValueError("fixture_ref is invalid")
        if not 1 <= int(width) <= 32768 or not 1 <= int(height) <= 32768:
            raise ValueError("camera dimensions are invalid")
        if len(str(analysis)) > self.MAX_ANALYSIS:
            raise ValueError("camera analysis is too large")
        return self._inject(
            device_id,
            SensorKind.CAMERA,
            {"fixture_ref": ref, "analysis": str(analysis), "width": int(width), "height": int(height), "raw_bytes": False},
            controller_device_id=controller_device_id,
            classification=DataClassification.SENSITIVE,
        )

    def publish_microphone_fixture(
        self,
        device_id: str,
        *,
        fixture_ref: str,
        transcript: str = "",
        duration_ms: int = 1000,
        controller_device_id: str | None = None,
    ) -> dict[str, Any]:
        runtime = self._state(device_id)
        if runtime.permissions.get("microphone") != PermissionState.GRANTED:
            raise PermissionError("virtual microphone permission is not granted")
        ref = str(fixture_ref).strip()
        if not ref or len(ref) > self.MAX_FIXTURE_REF:
            raise ValueError("fixture_ref is invalid")
        if not 0 <= int(duration_ms) <= 600_000:
            raise ValueError("microphone duration is invalid")
        if len(str(transcript)) > self.MAX_ANALYSIS:
            raise ValueError("microphone transcript is too large")
        return self._inject(
            device_id,
            SensorKind.MICROPHONE,
            {"fixture_ref": ref, "transcript": str(transcript), "duration_ms": int(duration_ms), "raw_audio": False},
            controller_device_id=controller_device_id,
            classification=DataClassification.SENSITIVE,
        )

    def disconnect(self, device_id: str, *, controller_device_id: str | None = None) -> dict[str, Any]:
        self._inject(
            device_id,
            SensorKind.SYSTEM,
            {"connection": "disconnecting"},
            controller_device_id=controller_device_id,
        )
        device = self._lab.set_state(device_id, DeviceState.OFFLINE, controller_device_id=controller_device_id)
        return {"device": device, "simulated": True, "execution_authority": False}

    def reconnect(self, device_id: str, *, controller_device_id: str | None = None) -> dict[str, Any]:
        self._lab.set_state(device_id, DeviceState.ONLINE, controller_device_id=controller_device_id)
        self._inject(
            device_id,
            SensorKind.SYSTEM,
            {"connection": "reconnected"},
            controller_device_id=controller_device_id,
        )
        return self.snapshot(device_id, controller_device_id=controller_device_id)

    def simulate_fault(
        self,
        device_id: str,
        fault: VirtualFault | str,
        *,
        permission: str = "camera",
        controller_device_id: str | None = None,
    ) -> dict[str, Any]:
        normalized = VirtualFault(fault)
        runtime = self._state(device_id)
        if normalized == VirtualFault.NETWORK_DROP:
            result = self.set_network(device_id, NetworkType.OFFLINE, controller_device_id=controller_device_id)
        elif normalized == VirtualFault.LOW_BATTERY:
            result = self.set_battery(device_id, 5, charging=False, controller_device_id=controller_device_id)
        elif normalized == VirtualFault.PERMISSION_REVOCATION:
            result = self.set_permission(
                device_id,
                permission,
                PermissionState.DENIED,
                controller_device_id=controller_device_id,
            )
        else:
            self.disconnect(device_id, controller_device_id=controller_device_id)
            result = self.reconnect(device_id, controller_device_id=controller_device_id)
        with self._lock:
            runtime.last_fault = normalized.value
        return result
