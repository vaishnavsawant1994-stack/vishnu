from __future__ import annotations

import base64
import json
import os
import secrets
import uuid
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class VisualMemoryManager:
    """Explicit visual-retention boundary.

    ``none`` retains nothing. ``description`` stores only the semantic model
    observation in the existing encrypted MemoryStore. ``image`` additionally
    stores the already-sanitized image as an AEAD encrypted local blob. Raw
    camera frames are never accepted by this class.
    """

    MODES = frozenset({"none", "description", "image"})
    KEY_NAME = "sensorium.visual_memory.dek.v1"
    BLOB_VERSION = 1

    def __init__(self, memory_store=None, *, data_dir: Path | None = None, vault=None, events=None) -> None:
        self.memory = memory_store
        self.data_dir = Path(data_dir) if data_dir is not None else None
        self.vault = vault
        self.events = events
        self.blob_dir = self.data_dir / "visual-memory" if self.data_dir is not None else None
        if self.blob_dir is not None:
            self.blob_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def normalize_mode(cls, value: str | None) -> str:
        mode = str(value or "none").strip().lower().replace("-", "_")
        aliases = {
            "dont_remember": "none",
            "don't_remember": "none",
            "semantic": "description",
            "description_only": "description",
            "save_image": "image",
        }
        mode = aliases.get(mode, mode)
        if mode not in cls.MODES:
            raise ValueError("visual memory mode must be none, description, or image")
        return mode

    def _emit(self, event: str, **payload) -> None:
        if self.events is not None:
            self.events.emit(event, **payload)

    def _key(self) -> bytes:
        if self.vault is None:
            raise RuntimeError("encrypted visual image storage is unavailable")
        encoded = self.vault.get(self.KEY_NAME)
        if not encoded:
            key = secrets.token_bytes(32)
            self.vault.set(self.KEY_NAME, base64.b64encode(key).decode("ascii"))
            return key
        try:
            key = base64.b64decode(str(encoded), validate=True)
        except Exception as exc:
            raise RuntimeError("visual memory encryption key is invalid") from exc
        if len(key) != 32:
            raise RuntimeError("visual memory encryption key has invalid length")
        return key

    def _save_blob(self, image_bytes: bytes, *, metadata: dict) -> str:
        if self.blob_dir is None:
            raise RuntimeError("visual image storage directory is unavailable")
        if not image_bytes:
            raise ValueError("sanitized image is empty")
        blob_id = str(uuid.uuid4())
        nonce = secrets.token_bytes(12)
        aad = f"vishnu-visual-memory-v{self.BLOB_VERSION}:{blob_id}".encode()
        ciphertext = AESGCM(self._key()).encrypt(nonce, bytes(image_bytes), aad)
        payload = {
            "version": self.BLOB_VERSION,
            "id": blob_id,
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
            "metadata": {
                "mime_type": str(metadata.get("mime_type") or "image/jpeg")[:80],
                "width": int(metadata.get("width") or 0),
                "height": int(metadata.get("height") or 0),
                "privacy_processed": True,
            },
        }
        path = self.blob_dir / f"{blob_id}.vimg"
        tmp = path.with_suffix(".tmp")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        fd = os.open(tmp, flags, 0o600)
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
        return f"visual-memory:{blob_id}"

    def _read_blob_for_test_or_explicit_retrieval(self, ref: str) -> bytes:
        # Deliberately not exposed through the Sensorium API. A future owner
        # retrieval surface must perform its own authentication and approval.
        if self.blob_dir is None:
            raise RuntimeError("visual image storage directory is unavailable")
        prefix = "visual-memory:"
        if not str(ref).startswith(prefix):
            raise ValueError("invalid visual memory reference")
        blob_id = str(ref)[len(prefix):]
        path = self.blob_dir / f"{blob_id}.vimg"
        payload = json.loads(path.read_text(encoding="utf-8"))
        nonce = base64.b64decode(payload["nonce"])
        ciphertext = base64.b64decode(payload["ciphertext"])
        aad = f"vishnu-visual-memory-v{self.BLOB_VERSION}:{blob_id}".encode()
        return AESGCM(self._key()).decrypt(nonce, ciphertext, aad)

    def remember(
        self,
        *,
        mode: str,
        analysis: str,
        source: str,
        device_id: str,
        sanitized_image: bytes | None = None,
        metadata: dict | None = None,
    ) -> dict:
        selected = self.normalize_mode(mode)
        if selected == "none":
            return {"memory_mode": "none", "memory_id": None, "image_ref": None}
        if self.memory is None:
            raise RuntimeError("memory store is unavailable")
        meta = dict(metadata or {})
        image_ref = None
        if selected == "image":
            if sanitized_image is None:
                raise ValueError("save image requires a privacy-processed image")
            image_ref = self._save_blob(sanitized_image, metadata=meta)
        memory_id = self.memory.remember(
            type="visual_observation",
            subject=f"Vision observation from {str(source)[:80]}",
            content=str(analysis)[:20_000],
            source="sensorium.camera",
            confidence=0.7,
            verified=False,
            sensitivity="sensitive",
            tags=["vision", "sensorium", "camera"],
            importance=0.45,
            evidence=[image_ref] if image_ref else [],
            metadata={
                "device_id": str(device_id)[:200],
                "source": str(source)[:120],
                "memory_mode": selected,
                "image_ref": image_ref,
                "raw_frame_retained": False,
                "privacy_processed": True,
                **{k: meta.get(k) for k in ("width", "height", "facing", "camera_id", "task_mode") if meta.get(k) is not None},
            },
        )
        self._emit(
            "sensorium.camera.memory_saved",
            device_id=str(device_id),
            memory_id=memory_id,
            memory_mode=selected,
            image_saved=bool(image_ref),
        )
        return {"memory_mode": selected, "memory_id": memory_id, "image_ref": image_ref}
