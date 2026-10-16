"""Consent-aware metadata registry for Voice Lab test fixtures."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from urllib.parse import urlparse


class FixtureKind(str, Enum):
    CLEAN = "clean"
    NOISE = "noise"
    FAST = "fast"
    SLOW = "slow"
    SILENCE = "silence"
    OVERLAP = "overlap"
    NAMES = "names"
    MULTILINGUAL = "multilingual"
    CODE_SWITCH = "code_switch"
    LONG_FORM = "long_form"
    INTERRUPTION = "interruption"


@dataclass(frozen=True, slots=True)
class VoiceFixture:
    fixture_id: str
    kind: FixtureKind
    transcript: str = ""
    languages: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    local_audio_path: str | None = None
    sensitive: bool = False
    consent_reference: str | None = None

    def __post_init__(self) -> None:
        if not self.fixture_id.strip():
            raise ValueError("fixture_id is required")
        if len(set(self.languages)) != len(self.languages):
            raise ValueError("languages must be unique")
        if self.local_audio_path:
            parsed = urlparse(self.local_audio_path)
            if parsed.scheme or parsed.netloc:
                raise ValueError("Voice Lab fixtures must reference local paths, never remote URLs")
            if not Path(self.local_audio_path).expanduser().is_absolute():
                raise ValueError("audio fixture paths must be absolute")
        if self.sensitive and (not self.local_audio_path or not self.consent_reference):
            raise ValueError("sensitive voice fixtures require a local path and explicit consent reference")


_BUILTINS = (
    VoiceFixture("clean-short", FixtureKind.CLEAN, "Vishnu is ready to help.", ("en",)),
    VoiceFixture("noise-metadata", FixtureKind.NOISE, "Vishnu is ready to help.", ("en",), ("noise-required",)),
    VoiceFixture("fast-speech", FixtureKind.FAST, "Please summarize the latest result clearly.", ("en",)),
    VoiceFixture("slow-speech", FixtureKind.SLOW, "Please speak slowly and clearly.", ("en",)),
    VoiceFixture("silence", FixtureKind.SILENCE, "", ("und",)),
    VoiceFixture("overlap", FixtureKind.OVERLAP, "Stop and listen to the new speaker.", ("en",)),
    VoiceFixture("names", FixtureKind.NAMES, "Vishnu, Vaishnav, Maharashtra, Frankfurt.", ("en",)),
    VoiceFixture("multilingual", FixtureKind.MULTILINGUAL, "Hello. Namaste. Guten Tag.", ("en", "hi", "de")),
    VoiceFixture("code-switch", FixtureKind.CODE_SWITCH, "Vishnu, kal meeting hai, please remind me.", ("en", "hi")),
    VoiceFixture("long-form", FixtureKind.LONG_FORM, "Explain the result in a structured long-form answer.", ("en",)),
    VoiceFixture("interruption", FixtureKind.INTERRUPTION, "Stop speaking when I interrupt and discard stale audio.", ("en",)),
)


class FixtureRegistry:
    """In-memory registry. Built-ins contain text metadata only, never owner audio."""
    def __init__(self, fixtures: tuple[VoiceFixture, ...] = _BUILTINS):
        self._items: dict[str, VoiceFixture] = {}
        for fixture in fixtures:
            self.add(fixture)

    def add(self, fixture: VoiceFixture) -> None:
        if fixture.fixture_id in self._items and self._items[fixture.fixture_id] != fixture:
            raise ValueError(f"fixture {fixture.fixture_id!r} already exists with different metadata")
        self._items[fixture.fixture_id] = fixture

    def get(self, fixture_id: str) -> VoiceFixture | None:
        return self._items.get(fixture_id)

    def resolve(self, fixture_ids: tuple[str, ...]) -> tuple[VoiceFixture, ...]:
        missing = tuple(item for item in fixture_ids if item not in self._items)
        if missing:
            raise KeyError(f"unknown Voice Lab fixture(s): {', '.join(missing)}")
        return tuple(self._items[item] for item in fixture_ids)

    def list(self) -> tuple[VoiceFixture, ...]:
        return tuple(self._items[key] for key in sorted(self._items))


def builtin_fixture_ids() -> tuple[str, ...]:
    return tuple(item.fixture_id for item in _BUILTINS)
