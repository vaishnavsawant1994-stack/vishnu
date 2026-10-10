from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum


class IntelligenceMode(str, Enum):
    """Owner-selectable ceiling for Vishnu model intelligence.

    STANDARD deliberately preserves the existing single-route behavior. Higher
    modes only permit additional intelligence; they never grant tool or action
    authority and they do not override routing/privacy policy.
    """

    STANDARD = 'standard'
    SMART = 'smart'
    DEEP = 'deep'
    RESEARCH = 'research'


@dataclass(frozen=True)
class IntelligenceProfile:
    mode: IntelligenceMode
    adaptive_routing: bool
    verification: bool
    deliberation: bool
    training_capture: bool = True
    max_models: int = 1

    def __post_init__(self) -> None:
        if not 1 <= int(self.max_models) <= 5:
            raise ValueError('max_models must be between 1 and 5')
        if self.mode is IntelligenceMode.STANDARD and int(self.max_models) != 1:
            raise ValueError('standard mode must remain single-model')

    def with_training_capture(self, enabled: bool) -> 'IntelligenceProfile':
        """Return an owner override without mutating the canonical preset."""

        return replace(self, training_capture=bool(enabled))


_PROFILES: dict[IntelligenceMode, IntelligenceProfile] = {
    IntelligenceMode.STANDARD: IntelligenceProfile(
        mode=IntelligenceMode.STANDARD,
        adaptive_routing=False,
        verification=False,
        deliberation=False,
        training_capture=True,
        max_models=1,
    ),
    IntelligenceMode.SMART: IntelligenceProfile(
        mode=IntelligenceMode.SMART,
        adaptive_routing=True,
        verification=True,
        deliberation=False,
        training_capture=True,
        max_models=2,
    ),
    IntelligenceMode.DEEP: IntelligenceProfile(
        mode=IntelligenceMode.DEEP,
        adaptive_routing=True,
        verification=True,
        deliberation=True,
        training_capture=True,
        max_models=4,
    ),
    IntelligenceMode.RESEARCH: IntelligenceProfile(
        mode=IntelligenceMode.RESEARCH,
        adaptive_routing=True,
        verification=True,
        deliberation=True,
        training_capture=True,
        max_models=5,
    ),
}


def intelligence_profile(
    mode: IntelligenceMode | str = IntelligenceMode.STANDARD,
    *,
    training_capture: bool | None = None,
) -> IntelligenceProfile:
    """Resolve a canonical profile with an optional owner training override."""

    try:
        selected = mode if isinstance(mode, IntelligenceMode) else IntelligenceMode(str(mode).strip().lower())
    except ValueError as exc:
        raise ValueError('unsupported intelligence mode') from exc
    profile = _PROFILES[selected]
    if training_capture is None:
        return profile
    return profile.with_training_capture(training_capture)
