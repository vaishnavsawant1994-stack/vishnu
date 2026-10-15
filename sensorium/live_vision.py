from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from threading import RLock


@dataclass
class LiveVisionSession:
    id: str
    controller_device_id: str
    target_device_id: str
    resource_id: str
    question: str
    task_mode: str
    memory_mode: str
    sample_interval: float
    scene_threshold: float
    started_at: float
    expires_at: float
    max_frames: int
    max_bytes: int
    max_model_calls: int
    min_battery_percent: int
    frames_seen: int = 0
    bytes_seen: int = 0
    model_calls: int = 0
    last_sample_at: float = 0.0
    last_fingerprint: tuple[int, ...] | None = None
    last_battery_percent: int | None = None
    stopped: bool = False

    def public(self) -> dict:
        return {
            "session_id": self.id,
            "controller_device_id": self.controller_device_id,
            "target_device_id": self.target_device_id,
            "resource_id": self.resource_id,
            "task_mode": self.task_mode,
            "memory_mode": self.memory_mode,
            "sample_interval": self.sample_interval,
            "sample_fps": round(1.0 / self.sample_interval, 3),
            "scene_threshold": self.scene_threshold,
            "started_at": self.started_at,
            "expires_at": self.expires_at,
            "max_frames": self.max_frames,
            "max_bytes": self.max_bytes,
            "max_model_calls": self.max_model_calls,
            "min_battery_percent": self.min_battery_percent,
            "last_battery_percent": self.last_battery_percent,
            "frames_seen": self.frames_seen,
            "bytes_seen": self.bytes_seen,
            "model_calls": self.model_calls,
            "stopped": self.stopped,
        }


