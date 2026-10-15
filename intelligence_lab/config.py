from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
import os
from pathlib import Path


_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


class LabConfigurationError(ValueError):
    """Raised when Intelligence Lab configuration is invalid."""


class CapabilityLevel(IntEnum):
    """Maximum authority exposed to the experimental runtime.

    These levels are deliberately separate from the stable Vishnu autonomy mode.
    Raising a Lab level never changes ToolRegistry permissions or owner policy.
    """

    OFF = 0
    OBSERVE = 1
    THINK = 2
    SIMULATE = 3
    PROPOSE = 4
    GOVERNED_EXECUTION = 5
    LIMITED_AUTONOMY = 6

    @classmethod
    def parse(cls, value: str | int | "CapabilityLevel") -> "CapabilityLevel":
        if isinstance(value, cls):
            return value
        if isinstance(value, int):
            try:
                return cls(value)
            except ValueError as exc:
                raise LabConfigurationError(f"invalid Intelligence Lab level: {value}") from exc
        normalized = str(value).strip().upper().replace(" ", "_").replace("-", "_")
        aliases = {
            "0": cls.OFF,
            "1": cls.OBSERVE,
            "2": cls.THINK,
            "3": cls.SIMULATE,
            "4": cls.PROPOSE,
            "5": cls.GOVERNED_EXECUTION,
            "6": cls.LIMITED_AUTONOMY,
        }
        if normalized in aliases:
            return aliases[normalized]
        try:
            return cls[normalized]
        except KeyError as exc:
            raise LabConfigurationError(f"invalid Intelligence Lab level: {value}") from exc


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in _TRUE:
        return True
    if normalized in _FALSE:
        return False
    raise LabConfigurationError(f"{name} must be a boolean")


@dataclass(frozen=True)
class LabSettings:
    """Configuration for the isolated Intelligence Lab.

    The Lab is fail-closed: disabled by default. When disabled, the effective
    level is always OFF even if a higher level was supplied in the environment.
    """

    enabled: bool = False
    level: CapabilityLevel = CapabilityLevel.OFF
    data_dir: Path = Path.home() / ".personal_ai" / "intelligence-lab"
    autonomous_allowlist: tuple[str, ...] = ()
    max_plan_steps: int = 12
    minimum_promotion_score: float = 0.85

    def __post_init__(self) -> None:
        object.__setattr__(self, "data_dir", Path(self.data_dir).expanduser().resolve())
        if not self.enabled:
            object.__setattr__(self, "level", CapabilityLevel.OFF)
        elif self.level is CapabilityLevel.OFF:
            # Enabled with OFF is valid and useful for configuration checks.
            pass
        if not 1 <= int(self.max_plan_steps) <= 64:
            raise LabConfigurationError("max_plan_steps must be between 1 and 64")
        if not 0.0 <= float(self.minimum_promotion_score) <= 1.0:
            raise LabConfigurationError("minimum_promotion_score must be between 0 and 1")

    @classmethod
    def from_environment(cls, *, stable_data_dir: Path | None = None) -> "LabSettings":
        enabled = _env_bool("VISHNU_INTELLIGENCE_LAB_ENABLED", False)
        raw_level = os.getenv("VISHNU_INTELLIGENCE_LAB_LEVEL", "1" if enabled else "0")
        level = CapabilityLevel.parse(raw_level)
        default_dir = (
            Path(stable_data_dir) / "intelligence-lab"
            if stable_data_dir is not None
            else Path.home() / ".personal_ai" / "intelligence-lab"
        )
        data_dir = Path(os.getenv("VISHNU_INTELLIGENCE_LAB_DATA_DIR", str(default_dir)))
        allowlist = tuple(
            item.strip()
            for item in os.getenv("VISHNU_INTELLIGENCE_LAB_AUTONOMY_ALLOWLIST", "").split(",")
            if item.strip()
        )
        try:
            max_steps = int(os.getenv("VISHNU_INTELLIGENCE_LAB_MAX_PLAN_STEPS", "12"))
            promotion_score = float(os.getenv("VISHNU_INTELLIGENCE_LAB_MIN_PROMOTION_SCORE", "0.85"))
        except ValueError as exc:
            raise LabConfigurationError("invalid numeric Intelligence Lab setting") from exc
        return cls(
            enabled=enabled,
            level=level,
            data_dir=data_dir,
            autonomous_allowlist=allowlist,
            max_plan_steps=max_steps,
            minimum_promotion_score=promotion_score,
        )

    def require(self, minimum: CapabilityLevel) -> None:
        if not self.enabled:
            raise PermissionError("Vishnu Intelligence Lab is disabled")
        if self.level < minimum:
            raise PermissionError(
                f"Intelligence Lab level {self.level.name} does not permit {minimum.name}"
            )

    def public_snapshot(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "level": self.level.name,
            "level_value": int(self.level),
            "autonomous_allowlist": list(self.autonomous_allowlist),
            "max_plan_steps": self.max_plan_steps,
            "minimum_promotion_score": self.minimum_promotion_score,
        }
