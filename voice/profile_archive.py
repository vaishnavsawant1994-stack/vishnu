from __future__ import annotations

import base64
import json
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path

from security.vault import SecretVault
from voice.conversion import VoiceProfile, VoiceProfileError, VoiceProfileRegistry


BUNDLE_VERSION = 1


def _encoded_sample(sample: bytes) -> dict[str, str]:
    raw = bytes(sample)
    return {
        "sha256": sha256(raw).hexdigest(),
        "audio_base64": base64.b64encode(raw).decode("ascii"),
    }


def _decoded_samples(rows: list[dict]) -> tuple[bytes, ...]:
    samples: list[bytes] = []
    for row in rows:
        try:
            raw = base64.b64decode(str(row["audio_base64"]), validate=True)
            expected = str(row["sha256"])
        except (KeyError, ValueError, TypeError) as exc:
            raise VoiceProfileError("encrypted voice bundle contains an invalid sample") from exc
        if sha256(raw).hexdigest() != expected:
            raise VoiceProfileError("encrypted voice bundle sample failed integrity validation")
        samples.append(raw)
    if not samples:
        raise VoiceProfileError("encrypted voice bundle contains no samples")
    return tuple(samples)


class EncryptedVoiceSampleStore:
    """Encrypted local multi-sample storage using Vishnu's existing SecretVault."""

    def __init__(
        self,
        path: str | Path,
        *,
        registry: VoiceProfileRegistry,
        password: str | None = None,
        root_key_store=None,
    ) -> None:
        self.registry = registry
        self.vault = SecretVault(Path(path), password=password, root_key_store=root_key_store)

    def put(
        self,
        profile_id: str,
        samples: tuple[bytes, ...] | list[bytes],
        *,
        consent_attested: bool,
        purpose: str,
    ) -> int:
        if not consent_attested:
            raise VoiceProfileError("explicit consent attestation is required for voice sample storage")
        allowed_purpose = str(purpose or "").strip()
        if not allowed_purpose:
            raise VoiceProfileError("purpose is required for voice sample storage")
        profile = self.registry.get(profile_id, require_active=True)
        encoded = []
        for sample in samples:
            self.registry._validate_reference(sample)
            encoded.append(_encoded_sample(sample))
        if not encoded:
            raise VoiceProfileError("at least one voice sample is required")
        payload = {
            "version": BUNDLE_VERSION,
            "profile_id": profile.profile_id,
            "purpose": allowed_purpose,
            "consent_attested": True,
            "samples": encoded,
        }
        self.vault.set(f"voice.samples.{profile.profile_id}", json.dumps(payload, sort_keys=True))
        return len(encoded)

    def get(self, profile_id: str) -> tuple[bytes, ...]:
        profile = self.registry.get(profile_id, require_active=True)
        raw = self.vault.get(f"voice.samples.{profile.profile_id}")
        if raw is None:
            return ()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise VoiceProfileError("encrypted voice sample metadata is unreadable") from exc
        if payload.get("version") != BUNDLE_VERSION or payload.get("profile_id") != profile.profile_id:
            raise VoiceProfileError("encrypted voice sample metadata is invalid")
        if payload.get("consent_attested") is not True:
            raise VoiceProfileError("encrypted voice samples lack consent attestation")
        samples = _decoded_samples(payload.get("samples") or [])
        for sample in samples:
            self.registry._validate_reference(sample)
        return samples

    def delete(self, profile_id: str) -> None:
        self.vault.delete(f"voice.samples.{profile_id}")


class VoiceProfileArchive:
    """Portable encrypted import/export for governed voice profiles.

    Export never grants consent on another installation. Import requires a fresh
    explicit consent attestation and re-enrolls through VoiceProfileRegistry so
    all existing profile validation and provenance rules remain authoritative.
    """

    def __init__(
        self,
        registry: VoiceProfileRegistry,
        *,
        sample_store: EncryptedVoiceSampleStore | None = None,
    ) -> None:
        self.registry = registry
        self.sample_store = sample_store

    def export_profile(
        self,
        profile_id: str,
        destination: str | Path,
        *,
        password: str,
        extra_samples: tuple[bytes, ...] | list[bytes] = (),
    ) -> Path:
        if len(password) < 12:
            raise ValueError("voice profile export password must contain at least 12 characters")
        profile = self.registry.get(profile_id, require_active=True)
        primary = self.registry.reference_path(profile).read_bytes()
        samples: list[bytes] = [primary]
        if self.sample_store is not None:
            samples.extend(self.sample_store.get(profile.profile_id))
        samples.extend(bytes(sample) for sample in extra_samples)
        for sample in samples:
            self.registry._validate_reference(sample)

        payload = {
            "version": BUNDLE_VERSION,
            "profile": asdict(profile),
            "samples": [_encoded_sample(sample) for sample in samples],
        }
        target = Path(destination).expanduser().resolve()
        vault = SecretVault(target, password=password)
        vault.set("voice.profile.bundle", json.dumps(payload, sort_keys=True))
        return target

    def import_profile(
        self,
        source: str | Path,
        *,
        password: str,
        consent_attested: bool,
        purpose: str | None = None,
        display_name: str | None = None,
        profile_id: str | None = None,
        canonical: bool = False,
    ) -> VoiceProfile:
        if not consent_attested:
            raise VoiceProfileError("fresh explicit consent is required to import a voice profile")
        vault = SecretVault(Path(source).expanduser().resolve(), password=password)
        raw = vault.get("voice.profile.bundle")
        if raw is None:
            raise VoiceProfileError("encrypted voice profile bundle is empty")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise VoiceProfileError("encrypted voice profile bundle is unreadable") from exc
        if payload.get("version") != BUNDLE_VERSION or not isinstance(payload.get("profile"), dict):
            raise VoiceProfileError("unsupported encrypted voice profile bundle")
        samples = _decoded_samples(payload.get("samples") or [])
        for sample in samples:
            self.registry._validate_reference(sample)
        source_profile = payload["profile"]
        enrolled = self.registry.enroll(
            samples[0],
            display_name=display_name or str(source_profile.get("display_name") or "Imported voice"),
            purpose=purpose or str(source_profile.get("purpose") or "Imported consented voice profile"),
            consent_attested=True,
            profile_id=profile_id,
            canonical=canonical,
            engine=str(source_profile.get("engine") or "openvoice"),
            engine_version=str(source_profile.get("engine_version") or "v2"),
        )
        if self.sample_store is not None and len(samples) > 1:
            self.sample_store.put(
                enrolled.profile_id,
                samples[1:],
                consent_attested=True,
                purpose=purpose or enrolled.purpose,
            )
        return enrolled
