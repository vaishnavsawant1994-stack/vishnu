from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
import tempfile
from typing import Mapping

from voice.intelligence import VoicePreferences


class VoicePreferenceStore:
    """Atomic local store for per-owner voice presentation preferences.

    The store contains presentation choices only. It never stores reference audio,
    transcripts, provider credentials, or voice-cloning consent records.
    """

    def __init__(self, path: Path):
        self.path = Path(path)

    def all(self) -> dict[str, VoicePreferences]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            raise ValueError("voice preference store is invalid") from exc
        if not isinstance(payload, dict):
            raise ValueError("voice preference store is invalid")
        rows: dict[str, VoicePreferences] = {}
        for owner_id, value in payload.items():
            self._validate_owner_id(owner_id)
            if not isinstance(value, dict):
                raise ValueError("voice preference store is invalid")
            rows[owner_id] = VoicePreferences(**value)
        return rows

    def get(self, owner_id: str = "owner") -> VoicePreferences:
        self._validate_owner_id(owner_id)
        return self.all().get(owner_id, VoicePreferences())

    def put(self, preferences: VoicePreferences, *, owner_id: str = "owner") -> VoicePreferences:
        self._validate_owner_id(owner_id)
        rows = self.all()
        rows[owner_id] = preferences
        self._write(rows)
        return preferences

    def delete(self, owner_id: str = "owner") -> None:
        self._validate_owner_id(owner_id)
        rows = self.all()
        rows.pop(owner_id, None)
        self._write(rows)

    @staticmethod
    def _validate_owner_id(owner_id: str) -> None:
        value = str(owner_id or "")
        if not value or len(value) > 128 or any(char.isspace() for char in value):
            raise ValueError("invalid owner id")

    def _write(self, rows: Mapping[str, VoicePreferences]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        body = json.dumps(
            {key: asdict(value) for key, value in sorted(rows.items())},
            indent=2,
            sort_keys=True,
        ) + "\n"
        fd, temporary = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(body)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.chmod(temporary, 0o600)
            except OSError:
                pass
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
