from __future__ import annotations

import base64
import json
import os
import secrets
import uuid
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class EpisodicMemoryManager:
    """Explicit multimodal retention boundary for Sensorium episodes.

    Raw media disappears unless the owner selects ``media`` and the caller marks
    the supplied bytes as already privacy-processed. ``summary`` stores only a
    short semantic memory. ``event`` additionally stores structured semantic
    context. None of these modes preserve raw sensor streams.
    """

    MODES = frozenset({"none", "summary", "event", "media"})
    KEY_NAME = "sensorium.episodic_media.dek.v1"
    VERSION = 1

    def __init__(self, memory_store=None, *, data_dir: Path | None = None, vault=None, events=None) -> None:
        self.memory = memory_store
        self.data_dir = Path(data_dir) if data_dir is not None else None
        self.vault = vault
        self.events = events
        self.blob_dir = self.data_dir / "sensorium-episodes" if self.data_dir is not None else None
        if self.blob_dir is not None:
            self.blob_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def normalize_mode(cls, value: str | None) -> str:
        mode = str(value or "none").strip().lower().replace("-", "_")
        aliases = {
            "dont_remember": "none",
            "don't_remember": "none",
            "summary_only": "summary",
            "event_memory": "event",
            "save_selected_media": "media",
        }
        mode = aliases.get(mode, mode)
        if mode not in cls.MODES:
            raise ValueError("episodic memory mode must be none, summary, event, or media")
        return mode

    def _emit(self, event: str, **payload) -> None:
        if self.events is not None:
            self.events.emit(event, **payload)

    def _key(self) -> bytes:
        if self.vault is None:
            raise RuntimeError("encrypted episodic media storage is unavailable")
        encoded = self.vault.get(self.KEY_NAME)
        if not encoded:
            key = secrets.token_bytes(32)
            self.vault.set(self.KEY_NAME, base64.b64encode(key).decode("ascii"))
            return key
        try:
            key = base64.b64decode(str(encoded), validate=True)
        except Exception as exc:
            raise RuntimeError("episodic media encryption key is invalid") from exc
        if len(key) != 32:
            raise RuntimeError("episodic media encryption key has invalid length")
        return key

    def _save_media(self, media: bytes, *, metadata: dict[str, Any]) -> str:
        if self.blob_dir is None:
            raise RuntimeError("episodic media directory is unavailable")
        if not media or len(media) > 8 * 1024 * 1024:
            raise ValueError("selected episodic media must contain 1 byte to 8 MB")
        if metadata.get("privacy_processed") is not True:
            raise PermissionError("episodic media must be privacy-processed before retention")
        media_id = str(uuid.uuid4())
        nonce = secrets.token_bytes(12)
        aad = f"vishnu-sensorium-episode-v{self.VERSION}:{media_id}".encode()
        ciphertext = AESGCM(self._key()).encrypt(nonce, bytes(media), aad)
        payload = {
            "version": self.VERSION,
            "media_id": media_id,
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
            "metadata": {
                "mime_type": str(metadata.get("mime_type") or "application/octet-stream")[:120],
                "privacy_processed": True,
                "source": str(metadata.get("source") or "sensorium")[:160],
            },
        }
        path = self.blob_dir / f"{media_id}.episode"
        tmp = path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
        except BaseException:
            try:
                tmp.unlink()
            except OSError:
                pass
            raise
        return f"sensorium-episode:{media_id}"

    def remember(
        self,
        *,
        mode: str,
        summary: str,
        device_id: str,
        modalities: list[str] | tuple[str, ...],
        event: dict[str, Any] | None = None,
        selected_media: bytes | None = None,
        media_metadata: dict[str, Any] | None = None,
        confidence: float = 0.7,
        privacy_forbid_media: bool = False,
    ) -> dict:
        selected = self.normalize_mode(mode)
        if selected == "none":
            return {"memory_mode": "none", "memory_id": None, "media_ref": None}
        if self.memory is None:
            raise RuntimeError("memory store is unavailable")
        if selected == "media" and privacy_forbid_media:
            raise PermissionError("the active privacy zone forbids media retention")
        text = str(summary or "").strip()[:20_000]
        if not text:
            raise ValueError("episodic memory summary is required")
        safe_modalities = sorted({str(item).strip().lower() for item in modalities if str(item).strip()})[:32]
        safe_event = dict(list((event or {}).items())[:128]) if selected in {"event", "media"} else {}
        media_ref = None
        if selected == "media":
            if selected_media is None:
                raise ValueError("media mode requires selected privacy-processed media")
            media_ref = self._save_media(selected_media, metadata=dict(media_metadata or {}))
        memory_id = self.memory.remember(
            type="sensorium_episode",
            subject="Sensorium episode",
            content=text,
            source="sensorium.episodic",
            confidence=max(0.0, min(float(confidence), 1.0)),
            verified=False,
            sensitivity="sensitive",
            tags=["sensorium", "episode", *safe_modalities[:8]],
            importance=0.5,
            evidence=[media_ref] if media_ref else [],
            metadata={
                "device_id": str(device_id)[:200],
                "modalities": safe_modalities,
                "memory_mode": selected,
                "event": safe_event,
                "media_ref": media_ref,
                "raw_audio_retained": False,
                "raw_video_retained": False,
            },
        )
        self._emit(
            "sensorium.episode.saved",
            device_id=str(device_id),
            memory_id=memory_id,
            memory_mode=selected,
            modalities=safe_modalities,
            media_saved=bool(media_ref),
        )
        return {"memory_mode": selected, "memory_id": memory_id, "media_ref": media_ref}