class LiveVisionManager:
    """Bounded pull-based live vision.

    This object never creates a background camera loop. Clients explicitly call a
    tick endpoint and the manager enforces 0.2-1 FPS sampling, duration, frame,
    byte, model-call and battery budgets. This keeps live vision observable and
    auditable while preventing accidental 30/60 FPS streaming or an unattended
    session draining a mobile device below the owner-selected battery floor.
    """

    MIN_INTERVAL = 1.0          # 1 FPS maximum
    MAX_INTERVAL = 5.0          # 0.2 FPS minimum
    MAX_DURATION = 10 * 60
    DEFAULT_DURATION = 5 * 60
    DEFAULT_MAX_FRAMES = 150
    MAX_FRAMES = 600
    DEFAULT_MAX_BYTES = 40 * 1024 * 1024
    MAX_BYTES = 120 * 1024 * 1024
    DEFAULT_MODEL_CALLS = 90
    MAX_MODEL_CALLS = 300
    DEFAULT_MIN_BATTERY_PERCENT = 15

    def __init__(self, *, events=None) -> None:
        self.events = events
        self.lock = RLock()
        self.sessions: dict[str, LiveVisionSession] = {}

    def _emit(self, event: str, **payload) -> None:
        if self.events is not None:
            self.events.emit(event, **payload)

    def start(
        self,
        *,
        controller_device_id: str,
        target_device_id: str,
        resource_id: str,
        question: str,
        task_mode: str = "general",
        memory_mode: str = "none",
        sample_fps: float = 0.5,
        duration_seconds: float = DEFAULT_DURATION,
        scene_threshold: float = 0.035,
        max_frames: int = DEFAULT_MAX_FRAMES,
        max_bytes: int = DEFAULT_MAX_BYTES,
        max_model_calls: int = DEFAULT_MODEL_CALLS,
        min_battery_percent: int = DEFAULT_MIN_BATTERY_PERCENT,
    ) -> LiveVisionSession:
        fps = max(0.2, min(float(sample_fps), 1.0))
        interval = 1.0 / fps
        duration = max(30.0, min(float(duration_seconds), float(self.MAX_DURATION)))
        frame_budget = max(1, min(int(max_frames), self.MAX_FRAMES))
        byte_budget = max(1_000_000, min(int(max_bytes), self.MAX_BYTES))
        model_budget = max(1, min(int(max_model_calls), self.MAX_MODEL_CALLS))
        battery_floor = max(0, min(int(min_battery_percent), 100))
        threshold = max(0.0, min(float(scene_threshold), 1.0))
        now = time.time()
        session = LiveVisionSession(
            id=str(uuid.uuid4()),
            controller_device_id=str(controller_device_id),
            target_device_id=str(target_device_id),
            resource_id=str(resource_id or "*"),
            question=str(question),
            task_mode=str(task_mode),
            memory_mode=str(memory_mode),
            sample_interval=max(self.MIN_INTERVAL, min(interval, self.MAX_INTERVAL)),
            scene_threshold=threshold,
            started_at=now,
            expires_at=now + duration,
            max_frames=frame_budget,
            max_bytes=byte_budget,
            max_model_calls=model_budget,
            min_battery_percent=battery_floor,
        )
        with self.lock:
            self.sessions[session.id] = session
        self._emit(
            "sensorium.camera.live_started",
            session_id=session.id,
            controller_device_id=session.controller_device_id,
            target_device_id=session.target_device_id,
            resource_id=session.resource_id,
            sample_fps=round(1.0 / session.sample_interval, 3),
            min_battery_percent=session.min_battery_percent,
            max_bytes=session.max_bytes,
            expires_at=session.expires_at,
        )
        return session

    def get(self, session_id: str) -> LiveVisionSession:
        key = str(session_id or "").strip()
        with self.lock:
            session = self.sessions.get(key)
        if session is None:
            raise KeyError("live vision session not found")
        if session.stopped or time.time() >= session.expires_at:
            self.stop(key, reason="expired")
            raise TimeoutError("live vision session expired")
        return session

    def check_battery(self, session_id: str, percent: int | float | None) -> LiveVisionSession:
        """Enforce a battery floor when the source can report battery state.

        A source that cannot expose battery state passes ``None`` and remains
        governed by the other budgets. A reported value below the configured
        floor stops the live session before the next camera sample/model call.
        """
        session = self.get(session_id)
        if percent is None:
            return session
        try:
            level = int(float(percent))
        except (TypeError, ValueError):
            return session
        if level < 0 or level > 100:
            return session
        with self.lock:
            session.last_battery_percent = level
        if level < session.min_battery_percent:
            self.stop(session.id, reason="battery_limit")
            raise RuntimeError("live vision battery limit reached")
        return session

    def reserve_tick(self, session_id: str, *, frame_bytes: int) -> LiveVisionSession:
        session = self.get(session_id)
        now = time.time()
        if session.last_sample_at and now - session.last_sample_at < session.sample_interval:
            raise RuntimeError("live vision sample interval has not elapsed")
        size = max(0, int(frame_bytes))
        if session.frames_seen + 1 > session.max_frames:
            self.stop(session.id, reason="frame_budget")
            raise RuntimeError("live vision frame budget exhausted")
        if session.bytes_seen + size > session.max_bytes:
            self.stop(session.id, reason="byte_budget")
            raise RuntimeError("live vision data budget exhausted")
        with self.lock:
            session.frames_seen += 1
            session.bytes_seen += size
            session.last_sample_at = now
        return session

    def scene_decision(
        self,
        session_id: str,
        fingerprint: tuple[int, ...],
        *,
        delta: float,
    ) -> bool:
        session = self.get(session_id)
        changed = session.last_fingerprint is None or float(delta) >= session.scene_threshold
        with self.lock:
            session.last_fingerprint = fingerprint
        if not changed:
            self._emit(
                "sensorium.camera.live_scene_unchanged",
                session_id=session.id,
                scene_delta=float(delta),
            )
        return changed

    def reserve_model_call(self, session_id: str) -> LiveVisionSession:
        session = self.get(session_id)
        if session.model_calls + 1 > session.max_model_calls:
            self.stop(session.id, reason="model_budget")
            raise RuntimeError("live vision model budget exhausted")
        with self.lock:
            session.model_calls += 1
        return session

    def stop(self, session_id: str, *, reason: str = "owner") -> dict:
        key = str(session_id or "").strip()
        with self.lock:
            session = self.sessions.get(key)
            if session is None:
                return {"session_id": key, "stopped": True, "reason": reason}
            session.stopped = True
        self._emit(
            "sensorium.camera.live_stopped",
            session_id=key,
            controller_device_id=session.controller_device_id,
            target_device_id=session.target_device_id,
            reason=str(reason)[:80],
            frames_seen=session.frames_seen,
            bytes_seen=session.bytes_seen,
            model_calls=session.model_calls,
            last_battery_percent=session.last_battery_percent,
        )
        return {**session.public(), "stopped": True, "reason": str(reason)[:80]}

    def stop_for_device(self, device_id: str, *, reason: str = "device_disconnect") -> int:
        device = str(device_id or "").strip()
        with self.lock:
            ids = [
                key for key, session in self.sessions.items()
                if not session.stopped and device in {session.controller_device_id, session.target_device_id}
            ]
        for key in ids:
            self.stop(key, reason=reason)
        return len(ids)
