from __future__ import annotations

import hashlib
import math
import statistics
import time
from dataclasses import dataclass
from typing import Any


class PredictiveEnvironmentModel:
    """Bounded trend prediction with confidence decay; no autonomous actuation."""

    def predict_numeric(
        self,
        samples: list[dict[str, float]],
        *,
        horizon_seconds: float,
    ) -> dict[str, Any]:
        if len(samples) < 2 or len(samples) > 10_000:
            raise ValueError("numeric prediction requires two to 10,000 samples")
        horizon = max(0.0, min(float(horizon_seconds), 86_400.0))
        ordered = sorted(samples, key=lambda item: float(item["timestamp"]))
        t0 = float(ordered[0]["timestamp"])
        xs = [float(item["timestamp"]) - t0 for item in ordered]
        ys = [float(item["value"]) for item in ordered]
        x_mean, y_mean = statistics.mean(xs), statistics.mean(ys)
        denominator = sum((x - x_mean) ** 2 for x in xs)
        slope = (
            sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
            / denominator
            if denominator
            else 0.0
        )
        target_x = xs[-1] + horizon
        predicted = y_mean + slope * (target_x - x_mean)
        residuals = [
            y - (y_mean + slope * (x - x_mean))
            for x, y in zip(xs, ys)
        ]
        noise = statistics.pstdev(residuals) if len(residuals) > 1 else 0.0
        scale = max(abs(y_mean), 1.0)
        confidence = max(
            0.05,
            min(
                0.95,
                math.exp(-noise / scale) * math.exp(-horizon / 86_400.0),
            ),
        )
        return {
            "predicted_value": predicted,
            "slope_per_second": slope,
            "horizon_seconds": horizon,
            "confidence": confidence,
            "execution_authority": False,
        }


class ContextAnomalyDetector:
    def score(self, history: list[float], value: float) -> dict[str, Any]:
        if len(history) < 3:
            return {
                "score": 0.0,
                "anomaly": False,
                "reason": "insufficient_history",
                "execution_authority": False,
            }
        bounded = [float(item) for item in history[-10_000:]]
        mean = statistics.mean(bounded)
        deviation = statistics.pstdev(bounded)
        z = 0.0 if deviation == 0 else abs(float(value) - mean) / deviation
        return {
            "score": min(z / 6.0, 1.0),
            "z_score": z,
            "anomaly": z >= 3.0,
            "baseline_mean": mean,
            "baseline_stddev": deviation,
            "execution_authority": False,
        }


@dataclass(frozen=True, slots=True)
class LocalModelProfile:
    model_id: str
    modalities: tuple[str, ...]
    operations: tuple[str, ...]
    max_input_bytes: int
    local_only: bool = True


class LocalMultimodalRegistry:
    def __init__(self) -> None:
        self._profiles: dict[str, LocalModelProfile] = {}

    def register(self, profile: LocalModelProfile) -> dict[str, Any]:
        if not profile.model_id or profile.max_input_bytes <= 0:
            raise ValueError("invalid local model profile")
        self._profiles[profile.model_id] = profile
        return {
            "model_id": profile.model_id,
            "registered": True,
            "execution_authority": False,
        }

    def choose(
        self,
        *,
        modality: str,
        operation: str,
        input_bytes: int,
    ) -> dict[str, Any] | None:
        candidates = [
            profile
            for profile in self._profiles.values()
            if modality in profile.modalities
            and operation in profile.operations
            and input_bytes <= profile.max_input_bytes
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda item: (item.max_input_bytes, item.model_id))
        chosen = candidates[0]
        return {
            "model_id": chosen.model_id,
            "local_only": chosen.local_only,
            "execution_authority": False,
        }


class IndoorPositioningFusion:
    """Fuses already-permitted UWB/BLE/Wi-Fi/local-anchor positions."""

    SOURCE_WEIGHTS = {
        "uwb": 1.0,
        "lidar_anchor": 0.9,
        "ble": 0.6,
        "wifi": 0.45,
        "visual_anchor": 0.75,
    }

    def fuse(self, observations: list[dict[str, Any]]) -> dict[str, Any]:
        usable = []
        for item in observations[:256]:
            source = str(item.get("source") or "").lower()
            if source not in self.SOURCE_WEIGHTS:
                continue
            confidence = max(
                0.0,
                min(float(item.get("confidence", 0.5)), 1.0),
            )
            weight = self.SOURCE_WEIGHTS[source] * confidence
            if weight <= 0:
                continue
            usable.append((item, weight))
        if not usable:
            raise ValueError("no usable indoor positioning observations")
        total = sum(weight for _, weight in usable)
        x = sum(float(item["x"]) * weight for item, weight in usable) / total
        y = sum(float(item["y"]) * weight for item, weight in usable) / total
        z = sum(
            float(item.get("z", 0.0)) * weight
            for item, weight in usable
        ) / total
        return {
            "position": {"x": x, "y": y, "z": z},
            "sources": [item["source"] for item, _ in usable],
            "confidence": min(total / len(usable), 1.0),
            "execution_authority": False,
        }


