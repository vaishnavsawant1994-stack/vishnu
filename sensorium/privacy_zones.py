from __future__ import annotations

import json
import math
import time
import uuid
from pathlib import Path
from typing import Any

from core.sqlite import Migration, connect_sqlite, run_migrations


class PrivacyZoneStore:
    """Owner-defined privacy rules with sensitive rule payloads held in SecretVault.

    Zones can be location-based, context-tag based, or both. A matching zone can
    deny specific sensors, require local-only processing, require bystander
    redaction, or forbid media retention. No zone grants permission; rules only
    restrict an otherwise permitted sensor session.
    """

    COMPONENT = "sensorium_privacy_zones"

    def __init__(self, path: Path, *, vault, events=None) -> None:
        if vault is None:
            raise ValueError("privacy zones require encrypted SecretVault storage")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.vault = vault
        self.events = events
        with self._con() as con:
            run_migrations(
                con,
                component=self.COMPONENT,
                migrations=(Migration(1, "privacy-zones", self._migration_001),),
            )

    def _con(self):
        return connect_sqlite(self.path)

    @staticmethod
    def _migration_001(con) -> None:
        con.execute(
            """CREATE TABLE IF NOT EXISTS privacy_zones(
                zone_id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                enabled INTEGER NOT NULL,
                vault_key TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )"""
        )

    @staticmethod
    def _rule_payload(rule: dict[str, Any]) -> dict[str, Any]:
        denied = sorted({str(item).strip().lower() for item in rule.get("deny_sensors", []) if str(item).strip()})[:64]
        tags = sorted({str(item).strip().lower() for item in rule.get("context_tags", []) if str(item).strip()})[:64]
        latitude = rule.get("latitude")
        longitude = rule.get("longitude")
        radius_m = rule.get("radius_m")
        if latitude is not None:
            latitude = float(latitude)
            if latitude < -90 or latitude > 90:
                raise ValueError("privacy-zone latitude is invalid")
        if longitude is not None:
            longitude = float(longitude)
            if longitude < -180 or longitude > 180:
                raise ValueError("privacy-zone longitude is invalid")
        if (latitude is None) != (longitude is None):
            raise ValueError("privacy-zone latitude and longitude must be supplied together")
        if radius_m is not None:
            radius_m = max(1.0, min(float(radius_m), 100_000.0))
        return {
            "deny_sensors": denied,
            "context_tags": tags,
            "latitude": latitude,
            "longitude": longitude,
            "radius_m": radius_m,
            "require_local_processing": bool(rule.get("require_local_processing", False)),
            "require_bystander_redaction": bool(rule.get("require_bystander_redaction", False)),
            "forbid_media_retention": bool(rule.get("forbid_media_retention", False)),
            "private_screen": bool(rule.get("private_screen", False)),
            "meeting_mode": bool(rule.get("meeting_mode", False)),
        }

    def _emit(self, event: str, **payload) -> None:
        if self.events is not None:
            self.events.emit(event, **payload)

    def put(self, *, label: str, rule: dict[str, Any], zone_id: str | None = None, enabled: bool = True) -> dict:
        zone = str(zone_id or uuid.uuid4())
        title = str(label or "").strip()[:160]
        if not title:
            raise ValueError("privacy-zone label is required")
        payload = self._rule_payload(rule)
        vault_key = f"sensorium.privacy_zone.{zone}.v1"
        self.vault.set(vault_key, json.dumps(payload, sort_keys=True, separators=(",", ":")))
        now = time.time()
        with self._con() as con:
            con.execute(
                """INSERT INTO privacy_zones(zone_id,label,enabled,vault_key,created_at,updated_at)
                   VALUES(?,?,?,?,?,?) ON CONFLICT(zone_id) DO UPDATE SET
                   label=excluded.label,enabled=excluded.enabled,vault_key=excluded.vault_key,updated_at=excluded.updated_at""",
                (zone, title, int(bool(enabled)), vault_key, now, now),
            )
        self._emit("sensorium.privacy_zone.saved", zone_id=zone, enabled=bool(enabled))
        return self.get(zone)

    def _decode(self, row) -> dict:
        raw = self.vault.get(row["vault_key"])
        if not raw:
            raise RuntimeError("privacy-zone encrypted rule is missing")
        payload = json.loads(str(raw))
        return {
            "zone_id": row["zone_id"],
            "label": row["label"],
            "enabled": bool(row["enabled"]),
            "rule": payload,
            "created_at": float(row["created_at"]),
            "updated_at": float(row["updated_at"]),
        }

    def get(self, zone_id: str) -> dict:
        with self._con() as con:
            row = con.execute("SELECT * FROM privacy_zones WHERE zone_id=?", (str(zone_id),)).fetchone()
        if row is None:
            raise KeyError("privacy zone not found")
        return self._decode(row)

    def list(self) -> list[dict]:
        with self._con() as con:
            rows = con.execute("SELECT * FROM privacy_zones ORDER BY label,zone_id").fetchall()
        return [self._decode(row) for row in rows]

    def delete(self, zone_id: str) -> bool:
        zone = self.get(zone_id)
        vault_key = f"sensorium.privacy_zone.{zone['zone_id']}.v1"
        try:
            self.vault.delete(vault_key)
        except AttributeError:
            self.vault.set(vault_key, "")
        with self._con() as con:
            removed = con.execute("DELETE FROM privacy_zones WHERE zone_id=?", (zone["zone_id"],)).rowcount == 1
        if removed:
            self._emit("sensorium.privacy_zone.deleted", zone_id=zone["zone_id"])
        return removed

    @staticmethod
    def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        radius = 6_371_000.0
        p1 = math.radians(lat1)
        p2 = math.radians(lat2)
        dp = math.radians(lat2 - lat1)
        dl = math.radians(lon2 - lon1)
        a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1 - a)))

    def evaluate(self, context: dict[str, Any] | None) -> dict:
        data = dict(context or {})
        tags = {str(item).strip().lower() for item in data.get("context_tags", []) if str(item).strip()}
        latitude = data.get("latitude")
        longitude = data.get("longitude")
        matches: list[str] = []
        denied: set[str] = set()
        local_only = False
        redact = False
        no_media = False
        private_screen = False
        meeting = False
        for zone in self.list():
            if not zone["enabled"]:
                continue
            rule = zone["rule"]
            tag_match = bool(set(rule.get("context_tags") or ()) & tags)
            location_match = False
            if latitude is not None and longitude is not None and rule.get("latitude") is not None:
                distance = self._distance_m(float(latitude), float(longitude), float(rule["latitude"]), float(rule["longitude"]))
                location_match = distance <= float(rule.get("radius_m") or 100)
            if not tag_match and not location_match:
                continue
            matches.append(zone["zone_id"])
            denied.update(rule.get("deny_sensors") or ())
            local_only = local_only or bool(rule.get("require_local_processing"))
            redact = redact or bool(rule.get("require_bystander_redaction"))
            no_media = no_media or bool(rule.get("forbid_media_retention"))
            private_screen = private_screen or bool(rule.get("private_screen"))
            meeting = meeting or bool(rule.get("meeting_mode"))
        result = {
            "matched_zone_ids": matches,
            "deny_sensors": sorted(denied),
            "require_local_processing": local_only,
            "require_bystander_redaction": redact,
            "forbid_media_retention": no_media,
            "private_screen": private_screen,
            "meeting_mode": meeting,
            "execution_authority": False,
        }
        if matches:
            self._emit(
                "sensorium.privacy_zone.matched",
                matched_zone_ids=matches,
                deny_sensors=sorted(denied),
                execution_authority=False,
            )
        return result
