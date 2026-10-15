from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class VisionVoiceRequest:
    transcript: str
    task_mode: str = "general"
    memory_mode: str = "none"
    speak: bool = True


class VisionVoiceCoordinator:
    """Explicit bridge between speech intent and governed camera observation.

    Speech is converted to text by the existing voice provider/client first. The
    transcript becomes the visual question; the camera service retains all of
    its own sensor permission/privacy rules. The optional answer is spoken by
    the existing VoiceRuntime, never by bypassing its provider boundary.
    """

    def __init__(self, camera_service, *, events=None) -> None:
        self.camera = camera_service
        self.events = events

    @staticmethod
    def transcript(value: str) -> str:
        text = str(value or "").strip()
        if not text or len(text) > 2_000:
            raise ValueError("Vision + Voice transcript must contain 1-2000 characters")
        return text

    async def mobile(
        self,
        controller_device_id: str,
        target_device_id: str,
        *,
        transcript: str,
        camera_id: str | None = None,
        facing: str = "front",
        privacy: dict[str, Any] | None = None,
        task_mode: str = "general",
        memory_mode: str = "none",
        speak: bool = True,
        timeout: float = 25.0,
    ) -> dict:
        question = self.transcript(transcript)
        result = await self.camera.snapshot(
            controller_device_id,
            target_device_id,
            question=question,
            facing=facing,
            camera_id=camera_id,
            privacy=privacy,
            task_mode=task_mode,
            memory_mode=memory_mode,
            speak=speak,
            timeout=timeout,
        )
        if self.events is not None:
            self.events.emit(
                "sensorium.vision_voice.completed",
                controller_device_id=controller_device_id,
                target_device_id=target_device_id,
                camera_id=result.get("camera_id"),
                task_mode=result.get("task_mode"),
                spoken=bool(result.get("spoken")),
            )
        return result

    def browser(
        self,
        controller_device_id: str,
        *,
        transcript: str,
        data_url: str,
        resource_id: str,
        sensor_session_id: str,
        privacy: dict[str, Any] | None = None,
        task_mode: str = "general",
        memory_mode: str = "none",
        speak: bool = True,
    ) -> dict:
        question = self.transcript(transcript)
        result = self.camera.analyze_browser_snapshot(
            controller_device_id,
            data_url=data_url,
            question=question,
            resource_id=resource_id,
            sensor_session_id=sensor_session_id,
            privacy=privacy,
            task_mode=task_mode,
            memory_mode=memory_mode,
            speak=speak,
        )
        if self.events is not None:
            self.events.emit(
                "sensorium.vision_voice.completed",
                controller_device_id=controller_device_id,
                target_device_id=controller_device_id,
                camera_id=result.get("camera_id"),
                task_mode=result.get("task_mode"),
                spoken=bool(result.get("spoken")),
            )
        return result
