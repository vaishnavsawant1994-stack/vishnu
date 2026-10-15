from __future__ import annotations

import time
from typing import Any


class EnvironmentalAudioIntelligence:
    """Consumes local audio features/events instead of raw continuous audio."""

    LABELS = frozenset({
        "silence",
        "speech_likely",
        "alarm_tone_likely",
        "doorbell_likely",
        "music_likely",
        "appliance_hum_likely",
        "mechanical_noise_likely",
        "ambient_noise",
        "unknown",
    })

    def __init__(self, *, events=None) -> None:
        self.events = events

    def normalize(self, sample: dict[str, Any] | None, *, source: str = "microphone") -> dict:
        data = dict(sample or {})
        label = str(data.get("label") or "unknown").strip().lower()
        if label not in self.LABELS:
            label = "unknown"
        confidence = max(0.0, min(float(data.get("confidence", 0.5)), 1.0))
        rms = max(0.0, min(float(data.get("rms", 0.0)), 1.0))
        zcr = max(0.0, min(float(data.get("zero_crossing_rate", 0.0)), 1.0))
        speech = bool(data.get("speech", label == "speech_likely"))
        speaker_turns = max(0, min(int(data.get("speaker_turn_count", 0)), 1000))
        result = {
            "source": str(source or "microphone")[:160],
            "label": label,
            "confidence": confidence,
            "rms": rms,
            "peak_frame_rms": max(0.0, min(float(data.get("peak_frame_rms", rms)), 1.0)),
            "energy_variation": max(0.0, min(float(data.get("energy_variation", 0.0)), 8.0)),
            "active_ratio": max(0.0, min(float(data.get("active_ratio", 0.0)), 1.0)),
            "zero_crossing_rate": zcr,
            "speech": speech,
            "speaker_turn_count": speaker_turns,
            "vad_active": bool(data.get("vad_active", speech)),
            "duration_ms": max(0, min(int(data.get("duration_ms", 0)), 60_000)),
            "classification_scope": str(data.get("classification_scope") or "local_acoustic_cues")[:80],
            "captured_at": float(data.get("captured_at") or time.time()),
            "raw_audio_retained": False,
            "raw_audio_required": False,
            "local_feature_extraction": True,
            "instruction_trust": "untrusted",
            "execution_authority": False,
        }
        if self.events is not None:
            self.events.emit(
                "sensorium.audio.observed",
                source=result["source"],
                label=label,
                confidence=confidence,
                speech=speech,
                speaker_turn_count=speaker_turns,
                raw_audio_retained=False,
                execution_authority=False,
            )
        return result
