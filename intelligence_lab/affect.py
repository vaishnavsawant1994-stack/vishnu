from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
import time
from typing import Any, Mapping

from .memory import LabMemory
from .models import AffectEstimate, new_id


@dataclass(frozen=True)
class AffectiveContext:
    labels: tuple[str, ...]
    valence: float
    arousal: float
    confidence: float
    evidence: tuple[str, ...]
    suggested_tone: str
    modalities_used: tuple[str, ...]
    raw_media_stored: bool = False
    sensitive_trait_inference: bool = False
    subjective_experience_claimed: bool = False
    id: str = field(default_factory=lambda: new_id("affectctx"))
    created_at: float = field(default_factory=time.time)

    def public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["caveat"] = (
            "Probabilistic context estimate only. It is not mind-reading, diagnosis, or proof of a person's feelings."
        )
        return data


class AffectiveContextEngine:
    """Consent-gated fusion of text and already-derived contextual signals.

    The engine intentionally refuses raw audio/video/image payloads and sensitive
    trait inference. Sensorium or another trusted component may provide derived
    prosody/face/interaction scores after its own consent checks.
    """

    _RAW_MEDIA_KEYS = {"audio", "video", "image", "frame", "waveform", "recording"}
    _FORBIDDEN_TRAITS = {
        "race", "ethnicity", "religion", "politics", "political", "sexuality",
        "sexual_orientation", "health_diagnosis", "disability", "criminal_history",
    }
    _MODALITIES = {"voice", "face", "interaction", "history"}

    def __init__(self, text_estimator: Any, memory: LabMemory, *, history_limit: int = 100):
        self.text_estimator = text_estimator
        self.memory = memory
        self.history_limit = max(10, min(int(history_limit), 500))

    @staticmethod
    def _number(value: Any, default: float = 0.0) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return default
        if not math.isfinite(parsed):
            return default
        return parsed

    def estimate(
        self,
        text: str,
        *,
        derived_signals: Mapping[str, Any] | None = None,
        consent: Mapping[str, bool] | None = None,
    ) -> AffectiveContext:
        derived_signals = dict(derived_signals or {})
        consent = dict(consent or {})
        self._validate_signals(derived_signals, consent)
        text_estimate: AffectEstimate = self.text_estimator.estimate(str(text), signals=None)

        weighted_valence = text_estimate.valence * max(0.05, text_estimate.confidence)
        weighted_arousal = text_estimate.arousal * max(0.05, text_estimate.confidence)
        weight = max(0.05, text_estimate.confidence)
        evidence = list(text_estimate.evidence)
        modalities = ["text"]

        for modality in sorted(self._MODALITIES):
            payload = derived_signals.get(modality)
            if not isinstance(payload, Mapping):
                continue
            confidence = max(0.0, min(self._number(payload.get("confidence"), 0.5), 1.0))
            if confidence <= 0:
                continue
            valence = max(-1.0, min(self._number(payload.get("valence"), 0.0), 1.0))
            arousal = max(0.0, min(self._number(payload.get("arousal"), 0.5), 1.0))
            modality_weight = confidence * 0.8
            weighted_valence += valence * modality_weight
            weighted_arousal += arousal * modality_weight
            weight += modality_weight
            modalities.append(modality)
            evidence.append(f"derived_{modality}_signal")

        valence = max(-1.0, min(weighted_valence / max(weight, 0.001), 1.0))
        arousal = max(0.0, min(weighted_arousal / max(weight, 0.001), 1.0))
        confidence = min(0.9, 0.2 + min(weight, 1.4) * 0.45)
        labels = self._labels(valence, arousal)
        tone = self._tone(valence, arousal, confidence)
        result = AffectiveContext(
            labels=labels,
            valence=valence,
            arousal=arousal,
            confidence=confidence,
            evidence=tuple(dict.fromkeys(evidence)),
            suggested_tone=tone,
            modalities_used=tuple(modalities),
        )
        self.memory.put(
            result.id,
            "affect_context",
            {
                **result.public_dict(),
                "raw_signals": None,
                "raw_media_stored": False,
                "consent_snapshot": {key: bool(consent.get(key, False)) for key in self._MODALITIES},
            },
        )
        self.memory.audit(
            "human_context",
            "multimodal_affect_estimated",
            {
                "id": result.id,
                "modalities": list(result.modalities_used),
                "confidence": result.confidence,
                "raw_media_stored": False,
                "sensitive_trait_inference": False,
            },
        )
        return result

    def trend(self, *, limit: int = 20) -> dict[str, Any]:
        rows = self.memory.recent("affect_context", max(1, min(int(limit), self.history_limit)))
        if not rows:
            return {"samples": 0, "valence": 0.0, "arousal": 0.0, "confidence": 0.0}
        payloads = [row.get("payload", {}) for row in rows]
        return {
            "samples": len(payloads),
            "valence": sum(self._number(item.get("valence")) for item in payloads) / len(payloads),
            "arousal": sum(self._number(item.get("arousal")) for item in payloads) / len(payloads),
            "confidence": sum(self._number(item.get("confidence")) for item in payloads) / len(payloads),
            "diagnosis": False,
            "mind_reading_claim": False,
        }

    def _validate_signals(self, signals: Mapping[str, Any], consent: Mapping[str, bool]) -> None:
        lowered = {str(key).strip().lower() for key in signals}
        if lowered & self._RAW_MEDIA_KEYS:
            raise PermissionError("raw audio/video/image data is not accepted by the Lab affect engine")
        if lowered & self._FORBIDDEN_TRAITS:
            raise PermissionError("sensitive-trait inference is outside the Lab affect boundary")
        unknown = lowered - self._MODALITIES
        if unknown:
            raise ValueError(f"unsupported derived affect modalities: {sorted(unknown)}")
        for modality in lowered:
            if not bool(consent.get(modality, False)):
                raise PermissionError(f"explicit consent is required for derived {modality} signals")
            payload = signals.get(modality)
            if not isinstance(payload, Mapping):
                raise ValueError(f"derived {modality} signal must be an object")
            nested_keys = {str(key).strip().lower() for key in payload}
            if nested_keys & self._RAW_MEDIA_KEYS:
                raise PermissionError("raw media must remain outside the Lab affect store")
            if nested_keys & self._FORBIDDEN_TRAITS:
                raise PermissionError("sensitive-trait inference is not permitted")

    @staticmethod
    def _labels(valence: float, arousal: float) -> tuple[str, ...]:
        labels: list[str] = []
        if valence <= -0.35:
            labels.append("possibly_negative")
        elif valence >= 0.35:
            labels.append("possibly_positive")
        else:
            labels.append("uncertain_or_neutral")
        if arousal >= 0.7:
            labels.append("possibly_high_arousal")
        elif arousal <= 0.3:
            labels.append("possibly_low_arousal")
        return tuple(labels)

    @staticmethod
    def _tone(valence: float, arousal: float, confidence: float) -> str:
        if confidence < 0.45:
            return "neutral_and_check_understanding"
        if valence < -0.25 and arousal > 0.6:
            return "calm_concise_nonjudgmental"
        if valence < -0.25:
            return "supportive_clear"
        if valence > 0.35 and arousal > 0.6:
            return "warm_energetic"
        return "clear_balanced"
