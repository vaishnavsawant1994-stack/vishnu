from __future__ import annotations

import base64
from hashlib import sha256
from uuid import uuid4

from devices.gateway import DeviceCommand


class TrustedVoiceOutputRouter:
    """Route synthesized WAV bytes through the existing trusted DeviceGateway.

    DeviceRegistry/DeviceGateway remain the device trust and transport authorities.
    This adapter only selects online devices that explicitly advertise the bounded
    ``voice.play_audio`` capability and packages already-produced audio for them.
    """

    CAPABILITY = "voice.play_audio"

    def __init__(self, gateway, *, events=None, max_audio_bytes: int = 4 * 1024 * 1024) -> None:
        if max_audio_bytes < 1024:
            raise ValueError("max_audio_bytes must be >= 1024")
        self.gateway = gateway
        self.events = events
        self.max_audio_bytes = max_audio_bytes

    def available_devices(self) -> tuple[str, ...]:
        return tuple(
            device_id
            for device_id in self.gateway.online()
            if self.CAPABILITY in self.gateway.capabilities(device_id)
        )

    async def send_wav(
        self,
        device_id: str,
        wav: bytes,
        *,
        request_id: str | None = None,
    ) -> dict:
        if not isinstance(wav, (bytes, bytearray)) or not wav:
            raise ValueError("voice output must contain WAV bytes")
        payload = bytes(wav)
        if len(payload) > self.max_audio_bytes:
            raise ValueError("voice output exceeds the configured device payload limit")
        if self.CAPABILITY not in self.gateway.capabilities(device_id):
            raise PermissionError("trusted device did not advertise voice.play_audio")

        scoped_request_id = str(request_id or uuid4())
        digest = sha256(payload).hexdigest()
        result = await self.gateway.send(
            device_id,
            DeviceCommand(
                action=self.CAPABILITY,
                request_id=scoped_request_id,
                parameters={
                    "mime_type": "audio/wav",
                    "audio_base64": base64.b64encode(payload).decode("ascii"),
                    "sha256": digest,
                    "byte_length": len(payload),
                },
            ),
        )
        if self.events is not None:
            self.events.emit(
                "voice.device_output.queued",
                device_id=device_id,
                request_id=scoped_request_id,
                byte_length=len(payload),
            )
        return result

    async def broadcast_wav(self, wav: bytes, *, request_id: str | None = None) -> dict[str, dict]:
        base_request_id = str(request_id or uuid4())
        results: dict[str, dict] = {}
        for device_id in self.available_devices():
            results[device_id] = await self.send_wav(
                device_id,
                wav,
                request_id=f"{base_request_id}:{device_id}",
            )
        return results
