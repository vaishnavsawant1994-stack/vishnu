from __future__ import annotations

import time
from typing import Any

from sensorium.scene_graph import SemanticSceneGraph
from sensorium.world_model import TemporalWorldModel


class UnifiedRealityModel:
    """Combines permitted evidence from trusted devices while preserving provenance."""

    def __init__(
        self,
        *,
        world: TemporalWorldModel,
        scene: SemanticSceneGraph,
        events=None,
    ) -> None:
        self.world = world
        self.scene = scene
        self.events = events

    def ingest(
        self,
        *,
        source_device_id: str,
        trusted_device: bool,
        permission_valid: bool,
        modality: str,
        observed_id: str,
        kind: str,
        label: str | None,
        stable_key: str | None,
        attributes: dict[str, Any],
        relations: list[dict[str, Any]] | None = None,
        confidence: float = 0.7,
        freshness_seconds: float = 30.0,
        captured_at: float | None = None,
    ) -> dict[str, Any]:
        device = str(source_device_id or "").strip()
        if not device or not trusted_device:
            raise PermissionError("untrusted devices cannot contribute to the unified reality model")
        if not permission_valid:
            raise PermissionError("source sensor permission/session is not valid")
        timestamp = float(captured_at or time.time())
        resolved = self.scene.resolve_or_create(
            observed_id,
            kind=kind,
            label=label,
            stable_key=stable_key,
            source_device_id=device,
        )
        entity_id = str(resolved["entity_id"])
        world_observations: list[dict[str, Any]] = []
        for attribute, value in list(attributes.items())[:128]:
            world_observations.append(
                self.world.observe(
                    entity_id,
                    attribute=str(attribute)[:120],
                    value=value,
                    source=f"device:{device}",
                    modality=str(modality)[:80],
                    confidence=confidence,
                    freshness_seconds=freshness_seconds,
                    captured_at=timestamp,
                    kind=kind,
                    label=label,
                )
            )
        relation_results: list[dict[str, Any]] = []
        for relation in (relations or [])[:128]:
            object_observed_id = str(relation.get("object_observed_id") or "").strip()
            predicate = str(relation.get("predicate") or "").strip()
            if not object_observed_id or not predicate:
                continue
            object_resolved = self.scene.resolve_or_create(
                object_observed_id,
                kind=str(relation.get("object_kind") or "object"),
                label=(str(relation.get("object_label")) if relation.get("object_label") else None),
                stable_key=(
                    str(relation.get("object_stable_key"))
                    if relation.get("object_stable_key")
                    else None
                ),
                source_device_id=device,
            )
            object_id = str(object_resolved["entity_id"])
            relation_result = self.scene.relate(
                entity_id,
                predicate,
                object_id,
                source_device_id=device,
                source_modality=str(modality),
                confidence=float(relation.get("confidence", confidence)),
                freshness_seconds=float(
                    relation.get("freshness_seconds", freshness_seconds)
                ),
                captured_at=timestamp,
            )
            self.world.relate(
                entity_id,
                predicate,
                object_id,
                source=f"device:{device}",
                confidence=float(relation.get("confidence", confidence)),
                captured_at=timestamp,
            )
            relation_results.append(relation_result)
        if self.events is not None:
            self.events.emit(
                "sensorium.v3.reality.ingested",
                source_device_id=device,
                entity_id=entity_id,
                modality=str(modality)[:80],
                execution_authority=False,
            )
        return {
            "entity_id": entity_id,
            "identity_match": resolved["matched_by"],
            "observations": world_observations,
            "relations": relation_results,
            "source_device_id": device,
            "execution_authority": False,
        }

    def snapshot(self, *, limit: int = 100) -> dict[str, Any]:
        return {
            "world": self.world.snapshot(limit=limit),
            "scene": self.scene.snapshot(limit=limit),
            "execution_authority": False,
        }
