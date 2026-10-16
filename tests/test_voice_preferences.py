from __future__ import annotations

import io
import math
from pathlib import Path
import struct
import wave

import pytest

from voice.conversion import VoiceProfileRegistry
from voice.intelligence import VoicePersona, VoicePreferences
from voice.platform import VoiceIntelligenceService
from voice.preferences import VoicePreferenceStore


def wav_bytes(*, seconds: float = 0.25, sample_rate: int = 16000) -> bytes:
    frames = bytearray()
    for index in range(max(1, int(seconds * sample_rate))):
        value = int(32767 * 0.15 * math.sin(2 * math.pi * 180 * index / sample_rate))
        frames.extend(struct.pack("<h", value))
    output = io.BytesIO()
    with wave.open(output, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(sample_rate)
        writer.writeframes(bytes(frames))
    return output.getvalue()


class FakeConversion:
    def __init__(self, root: Path):
        self.registry = VoiceProfileRegistry(root)


class FakeRouter:
    def __init__(self, root: Path):
        self.voice_conversion = FakeConversion(root / "profiles")
        self.calls = []

    def synthesize(self, text, *, voice_profile_id=None, voice_style="normal"):
        self.calls.append((text, voice_profile_id, voice_style))
        return wav_bytes()


def test_preferences_round_trip_and_owner_isolation(tmp_path):
    store = VoicePreferenceStore(tmp_path / "preferences.json")
    owner_preferences = VoicePreferences(
        persona_id="vishnu_warm",
        language="en-GB",
        style="warm",
        speaking_rate=1.1,
        expression_intensity=1.3,
        formality=0.7,
    )
    store.put(owner_preferences, owner_id="owner")
    store.put(VoicePreferences(language="de"), owner_id="second-owner")

    loaded = VoicePreferenceStore(tmp_path / "preferences.json")
    assert loaded.get("owner") == owner_preferences
    assert loaded.get("second-owner").language == "de"
    loaded.delete("second-owner")
    assert loaded.get("second-owner") == VoicePreferences()


def test_preferences_reject_invalid_owner_id(tmp_path):
    store = VoicePreferenceStore(tmp_path / "preferences.json")
    with pytest.raises(ValueError):
        store.put(VoicePreferences(), owner_id="bad owner")


def test_service_persists_and_uses_preferences(tmp_path):
    router = FakeRouter(tmp_path)
    service = VoiceIntelligenceService(router, data_dir=tmp_path)
    service.set_preferences(
        VoicePreferences(
            persona_id="vishnu_professional",
            language="de-DE",
            style="serious",
        )
    )

    replacement = VoiceIntelligenceService(router, data_dir=tmp_path)
    result = replacement.synthesize("Guten Tag.")
    assert result.plan.persona_id == "vishnu_professional"
    assert result.plan.language == "de-DE"
    assert result.plan.style == "serious"
    assert router.calls[-1] == ("Guten Tag.", None, "serious")


def test_neutral_style_maps_to_existing_conversion_normal_contract(tmp_path):
    router = FakeRouter(tmp_path)
    service = VoiceIntelligenceService(router, data_dir=tmp_path)
    result = service.synthesize("Hello.", persona_id="vishnu_original")

    assert result.plan.style == "neutral"
    assert router.calls[-1] == ("Hello.", None, "normal")


def test_custom_persona_can_only_be_selected_after_creation(tmp_path):
    service = VoiceIntelligenceService(FakeRouter(tmp_path), data_dir=tmp_path)
    with pytest.raises(ValueError):
        service.set_preferences(VoicePreferences(persona_id="missing-persona"))

    service.put_persona(VoicePersona("teacher_custom", "Teacher", style="warm"))
    saved = service.set_preferences(VoicePreferences(persona_id="teacher_custom"))
    assert saved.persona_id == "teacher_custom"


def test_service_profile_management_reuses_governed_registry(tmp_path):
    router = FakeRouter(tmp_path)
    service = VoiceIntelligenceService(router, data_dir=tmp_path)
    enrolled = service.enroll_voice_profile(
        wav_bytes(),
        display_name="Authorized narrator",
        purpose="Owner-approved narration",
        consent_attested=True,
        profile_id="narrator",
    )

    assert enrolled["profile_id"] == "narrator"
    assert enrolled["active"] is True
    profiles = service.list_voice_profiles()
    assert profiles == [
        {
            "profile_id": "narrator",
            "display_name": "Authorized narrator",
            "purpose": "Owner-approved narration",
            "active": True,
            "canonical": False,
            "engine": "openvoice",
            "engine_version": "v2",
            "created_at": profiles[0]["created_at"],
            "revoked_at": None,
        }
    ]
    assert "reference_file" not in profiles[0]
    assert "reference_sha256" not in profiles[0]

    revoked = service.revoke_voice_profile("narrator")
    assert revoked["active"] is False
    service.delete_voice_profile("narrator")
    assert service.list_voice_profiles() == []


def test_service_rejects_builtin_persona_overwrite(tmp_path):
    service = VoiceIntelligenceService(FakeRouter(tmp_path), data_dir=tmp_path)
    with pytest.raises(ValueError):
        service.put_persona(VoicePersona("vishnu_original", "Replacement"))
