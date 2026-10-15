from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from .store import TrustContinuityStore, utcnow


class MemoryIntelligence:
    """Provenance/confidence/contradiction/timeline layer over memory metadata.

    These records are knowledge evidence only and never carry execution authority.
    """

    def __init__(self, store: TrustContinuityStore):
        self.store = store

    def remember(
        self,
        *,
        owner_id: str,
        entity: str,
        predicate: str,
        value: Any,
        source: dict[str, Any],
        confidence: float,
        observed_at: str | None = None,
        retention_days: int | None = None,
        project_id: str | None = None,
    ) -> str:
        confidence = float(confidence)
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if not entity or not predicate:
            raise ValueError("entity and predicate are required")
        fact_id = uuid4().hex
        now = utcnow()
        expires_at = None
        if retention_days is not None:
            retention_days = max(0, min(int(retention_days), 36500))
            expires_at = (
                datetime.now(timezone.utc) + timedelta(days=retention_days)
            ).isoformat()
        normalized_entity = self.resolve_entity(owner_id=owner_id, label=entity)
        payload = {
            "entity": normalized_entity,
            "original_entity": entity[:500],
            "predicate": predicate[:500],
            "value": value,
            "source": self._safe_source(source),
            "confidence": confidence,
            "observed_at": observed_at or now,
            "valid_from": observed_at or now,
            "valid_to": None,
            "expires_at": expires_at,
            "project_id": project_id,
            "superseded_by": None,
            "contradicts": [],
            "execution_authority": False,
            "created_at": now,
        }
        existing = self.query(
            owner_id=owner_id,
            entity=normalized_entity,
            predicate=predicate,
            include_expired=False,
        )
        contradictions: list[str] = []
        for fact in existing:
            if (
                fact["payload"]["value"] != value
                and fact["payload"].get("valid_to") is None
            ):
                contradictions.append(fact["record_id"])
        payload["contradicts"] = contradictions
        self.store.put("memory_fact", fact_id, payload, owner_id=owner_id)
        for old_id in contradictions:
            old = self.store.get("memory_fact", old_id)
            if old:
                old_payload = dict(old["payload"])
                old_payload["contradicts"] = sorted(
                    set(old_payload.get("contradicts", []) + [fact_id])
                )
                self.store.put(
                    "memory_fact",
                    old_id,
                    old_payload,
                    status=old["status"],
                    owner_id=owner_id,
                )
        self.store.audit(
            "memory",
            "fact_recorded",
            actor=owner_id,
            subject=fact_id,
            payload={
                "entity": normalized_entity,
                "predicate": predicate,
                "confidence": confidence,
            },
        )
        return fact_id

    def edit_fact(
        self,
        fact_id: str,
        *,
        owner_id: str,
        value: Any,
        reason: str,
    ) -> str:
        row = self._owned_fact(fact_id, owner_id)
        payload = row["payload"]
        replacement = self.remember(
            owner_id=owner_id,
            entity=payload["entity"],
            predicate=payload["predicate"],
            value=value,
            source={"kind": "owner_edit", "reason": reason[:1000], "replaces": fact_id},
            confidence=1.0,
            observed_at=utcnow(),
            project_id=payload.get("project_id"),
        )
        payload = dict(payload)
        payload["valid_to"] = utcnow()
        payload["superseded_by"] = replacement
        self.store.put(
            "memory_fact",
            fact_id,
            payload,
            status="superseded",
            owner_id=owner_id,
        )
        self.store.audit(
            "memory",
            "fact_edited",
            actor=owner_id,
            subject=fact_id,
            payload={"replacement": replacement},
        )
        return replacement

    def forget(self, fact_id: str, *, owner_id: str) -> bool:
        self._owned_fact(fact_id, owner_id)
        deleted = self.store.delete("memory_fact", fact_id)
        self.store.audit("memory", "fact_forgotten", actor=owner_id, subject=fact_id)
        return deleted

    def purge_expired(self, *, owner_id: str) -> int:
        now = datetime.now(timezone.utc)
        deleted = 0
        for row in self.query(owner_id=owner_id, include_expired=True, limit=1000):
            expires_at = row["payload"].get("expires_at")
            if not expires_at:
                continue
            expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if expiry <= now and self.store.delete("memory_fact", row["record_id"]):
                deleted += 1
        if deleted:
            self.store.audit(
                "memory",
                "expired_facts_purged",
                actor=owner_id,
                payload={"count": deleted},
            )
        return deleted

    def query(
        self,
        *,
        owner_id: str,
        entity: str | None = None,
        predicate: str | None = None,
        include_expired: bool = False,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        rows = self.store.list("memory_fact", owner_id=owner_id, limit=limit)
        now = datetime.now(timezone.utc)
        output = []
        for row in rows:
            payload = row["payload"]
            if entity is not None and payload.get("entity") != entity:
                continue
            if predicate is not None and payload.get("predicate") != predicate:
                continue
            expires_at = payload.get("expires_at")
            if not include_expired and expires_at:
                expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                if expiry <= now:
                    continue
            output.append(row)
        return output

    def why_known(self, fact_id: str, *, owner_id: str) -> dict[str, Any]:
        row = self._owned_fact(fact_id, owner_id)
        payload = row["payload"]
        return {
            "fact_id": fact_id,
            "entity": payload["entity"],
            "predicate": payload["predicate"],
            "source": payload["source"],
            "confidence": payload["confidence"],
            "observed_at": payload["observed_at"],
            "contradicts": payload.get("contradicts", []),
            "execution_authority": False,
        }

    def timeline(
        self,
        *,
        owner_id: str,
        project_id: str | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        rows = self.query(owner_id=owner_id, include_expired=False, limit=limit)
        if project_id is not None:
            rows = [
                row
                for row in rows
                if row["payload"].get("project_id") == project_id
            ]
        rows.sort(key=lambda row: row["payload"].get("observed_at") or row["created_at"])
        return rows

    def consolidate(self, *, owner_id: str) -> dict[str, Any]:
        rows = self.query(owner_id=owner_id, include_expired=False, limit=1000)
        groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for row in rows:
            payload = row["payload"]
            groups.setdefault((payload["entity"], payload["predicate"]), []).append(row)
        canonical = []
        contradictions = []
        for key, facts in groups.items():
            ranked = sorted(
                facts,
                key=lambda row: (
                    float(row["payload"]["confidence"]),
                    row["updated_at"],
                ),
                reverse=True,
            )
            canonical.append(ranked[0]["record_id"])
            values = {
                repr(row["payload"]["value"])
                for row in facts
                if row["payload"].get("valid_to") is None
            }
            if len(values) > 1:
                contradictions.append(
                    {
                        "entity": key[0],
                        "predicate": key[1],
                        "facts": [row["record_id"] for row in facts],
                    }
                )
        return {
            "canonical_fact_ids": canonical,
            "contradictions": contradictions,
            "execution_authority": False,
        }

    def export_owner(self, owner_id: str) -> dict[str, Any]:
        return {
            "version": 1,
            "owner_id": owner_id,
            "facts": self.query(
                owner_id=owner_id,
                include_expired=True,
                limit=1000,
            ),
            "exported_at": utcnow(),
        }

    def import_owner(
        self,
        *,
        owner_id: str,
        package: dict[str, Any],
    ) -> dict[str, int]:
        if package.get("version") != 1:
            raise ValueError("unsupported memory export version")
        package_owner = package.get("owner_id")
        if package_owner and str(package_owner) != owner_id:
            raise PermissionError("memory package belongs to another owner")
        facts = package.get("facts")
        if not isinstance(facts, list) or len(facts) > 1000:
            raise ValueError("memory package facts must be a bounded list")
        imported = 0
        skipped = 0
        for item in facts:
            payload = item.get("payload") if isinstance(item, dict) else None
            if not isinstance(payload, dict):
                skipped += 1
                continue
            entity = str(payload.get("entity") or "").strip()
            predicate = str(payload.get("predicate") or "").strip()
            if not entity or not predicate:
                skipped += 1
                continue
            confidence = float(payload.get("confidence", 0.5))
            self.remember(
                owner_id=owner_id,
                entity=entity,
                predicate=predicate,
                value=payload.get("value"),
                source={
                    "kind": "memory_import",
                    "original_source": self._safe_source(payload.get("source") or {}),
                },
                confidence=max(0.0, min(confidence, 1.0)),
                observed_at=payload.get("observed_at"),
                project_id=payload.get("project_id"),
            )
            imported += 1
        self.store.audit(
            "memory",
            "owner_import",
            actor=owner_id,
            payload={"imported": imported, "skipped": skipped},
        )
        return {"imported": imported, "skipped": skipped}

    def resolve_entity(self, *, owner_id: str, label: str) -> str:
        normalized = " ".join(label.strip().lower().split())
        aliases = self.store.list(
            "memory_entity_alias",
            owner_id=owner_id,
            limit=1000,
        )
        for row in aliases:
            if row["payload"].get("alias") == normalized:
                return str(row["payload"]["canonical"])
        return normalized

    def add_entity_alias(
        self,
        *,
        owner_id: str,
        alias: str,
        canonical: str,
    ) -> str:
        record_id = uuid4().hex
        self.store.put(
            "memory_entity_alias",
            record_id,
            {
                "alias": " ".join(alias.strip().lower().split()),
                "canonical": " ".join(canonical.strip().lower().split()),
            },
            owner_id=owner_id,
        )
        return record_id

    @staticmethod
    def _safe_source(source: dict[str, Any]) -> dict[str, Any]:
        safe = dict(source)
        for key in list(safe):
            if key.lower() in {
                "token",
                "password",
                "secret",
                "private_key",
                "credential",
            }:
                safe.pop(key)
        return safe

    def _owned_fact(self, fact_id: str, owner_id: str) -> dict[str, Any]:
        row = self.store.get("memory_fact", fact_id)
        if row is None:
            raise KeyError(fact_id)
        if row["owner_id"] != owner_id:
            raise PermissionError("fact belongs to another owner")
        return row
