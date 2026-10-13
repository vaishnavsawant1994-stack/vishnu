from __future__ import annotations

import datetime as _dt
import hashlib
import hmac
import json
import urllib.parse
from dataclasses import dataclass
from typing import Any, Mapping

import httpx


class ProviderUnavailable(RuntimeError):
    pass


def _safe_key(value: str) -> str:
    raw = str(value).strip().replace('\\', '/').lstrip('/')
    if not raw or '..' in raw.split('/'):
        raise ValueError('invalid provider object key')
    return raw


class VaultCredentialResolver:
    def __init__(self, vault, connector_resolver=None):
        self.vault = vault
        self.connector_resolver = connector_resolver

    def resolve(self, reference: str | None):
        ref = str(reference or '').strip()
        if ref.startswith('vault:'):
            if self.vault is None:
                raise ProviderUnavailable('canonical vault is unavailable')
            value = self.vault.get(ref[6:])
            if value is None:
                raise ProviderUnavailable('vault credential reference is unavailable')
            return value
        if ref.startswith('connector:'):
            if self.connector_resolver is None:
                raise ProviderUnavailable('connector credential resolver is unavailable')
            value = self.connector_resolver(ref)
            if not value:
                raise ProviderUnavailable('connector credential reference is unavailable')
            return value
        raise ProviderUnavailable('provider credential must be a vault or connector reference')


class DropboxAdapter:
    API = 'https://api.dropboxapi.com/2'
    CONTENT = 'https://content.dropboxapi.com/2'

    def __init__(self, token: str, *, root: str = '/Vishnu', client=None):
        self.token = token
        self.root = '/' + root.strip('/')
        self.client = client or httpx.Client(timeout=30, follow_redirects=False)

    def _headers(self): return {'Authorization': f'Bearer {self.token}'}
    def _path(self, key): return f'{self.root}/{_safe_key(key)}'

    def verify(self):
        response = self.client.post(f'{self.API}/users/get_current_account', headers=self._headers())
        response.raise_for_status()
        return {'provider': 'dropbox', 'account_id': response.json().get('account_id')}

    def put(self, key: str, payload: bytes):
        arg = json.dumps({'path': self._path(key), 'mode': 'overwrite', 'autorename': False, 'mute': True})
        response = self.client.post(f'{self.CONTENT}/files/upload', headers={**self._headers(), 'Dropbox-API-Arg': arg, 'Content-Type': 'application/octet-stream'}, content=bytes(payload))
        response.raise_for_status()
        return {'object_id': response.json().get('id') or self._path(key)}

    def get(self, key: str) -> bytes:
        response = self.client.post(f'{self.CONTENT}/files/download', headers={**self._headers(), 'Dropbox-API-Arg': json.dumps({'path': self._path(key)})})
        response.raise_for_status()
        return bytes(response.content)

    def delete(self, key: str):
        response = self.client.post(f'{self.API}/files/delete_v2', headers={**self._headers(), 'Content-Type': 'application/json'}, json={'path': self._path(key)})
        response.raise_for_status()
        return {'deleted': True, 'reference': response.json().get('metadata', {}).get('id') or self._path(key)}


class OneDriveAdapter:
    GRAPH = 'https://graph.microsoft.com/v1.0'

    def __init__(self, token: str, *, root: str = 'Vishnu', client=None):
        self.token = token
        self.root = root.strip('/')
        self.client = client or httpx.Client(timeout=30, follow_redirects=False)

    def _headers(self): return {'Authorization': f'Bearer {self.token}'}
    def _url(self, key):
        path = urllib.parse.quote(f'{self.root}/{_safe_key(key)}', safe='/')
        return f'{self.GRAPH}/me/drive/root:/{path}:/content'

    def verify(self):
        response = self.client.get(f'{self.GRAPH}/me/drive', headers=self._headers())
        response.raise_for_status()
        return {'provider': 'onedrive', 'drive_id': response.json().get('id')}

    def put(self, key: str, payload: bytes):
        response = self.client.put(self._url(key), headers={**self._headers(), 'Content-Type': 'application/octet-stream'}, content=bytes(payload))
        response.raise_for_status()
        return {'object_id': response.json().get('id') or _safe_key(key)}

    def get(self, key: str) -> bytes:
        response = self.client.get(self._url(key), headers=self._headers())
        response.raise_for_status()
        return bytes(response.content)

    def delete(self, key: str):
        response = self.client.delete(self._url(key).removesuffix('/content'), headers=self._headers())
        if response.status_code not in (200, 202, 204): response.raise_for_status()
        return {'deleted': True, 'reference': _safe_key(key)}


