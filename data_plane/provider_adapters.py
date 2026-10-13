from __future__ import annotations

import hashlib
import hmac
import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping
from urllib.parse import quote, urlparse

import httpx

from .manager import _json
from .policy import StoragePolicy


MAX_PROVIDER_OBJECT_BYTES = 8 * 1024 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 30.0
_OBJECT_KEY_RE = re.compile(r"^[A-Za-z0-9._/@+=:-]{1,900}$")
_SQL_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


class ProviderAdapterError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderObjectInfo:
    object_key: str
    size: int | None = None
    etag: str | None = None
    content_type: str | None = None


class VaultCredentialResolver:
    """Resolve an opaque provider credential reference from Vishnu's canonical vault.

    The data-plane database stores only the reference. Secret values are read into
    process memory for the bounded provider operation and are never written back
    into provider config, logs, sync metadata, or data-plane events.
    """

    def __init__(self, vault):
        if vault is None:
            raise RuntimeError("provider adapters require Vishnu's canonical secret vault")
        self.vault = vault

    def resolve(self, credential_ref: str | None) -> dict[str, Any]:
        reference = str(credential_ref or "").strip()
        if not reference:
            raise ProviderAdapterError("provider credential reference is missing")
        raw = self.vault.get(reference)
        if raw is None:
            raise ProviderAdapterError("provider credential is unavailable from the canonical vault")
        if not isinstance(raw, str) or not raw:
            raise ProviderAdapterError("provider credential is invalid")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {"token": raw}
        if isinstance(parsed, str):
            parsed = {"token": parsed}
        if not isinstance(parsed, dict) or not parsed:
            raise ProviderAdapterError("provider credential must be a token or JSON object")
        return dict(parsed)


