from __future__ import annotations

import ipaddress
import json
import socket
import time
import uuid
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urlsplit, urlunsplit

import httpx

from core.sqlite import Migration, connect_sqlite, run_migrations


class HomeAssistantObservationAdapter:
    """Read-only, owner-configured Home Assistant Sensorium transport.

    The adapter intentionally exposes observations only. It does not call Home
    Assistant service/action endpoints; changing an appliance remains a separate
    IoT proposal that must pass Vishnu's existing approval/control authorities.

    Endpoint URLs are registered ahead of time, credentials live in SecretVault,
    request-time arbitrary URLs are forbidden, redirects are disabled, and
    response sizes/timeouts are bounded.
    """

    COMPONENT = "sensorium_iot_adapters"
    MAX_RESPONSE_BYTES = 128 * 1024
    MAX_ATTRIBUTES = 96

    def __init__(
        self,
        path: Path,
        *,
        vault,
        events=None,
        resolver: Callable[[str], set[str]] | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if vault is None:
            raise ValueError("Home Assistant adapter requires SecretVault")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.vault = vault
        self.events = events
        self._resolver = resolver or self._resolve_host
        self._transport = transport
        with self._con() as con:
            run_migrations(
                con,
                component=self.COMPONENT,
                migrations=(Migration(1, "home-assistant-observation-adapters", self._migration_001),),
            )

    def _con(self):
        return connect_sqlite(self.path)

    @staticmethod
    def _migration_001(con) -> None:
        con.execute(
            """CREATE TABLE IF NOT EXISTS sensorium_iot_adapters(
                adapter_id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                label TEXT NOT NULL,
                base_url TEXT NOT NULL,
                verify_tls INTEGER NOT NULL,
                allow_private_http INTEGER NOT NULL,
                secret_ref TEXT NOT NULL,
                enabled INTEGER NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )"""
        )

    @staticmethod
    def _resolve_host(host: str) -> set[str]:
        try:
            return {
                row[4][0]
                for row in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
                if row and row[4]
            }
        except OSError as exc:
            raise ValueError("IoT adapter host could not be resolved") from exc

    @staticmethod
    def _address(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
        try:
            return ipaddress.ip_address(value)
        except ValueError as exc:
            raise ValueError("IoT adapter resolved to an invalid network address") from exc

    @classmethod
    def _validate_addresses(cls, addresses: set[str]) -> tuple[bool, bool]:
        if not addresses:
            raise ValueError("IoT adapter host resolved to no addresses")
        has_private = False
        has_public = False
        for raw in addresses:
            address = cls._address(raw)
            if address.is_unspecified or address.is_multicast or address.is_link_local:
                raise ValueError("IoT adapter host resolves to a forbidden network address")
            if address.is_loopback or address.is_private:
                has_private = True
            else:
                has_public = True
        if has_private and has_public:
            raise ValueError("IoT adapter host has mixed public/private DNS results")
        return has_private, has_public

    def _normalize_url(self, value: str, *, allow_private_http: bool) -> str:
        parsed = urlsplit(str(value or "").strip())
        if parsed.scheme not in {"https", "http"} or not parsed.hostname:
            raise ValueError("Home Assistant base URL must be an absolute HTTP(S) URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Home Assistant base URL must not contain credentials, query or fragment")
        addresses = self._resolver(parsed.hostname)
        has_private, _ = self._validate_addresses(addresses)
        if parsed.scheme == "http" and not (allow_private_http and has_private):
            raise ValueError("HTTP is allowed only for explicitly approved private/loopback Home Assistant endpoints")
        path = parsed.path.rstrip("/")
        return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))

    def _emit(self, event: str, **payload) -> None:
        if self.events is not None:
            self.events.emit(event, **payload)

    def register(
        self,
        *,
        label: str,
        base_url: str,
        bearer_token: str,
        allow_private_http: bool = False,
        verify_tls: bool = True,
        adapter_id: str | None = None,
    ) -> dict:
        title = str(label or "").strip()[:160]
        token = str(bearer_token or "").strip()
        if not title:
            raise ValueError("Home Assistant adapter label is required")
        if len(token) < 12 or len(token) > 8192:
            raise ValueError("Home Assistant bearer token is invalid")
        normalized = self._normalize_url(base_url, allow_private_http=bool(allow_private_http))
        adapter = str(adapter_id or uuid.uuid4())[:200]
        secret_ref = f"sensorium.iot.home_assistant.{adapter}.bearer"
        self.vault.set(secret_ref, token)
        now = time.time()
        with self._con() as con:
            con.execute(
                """INSERT INTO sensorium_iot_adapters(
                    adapter_id,kind,label,base_url,verify_tls,allow_private_http,secret_ref,enabled,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,1,?,?)
                ON CONFLICT(adapter_id) DO UPDATE SET
                    kind=excluded.kind,label=excluded.label,base_url=excluded.base_url,
                    verify_tls=excluded.verify_tls,allow_private_http=excluded.allow_private_http,
                    secret_ref=excluded.secret_ref,enabled=1,updated_at=excluded.updated_at""",
                (
                    adapter,
                    "home_assistant",
                    title,
                    normalized,
                    1 if verify_tls else 0,
                    1 if allow_private_http else 0,
                    secret_ref,
                    now,
                    now,
                ),
            )
        self._emit("sensorium.iot.adapter_registered", adapter_id=adapter, kind="home_assistant")
        return self.get(adapter)

    def get(self, adapter_id: str) -> dict:
        with self._con() as con:
            row = con.execute(
                "SELECT * FROM sensorium_iot_adapters WHERE adapter_id=?",
                (str(adapter_id),),
            ).fetchone()
        if row is None:
            raise KeyError("IoT adapter not found")
        return {
            "adapter_id": row["adapter_id"],
            "kind": row["kind"],
            "label": row["label"],
            "base_url": row["base_url"],
            "verify_tls": bool(row["verify_tls"]),
            "allow_private_http": bool(row["allow_private_http"]),
            "enabled": bool(row["enabled"]),
            "created_at": float(row["created_at"]),
            "updated_at": float(row["updated_at"]),
            "credential_stored": True,
            "execution_authority": False,
        }

    def list(self) -> list[dict]:
        with self._con() as con:
            ids = [row["adapter_id"] for row in con.execute(
                "SELECT adapter_id FROM sensorium_iot_adapters ORDER BY label"
            ).fetchall()]
        return [self.get(adapter_id) for adapter_id in ids]

    def revoke(self, adapter_id: str) -> bool:
        adapter = self.get(adapter_id)
        with self._con() as con:
            row = con.execute(
                "SELECT secret_ref FROM sensorium_iot_adapters WHERE adapter_id=?",
                (str(adapter_id),),
            ).fetchone()
            changed = con.execute(
                "UPDATE sensorium_iot_adapters SET enabled=0,updated_at=? WHERE adapter_id=?",
                (time.time(), str(adapter_id)),
            ).rowcount
        if row is not None:
            secret_ref = str(row["secret_ref"])
            try:
                self.vault.delete(secret_ref)
            except AttributeError:
                self.vault.set(secret_ref, "")
        if changed:
            self._emit("sensorium.iot.adapter_revoked", adapter_id=str(adapter_id), kind=adapter["kind"])
        return bool(changed)

    @staticmethod
    def _entity(value: str) -> str:
        entity = str(value or "").strip().lower()
        if not entity or len(entity) > 200:
            raise ValueError("Home Assistant entity ID is required")
        allowed = set("abcdefghijklmnopqrstuvwxyz0123456789_.-")
        if any(ch not in allowed for ch in entity) or "." not in entity:
            raise ValueError("Invalid Home Assistant entity ID")
        return entity

    def _secret_ref(self, adapter_id: str) -> str:
        with self._con() as con:
            row = con.execute(
                "SELECT secret_ref FROM sensorium_iot_adapters WHERE adapter_id=? AND enabled=1",
                (str(adapter_id),),
            ).fetchone()
        if row is None:
            raise PermissionError("IoT adapter is disabled or missing")
        return str(row["secret_ref"])

    def observe_state(self, adapter_id: str, *, entity_id: str, timeout_seconds: float = 5.0) -> dict:
        adapter = self.get(adapter_id)
        if not adapter["enabled"]:
            raise PermissionError("IoT adapter is disabled")
        entity = self._entity(entity_id)
        parsed = urlsplit(adapter["base_url"])
        has_private, _ = self._validate_addresses(self._resolver(str(parsed.hostname)))
        if parsed.scheme == "http" and not (adapter["allow_private_http"] and has_private):
            raise PermissionError("Insecure IoT endpoint no longer satisfies the private-network policy")
        token = self.vault.get(self._secret_ref(adapter_id))
        if not token:
            raise PermissionError("IoT adapter credential is unavailable")
        url = f"{adapter['base_url']}/api/states/{quote(entity, safe='._-')}"
        timeout = max(1.0, min(float(timeout_seconds), 10.0))
        with httpx.Client(
            follow_redirects=False,
            verify=bool(adapter["verify_tls"]),
            timeout=httpx.Timeout(timeout),
            transport=self._transport,
        ) as client:
            response = client.get(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                    "User-Agent": "Vishnu-Sensorium/2.0",
                },
            )
        if 300 <= response.status_code < 400:
            raise RuntimeError("IoT adapter redirects are forbidden")
        if response.status_code != 200:
            raise RuntimeError(f"Home Assistant observation failed with HTTP {response.status_code}")
        raw = response.content
        if not raw or len(raw) > self.MAX_RESPONSE_BYTES:
            raise RuntimeError("Home Assistant observation exceeded the response-size limit")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("Home Assistant returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("Home Assistant returned an invalid entity state")
        attributes = payload.get("attributes") if isinstance(payload.get("attributes"), dict) else {}
        bounded_attributes = dict(list(attributes.items())[: self.MAX_ATTRIBUTES])
        result = {
            "adapter_id": adapter["adapter_id"],
            "adapter_kind": "home_assistant",
            "entity_id": entity,
            "state": str(payload.get("state") or "")[:1000],
            "attributes": bounded_attributes,
            "last_changed": str(payload.get("last_changed") or "")[:100],
            "last_updated": str(payload.get("last_updated") or "")[:100],
            "captured_at": time.time(),
            "confidence": 0.95,
            "instruction_trust": "untrusted",
            "execution_authority": False,
            "action_supported_here": False,
            "credential_exposed": False,
        }
        self._emit(
            "sensorium.iot.adapter_observed",
            adapter_id=adapter["adapter_id"],
            entity_id=entity,
            execution_authority=False,
        )
        return result
