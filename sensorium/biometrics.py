from __future__ import annotations

import base64
import json
import math
import secrets
import time
import uuid
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from core.sqlite import Migration, connect_sqlite, run_migrations


class BiometricIdentityStore:
    """Isolated biometric template authority; never invoked by camera Vision.

    Templates are owner-enrolled numeric embeddings, encrypted at rest, and
    disabled globally by default. This store accepts no raw face images and has
    no dependency from CameraVisionService, so ordinary visual observation
    cannot silently become identity recognition.
    """

    COMPONENT = "sensorium_biometrics"
    KEY_NAME = "sensorium.biometric.dek.v1"
    MAX_PROFILES = 64
    MIN_VECTOR = 16
    MAX_VECTOR = 4096

    def __init__(self, path: Path, *, vault, events=None) -> None:
        if vault is None:
            raise RuntimeError("biometric templates require encrypted vault storage")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.vault = vault
        self.events = events
        with self._con() as con:
            run_migrations(
                con,
                component=self.COMPONENT,
                migrations=(Migration(1, "biometric-template-store", self._migration_001),),
            )
            con.execute(
                "INSERT OR IGNORE INTO biometric_settings(key,value,updated_at) VALUES('enabled','false',?)",
                (time.time(),),
            )

    def _con(self):
        return connect_sqlite(self.path)

    @staticmethod
    def _migration_001(con) -> None:
        con.execute(
            """CREATE TABLE IF NOT EXISTS biometric_settings(
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at REAL NOT NULL
            )"""
        )
        con.execute(
            """CREATE TABLE IF NOT EXISTS biometric_profiles(
                id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                encrypted_template TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )"""
        )

    def _emit(self, event: str, **payload) -> None:
        if self.events is not None:
            self.events.emit(event, **payload)

    def _key(self) -> bytes:
        encoded = self.vault.get(self.KEY_NAME)
        if not encoded:
            key = secrets.token_bytes(32)
            self.vault.set(self.KEY_NAME, base64.b64encode(key).decode("ascii"))
            return key
        key = base64.b64decode(str(encoded), validate=True)
        if len(key) != 32:
            raise RuntimeError("biometric encryption key is invalid")
        return key

    @classmethod
    def _vector(cls, value) -> list[float]:
        if not isinstance(value, (list, tuple)) or not cls.MIN_VECTOR <= len(value) <= cls.MAX_VECTOR:
            raise ValueError("biometric template has an invalid vector length")
        output = []
        for item in value:
            number = float(item)
            if not math.isfinite(number) or abs(number) > 1_000_000:
                raise ValueError("biometric template contains an invalid value")
            output.append(number)
        magnitude = math.sqrt(sum(item * item for item in output))
        if magnitude <= 1e-12:
            raise ValueError("biometric template cannot be a zero vector")
        return [item / magnitude for item in output]

    def enabled(self) -> bool:
        with self._con() as con:
            row = con.execute("SELECT value FROM biometric_settings WHERE key='enabled'").fetchone()
        return bool(row and str(row["value"]).lower() == "true")

    def set_enabled(self, enabled: bool, *, explicit_consent: bool = False) -> bool:
        if enabled and not explicit_consent:
            raise PermissionError("enabling biometric identity requires explicit owner consent")
        with self._con() as con:
            con.execute(
                "INSERT INTO biometric_settings(key,value,updated_at) VALUES('enabled',?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
                ("true" if enabled else "false", time.time()),
            )
        self._emit("sensorium.biometric.enabled", enabled=bool(enabled))
        return self.enabled()

    def _encrypt(self, profile_id: str, vector: list[float]) -> str:
        nonce = secrets.token_bytes(12)
        aad = f"vishnu-biometric:{profile_id}".encode()
        plaintext = json.dumps(vector, separators=(",", ":")).encode()
        cipher = AESGCM(self._key()).encrypt(nonce, plaintext, aad)
        return base64.b64encode(nonce + cipher).decode("ascii")

    def _decrypt(self, profile_id: str, value: str) -> list[float]:
        raw = base64.b64decode(value, validate=True)
        if len(raw) < 13:
            raise RuntimeError("biometric ciphertext is invalid")
        nonce, cipher = raw[:12], raw[12:]
        aad = f"vishnu-biometric:{profile_id}".encode()
        data = AESGCM(self._key()).decrypt(nonce, cipher, aad)
        return self._vector(json.loads(data.decode()))

    def enroll(self, label: str, template, *, explicit_consent: bool = False) -> dict:
        if not explicit_consent:
            raise PermissionError("biometric enrollment requires explicit owner consent")
        vector = self._vector(template)
        name = str(label or "").strip()
        if not name or len(name) > 120:
            raise ValueError("biometric profile label is required")
        with self._con() as con:
            count = int(con.execute("SELECT COUNT(*) FROM biometric_profiles").fetchone()[0])
            if count >= self.MAX_PROFILES:
                raise RuntimeError("biometric profile limit reached")
            profile_id = str(uuid.uuid4())
            stamp = time.time()
            con.execute(
                "INSERT INTO biometric_profiles(id,label,encrypted_template,created_at,updated_at) VALUES(?,?,?,?,?)",
                (profile_id, name, self._encrypt(profile_id, vector), stamp, stamp),
            )
        self._emit("sensorium.biometric.enrolled", profile_id=profile_id)
        return {"profile_id": profile_id, "label": name, "created_at": stamp}

    def list_profiles(self) -> list[dict]:
        with self._con() as con:
            rows = con.execute(
                "SELECT id,label,created_at,updated_at FROM biometric_profiles ORDER BY created_at"
            ).fetchall()
        return [
            {
                "profile_id": row["id"],
                "label": row["label"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def delete(self, profile_id: str) -> bool:
        key = str(profile_id or "").strip()
        with self._con() as con:
            deleted = con.execute("DELETE FROM biometric_profiles WHERE id=?", (key,)).rowcount == 1
        if deleted:
            self._emit("sensorium.biometric.deleted", profile_id=key)
        return deleted

    @staticmethod
    def _cosine(left: list[float], right: list[float]) -> float:
        if len(left) != len(right):
            return -1.0
        return sum(a * b for a, b in zip(left, right))

    def match(self, template, *, threshold: float = 0.82) -> dict | None:
        if not self.enabled():
            raise PermissionError("biometric identity is disabled")
        vector = self._vector(template)
        threshold = max(0.0, min(float(threshold), 1.0))
        best = None
        with self._con() as con:
            rows = con.execute("SELECT id,label,encrypted_template FROM biometric_profiles").fetchall()
        for row in rows:
            candidate = self._decrypt(row["id"], row["encrypted_template"])
            score = self._cosine(vector, candidate)
            if best is None or score > best["score"]:
                best = {"profile_id": row["id"], "label": row["label"], "score": score}
        if best is None or best["score"] < threshold:
            return None
        return best
