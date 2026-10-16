"""Side-effect-free Voice Lab dashboard model."""
from __future__ import annotations
from dataclasses import dataclass
from .catalog import all_capabilities, gaps, qualification_required


VOICE_LAB_SECTIONS = (
    "Overview","Conversation","STT","TTS","Voice Profiles","Voice Intelligence","Multilingual",
    "Realtime","Audio / Sensorium","Devices","Providers & Models","Experiments","Benchmarks",
    "Qualification","Release",
)


@dataclass(frozen=True, slots=True)
class VoiceLabDashboardSnapshot:
    sections: tuple[str, ...]
    capabilities: int
    gaps: int
    qualification_required: int
    experiment_count: int = 0
    evidence_count: int = 0


def snapshot(*, experiment_count: int = 0, evidence_count: int = 0) -> VoiceLabDashboardSnapshot:
    return VoiceLabDashboardSnapshot(VOICE_LAB_SECTIONS,len(all_capabilities()),len(gaps()),len(qualification_required()),experiment_count,evidence_count)