class S3Adapter:
    """Minimal SigV4 adapter shared by AWS S3, Cloudflare R2 and B2 S3."""
    def __init__(self, credentials: Mapping[str, Any], config: Mapping[str, Any], *, client=None):
        self.access_key = str(credentials['access_key'])
        self.secret_key = str(credentials['secret_key'])
        self.session_token = str(credentials.get('session_token') or '')
        self.region = str(config.get('region') or credentials.get('region') or 'us-east-1')
        self.bucket = str(config['bucket'])
        self.endpoint = str(config.get('endpoint') or f'https://s3.{self.region}.amazonaws.com').rstrip('/')
        self.prefix = str(config.get('prefix') or 'vishnu').strip('/')
        self.client = client or httpx.Client(timeout=30, follow_redirects=False)

    def _object_path(self, key):
        object_key = f'{self.prefix}/{_safe_key(key)}' if self.prefix else _safe_key(key)
        return f"/{urllib.parse.quote(self.bucket, safe='')}/{urllib.parse.quote(object_key, safe='/~')}"

    def _signed_headers(self, method: str, path: str, payload: bytes, *, now=None):
        now = now or _dt.datetime.now(_dt.timezone.utc)
        amz_date, date = now.strftime('%Y%m%dT%H%M%SZ'), now.strftime('%Y%m%d')
        host = urllib.parse.urlparse(self.endpoint).netloc
        payload_hash = hashlib.sha256(payload).hexdigest()
        canonical_headers = f'host:{host}\nx-amz-content-sha256:{payload_hash}\nx-amz-date:{amz_date}\n'
        signed_headers = 'host;x-amz-content-sha256;x-amz-date'
        canonical_request = '\n'.join([method, path, '', canonical_headers, signed_headers, payload_hash])
        scope = f'{date}/{self.region}/s3/aws4_request'
        string_to_sign = '\n'.join(['AWS4-HMAC-SHA256', amz_date, scope, hashlib.sha256(canonical_request.encode()).hexdigest()])
        def sign(key, msg): return hmac.new(key, msg.encode(), hashlib.sha256).digest()
        k_date = sign(('AWS4' + self.secret_key).encode(), date)
        k_region, k_service = sign(k_date, self.region), None
        k_service = sign(k_region, 's3')
        k_signing = sign(k_service, 'aws4_request')
        signature = hmac.new(k_signing, string_to_sign.encode(), hashlib.sha256).hexdigest()
        headers = {'Host': host, 'x-amz-content-sha256': payload_hash, 'x-amz-date': amz_date, 'Authorization': f'AWS4-HMAC-SHA256 Credential={self.access_key}/{scope}, SignedHeaders={signed_headers}, Signature={signature}'}
        if self.session_token: headers['x-amz-security-token'] = self.session_token
        return headers

    def _request(self, method, key, payload=b''):
        path = self._object_path(key)
        response = self.client.request(method, self.endpoint + path, headers=self._signed_headers(method, path, payload), content=payload)
        response.raise_for_status()
        return response

    def verify(self):
        probe = f".vishnu-verify/{hashlib.sha256(self.access_key.encode()).hexdigest()[:12]}"
        self.put(probe, b'vishnu'); self.delete(probe)
        return {'provider': 's3', 'bucket': self.bucket, 'endpoint': self.endpoint}
    def put(self, key: str, payload: bytes):
        response = self._request('PUT', key, bytes(payload)); return {'object_id': _safe_key(key), 'etag': response.headers.get('etag')}
    def get(self, key: str) -> bytes: return bytes(self._request('GET', key).content)
    def delete(self, key: str): self._request('DELETE', key); return {'deleted': True, 'reference': _safe_key(key)}


class PostgresAdapter:
    def __init__(self, dsn: str, config: Mapping[str, Any]):
        self.dsn = dsn
        table = str(config.get('table') or 'vishnu_encrypted_objects')
        if not table.replace('_', '').isalnum(): raise ValueError('invalid PostgreSQL object table')
        self.table = table
    def _connect(self):
        try: import psycopg
        except Exception as exc: raise ProviderUnavailable('psycopg is required for PostgreSQL storage adapters') from exc
        return psycopg.connect(self.dsn, connect_timeout=10)
    def _ensure(self, con): con.execute(f'CREATE TABLE IF NOT EXISTS {self.table}(object_key TEXT PRIMARY KEY,payload BYTEA NOT NULL,updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())')
    def verify(self):
        with self._connect() as con: con.execute('SELECT 1').fetchone(); self._ensure(con)
        return {'provider': 'postgres', 'table': self.table}
    def put(self, key: str, payload: bytes):
        key = _safe_key(key)
        with self._connect() as con:
            self._ensure(con); con.execute(f'INSERT INTO {self.table}(object_key,payload,updated_at) VALUES(%s,%s,NOW()) ON CONFLICT(object_key) DO UPDATE SET payload=excluded.payload,updated_at=NOW()', (key, bytes(payload)))
        return {'object_id': key}
    def get(self, key: str) -> bytes:
        key = _safe_key(key)
        with self._connect() as con: self._ensure(con); row = con.execute(f'SELECT payload FROM {self.table} WHERE object_key=%s', (key,)).fetchone()
        if row is None: raise KeyError('provider object not found')
        return bytes(row[0])
    def delete(self, key: str):
        key = _safe_key(key)
        with self._connect() as con: self._ensure(con); con.execute(f'DELETE FROM {self.table} WHERE object_key=%s', (key,))
        return {'deleted': True, 'reference': key}


