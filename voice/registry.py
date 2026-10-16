from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ModelKind(str, Enum):
    STT = "stt"
    TTS = "tts"
    VOICE_CONVERSION = "voice_conversion"


class ModelLicenseError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class VoiceModelMetadata:
    model_id: str
    provider_id: str
    kind: ModelKind
    upstream: str
    license_id: str | None
    redistributable: bool = False
    commercial_use: bool = False
    local_only: bool = False
    code_license_id: str | None = None
    weights_license_id: str | None = None
    code_upstream: str | None = None
    weights_upstream: str | None = None
    artifact_sha256: str | None = None
    languages: tuple[str, ...] = ()
    hardware: tuple[str, ...] = ()
    revision: str = ""
    size_bytes: int | None = None

    def __post_init__(self) -> None:
        for field_name in ("model_id", "provider_id", "upstream"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must not be empty")
        if self.artifact_sha256 is not None and not _SHA256_RE.fullmatch(self.artifact_sha256.lower()):
            raise ValueError("artifact_sha256 must be a 64-character hexadecimal SHA-256 digest")
        if self.size_bytes is not None and self.size_bytes < 0:
            raise ValueError("size_bytes must be >= 0")
        if any(not str(value).strip() for value in self.languages):
            raise ValueError("languages must not contain empty values")
        if any(not str(value).strip() for value in self.hardware):
            raise ValueError("hardware must not contain empty values")

    @property
    def effective_code_license(self) -> str | None:
        return self.code_license_id or self.license_id

    @property
    def effective_weights_license(self) -> str | None:
        return self.weights_license_id or self.license_id


class VoiceModelRegistry:
    """Fail-closed metadata registry for voice models.

    This registry records licensing, provenance, compatibility and artifact
    integrity facts. It does not download, execute, approve, or grant device
    access to a model.
    """

    DEFAULT_ALLOWED_LICENSES = frozenset(
        {"Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "MIT", "MPL-2.0"}
    )

    def __init__(
        self,
        *,
        allowed_licenses: set[str] | frozenset[str] | None = None,
        allow_unverified: bool = False,
    ) -> None:
        self._models: dict[str, VoiceModelMetadata] = {}
        self._allowed_licenses = frozenset(
            self.DEFAULT_ALLOWED_LICENSES if allowed_licenses is None else allowed_licenses
        )
        self._allow_unverified = allow_unverified

    def register(self, metadata: VoiceModelMetadata) -> None:
        if metadata.model_id in self._models:
            raise ValueError(f"voice model already registered: {metadata.model_id}")
        self.validate_license(metadata)
        self._models[metadata.model_id] = metadata

    def get(self, model_id: str) -> VoiceModelMetadata:
        try:
            return self._models[model_id]
        except KeyError as exc:
            raise KeyError(f"unknown voice model: {model_id}") from exc

    def list(self, *, kind: ModelKind | None = None) -> tuple[VoiceModelMetadata, ...]:
        models = self._models.values()
        if kind is not None:
            models = (model for model in models if model.kind is kind)
        return tuple(sorted(models, key=lambda model: model.model_id))

    def validate_license(
        self,
        metadata: VoiceModelMetadata,
        *,
        require_commercial: bool = False,
        require_redistribution: bool = False,
    ) -> None:
        licenses = {
            "code": metadata.effective_code_license,
            "weights": metadata.effective_weights_license,
        }
        if not self._allow_unverified:
            for component, license_id in licenses.items():
                if not license_id or license_id not in self._allowed_licenses:
                    raise ModelLicenseError(
                        f"voice model {metadata.model_id!r} has an unapproved or unknown "
                        f"{component} license: {license_id!r}"
                    )
        if require_commercial and not metadata.commercial_use:
            raise ModelLicenseError(f"voice model {metadata.model_id!r} is not cleared for commercial use")
        if require_redistribution and not metadata.redistributable:
            raise ModelLicenseError(f"voice model {metadata.model_id!r} is not cleared for redistribution")
