from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PhysicalTaskSession:
    session_id: str
    device_id: str
    purpose: str
    allowed_sensors: tuple[str, ...]
    started_at: float
    expires_at: float
    cues: list[dict[str, Any]] = field(default_factory=list)
    stopped: bool = False

    def public(self) -> dict:
        return {
            "session_id": self.session_id,
            "device_id": self.device_id,
            "purpose": self.purpose,
            "allowed_sensors": list(self.allowed_sensors),
            "started_at": self.started_at,
            "expires_at": self.expires_at,
            "cue_count": len(self.cues),
            "stopped": self.stopped,
            "execution_authority": False,
        }


class ProactivePhysicalAssistant:
    """Task-bound change detector that cannot become general surveillance."""

    MAX_DURATION = 60 * 60

    def __init__(self, *, events=None) -> None:
        self.events = events
        self.sessions: dict[str, PhysicalTaskSession] = {}

    def _emit(self, event: str, **payload) -> None:
        if self.events is not None:
            self.events.emit(event, **payload)

    def start(
        self,
        device_id: str,
        *,
        purpose: str,
        allowed_sensors,
        duration_seconds: float = 15 * 60,
    ) -> dict:
        text = str(purpose or "").strip()[:1000]
        if not text:
            raise ValueError("physical assistance purpose is required")
        sensors = tuple(sorted({str(item).strip().lower() for item in allowed_sensors if str(item).strip()}))
        if not sensors:
            raise ValueError("physical assistance needs at least one explicitly permitted sensor")
        now = time.time()
        duration = max(30.0, min(float(duration_seconds), float(self.MAX_DURATION)))
        session = PhysicalTaskSession(
            session_id=str(uuid.uuid4()),
            device_id=str(device_id)[:200],
            purpose=text,
            allowed_sensors=sensors,
            started_at=now,
            expires_at=now + duration,
        )
        self.sessions[session.session_id] = session
        self._emit(
            "sensorium.proactive.started",
            session_id=session.session_id,
            device_id=session.device_id,
            allowed_sensors=list(sensors),
            expires_at=session.expires_at,
            execution_authority=False,
        )
        return session.public()

    def _get(self, session_id: str) -> PhysicalTaskSession:
        session = self.sessions.get(str(session_id))
        if session is None:
            raise KeyError("physical assistance session not found")
        if session.stopped or time.time() >= session.expires_at:
            session.stopped = True
            raise TimeoutError("physical assistance session expired")
        return session

    def evaluate(
        self,
        session_id: str,
        *,
        sensor: str,
        observation: dict[str, Any],
        significance: float,
        message: str,
        confidence: float = 0.7,
    ) -> dict:
        session = self._get(session_id)
        kind = str(sensor or "").strip().lower()
        if kind not in session.allowed_sensors:
            raise PermissionError("sensor is outside this physical assistance task")
        significance_score = max(0.0, min(float(significance), 1.0))
        confidence_score = max(0.0, min(float(confidence), 1.0))
        cue = None
        if significance_score >= 0.6 and confidence_score >= 0.5:
            cue = {
                "cue_id": str(uuid.uuid4()),
                "sensor": kind,
                "message": str(message or "Meaningful task change detected.")[:1000],
                "confidence": confidence_score,
                "significance": significance_score,
                "created_at": time.time(),
                "observation_summary": dict(list((observation or {}).items())[:32]),
                "requires_user_attention": True,
                "execution_authority": False,
            }
            session.cues.append(cue)
            session.cues[:] = session.cues[-100:]
            self._emit(
                "sensorium.proactive.cue",
                session_id=session.session_id,
                sensor=kind,
                confidence=confidence_score,
                significance=significance_score,
                execution_authority=False,
            )
        return {
            "session": session.public(),
            "cue": cue,
            "acted": False,
            "execution_authority": False,
        }

    def stop(self, session_id: str, *, reason: str = "owner") -> dict:
        session = self.sessions.get(str(session_id))
        if session is None:
            return {"session_id": str(session_id), "stopped": True, "reason": reason}
        session.stopped = True
        self._emit(
            "sensorium.proactive.stopped",
            session_id=session.session_id,
            reason=str(reason)[:120],
            execution_authority=False,
        )
        return {**session.public(), "reason": str(reason)[:120]}
