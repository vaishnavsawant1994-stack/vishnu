from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from training.contributions import ContributionMode, ContributionPreferences


@dataclass(frozen=True)
class ContributionSettingsSnapshot:
    preferences: ContributionPreferences

    def public(self) -> dict[str, object]:
        return self.preferences.public()


class ContributionSettingsService:
    """Persist owner-controlled shared-learning preferences.

    Defaults are deliberately private. Changing these settings only changes
    contribution eligibility; it never bypasses Vishnu's existing training
    candidate privacy/provenance/approval pipeline.
    """

    def __init__(self, path: str | Path, *, events=None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.events = events

    def _load(self) -> ContributionPreferences:
        if not self.path.exists():
            return ContributionPreferences()
        if not self.path.is_file() or self.path.is_symlink():
            raise ValueError("contribution settings path is invalid")
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError("contribution settings are unreadable") from exc
        if not isinstance(payload, dict):
            raise ValueError("contribution settings must be an object")
        try:
            mode = ContributionMode(str(payload.get("mode") or ContributionMode.PRIVATE.value))
        except ValueError as exc:
            raise ValueError("invalid contribution mode") from exc
        return ContributionPreferences(
            mode=mode,
            conversations=bool(payload.get("conversations", False)),
            agent_outcomes=bool(payload.get("agent_outcomes", True)),
            corrections=bool(payload.get("corrections", False)),
            tool_metrics=bool(payload.get("tool_metrics", True)),
            documents=bool(payload.get("documents", False)),
        )

    def snapshot(self) -> ContributionSettingsSnapshot:
        return ContributionSettingsSnapshot(self._load())

    def update(self, **values: Any) -> ContributionSettingsSnapshot:
        allowed = {
            "mode",
            "conversations",
            "agent_outcomes",
            "corrections",
            "tool_metrics",
            "documents",
        }
        unknown = set(values) - allowed
        if unknown:
            raise ValueError(f"unsupported contribution settings: {sorted(unknown)}")
        current = self._load()
        mode_value = values.get("mode", current.mode)
        try:
            mode = mode_value if isinstance(mode_value, ContributionMode) else ContributionMode(str(mode_value))
        except ValueError as exc:
            raise ValueError("invalid contribution mode") from exc
        preferences = ContributionPreferences(
            mode=mode,
            conversations=bool(values.get("conversations", current.conversations)),
            agent_outcomes=bool(values.get("agent_outcomes", current.agent_outcomes)),
            corrections=bool(values.get("corrections", current.corrections)),
            tool_metrics=bool(values.get("tool_metrics", current.tool_metrics)),
            documents=bool(values.get("documents", current.documents)),
        )
        # Documents are the highest-risk contribution class and remain disabled
        # unless the owner explicitly selects training-contributor mode.
        if preferences.documents and preferences.mode is not ContributionMode.TRAINING_CONTRIBUTOR:
            raise ValueError("document contribution requires training_contributor mode")
        self._write(preferences.public())
        if self.events is not None:
            self.events.emit("owner.learning.contribution_settings_updated", **preferences.public())
        return ContributionSettingsSnapshot(self._load())

    def _write(self, payload: dict[str, object]) -> None:
        temporary = self.path.with_name(f".{self.path.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                try:
                    os.chmod(temporary, 0o600)
                except OSError:
                    pass
                json.dump(payload, handle, sort_keys=True, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)