class EcosystemBoundary:
    """Matter/HomeKit-style observation and action-proposal separation."""

    def observe(
        self,
        ecosystem: str,
        accessory_id: str,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "ecosystem": str(ecosystem)[:40],
            "accessory_id": str(accessory_id)[:200],
            "state": state,
            "instruction_trust": "untrusted",
            "action_authorized": False,
            "execution_authority": False,
        }

    def propose_action(
        self,
        ecosystem: str,
        accessory_id: str,
        capability: str,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "proposal_id": hashlib.sha256(
                (
                    f"{ecosystem}|{accessory_id}|{capability}|{time.time_ns()}"
                ).encode()
            ).hexdigest()[:32],
            "ecosystem": str(ecosystem)[:40],
            "accessory_id": str(accessory_id)[:200],
            "capability": str(capability)[:120],
            "parameters": parameters,
            "requires_existing_action_authority": True,
            "action_authorized": False,
            "execution_authority": False,
        }


class RoboticsBoundary:
    """Robot observations and proposals only; no motor/actuator transport."""

    def observe(
        self,
        robot_id: str,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "robot_id": str(robot_id)[:200],
            "state": state,
            "action_authorized": False,
            "execution_authority": False,
        }

    def propose(
        self,
        robot_id: str,
        skill: str,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "robot_id": str(robot_id)[:200],
            "skill": str(skill)[:160],
            "parameters": parameters,
            "requires_robot_control_authority": True,
            "action_authorized": False,
            "execution_authority": False,
        }


class RoomReconstruction:
    """Semantic merge of privacy-processed planes/anchors from AR/LiDAR sources."""

    def reconstruct(
        self,
        observations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        surfaces: dict[str, dict[str, Any]] = {}
        anchors: dict[str, dict[str, Any]] = {}
        for item in observations[:20_000]:
            kind = str(item.get("kind") or "")
            stable_id = str(item.get("id") or "").strip()
            if not stable_id:
                continue
            record = {
                "id": stable_id[:200],
                "source_device_id": str(
                    item.get("source_device_id") or ""
                )[:200],
                "geometry": item.get("geometry") or {},
                "confidence": max(
                    0.0,
                    min(float(item.get("confidence", 0.5)), 1.0),
                ),
            }
            if kind == "surface":
                surfaces[stable_id] = record
            elif kind == "anchor":
                anchors[stable_id] = record
        return {
            "surfaces": list(surfaces.values()),
            "anchors": list(anchors.values()),
            "raw_media_retained": False,
            "execution_authority": False,
        }


class CollaborativePerception:
    """Shares bounded semantic summaries between trusted devices; refuses raw media."""

    FORBIDDEN_KEYS = {
        "image",
        "video",
        "audio",
        "pcm",
        "frame",
        "base64",
        "raw_bytes",
        "photo",
    }

    def fuse(
        self,
        summaries: list[dict[str, Any]],
    ) -> dict[str, Any]:
        fused: list[dict[str, Any]] = []
        for summary in summaries[:256]:
            if not bool(summary.get("trusted_device")):
                continue
            if not bool(summary.get("permission_valid")):
                continue
            payload = dict(summary.get("payload") or {})
            if any(key.lower() in self.FORBIDDEN_KEYS for key in payload):
                raise ValueError(
                    "collaborative perception accepts semantic summaries, not raw media"
                )
            fused.append(
                {
                    "source_device_id": str(
                        summary.get("source_device_id") or ""
                    )[:200],
                    "captured_at": float(
                        summary.get("captured_at") or time.time()
                    ),
                    "payload": payload,
                    "confidence": max(
                        0.0,
                        min(float(summary.get("confidence", 0.5)), 1.0),
                    ),
                }
            )
        return {
            "summaries": fused,
            "source_count": len(
                {item["source_device_id"] for item in fused}
            ),
            "raw_media_retained": False,
            "execution_authority": False,
        }
