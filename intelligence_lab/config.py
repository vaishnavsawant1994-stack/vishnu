from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
import math
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


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise LabConfigurationError(f"{name} must be an integer") from exc


def _env_float(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError as exc:
        raise LabConfigurationError(f"{name} must be numeric") from exc
    if not math.isfinite(value):
        raise LabConfigurationError(f"{name} must be finite")
    return value


@dataclass(frozen=True)
class LabSettings:
    """Configuration for the isolated Intelligence Lab.

    The Lab is fail-closed: disabled by default. Phase-2 intelligence limits are
    resource ceilings only; none grant Core execution or security authority.
    """

    enabled: bool = False
    level: CapabilityLevel = CapabilityLevel.OFF
    data_dir: Path = Path.home() / ".personal_ai" / "intelligence-lab"
    autonomous_allowlist: tuple[str, ...] = ()
    max_plan_steps: int = 12
    minimum_promotion_score: float = 0.85
    max_models: int = 3
    benchmark_variants: int = 3
    max_skill_steps: int = 12
    learning_window: int = 200
    world_history_limit: int = 500
    affect_history_limit: int = 100
    max_long_horizon_cycles: int = 64
    max_long_horizon_failures: int = 8
    max_long_horizon_actions: int = 64

    def __post_init__(self) -> None:
        object.__setattr__(self, "data_dir", Path(self.data_dir).expanduser().resolve())
        if not self.enabled:
            object.__setattr__(self, "level", CapabilityLevel.OFF)
        self._bounded("max_plan_steps", self.max_plan_steps, 1, 64)
        self._bounded("max_models", self.max_models, 2, 5)
        self._bounded("benchmark_variants", self.benchmark_variants, 1, 20)
        self._bounded("max_skill_steps", self.max_skill_steps, 1, 32)
        self._bounded("learning_window", self.learning_window, 20, 1000)
        self._bounded("world_history_limit", self.world_history_limit, 20, 500)
        self._bounded("affect_history_limit", self.affect_history_limit, 10, 500)
        self._bounded("max_long_horizon_cycles", self.max_long_horizon_cycles, 1, 512)
        self._bounded("max_long_horizon_failures", self.max_long_horizon_failures, 1, 64)
        self._bounded("max_long_horizon_actions", self.max_long_horizon_actions, 1, 512)
        if not 0.0 <= float(self.minimum_promotion_score) <= 1.0:
            raise LabConfigurationError("minimum_promotion_score must be between 0 and 1")

    @staticmethod
    def _bounded(name: str, value: int, minimum: int, maximum: int) -> None:
        if not minimum <= int(value) <= maximum:
            raise LabConfigurationError(f"{name} must be between {minimum} and {maximum}")

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
        return cls(
            enabled=enabled,
            level=level,
            data_dir=data_dir,
            autonomous_allowlist=allowlist,
            max_plan_steps=_env_int("VISHNU_INTELLIGENCE_LAB_MAX_PLAN_STEPS", 12),
            minimum_promotion_score=_env_float("VISHNU_INTELLIGENCE_LAB_MIN_PROMOTION_SCORE", 0.85),
            max_models=_env_int("VISHNU_INTELLIGENCE_LAB_MAX_MODELS", 3),
            benchmark_variants=_env_int("VISHNU_INTELLIGENCE_LAB_BENCHMARK_VARIANTS", 3),
            max_skill_steps=_env_int("VISHNU_INTELLIGENCE_LAB_MAX_SKILL_STEPS", 12),
            learning_window=_env_int("VISHNU_INTELLIGENCE_LAB_LEARNING_WINDOW", 200),
            world_history_limit=_env_int("VISHNU_INTELLIGENCE_LAB_WORLD_HISTORY_LIMIT", 500),
            affect_history_limit=_env_int("VISHNU_INTELLIGENCE_LAB_AFFECT_HISTORY_LIMIT", 100),
            max_long_horizon_cycles=_env_int("VISHNU_INTELLIGENCE_LAB_MAX_LONG_HORIZON_CYCLES", 64),
            max_long_horizon_failures=_env_int("VISHNU_INTELLIGENCE_LAB_MAX_LONG_HORIZON_FAILURES", 8),
            max_long_horizon_actions=_env_int("VISHNU_INTELLIGENCE_LAB_MAX_LONG_HORIZON_ACTIONS", 64),
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
            "max_models": self.max_models,
            "benchmark_variants": self.benchmark_variants,
            "max_skill_steps": self.max_skill_steps,
            "learning_window": self.learning_window,
            "world_history_limit": self.world_history_limit,
            "affect_history_limit": self.affect_history_limit,
            "max_long_horizon_cycles": self.max_long_horizon_cycles,
            "max_long_horizon_failures": self.max_long_horizon_failures,
            "max_long_horizon_actions": self.max_long_horizon_actions,
        }