class ProviderObjectAdapter(ABC):
    def __init__(
        self,
        *,
        provider_id: str,
        config: Mapping[str, Any],
        credentials: Mapping[str, Any],
        client: Any | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ):
        self.provider_id = str(provider_id)
        self.config = dict(config or {})
        self.credentials = dict(credentials or {})
        self.client = client or httpx.Client(timeout=timeout, follow_redirects=False)
        self.timeout = float(timeout)

    @staticmethod
    def _key(object_key: str) -> str:
        key = str(object_key or "").strip().lstrip("/")
        if not _OBJECT_KEY_RE.fullmatch(key) or ".." in key.split("/"):
            raise ValueError("invalid provider object key")
        return key

    @staticmethod
    def _bounded(payload: bytes) -> bytes:
        data = bytes(payload)
        if len(data) > MAX_PROVIDER_OBJECT_BYTES:
            raise ValueError("provider object exceeds bounded data-plane limit")
        return data

    @staticmethod
    def _https(url: str) -> str:
        value = str(url or "").rstrip("/")
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ProviderAdapterError("provider endpoint must be credential-free HTTPS")
        return value

    @abstractmethod
    def verify(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def put(self, object_key: str, payload: bytes, *, content_type: str = "application/octet-stream") -> ProviderObjectInfo:
        raise NotImplementedError

    @abstractmethod
    def get(self, object_key: str) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def delete(self, object_key: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def head(self, object_key: str) -> ProviderObjectInfo | None:
        raise NotImplementedError


class DropboxAdapter(ProviderObjectAdapter):
    API = "https://api.dropboxapi.com/2"
    CONTENT = "https://content.dropboxapi.com/2"

    def _token(self) -> str:
        token = str(self.credentials.get("access_token") or self.credentials.get("token") or "")
        if not token:
            raise ProviderAdapterError("Dropbox access token is missing")
        return token

    def _path(self, key: str) -> str:
        prefix = str(self.config.get("root") or "/Apps/Vishnu").strip()
        if not prefix.startswith("/"):
            prefix = "/" + prefix
        return prefix.rstrip("/") + "/" + self._key(key)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token()}"}

    def verify(self) -> dict[str, Any]:
        response = self.client.post(f"{self.API}/users/get_current_account", headers=self._headers())
        response.raise_for_status()
        body = response.json()
        return {"ok": True, "provider_id": self.provider_id, "account_id": body.get("account_id")}

    def put(self, object_key: str, payload: bytes, *, content_type: str = "application/octet-stream") -> ProviderObjectInfo:
        data = self._bounded(payload)
        path = self._path(object_key)
        headers = {
            **self._headers(),
            "Content-Type": "application/octet-stream",
            "Dropbox-API-Arg": json.dumps({"path": path, "mode": "overwrite", "autorename": False, "mute": True}),
        }
        response = self.client.post(f"{self.CONTENT}/files/upload", headers=headers, content=data)
        response.raise_for_status()
        body = response.json()
        return ProviderObjectInfo(self._key(object_key), size=int(body.get("size") or len(data)), etag=body.get("content_hash"), content_type=content_type)

    def get(self, object_key: str) -> bytes:
        path = self._path(object_key)
        response = self.client.post(
            f"{self.CONTENT}/files/download",
            headers={**self._headers(), "Dropbox-API-Arg": json.dumps({"path": path})},
        )
        response.raise_for_status()
        data = bytes(response.content)
        if len(data) > MAX_PROVIDER_OBJECT_BYTES:
            raise ProviderAdapterError("Dropbox object exceeds bounded data-plane limit")
        return data

    def delete(self, object_key: str) -> bool:
        response = self.client.post(
            f"{self.API}/files/delete_v2",
            headers={**self._headers(), "Content-Type": "application/json"},
            json={"path": self._path(object_key)},
        )
        if response.status_code == 409:
            return False
        response.raise_for_status()
        return True

    def head(self, object_key: str) -> ProviderObjectInfo | None:
        response = self.client.post(
            f"{self.API}/files/get_metadata",
            headers={**self._headers(), "Content-Type": "application/json"},
            json={"path": self._path(object_key), "include_deleted": False},
        )
        if response.status_code == 409:
            return None
        response.raise_for_status()
        body = response.json()
        return ProviderObjectInfo(self._key(object_key), size=int(body.get("size") or 0), etag=body.get("content_hash"))


class OneDriveAdapter(ProviderObjectAdapter):
    GRAPH = "https://graph.microsoft.com/v1.0"

    def _token(self) -> str:
        token = str(self.credentials.get("access_token") or self.credentials.get("token") or "")
        if not token:
            raise ProviderAdapterError("OneDrive access token is missing")
        return token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token()}"}

    def _path_url(self, key: str, suffix: str = "") -> str:
        root = str(self.config.get("root") or "Vishnu").strip("/")
        joined = f"{root}/{self._key(key)}" if root else self._key(key)
        encoded = "/".join(quote(part, safe="") for part in joined.split("/"))
        return f"{self.GRAPH}/me/drive/root:/{encoded}:{suffix}"

    def verify(self) -> dict[str, Any]:
        response = self.client.get(f"{self.GRAPH}/me/drive", headers=self._headers())
        response.raise_for_status()
        body = response.json()
        return {"ok": True, "provider_id": self.provider_id, "drive_id": body.get("id")}

    def put(self, object_key: str, payload: bytes, *, content_type: str = "application/octet-stream") -> ProviderObjectInfo:
        data = self._bounded(payload)
        response = self.client.put(
            self._path_url(object_key, "/content"),
            headers={**self._headers(), "Content-Type": content_type},
            content=data,
        )
        response.raise_for_status()
        body = response.json()
        file_meta = body.get("file") or {}
        hashes = file_meta.get("hashes") or {}
        return ProviderObjectInfo(self._key(object_key), size=int(body.get("size") or len(data)), etag=hashes.get("sha256Hash") or body.get("eTag"), content_type=content_type)

    def get(self, object_key: str) -> bytes:
        response = self.client.get(self._path_url(object_key, "/content"), headers=self._headers(), follow_redirects=False)
        if 300 <= response.status_code < 400:
            location = response.headers.get("location")
            if not location:
                raise ProviderAdapterError("OneDrive download redirect is missing location")
            # Download URLs are pre-authenticated and may use Microsoft CDN hosts.
            response = self.client.get(location, follow_redirects=False)
        response.raise_for_status()
        data = bytes(response.content)
        if len(data) > MAX_PROVIDER_OBJECT_BYTES:
            raise ProviderAdapterError("OneDrive object exceeds bounded data-plane limit")
        return data

    def delete(self, object_key: str) -> bool:
        response = self.client.delete(self._path_url(object_key), headers=self._headers())
        if response.status_code == 404:
            return False
        response.raise_for_status()
        return True

    def head(self, object_key: str) -> ProviderObjectInfo | None:
        response = self.client.get(self._path_url(object_key), headers=self._headers())
        if response.status_code == 404:
            return None
        response.raise_for_status()
        body = response.json()
        hashes = (body.get("file") or {}).get("hashes") or {}
        return ProviderObjectInfo(self._key(object_key), size=int(body.get("size") or 0), etag=hashes.get("sha256Hash") or body.get("eTag"))


