from __future__ import annotations

from enum import Enum
from typing import Any, Mapping


class StoragePolicy(str, Enum):
    """Where an item's durable bytes are allowed to live."""

    DEVICE_ONLY = 'device_only'
    SYNC_EVERYWHERE = 'sync_everywhere'
    PROGRESS_ONLY = 'progress_only'
    ON_DEMAND = 'on_demand'


class CloudMode(str, Enum):
    LOCAL_ONLY = 'local_only'
    OWN_CLOUD = 'own_cloud'
    VISHNU_CLOUD = 'vishnu_cloud'
    HYBRID = 'hybrid'


class BackupMode(str, Enum):
    OFF = 'off'
    ENCRYPTED = 'encrypted'


# Progress-only replication is deliberately narrow. Raw file content, prompts,
# credentials and arbitrary metadata never become progress by accident.
PROGRESS_FIELDS = frozenset({
    'project_id',
    'project_name',
    'status',
    'progress',
    'task_id',
    'task_title',
    'task_status',
    'milestone_id',
    'milestone_title',
    'milestone_status',
    'last_step',
    'next_step',
    'last_activity',
    'allowed_notes',
    'updated_at',
})

SECRET_KEYS = frozenset({
    'password', 'passwd', 'passphrase', 'secret', 'token', 'access_token',
    'refresh_token', 'api_key', 'apikey', 'authorization', 'cookie',
    'credential', 'private_key', 'session_token', 'bearer_token',
})

RAW_CONTENT_KEYS = frozenset({
    'bytes', 'content_bytes', 'raw', 'raw_bytes', 'raw_content', 'file_bytes',
    'image_bytes', 'audio_bytes', 'video_bytes', 'document_content',
})


def _key(value: Any) -> str:
    return str(value).strip().lower().replace('-', '_').replace(' ', '_')


def contains_secret_or_raw_content(value: Any, *, depth: int = 0) -> bool:
    if depth > 8:
        return True
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = _key(raw_key)
            if (
                key in SECRET_KEYS
                or key in RAW_CONTENT_KEYS
                or key.endswith('_password')
                or key.endswith('_secret')
                or key.endswith('_token')
                or key.endswith('_credential')
            ):
                return True
            if contains_secret_or_raw_content(child, depth=depth + 1):
                return True
        return False
    if isinstance(value, (list, tuple)):
        return any(contains_secret_or_raw_content(item, depth=depth + 1) for item in value)
    return False


def progress_projection(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = dict(payload or {})
    if contains_secret_or_raw_content(payload):
        raise ValueError('progress payload contains secret-bearing or raw-content fields')
    return {key: payload[key] for key in PROGRESS_FIELDS if key in payload}