@dataclass
class AdapterContext:
    provider_id: str
    credential_ref: str | None
    config: dict[str, Any]


class StorageAdapterManager:
    S3_PROVIDERS = {'s3', 'cloudflare_r2', 'backblaze_b2'}
    POSTGRES_PROVIDERS = {'postgres', 'supabase', 'neon', 'aws_rds'}
    def __init__(self, data_plane, vault, *, connector_resolver=None, client_factory=None):
        self.data_plane = data_plane
        self.credentials = VaultCredentialResolver(vault, connector_resolver)
        self.client_factory = client_factory or (lambda: httpx.Client(timeout=30, follow_redirects=False))
    @staticmethod
    def _decode_json_secret(raw):
        if isinstance(raw, Mapping): return dict(raw)
        try: value = json.loads(str(raw))
        except Exception as exc: raise ProviderUnavailable('provider vault credential must be valid JSON') from exc
        if not isinstance(value, dict): raise ProviderUnavailable('provider vault credential must be a JSON object')
        return value
    def context(self, provider_id: str) -> AdapterContext:
        status = self.data_plane.provider_status(provider_id)
        if not status['configured'] or not status['configured_enabled']: raise ProviderUnavailable('provider is not enabled in Vishnu data policy')
        return AdapterContext(provider_id, status.get('credential_ref'), dict(status.get('config') or {}))
    def adapter(self, provider_id: str):
        ctx = self.context(provider_id); raw = self.credentials.resolve(ctx.credential_ref)
        if provider_id == 'dropbox':
            secret = self._decode_json_secret(raw); return DropboxAdapter(str(secret['access_token']), root=str(ctx.config.get('root') or '/Vishnu'), client=self.client_factory())
        if provider_id == 'onedrive':
            secret = self._decode_json_secret(raw); return OneDriveAdapter(str(secret['access_token']), root=str(ctx.config.get('root') or 'Vishnu'), client=self.client_factory())
        if provider_id in self.S3_PROVIDERS: return S3Adapter(self._decode_json_secret(raw), ctx.config, client=self.client_factory())
        if provider_id in self.POSTGRES_PROVIDERS:
            secret = self._decode_json_secret(raw); return PostgresAdapter(str(secret['dsn']), ctx.config)
        raise ProviderUnavailable(f'no governed storage adapter is available for {provider_id}')
    def verify(self, provider_id: str):
        ctx = self.context(provider_id); result = self.adapter(provider_id).verify()
        status = self.data_plane.configure_provider(provider_id, enabled=True, credential_ref=ctx.credential_ref, config=ctx.config, verified=True)
        return {'verification': result, 'status': status}


class EncryptedProviderService:
    def __init__(self, data_plane, envelopes, adapters: StorageAdapterManager): self.data_plane, self.envelopes, self.adapters = data_plane, envelopes, adapters
    @staticmethod
    def _object_key(global_id: str, version: int): return f"objects/{hashlib.sha256(str(global_id).encode()).hexdigest()}/v{int(version)}.json"
    def put_plaintext(self, global_id: str, version: int, plaintext: bytes, provider_id: str, *, content_type='application/octet-stream'):
        item = self.data_plane.item(global_id)
        if item['storage_policy'] in {'device_only', 'progress_only'}: raise PermissionError('storage policy does not allow durable provider replication')
        if not self.data_plane.provider_status(provider_id)['available']: raise ProviderUnavailable('provider is not verified and available')
        package = self.envelopes.encrypt_bytes(global_id, version, plaintext, content_type=content_type)
        payload = json.dumps(package, sort_keys=True, separators=(',', ':')).encode(); key = self._object_key(global_id, version)
        result = self.adapters.adapter(provider_id).put(key, payload)
        self.data_plane.mark_location(global_id, location_type='provider', location_id=key, provider_id=provider_id, has_bytes=True, available=True)
        return {'provider_id': provider_id, 'object_key': key, 'provider_result': result, 'content_digest': package['content_digest']}
    def get_plaintext(self, global_id: str, version: int, provider_id: str) -> bytes:
        key = self._object_key(global_id, version); payload = self.adapters.adapter(provider_id).get(key); package = json.loads(payload.decode())
        if str(package.get('global_id')) != str(global_id) or int(package.get('object_version') or 0) != int(version): raise ValueError('provider object identity mismatch')
        return self.envelopes.decrypt_bytes(package)
    def delete_copy(self, global_id: str, version: int, provider_id: str):
        key = self._object_key(global_id, version); removal = self.data_plane.begin_copy_removal(global_id, location_type='provider', location_id=key)
        result = self.adapters.adapter(provider_id).delete(key); verified = self.data_plane.confirm_copy_removal(removal['removal_id'], verification_ref=str(result.get('reference') or key))
        return {'provider_result': result, 'removal': verified}