class S3CompatibleAdapter(ProviderObjectAdapter):
    """AWS Signature V4 adapter for S3, Cloudflare R2, and Backblaze B2 S3 APIs."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.region = str(self.config.get("region") or ("auto" if self.provider_id == "cloudflare_r2" else "us-east-1"))
        self.bucket = str(self.config.get("bucket") or "").strip()
        if not self.bucket or any(c in self.bucket for c in "/\\"):
            raise ProviderAdapterError("S3-compatible provider requires a valid bucket")
        endpoint = self.config.get("endpoint")
        if not endpoint:
            if self.provider_id == "s3":
                endpoint = f"https://s3.{self.region}.amazonaws.com"
            else:
                raise ProviderAdapterError("S3-compatible provider requires an HTTPS endpoint")
        self.endpoint = self._https(str(endpoint))

    def _keys(self) -> tuple[str, str, str | None]:
        access = str(self.credentials.get("access_key_id") or self.credentials.get("access_key") or "")
        secret = str(self.credentials.get("secret_access_key") or self.credentials.get("secret_key") or "")
        session = self.credentials.get("session_token")
        if not access or not secret:
            raise ProviderAdapterError("S3-compatible access key material is missing")
        return access, secret, str(session) if session else None

    def _url(self, object_key: str | None = None) -> str:
        path = f"/{quote(self.bucket, safe='')}"
        if object_key is not None:
            path += "/" + quote(self._key(object_key), safe="/-_.~")
        return self.endpoint + path

    @staticmethod
    def _signing_key(secret: str, datestamp: str, region: str) -> bytes:
        k_date = hmac.new(("AWS4" + secret).encode(), datestamp.encode(), hashlib.sha256).digest()
        k_region = hmac.new(k_date, region.encode(), hashlib.sha256).digest()
        k_service = hmac.new(k_region, b"s3", hashlib.sha256).digest()
        return hmac.new(k_service, b"aws4_request", hashlib.sha256).digest()

    def _signed_headers(self, method: str, url: str, payload: bytes = b"", extra: Mapping[str, str] | None = None) -> dict[str, str]:
        access, secret, session = self._keys()
        parsed = urlparse(url)
        now = datetime.now(timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        datestamp = now.strftime("%Y%m%d")
        payload_hash = hashlib.sha256(payload).hexdigest()
        headers = {
            "host": parsed.netloc,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amz_date,
        }
        if session:
            headers["x-amz-security-token"] = session
        for key, value in (extra or {}).items():
            headers[str(key).lower()] = str(value).strip()
        signed_names = ";".join(sorted(headers))
        canonical_headers = "".join(f"{name}:{headers[name]}\n" for name in sorted(headers))
        canonical_request = "\n".join([
            method.upper(),
            parsed.path or "/",
            parsed.query,
            canonical_headers,
            signed_names,
            payload_hash,
        ])
        scope = f"{datestamp}/{self.region}/s3/aws4_request"
        string_to_sign = "\n".join([
            "AWS4-HMAC-SHA256",
            amz_date,
            scope,
            hashlib.sha256(canonical_request.encode()).hexdigest(),
        ])
        signature = hmac.new(self._signing_key(secret, datestamp, self.region), string_to_sign.encode(), hashlib.sha256).hexdigest()
        result = {name.title(): value for name, value in headers.items()}
        result["Authorization"] = (
            f"AWS4-HMAC-SHA256 Credential={access}/{scope}, SignedHeaders={signed_names}, Signature={signature}"
        )
        return result

    def _request(self, method: str, object_key: str | None = None, payload: bytes = b"", extra: Mapping[str, str] | None = None):
        url = self._url(object_key)
        headers = self._signed_headers(method, url, payload, extra)
        return self.client.request(method, url, headers=headers, content=payload, follow_redirects=False)

    def verify(self) -> dict[str, Any]:
        response = self._request("HEAD")
        response.raise_for_status()
        return {"ok": True, "provider_id": self.provider_id, "bucket": self.bucket, "region": self.region}

    def put(self, object_key: str, payload: bytes, *, content_type: str = "application/octet-stream") -> ProviderObjectInfo:
        data = self._bounded(payload)
        response = self._request("PUT", object_key, data, {"content-type": content_type})
        response.raise_for_status()
        return ProviderObjectInfo(self._key(object_key), size=len(data), etag=(response.headers.get("etag") or "").strip('"') or None, content_type=content_type)

    def get(self, object_key: str) -> bytes:
        response = self._request("GET", object_key)
        response.raise_for_status()
        data = bytes(response.content)
        if len(data) > MAX_PROVIDER_OBJECT_BYTES:
            raise ProviderAdapterError("S3-compatible object exceeds bounded data-plane limit")
        return data

    def delete(self, object_key: str) -> bool:
        response = self._request("DELETE", object_key)
        if response.status_code == 404:
            return False
        response.raise_for_status()
        return True

    def head(self, object_key: str) -> ProviderObjectInfo | None:
        response = self._request("HEAD", object_key)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        size = response.headers.get("content-length")
        return ProviderObjectInfo(
            self._key(object_key),
            size=int(size) if size is not None else None,
            etag=(response.headers.get("etag") or "").strip('"') or None,
            content_type=response.headers.get("content-type"),
        )


class PostgreSQLObjectAdapter(ProviderObjectAdapter):
    """Encrypted-object storage for PostgreSQL, Supabase, Neon, and RDS Postgres."""

    def __init__(self, **kwargs):
        # No HTTP client is required. Keep base validation/fields but avoid opening one.
        client = kwargs.pop("client", None)
        super().__init__(client=client or _NullClient(), **kwargs)
        table = str(self.config.get("table") or "vishnu_encrypted_objects")
        if not _SQL_IDENT_RE.fullmatch(table):
            raise ProviderAdapterError("invalid PostgreSQL object table name")
        self.table = table

    def _dsn(self) -> str:
        value = self.credentials.get("dsn") or self.credentials.get("database_url") or self.credentials.get("token")
        dsn = str(value or "").strip()
        if not dsn:
            raise ProviderAdapterError("PostgreSQL DSN is missing")
        if not (dsn.startswith("postgresql://") or dsn.startswith("postgres://")):
            raise ProviderAdapterError("PostgreSQL DSN must use postgres/postgresql scheme")
        return dsn

    @staticmethod
    def _psycopg():
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - exercised by packaging gate when dependency missing
            raise ProviderAdapterError("psycopg is required for PostgreSQL storage adapters") from exc
        return psycopg

    def _connect(self):
        return self._psycopg().connect(self._dsn(), connect_timeout=max(1, int(self.timeout)))

    def _ensure_table(self, con) -> None:
        con.execute(
            f"""CREATE TABLE IF NOT EXISTS {self.table}(
                object_key TEXT PRIMARY KEY,
                payload BYTEA NOT NULL,
                content_type TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )"""
        )

    def verify(self) -> dict[str, Any]:
        with self._connect() as con:
            self._ensure_table(con)
            row = con.execute("SELECT current_database(), current_user").fetchone()
        return {"ok": True, "provider_id": self.provider_id, "database": row[0] if row else None}

    def put(self, object_key: str, payload: bytes, *, content_type: str = "application/octet-stream") -> ProviderObjectInfo:
        key = self._key(object_key)
        data = self._bounded(payload)
        digest = hashlib.sha256(data).hexdigest()
        with self._connect() as con:
            self._ensure_table(con)
            con.execute(
                f"""INSERT INTO {self.table}(object_key,payload,content_type,sha256,updated_at)
                    VALUES(%s,%s,%s,%s,CURRENT_TIMESTAMP)
                    ON CONFLICT(object_key) DO UPDATE SET payload=EXCLUDED.payload,
                    content_type=EXCLUDED.content_type,sha256=EXCLUDED.sha256,updated_at=CURRENT_TIMESTAMP""",
                (key, data, content_type, digest),
            )
        return ProviderObjectInfo(key, size=len(data), etag=digest, content_type=content_type)

    def get(self, object_key: str) -> bytes:
        key = self._key(object_key)
        with self._connect() as con:
            self._ensure_table(con)
            row = con.execute(f"SELECT payload FROM {self.table} WHERE object_key=%s", (key,)).fetchone()
        if row is None:
            raise FileNotFoundError(key)
        data = bytes(row[0])
        if len(data) > MAX_PROVIDER_OBJECT_BYTES:
            raise ProviderAdapterError("PostgreSQL object exceeds bounded data-plane limit")
        return data

    def delete(self, object_key: str) -> bool:
        key = self._key(object_key)
        with self._connect() as con:
            self._ensure_table(con)
            cur = con.execute(f"DELETE FROM {self.table} WHERE object_key=%s", (key,))
            deleted = bool(cur.rowcount)
        return deleted

    def head(self, object_key: str) -> ProviderObjectInfo | None:
        key = self._key(object_key)
        with self._connect() as con:
            self._ensure_table(con)
            row = con.execute(
                f"SELECT octet_length(payload),sha256,content_type FROM {self.table} WHERE object_key=%s",
                (key,),
            ).fetchone()
        if row is None:
            return None
        return ProviderObjectInfo(key, size=int(row[0]), etag=str(row[1]), content_type=str(row[2]))


class _NullClient:
    def request(self, *args, **kwargs):  # pragma: no cover - defensive only
        raise RuntimeError("HTTP client is not available for PostgreSQL adapter")


class ProviderAdapterFactory:
    """Build verified adapters from data-plane config plus canonical vault refs."""

    S3_IDS = frozenset({"s3", "cloudflare_r2", "backblaze_b2"})
    POSTGRES_IDS = frozenset({"postgres", "supabase", "neon", "aws_rds"})

    def __init__(self, manager, vault, *, client_factory=None):
        self.manager = manager
        self.credentials = VaultCredentialResolver(vault)
        self.client_factory = client_factory

    def _client(self):
        return self.client_factory() if self.client_factory else None

    def build(self, provider_id: str) -> ProviderObjectAdapter:
        provider_id = str(provider_id)
        status = self.manager.provider_status(provider_id)
        if not status.get("available"):
            raise PermissionError("online storage provider is not connected, enabled, and verified")
        credential_ref = status.get("credential_ref")
        if str(credential_ref or "").startswith("integration:"):
            raise ProviderAdapterError("canonical integration-backed providers must use their existing governed adapter")
        credentials = self.credentials.resolve(credential_ref)
        common = {
            "provider_id": provider_id,
            "config": status.get("config") or {},
            "credentials": credentials,
        }
        client = self._client()
        if client is not None:
            common["client"] = client
        if provider_id == "dropbox":
            return DropboxAdapter(**common)
        if provider_id == "onedrive":
            return OneDriveAdapter(**common)
        if provider_id in self.S3_IDS:
            return S3CompatibleAdapter(**common)
        if provider_id in self.POSTGRES_IDS:
            return PostgreSQLObjectAdapter(**common)
        raise ProviderAdapterError(f"no direct data-plane object adapter is implemented for {provider_id}")


class EncryptedProviderStore:
    """Store provider payloads only as authenticated encrypted Vishnu envelopes."""

    FORMAT = "vishnu-encrypted-provider-object-v1"

    def __init__(self, manager, envelopes, factory: ProviderAdapterFactory):
        self.manager = manager
        self.envelopes = envelopes
        self.factory = factory

    @staticmethod
    def object_key(global_id: str, version: int) -> str:
        opaque = hashlib.sha256(str(global_id).encode("utf-8")).hexdigest()
        return f"v1/{opaque[:2]}/{opaque}/{int(version)}.vishnu"

    def _assert_upload_policy(self, item: Mapping[str, Any]) -> None:
        policy = StoragePolicy(str(item["storage_policy"]))
        if policy in {StoragePolicy.DEVICE_ONLY, StoragePolicy.PROGRESS_ONLY}:
            raise PermissionError(f"{policy.value} data cannot be uploaded to provider object storage")
        if not bool(item.get("copy_allowed")):
            raise PermissionError("durable provider copy requires explicit copy authority")

    def put(
        self,
        provider_id: str,
        global_id: str,
        plaintext: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> dict[str, Any]:
        item = self.manager.item(global_id)
        if item.get("tombstone"):
            raise KeyError("data item is deleted")
        self._assert_upload_policy(item)
        adapter = self.factory.build(provider_id)
        version = int(item["version"])
        envelope = self.envelopes.encrypt_bytes(global_id, version, self._bounded_plaintext(plaintext), content_type=content_type)
        package = {"format": self.FORMAT, "envelope": envelope}
        encoded = _json(package).encode("utf-8")
        key = self.object_key(global_id, version)
        info = adapter.put(key, encoded, content_type="application/vnd.vishnu.encrypted+json")
        # A durable location is recorded only after provider write success.
        self.manager.mark_location(
            global_id,
            location_type="provider",
            location_id=f"{provider_id}:{key}",
            provider_id=provider_id,
            has_bytes=True,
            available=True,
        )
        return {
            "provider_id": provider_id,
            "global_id": str(global_id),
            "object_version": version,
            "object_key": key,
            "ciphertext_only": True,
            "plaintext_size": int(envelope["plaintext_size"]),
            "provider_size": info.size,
            "content_digest": envelope["content_digest"],
        }

    @staticmethod
    def _bounded_plaintext(payload: bytes) -> bytes:
        data = bytes(payload)
        if len(data) > MAX_PROVIDER_OBJECT_BYTES:
            raise ValueError("provider plaintext exceeds bounded data-plane limit")
        return data

    def get(self, provider_id: str, global_id: str, *, version: int | None = None) -> bytes:
        item = self.manager.item(global_id)
        target_version = int(version or item["version"])
        adapter = self.factory.build(provider_id)
        key = self.object_key(global_id, target_version)
        raw = adapter.get(key)
        try:
            package = json.loads(raw)
        except Exception as exc:
            raise ProviderAdapterError("provider object is not a Vishnu encrypted package") from exc
        if package.get("format") != self.FORMAT or not isinstance(package.get("envelope"), dict):
            raise ProviderAdapterError("provider object format is unsupported")
        envelope = package["envelope"]
        if str(envelope.get("global_id")) != str(global_id) or int(envelope.get("object_version") or 0) != target_version:
            raise ProviderAdapterError("provider encrypted package identity mismatch")
        return self.envelopes.decrypt_bytes(envelope)

    def delete(self, provider_id: str, global_id: str, *, version: int | None = None) -> bool:
        item = self.manager.item(global_id)
        target_version = int(version or item["version"])
        key = self.object_key(global_id, target_version)
        adapter = self.factory.build(provider_id)
        deleted = adapter.delete(key)
        if deleted:
            location_id = f"{provider_id}:{key}"
            with self.manager._con() as con:
                con.execute(
                    "DELETE FROM data_plane_locations WHERE global_id=? AND location_type='provider' AND location_id=?",
                    (str(global_id), location_id),
                )
        return deleted

    def verify_provider(self, provider_id: str) -> dict[str, Any]:
        return self.factory.build(provider_id).verify()
