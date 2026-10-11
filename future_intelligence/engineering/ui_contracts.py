from __future__ import annotations

from dataclasses import dataclass

from .contracts import BrowserEngine, DeviceProfile, EngineeringSpec


CANONICAL_DEVICES: tuple[DeviceProfile, ...] = (
    DeviceProfile("tiny-phone", 320, 568, 2.0, True, True),
    DeviceProfile("android-compact", 360, 800, 2.0, True, True),
    DeviceProfile("iphone-compact", 375, 812, 3.0, True, True),
    DeviceProfile("iphone-standard", 390, 844, 3.0, True, True),
    DeviceProfile("large-phone", 430, 932, 3.0, True, True),
    DeviceProfile("tablet-portrait", 768, 1024, 2.0, True, True),
    DeviceProfile("tablet-landscape", 1024, 768, 2.0, True, True, "landscape"),
    DeviceProfile("laptop", 1280, 720),
    DeviceProfile("desktop", 1440, 900),
    DeviceProfile("reference-desktop", 1536, 1024),
    DeviceProfile("full-hd", 1920, 1080),
    DeviceProfile("large-desktop", 2560, 1440),
)

CANONICAL_STATES = (
    "empty", "normal", "large", "loading", "slow", "offline", "partial_failure",
    "unauthorized", "forbidden", "missing", "server_error", "session_expired",
    "blocked", "approval_required", "recovery", "long_content",
)

DEFAULT_BREAKPOINTS = (320, 360, 375, 390, 430, 600, 768, 820, 1024, 1280, 1440, 1536, 1920, 2560)


def breakpoint_neighbours(values=DEFAULT_BREAKPOINTS) -> tuple[int, ...]:
    result: set[int] = set()
    for value in values:
        width = int(value)
        result.update(item for item in (width - 1, width, width + 1) if item >= 240)
    return tuple(sorted(result))


@dataclass(frozen=True)
class UIQualificationPlan:
    devices: tuple[DeviceProfile, ...]
    browsers: tuple[BrowserEngine, ...]
    states: tuple[str, ...]
    breakpoint_widths: tuple[int, ...]
    accessibility_required: bool
    visual_review_required: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "devices": [item.to_dict() for item in self.devices],
            "browsers": [item.value for item in self.browsers],
            "states": list(self.states),
            "breakpoint_widths": list(self.breakpoint_widths),
            "accessibility_required": self.accessibility_required,
            "visual_review_required": self.visual_review_required,
        }


def plan_ui_qualification(spec: EngineeringSpec) -> UIQualificationPlan:
    devices = spec.devices or CANONICAL_DEVICES
    browsers = spec.browsers or (BrowserEngine.CHROMIUM,)
    states = spec.required_states or ("normal",)
    return UIQualificationPlan(
        devices=devices,
        browsers=browsers,
        states=states,
        breakpoint_widths=breakpoint_neighbours(),
        accessibility_required=spec.accessibility_required,
        visual_review_required=spec.visual_review_required,
    )
