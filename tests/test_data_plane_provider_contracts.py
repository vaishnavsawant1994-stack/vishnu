from __future__ import annotations

import json

import pytest

from data_plane.enforced import PolicyEnforcedDataPlane
from data_plane.provider_adapters import (
    DropboxAdapter,
    OneDriveAdapter,
    PostgreSQLObjectAdapter,
    ProviderAdapterError,
    ProviderAdapterFactory,
    S3CompatibleAdapter,
)


class Vault:
    def __init__(self):
        self.values = {}

    def get(self, name, default=None):
        return self.values.get(name, default)

    def set(self, name, value):
        self.values[name] = value


class Response:
    def __init__(self, status_code=200, body=None, *, headers=None, content=b''):
        self.status_code = status_code
        self._body = body or {}
        self.headers = headers or {}
        self.content = content

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f'HTTP {self.status_code}')


class DropboxClient:
    def __init__(self):
        self.calls = []
        self.payload = b''

    def post(self, url, *, headers=None, content=None, json=None):
        self.calls.append((url, headers or {}, content, json))
        if url.endswith('/users/get_current_account'):
            return Response(body={'account_id': 'dbid:owner'})
        if url.endswith('/files/upload'):
            self.payload = bytes(content or b'')
            return Response(body={'size': len(self.payload), 'content_hash': 'hash'})
        if url.endswith('/files/download'):
            return Response(content=self.payload)
        if url.endswith('/files/get_metadata'):
            return Response(body={'size': len(self.payload), 'content_hash': 'hash'})
        if url.endswith('/files/delete_v2'):
            self.payload = b''
            return Response(body={'.tag': 'file'})
        raise AssertionError(url)


class OneDriveRedirectClient:
    def __init__(self, location):
        self.location = location
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(('GET', url, kwargs))
        if url.startswith('https://graph.microsoft.com/'):
            return Response(status_code=302, headers={'location': self.location})
        raise AssertionError('unsafe redirect must be rejected before a second request')


@pytest.fixture
def manager(tmp_path):
    value = PolicyEnforcedDataPlane(tmp_path / 'providers.sqlite3')
    value.update_settings(cloud_enabled=True, cloud_mode='own_cloud')
    return value


def test_dropbox_contract_round_trip_uses_bearer_only_in_request_headers():
    client = DropboxClient()
    adapter = DropboxAdapter(
        provider_id='dropbox',
        config={'root': '/Apps/Vishnu'},
        credentials={'access_token': 'dropbox-secret'},
        client=client,
    )
    assert adapter.verify()['account_id'] == 'dbid:owner'
    info = adapter.put('v1/aa/object.vishnu', b'ciphertext-package')
    assert info.size == len(b'ciphertext-package')
    assert adapter.get('v1/aa/object.vishnu') == b'ciphertext-package'
    assert adapter.head('v1/aa/object.vishnu').etag == 'hash'
    assert adapter.delete('v1/aa/object.vishnu') is True
    request_dump = json.dumps([(url, headers) for url, headers, _content, _json in client.calls])
    assert 'dropbox-secret' in request_dump
    assert all('dropbox-secret' not in str(body) for _url, _headers, body, _json in client.calls if body)


def test_onedrive_rejects_plain_http_preauthenticated_download_redirect():
    client = OneDriveRedirectClient('http://cdn.example.test/private-download')
    adapter = OneDriveAdapter(
        provider_id='onedrive',
        config={'root': 'Vishnu'},
        credentials={'access_token': 'onedrive-secret'},
        client=client,
    )
    with pytest.raises(ProviderAdapterError, match='credential-free HTTPS'):
        adapter.get('v1/aa/object.vishnu')
    assert len(client.calls) == 1


def test_onedrive_rejects_credential_bearing_https_redirect():
    client = OneDriveRedirectClient('https://user:password@cdn.example.test/private-download')
    adapter = OneDriveAdapter(
        provider_id='onedrive',
        config={},
        credentials={'access_token': 'onedrive-secret'},
        client=client,
    )
    with pytest.raises(ProviderAdapterError, match='credential-free HTTPS'):
        adapter.get('v1/aa/object.vishnu')
    assert len(client.calls) == 1


@pytest.mark.parametrize('provider_id', ['s3', 'cloudflare_r2', 'backblaze_b2'])
def test_factory_builds_all_requested_s3_family_adapters(manager, provider_id):
    vault = Vault()
    ref = f'provider:{provider_id}'
    vault.set(ref, json.dumps({'access_key_id': 'ACCESS', 'secret_access_key': 'SECRET'}))
    config = {'bucket': 'owner-vishnu', 'region': 'eu-central-1'}
    if provider_id != 's3':
        config['endpoint'] = f'https://{provider_id}.example.test'
    manager.configure_provider(provider_id, enabled=True, credential_ref=ref, config=config, verified=True)
    adapter = ProviderAdapterFactory(manager, vault).build(provider_id)
    assert isinstance(adapter, S3CompatibleAdapter)
    assert adapter.provider_id == provider_id


@pytest.mark.parametrize('provider_id', ['postgres', 'supabase', 'neon', 'aws_rds'])
def test_factory_builds_all_requested_postgres_family_adapters(manager, provider_id):
    vault = Vault()
    ref = f'provider:{provider_id}'
    vault.set(ref, json.dumps({'dsn': 'postgresql://owner:secret@db.example.test/vishnu'}))
    manager.configure_provider(
        provider_id,
        enabled=True,
        credential_ref=ref,
        config={'table': 'vishnu_encrypted_objects'},
        verified=True,
    )
    adapter = ProviderAdapterFactory(manager, vault).build(provider_id)
    assert isinstance(adapter, PostgreSQLObjectAdapter)
    assert adapter.provider_id == provider_id
    status = manager.provider_status(provider_id)
    assert status['credential_ref'] == ref
    assert 'owner:secret' not in json.dumps(status)


def test_postgres_adapter_rejects_untrusted_table_identifier_before_connecting():
    with pytest.raises(ProviderAdapterError, match='table'):
        PostgreSQLObjectAdapter(
            provider_id='postgres',
            config={'table': 'objects; DROP TABLE audit'},
            credentials={'dsn': 'postgresql://owner:secret@db.example.test/vishnu'},
        )


def test_postgres_adapter_rejects_non_postgres_secret_value():
    adapter = PostgreSQLObjectAdapter(
        provider_id='postgres',
        config={},
        credentials={'dsn': 'https://db.example.test/not-a-postgres-dsn'},
    )
    with pytest.raises(ProviderAdapterError, match='postgres/postgresql'):
        adapter._dsn()
