from __future__ import annotations

import base64
import binascii
import json
import os
import re
import shutil
import threading
import time
import uuid
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Cookie, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.background import BackgroundTask

from security.request_context import current_trusted_request
from server.owner_product_schemas import (
    MemoryCreateBody,
    MemoryUpdateBody,
    RetentionBody,
    MemoryPreferencesBody,
    KnowledgeAvailabilityBody,
    KnowledgeCollectionBody,
    KnowledgeCollectionUpdateBody,
    KnowledgeUploadBody,
    KnowledgeUpdateBody,
    DevicePermissionsBody,
    ConfirmBody,
    DeleteAccountBody,
    QualificationSessionBody,
    QualificationTrialBody,
    QualificationFinishBody,
    WorkflowCreateBody,
    WorkflowPauseBody,
    WorkflowRunBody,
    EmergencyStopBody,
    OwnerPermissionsBody,
    OwnerDefaultProviderBody,
    OwnerProviderConnectBody,
    OwnerProviderTestBody,
    OwnerProviderModelBody,
    UiPreferencesBody,
    ProfileAvatarBody,
    ProfileUpdateBody,
    NotificationEventPreference,
    NotificationQuietHours,
    NotificationSummaryPreference,
    WeeklySummaryPreference,
    NotificationPreferencesBody,
)
from server.owner_product_knowledge import create_owner_knowledge_router
from server.owner_product_memory import create_owner_memory_router

__all__ = [
    'MemoryCreateBody', 'MemoryUpdateBody', 'RetentionBody', 'MemoryPreferencesBody',
    'KnowledgeAvailabilityBody', 'KnowledgeCollectionBody', 'KnowledgeCollectionUpdateBody',
    'KnowledgeUploadBody', 'KnowledgeUpdateBody', 'DevicePermissionsBody', 'ConfirmBody',
    'DeleteAccountBody', 'QualificationSessionBody', 'QualificationTrialBody',
    'QualificationFinishBody', 'WorkflowCreateBody', 'WorkflowPauseBody', 'WorkflowRunBody',
    'EmergencyStopBody', 'OwnerPermissionsBody', 'OwnerDefaultProviderBody',
    'OwnerProviderConnectBody', 'OwnerProviderTestBody', 'OwnerProviderModelBody',
    'UiPreferencesBody', 'ProfileAvatarBody', 'ProfileUpdateBody',
    'NotificationEventPreference', 'NotificationQuietHours', 'NotificationSummaryPreference',
    'WeeklySummaryPreference', 'NotificationPreferencesBody', 'owner_product_router',
    'stage_owner_data_deletion',
]


def stage_owner_data_deletion(data_dir: Path) -> Path:
    """Atomically detach this single-owner installation's complete data directory."""
    target = Path(data_dir)
    if target.is_symlink() or not target.exists() or not target.is_dir():
        raise ValueError('Owner data directory is unavailable')
    resolved = target.resolve(strict=True)
    if resolved.parent == resolved or resolved in {Path.home().resolve(), Path.cwd().resolve()}:
        raise ValueError('Refusing to delete an unsafe data directory')
    tombstone = resolved.with_name(f'.{resolved.name}.deleted-{uuid.uuid4().hex}')
    os.replace(resolved, tombstone)
    return tombstone



def _bounded_mapping(value, *, max_bytes=65536, max_depth=8, max_items=256, max_string=12000):
    if not isinstance(value, dict):
        raise HTTPException(422, 'Expected a JSON object')
    nodes = 0
    stack = [(value, 0)]
    while stack:
        current, depth = stack.pop()
        if depth > max_depth:
            raise HTTPException(413, 'JSON object nesting exceeds limit')
        if isinstance(current, dict):
            if len(current) > max_items:
                raise HTTPException(413, 'JSON object contains too many fields')
            for key, child in current.items():
                if len(str(key)) > 256:
                    raise HTTPException(413, 'JSON object key is too long')
                stack.append((child, depth + 1))
        elif isinstance(current, list):
            if len(current) > max_items:
                raise HTTPException(413, 'JSON collection contains too many items')
            for child in current:
                stack.append((child, depth + 1))
        elif isinstance(current, str) and len(current) > max_string:
            raise HTTPException(413, 'JSON string exceeds limit')
        nodes += 1
        if nodes > 4096:
            raise HTTPException(413, 'JSON object is too complex')
    try:
        encoded = json.dumps(value, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, 'JSON object contains unsupported values') from exc
    if len(encoded) > max_bytes:
        raise HTTPException(413, 'JSON object exceeds maximum size')
    return value


def owner_product_router(runtime):
    router = APIRouter(prefix='/iphone/api', tags=['owner-product'])
    registry = runtime['device_registry']
    memory = runtime['memory']
    knowledge = runtime['knowledge']
    backup_lock = runtime.setdefault('owner_backup_lock', threading.RLock())
    provider_attempt_lock = threading.Lock()
    provider_attempts: dict[str, tuple[float, int]] = {}

    def authenticate(device_id: str | None, token: str | None, scope: str):
        if not device_id or not token or not registry.authenticate(device_id, token):
            raise HTTPException(401, 'This browser is not trusted or its session was revoked')
        if hasattr(registry, 'authorize') and not registry.authorize(device_id, scope):
            raise HTTPException(403, f'This device is not permitted to use {scope}')
        return device_id

    def audit(action: str, *, device_id: str, **payload):
        memory.audit('owner-product', action, {'device_id': device_id, **payload})

    def limit_provider_attempts(device_id: str):
        now = time.monotonic()
        with provider_attempt_lock:
            for key, (started, _) in list(provider_attempts.items()):
                if now - started >= 60:
                    provider_attempts.pop(key, None)
            started, count = provider_attempts.get(device_id, (now, 0))
            if count >= 5:
                raise HTTPException(429, 'Too many provider connection attempts. Wait a minute and try again.')
            provider_attempts[device_id] = (started, count + 1)

    def backup_file(backup_id: str):
        service = runtime.get('backups')
        if service is None:
            raise HTTPException(503, 'Encrypted backup service is unavailable')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,159}\.paibackup', backup_id):
            raise HTTPException(404, 'Backup not found')
        candidate = service.backup_dir / backup_id
        if candidate.is_symlink():
            raise HTTPException(404, 'Backup not found')
        path = candidate.resolve()
        root = service.backup_dir.resolve()
        if root not in path.parents or path.is_symlink() or not path.is_file():
            raise HTTPException(404, 'Backup not found')
        return service, path

    def require_fresh_reauthentication():
        context = current_trusted_request()
        ttl = int(getattr(runtime.get('agent_executor'), 'reauth_ttl_seconds', 300) or 300)
        ttl = max(30, min(ttl, 900))
        stamp = getattr(context, 'reauthenticated_at', None) if context is not None else None
        try:
            age = time.time() - float(stamp)
        except (TypeError, ValueError):
            age = ttl + 1
        if context is None or age < 0 or age > ttl:
            raise HTTPException(401, {
                'code': 'reauthentication_required',
                'message': 'Fresh owner verification is required for this security-sensitive action.',
            })
        return context

    def workflow_authority(device_id: str):
        context = current_trusted_request()
        if context is not None and context.device_id != device_id:
            raise HTTPException(403, 'Authenticated browser session does not match this device')
        return {
            'owner_id': 'owner',
            'device_id': device_id,
            'session_id': context.session_id if context is not None else None,
            'reauthenticated_at': context.reauthenticated_at if context is not None else None,
        }

    def workflow_binding_matches(engine, run_id: str, auth: dict) -> bool:
        reader = getattr(engine, 'run_binding', None)
        if not callable(reader):
            return False
        binding = reader(run_id)
        if not binding:
            return False
        return (
            binding.get('owner_id') in (None, auth['owner_id'])
            and binding.get('device_id') in (None, auth['device_id'])
            and binding.get('session_id') in (None, auth['session_id'])
        )

    def knowledge_access(device_id: str):
        classes = {'owner', 'trusted-devices'}
        if not hasattr(registry, 'authorize') or registry.authorize(device_id, 'knowledge:private'):
            classes.add('private')
        return classes

    def ui_preferences(device_id: str):
        defaults = UiPreferencesBody().model_dump()
        try:
            stored = json.loads(registry.metadata(device_id).get('ui.preferences', '{}'))
        except (TypeError, ValueError, json.JSONDecodeError):
            stored = {}
        app_preferences = runtime.get('preferences')
        if app_preferences is not None:
            stored = {**stored, 'privacy_memory_enabled': bool(app_preferences.get('memory_enabled', True)), 'profile_display_name': str(app_preferences.get('preferred_name', '') or '')}
        try:
            return UiPreferencesBody(**{**defaults, **stored}).model_dump()
        except (TypeError, ValueError):
            return defaults

    @router.get('/preferences')
    def preferences_get(pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, 'ai:chat')
        return ui_preferences(device_id)

    @router.put('/preferences')
    def preferences_update(
        body: UiPreferencesBody,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token, 'ai:chat')
        value = body.model_dump()
        if value['privacy_allow_project_context_general'] or value['chat_project_context_enabled'] or value['chat_new_context'] == 'project':
            raise HTTPException(422, 'Project context is not available for general chats in this installation')
        if not registry.set_metadata(device_id, 'ui.preferences', json.dumps(value, separators=(',', ':'))):
            raise HTTPException(404, 'Active device not found')
        app_preferences = runtime.get('preferences')
        if app_preferences is not None:
            app_preferences.set('memory_enabled', value['privacy_memory_enabled'])
            app_preferences.set('preferred_name', value['profile_display_name'].strip())
        audit('device.preferences.updated', device_id=device_id)
        return value

    @router.get('/notifications/preferences')
    def notification_preferences_get(pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, 'ai:chat')
        service = runtime.get('notifications')
        if service is None:
            raise HTTPException(503, 'Notification preferences are unavailable')
        return {'preferences': service.preferences(device_id), 'availability': service.status(device_id)}

    @router.put('/notifications/preferences')
    def notification_preferences_update(body: NotificationPreferencesBody, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, 'ai:chat')
        service = runtime.get('notifications')
        if service is None:
            raise HTTPException(503, 'Notification preferences are unavailable')
        value = body.model_dump()
        # Reject channels that cannot actually deliver in this installation.
        supported_events = set(service.status(device_id).get('supported_events', []))
        for category, rule in value['events'].items():
            if category not in supported_events and (rule['enabled'] or rule['channels']):
                raise HTTPException(422, f'{category.replace("_", " ").title()} events are not available in this installation')
        for rule in value['events'].values():
            if 'email' in rule['channels']:
                raise HTTPException(422, 'Email delivery is not configured on this installation')
        if not service.status(device_id)['push'] and any('push' in rule['channels'] for rule in value['events'].values()):
            raise HTTPException(422, 'Push delivery is not configured for this trusted device')
        try:
            saved = service.save_preferences(device_id, value)
        except KeyError as exc:
            raise HTTPException(404, 'Active device not found') from exc
        audit('notifications.preferences.updated', device_id=device_id)
        return {'preferences': saved, 'availability': service.status(device_id)}

    @router.get('/notifications/inbox')
    def notification_inbox(pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, 'ai:chat')
        service = runtime.get('notifications')
        if service is None:
            raise HTTPException(503, 'Notification inbox is unavailable')
        items = service.list(device_id)
        return {'notifications': items, 'unread_count': sum(1 for item in items if not item['read_at'])}

    @router.post('/notifications/inbox/{notification_id}/read')
    def notification_mark_read(notification_id: str, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, 'ai:chat')
        service = runtime.get('notifications')
        if service is None:
            raise HTTPException(503, 'Notification inbox is unavailable')
        if not service.mark_read(device_id, notification_id):
            raise HTTPException(404, 'Notification not found')
        return {'marked_read': True}

    def profile_avatar_path():
        preferences = runtime.get('preferences')
        if preferences is None:
            raise HTTPException(503, 'Profile storage is unavailable')
        directory = Path(preferences.path).parent / 'profile'
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            os.chmod(directory, 0o700)
        except OSError:
            pass
        return directory / 'owner-avatar'

    @router.get('/profile/metadata')
    def profile_metadata(pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, 'ai:chat')
        preferences = runtime.get('preferences')
        if preferences is None:
            raise HTTPException(503, 'Owner profile metadata is unavailable')
        account_id = str(preferences.get('owner_account_id', '') or '')
        if not account_id:
            raise HTTPException(503, 'Owner account identifier is unavailable')
        settings = runtime.get('settings')
        email = str(getattr(settings, 'owner_google_email', '') or '').strip()
        verified = bool(email and getattr(settings, 'google_signin_client_id', ''))
        avatar = profile_avatar_path()
        return {
            'display_name': str(preferences.get('preferred_name', '') or ''),
            'first_name': str(preferences.get('profile_first_name', '') or ''),
            'last_name': str(preferences.get('profile_last_name', '') or ''),
            'email': email if verified else '',
            'email_verified': verified,
            'account_created_at': preferences.get('owner_account_created_at'),
            'account_id_masked': '•••• ' + account_id[-4:],
            'avatar_available': any(avatar.parent.glob('owner-avatar.*')),
        }

    @router.put('/profile')
    def profile_update(body: ProfileUpdateBody, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, 'ai:chat')
        preferences = runtime.get('preferences')
        if preferences is None:
            raise HTTPException(503, 'Owner profile storage is unavailable')
        preferences.update(profile_first_name=body.first_name, profile_last_name=body.last_name, preferred_name=body.display_name)
        audit('profile.updated', device_id=device_id)
        return {'saved': True, 'first_name': body.first_name, 'last_name': body.last_name, 'display_name': body.display_name}

    @router.post('/profile/account-id/copy')
    def profile_account_id_copy(pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, 'ai:chat')
        preferences = runtime.get('preferences')
        account_id = str(preferences.get('owner_account_id', '') or '') if preferences else ''
        if not account_id:
            raise HTTPException(503, 'Owner account identifier is unavailable')
        audit('profile.account_id_copied', device_id=device_id)
        return {'account_id': account_id}

    @router.get('/profile/avatar')
    def profile_avatar(pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, 'ai:chat')
        base = profile_avatar_path()
        path = next((base.parent / f'owner-avatar{suffix}' for suffix in ('.png', '.jpeg', '.webp') if (base.parent / f'owner-avatar{suffix}').is_file()), None)
        if path is None:
            raise HTTPException(404, 'No profile photo has been uploaded')
        media_type = {'png': 'image/png', 'jpeg': 'image/jpeg', 'webp': 'image/webp'}.get(path.suffix.lstrip('.'), 'application/octet-stream')
        return Response(content=path.read_bytes(), media_type=media_type, headers={'Cache-Control': 'no-store, private'})

    @router.put('/profile/avatar')
    def profile_avatar_upload(body: ProfileAvatarBody, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, 'ai:chat')
        try:
            image = base64.b64decode(body.data_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise HTTPException(422, 'Profile image must be valid base64 data') from exc
        if len(image) > 2 * 1024 * 1024:
            raise HTTPException(413, 'Profile images must be 2 MB or smaller')
        signatures = {
            'image/png': image.startswith(b'\x89PNG\r\n\x1a\n'),
            'image/jpeg': image.startswith(b'\xff\xd8\xff'),
            'image/webp': len(image) >= 12 and image[:4] == b'RIFF' and image[8:12] == b'WEBP',
        }
        if not signatures.get(body.media_type, False):
            raise HTTPException(415, 'The selected file does not match a supported image type')
        try:
            from PIL import Image
            with Image.open(BytesIO(image)) as decoded:
                if decoded.format not in {'PNG', 'JPEG', 'WEBP'} or decoded.width < 1 or decoded.height < 1 or decoded.width * decoded.height > 16_000_000:
                    raise HTTPException(415, 'The selected image dimensions or format are not supported')
                decoded.verify()
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(415, 'The selected file is not a valid supported image') from exc
        base = profile_avatar_path()
        extension = {'image/png': '.png', 'image/jpeg': '.jpeg', 'image/webp': '.webp'}[body.media_type]
        path = base.with_suffix(extension)
        temp = path.with_suffix(path.suffix + '.tmp')
        temp.write_bytes(image)
        os.chmod(temp, 0o600)
        temp.replace(path)
        for old in base.parent.glob('owner-avatar.*'):
            if old != path and old.is_file():
                old.unlink(missing_ok=True)
        audit('profile.avatar_updated', device_id=device_id)
        return {'saved': True, 'avatar_available': True}

    @router.delete('/profile/avatar')
    def profile_avatar_delete(pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, 'ai:chat')
        base = profile_avatar_path()
        for path in base.parent.glob('owner-avatar.*'):
            if path.is_file():
                path.unlink(missing_ok=True)
        audit('profile.avatar_removed', device_id=device_id)
        return {'saved': True, 'avatar_available': False}

    @router.get('/privacy/export')
    def privacy_export(pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, 'memory:read')
        if hasattr(registry, 'authorize') and not registry.authorize(device_id, 'ai:chat'):
            raise HTTPException(403, 'This device cannot export conversation history')
        if hasattr(registry, 'authorize') and not registry.authorize(device_id, 'knowledge:read'):
            raise HTTPException(403, 'This device cannot export Knowledge data')
        if not can_read_sensitive_memory(device_id):
            raise HTTPException(403, 'This device cannot export sensitive memory')
        continuity = runtime.get('continuity')
        conversations = []
        if continuity:
            for conversation_id in continuity.all_thread_ids(include_closed=True):
                try:
                    conversations.append(continuity.export_thread(conversation_id))
                except KeyError:
                    continue
        export = {
            'format': 'vishnu-account-data-v1',
            'exported_at': time.time(),
            'preferences': ui_preferences(device_id),
            'memories': memory.export(include_sensitive=True),
            'knowledge': knowledge.export(access_classes=knowledge_access(device_id)),
            'conversations': conversations,
        }
        audit('privacy.exported', device_id=device_id, conversation_count=len(conversations))
        return export

    def can_read_sensitive_memory(device_id: str):
        return not hasattr(registry, 'authorize') or registry.authorize(device_id, 'memory:sensitive')

    def filter_memories(rows, device_id: str):
        if can_read_sensitive_memory(device_id):
            return rows
        return [row for row in rows if str(row.get('sensitivity', 'normal')) not in {'sensitive', 'secret'}]

    def filter_tree(rows, device_id: str):
        output = []
        for row in rows:
            children = filter_tree(row.get('children', []), device_id)
            if can_read_sensitive_memory(device_id) or str(row.get('sensitivity', 'normal')) not in {'sensitive', 'secret'}:
                output.append({**row, 'children': children})
            else:
                output.extend(children)
        return output

    router.routes.extend(create_owner_memory_router(
        runtime,
        authenticate=authenticate,
        audit=audit,
        can_read_sensitive_memory=can_read_sensitive_memory,
        filter_memories=filter_memories,
        filter_tree=filter_tree,
    ).routes)

    router.routes.extend(create_owner_knowledge_router(
        runtime,
        authenticate=authenticate,
        audit=audit,
        knowledge_access=knowledge_access,
        bounded_mapping=_bounded_mapping,
    ).routes)

    @router.get('/owner/backups')
    def owner_backups(
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token, 'activities:read')
        service = runtime.get('backups')
        if service is None:
            return {'available': False, 'can_create': False, 'backups': [], 'total_size_bytes': None}
        all_paths = [path for path in service.backup_dir.glob('*.paibackup') if not path.is_symlink() and path.is_file()]
        rows = []
        for path in sorted(all_paths, key=lambda item: item.stat().st_mtime, reverse=True)[:100]:
            if path.is_symlink() or not path.is_file():
                continue
            stat = path.stat()
            with path.open('rb') as handle:
                encrypted = handle.read(11) == b'PAIBACKUP2\n'
            rows.append({
                'id': path.name,
                'created_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(stat.st_mtime)),
                'size_bytes': stat.st_size,
                'status': 'stored_unverified',
                'encrypted': encrypted,
            })
        return {
            'available': True,
            'can_create': bool(registry.authorize(device_id, 'device:admin')) if hasattr(registry, 'authorize') else False,
            'backups': rows,
            'total_size_bytes': sum(path.stat().st_size for path in all_paths),
            'backup_count': len(all_paths),
            'storage': 'local encrypted backup directory',
            'schedule': None,
        }

    @router.post('/owner/backups')
    def owner_backup_create(
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token, 'device:admin')
        service = runtime.get('backups')
        if service is None:
            raise HTTPException(503, 'Encrypted backup service is unavailable')
        from recovery.backup import BackupError
        backup_id = f"owner-{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}-{uuid.uuid4().hex[:10]}.paibackup"
        try:
            with backup_lock:
                path = service.create(backup_id)
                metadata = service.inspect(path)
        except (BackupError, OSError) as exc:
            audit('backup.create.failed', device_id=device_id, backup_id=backup_id, error_type=type(exc).__name__)
            raise HTTPException(503, 'The encrypted backup could not be created or verified') from exc
        audit('backup.created', device_id=device_id, backup_id=path.name, size_bytes=path.stat().st_size, encrypted=bool(metadata.get('encrypted')))
        return {
            'ok': True,
            'backup': {
                'id': path.name,
                'created_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(path.stat().st_mtime)),
                'size_bytes': path.stat().st_size,
                'status': 'verified' if metadata.get('encrypted') else 'verified_legacy_unencrypted',
                'encrypted': bool(metadata.get('encrypted')),
                'file_count': len(metadata.get('files', [])),
            },
        }

    @router.post('/owner/backups/{backup_id}/verify')
    def owner_backup_verify(
        backup_id: str,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token, 'activities:read')
        service, path = backup_file(backup_id)
        from recovery.backup import BackupError
        try:
            with backup_lock:
                metadata = service.inspect(path)
        except (BackupError, OSError) as exc:
            audit('backup.verification.failed', device_id=device_id, backup_id=path.name, error_type=type(exc).__name__)
            return {'ok': False, 'status': 'verification_failed', 'message': 'Backup integrity verification failed'}
        audit('backup.verified', device_id=device_id, backup_id=path.name, encrypted=bool(metadata.get('encrypted')), file_count=len(metadata.get('files', [])))
        return {'ok': True, 'status': 'verified', 'encrypted': bool(metadata.get('encrypted')), 'file_count': len(metadata.get('files', [])), 'created_at': metadata.get('created_at')}

    @router.get('/owner/backups/{backup_id}/download')
    def owner_backup_download(
        backup_id: str,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token, 'activities:read')
        _, path = backup_file(backup_id)
        audit('backup.downloaded', device_id=device_id, backup_id=path.name)
        return FileResponse(path, media_type='application/octet-stream', filename=path.name, headers={'Cache-Control': 'no-store'})

    @router.get('/activities')
    def activities(
        category: str | None = None,
        limit: int = 200,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        authenticate(pa_device, pa_token, 'activities:read')
        bounded = max(1, min(limit, 500))
        rows = memory.audit_entries(category, bounded)
        project_store = runtime.get('project_store')
        if project_store is not None and (category is None or category in {'project', 'projects'}):
            for item in project_store.activity_feed(limit=bounded):
                payload = {
                    'project_id': item['project_id'],
                    'project_name': item['project_name'],
                    'target_type': item['target_type'],
                    'target_id': item.get('target_id'),
                }
                if item['target_type'] == 'task' and item.get('target_id'):
                    payload['task_id'] = item['target_id']
                rows.append({
                    'id': item['id'], 'category': 'project', 'action': item['action'],
                    'actor': item['actor'], 'created_at': item['created_at'],
                    'payload': payload, 'status': 'recorded',
                })
        rows.sort(key=lambda item: str(item.get('created_at') or ''), reverse=True)
        return {'activities': rows[:bounded]}

    @router.get('/devices')
    def devices(pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, 'device:read')
        return {'current_device_id': device_id, 'devices': registry.list()}

    @router.patch('/devices/{target_device_id}/permissions')
    def device_permissions(
        target_device_id: str,
        body: DevicePermissionsBody,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token, 'device:admin')
        require_fresh_reauthentication()
        try:
            result = registry.set_permissions(target_device_id, body.scopes)
            cancelled_turns = cancelled_workflows = 0
            granted_scopes = set(result.get('scopes') or ())
            if 'ai:chat' not in granted_scopes:
                executor = runtime.get('executor')
                cancel_device_turns = getattr(executor, 'cancel_device_turns', None)
                if callable(cancel_device_turns):
                    cancelled_turns = int(cancel_device_turns(target_device_id, reason='device_permission_revoked'))
            if 'workflow:write' not in granted_scopes:
                automations = runtime.get('automations')
                cancel_device_runs = getattr(automations, 'cancel_device_runs', None)
                if callable(cancel_device_runs):
                    cancelled_workflows = int(cancel_device_runs(target_device_id, reason='workflow_permission_revoked'))
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        audit('device.permissions.updated', device_id=device_id, target_device_id=target_device_id, scopes=result['scopes'], cancelled_turns=cancelled_turns, cancelled_workflows=cancelled_workflows)
        return {**result, 'cancelled_turns': cancelled_turns, 'cancelled_workflows': cancelled_workflows}

    @router.post('/devices/{target_device_id}/revoke')
    def device_revoke(
        target_device_id: str,
        body: ConfirmBody,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token, 'device:admin')
        require_fresh_reauthentication()
        if not registry.revoke(target_device_id):
            raise HTTPException(404, 'Device not found')
        revoked_sessions = {}
        for key in ('pwa_sessions', 'cloud_sessions'):
            store = runtime.get(key)
            revoke_device = getattr(store, 'revoke_device', None)
            if callable(revoke_device):
                revoked_sessions[key] = int(revoke_device(target_device_id))
        gateway = runtime.get('device_gateway')
        if gateway is not None:
            gateway.disconnect(target_device_id)
        executor = runtime.get('executor')
        cancel_device_turns = getattr(executor, 'cancel_device_turns', None)
        cancelled_turns = int(cancel_device_turns(target_device_id, reason='device_revoked')) if callable(cancel_device_turns) else 0
        automations = runtime.get('automations')
        cancel_device_runs = getattr(automations, 'cancel_device_runs', None)
        cancelled_workflows = int(cancel_device_runs(target_device_id, reason='device_revoked')) if callable(cancel_device_runs) else 0
        audit(
            'device.revoked',
            device_id=device_id,
            target_device_id=target_device_id,
            revoked_sessions=revoked_sessions,
            cancelled_turns=cancelled_turns,
            cancelled_workflows=cancelled_workflows,
        )
        return {
            'ok': True,
            'revoked_device_id': target_device_id,
            'current_device_revoked': target_device_id == device_id,
            'revoked_sessions': revoked_sessions,
            'cancelled_turns': cancelled_turns,
            'cancelled_workflows': cancelled_workflows,
        }

    @router.delete('/privacy/account')
    def delete_owner_account(body: DeleteAccountBody, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, 'ai:chat')
        require_fresh_reauthentication()
        settings = runtime.get('settings')
        data_dir = getattr(settings, 'data_dir', None) if settings is not None else None
        if data_dir is None:
            raise HTTPException(503, 'This installation cannot delete owner data')
        try:
            tombstone = stage_owner_data_deletion(Path(data_dir))
        except (OSError, ValueError) as exc:
            raise HTTPException(500, 'Owner data could not be safely deleted') from exc
        # Stop background writers after the atomic rename; any already-open DB
        # handles now point at detached files and the trusted-device database is
        # no longer reachable at its configured location.
        try:
            if runtime.get('notifications'):
                runtime['notifications'].close()
            if runtime.get('automations'):
                runtime['automations'].stop()
            if runtime.get('apns'):
                runtime['apns'].close()
        except Exception:
            pass
        return JSONResponse(
            {'deleted': True},
            background=BackgroundTask(shutil.rmtree, tombstone, ignore_errors=True),
            headers={'Cache-Control': 'no-store'},
        )

    @router.get('/workflows')
    def workflows(pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, 'workflow:read')
        engine = runtime['automations']
        auth = workflow_authority(device_id)
        runs = [
            row for row in engine.runs(limit=100)
            if workflow_binding_matches(engine, row.get('id'), auth)
        ]
        return {'workflows': engine.workflows(), 'runs': runs}

    @router.post('/workflows')
    def workflow_create(body: WorkflowCreateBody, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, 'workflow:write')
        try:
            trigger = _bounded_mapping(body.trigger)
            steps = [_bounded_mapping(step, max_bytes=32768) for step in body.steps]
            embedded_policy = trigger.pop('policy', None)
            workflow_id = runtime['automations'].create_workflow(
                body.title, trigger, steps,
                next_run_at=body.next_run_at, interval_seconds=body.interval_seconds,
                policy=_bounded_mapping(embedded_policy) if embedded_policy is not None else None,
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, str(exc)) from exc
        audit('workflow.created', device_id=device_id, workflow_id=workflow_id)
        return runtime['automations'].workflow(workflow_id)

    @router.put('/workflows/{workflow_id}')
    def workflow_update(workflow_id: str, body: WorkflowCreateBody, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, 'workflow:write')
        try:
            trigger = _bounded_mapping(body.trigger)
            steps = [_bounded_mapping(step, max_bytes=32768) for step in body.steps]
            result = runtime['automations'].update_workflow(
                workflow_id, title=body.title, trigger=trigger, steps=steps,
                next_run_at=body.next_run_at, interval_seconds=body.interval_seconds,
            )
        except KeyError as exc:
            raise HTTPException(404, 'Workflow not found') from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, str(exc)) from exc
        audit('workflow.updated', device_id=device_id, workflow_id=workflow_id)
        return result

    @router.post('/workflows/pause')
    def workflow_pause(body: WorkflowPauseBody, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, 'workflow:write')
        try:
            result = runtime['automations'].pause_workflow(body.workflow_id, body.paused)
        except KeyError as exc:
            raise HTTPException(404, 'Workflow not found') from exc
        audit('workflow.paused' if body.paused else 'workflow.resumed', device_id=device_id, workflow_id=body.workflow_id)
        return result

    @router.post('/workflows/{workflow_id}/run')
    def workflow_run(workflow_id: str, body: WorkflowRunBody, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, 'workflow:write')
        try:
            context = _bounded_mapping(body.context)
            run_id = runtime['automations'].run_workflow(
                workflow_id,
                context=context,
                background=True,
                idempotency_key=body.idempotency_key,
                **workflow_authority(device_id),
            )
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        except (KeyError, RuntimeError) as exc:
            raise HTTPException(409, str(exc)) from exc
        audit('workflow.started', device_id=device_id, workflow_id=workflow_id, run_id=run_id)
        return {'workflow_id': workflow_id, 'run_id': run_id, 'status': 'queued'}

    @router.post('/workflows/runs/{run_id}/cancel')
    def workflow_cancel(run_id: str, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, 'workflow:write')
        try:
            authority = workflow_authority(device_id)
            authority.pop('reauthenticated_at', None)
            result = runtime['automations'].cancel_run(run_id, **authority)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        audit('workflow.cancelled', device_id=device_id, run_id=run_id)
        return result

    @router.post('/workflows/runs/{run_id}/recovery/link')
    def workflow_recovery_link(run_id: str, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, 'workflow:approve')
        try:
            result = runtime['automations'].link_recovery(run_id, **workflow_authority(device_id))
        except KeyError as exc:
            raise HTTPException(404, 'Workflow run not found') from exc
        except (RuntimeError, PermissionError) as exc:
            raise HTTPException(409, str(exc)) from exc
        audit('workflow.recovery_linked', device_id=device_id, run_id=run_id, recovery_transaction_id=result['recovery_transaction_id'])
        return result

    @router.post('/workflows/runs/{run_id}/recovery/refresh')
    def workflow_recovery_refresh(run_id: str, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, 'workflow:approve')
        try:
            return runtime['automations'].refresh_recovery(run_id, **workflow_authority(device_id))
        except KeyError as exc:
            raise HTTPException(404, 'Workflow run not found') from exc
        except (RuntimeError, PermissionError) as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.post('/workflows/runs/{run_id}/resume')
    def workflow_resume(run_id: str, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, 'workflow:write')
        try:
            authority = workflow_authority(device_id)
            authority.pop('reauthenticated_at', None)
            result = runtime['automations'].resume_run(run_id, **authority)
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        except (KeyError, RuntimeError) as exc:
            raise HTTPException(409, str(exc)) from exc
        audit('workflow.resumed', device_id=device_id, run_id=run_id)
        return result

    @router.post('/workflows/runs/{run_id}/approve')
    def workflow_approve(run_id: str, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, 'workflow:approve')
        engine = runtime['automations']
        auth = workflow_authority(device_id)
        if not workflow_binding_matches(engine, run_id, auth):
            raise HTTPException(403, 'Workflow authority mismatch')
        try:
            run = engine._run(run_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        approval_id = run.get('pending_approval_id')
        if not approval_id:
            raise HTTPException(409, 'Workflow is not waiting for approval')
        try:
            result = engine.approve_run(
                run_id,
                approval_id,
                **auth,
            )
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        except (KeyError, RuntimeError) as exc:
            raise HTTPException(409, str(exc)) from exc
        audit('workflow.approved', device_id=device_id, run_id=run_id, approval_id=approval_id)
        return result

    @router.post('/workflows/runs/{run_id}/reject')
    def workflow_reject(run_id: str, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, 'workflow:approve')
        engine = runtime['automations']
        authority = workflow_authority(device_id)
        if not workflow_binding_matches(engine, run_id, authority):
            raise HTTPException(403, 'Workflow authority mismatch')
        try:
            run = engine._run(run_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        approval_id = run.get('pending_approval_id')
        if not approval_id:
            raise HTTPException(409, 'Workflow is not waiting for approval')
        try:
            authority.pop('reauthenticated_at', None)
            result = engine.reject_run(run_id, approval_id, **authority)
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        except (KeyError, RuntimeError) as exc:
            raise HTTPException(409, str(exc)) from exc
        audit('workflow.rejected', device_id=device_id, run_id=run_id, approval_id=approval_id)
        return result

    @router.post('/system/emergency-stop')
    def emergency_stop(body: EmergencyStopBody, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, 'device:admin')
        if not body.enabled:
            require_fresh_reauthentication()
        runtime['tools'].set_emergency_stop(body.enabled)
        # ToolRegistry is the canonical E-stop authority and advances the
        # security epoch. Also cancel active canonical turns so this owner
        # surface converges with the cloud owner E-stop semantics.
        executor = runtime.get('executor')
        if body.enabled and executor is not None and hasattr(executor, 'cancel_active_turns'):
            executor.cancel_active_turns(reason='emergency_stop')
        events = runtime.get('events')
        if events is not None:
            events.emit('emergency.stop', enabled=body.enabled)
        autonomy = runtime.get('advanced_autonomy')
        if autonomy is not None:
            autonomy.emergency_stop('owner requested from trusted device') if body.enabled else autonomy.clear_emergency_stop()
        audit('system.emergency_stop', device_id=device_id, enabled=body.enabled)
        return {'enabled': body.enabled, 'message': 'All tool actions stopped' if body.enabled else 'Tool actions enabled'}

    @router.get('/qualification')
    def qualification_status(pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, 'qualification:read')
        return runtime['p3_qualification'].status()

    @router.post('/qualification/stages')
    def qualification_start(
        body: QualificationSessionBody,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token, 'qualification:record')
        environment = {**_bounded_mapping(body.environment), 'device_id': device_id, 'surface': 'ios-pwa'}
        try:
            session_id = runtime['p3_qualification'].start_session(
                body.stage,
                evidence_class=body.evidence_class,
                environment=environment,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        audit('qualification.session.started', device_id=device_id, session_id=session_id, stage=body.stage)
        return {'session_id': session_id, 'stage': body.stage, 'evidence_class': body.evidence_class}

    @router.post('/qualification/sessions/{session_id}/trials')
    def qualification_trial(
        session_id: str,
        body: QualificationTrialBody,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token, 'qualification:record')
        evidence = {**_bounded_mapping(body.evidence), 'device_id': device_id}
        metrics = _bounded_mapping(body.metrics)
        try:
            trial = runtime['p3_qualification'].record_trial(
                session_id,
                body.task,
                passed=body.passed,
                latency_ms=body.latency_ms,
                metrics=metrics,
                evidence=evidence,
            )
        except (KeyError, ValueError) as exc:
            raise HTTPException(400, str(exc)) from exc
        return {'trial': trial, 'session_id': session_id}

    @router.post('/qualification/sessions/{session_id}/finish')
    def qualification_finish(
        session_id: str,
        body: QualificationFinishBody,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token, 'qualification:record')
        try:
            result = runtime['p3_qualification'].finish_session(session_id, duration_seconds=body.duration_seconds)
        except (KeyError, ValueError) as exc:
            raise HTTPException(400, str(exc)) from exc
        audit('qualification.session.finished', device_id=device_id, session_id=session_id)
        return result

    @router.get('/system/status')
    def system_status(pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, 'activities:read')
        return {
            'model': runtime['models'].status(),
            'tools': [
                {'name': tool.name, 'description': tool.description, 'risk': tool.risk.name}
                for tool in runtime['tools'].all()
            ],
            'integrations': runtime['integrations'].list(),
            'future_intelligence': runtime['future_intelligence'].status(),
            'emergency_stop': bool(getattr(runtime['tools'], 'emergency_stop', False)),
            'model_evaluation': runtime['model_evaluation'].latest(),
        }

    @router.get('/owner/permissions')
    def owner_permissions_get(pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, 'device:admin')
        tools = runtime.get('tools')
        if tools is None or not callable(getattr(tools, 'owner_permissions', None)):
            raise HTTPException(503, 'Owner permission policy is unavailable')
        return tools.owner_permissions()

    @router.patch('/owner/permissions')
    def owner_permissions_patch(body: OwnerPermissionsBody, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, 'device:admin')
        tools = runtime.get('tools')
        if tools is None or not callable(getattr(tools, 'update_owner_permissions', None)):
            raise HTTPException(503, 'Owner permission policy is unavailable')
        try:
            result = tools.update_owner_permissions(body.mode, body.rules)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        audit('owner.permissions.updated', device_id=device_id, mode=result['mode'], rules=result['rules'])
        return {'ok': True, **result}

    @router.patch('/owner/ai-provider/default')
    def owner_default_provider(body: OwnerDefaultProviderBody, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, 'device:admin')
        models = runtime.get('models')
        setter = getattr(models, 'set_default_provider', None)
        if not callable(setter):
            raise HTTPException(503, 'Persistent provider selection is unavailable')
        try:
            result = setter(body.provider_id)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        audit('model.default_provider.changed', device_id=device_id, provider_id=result['provider'], previous_provider=result['previous_provider'])
        return {'ok': True, **result, 'model': models.status()}

    @router.post('/owner/ai-providers/test')
    def owner_provider_test(body: OwnerProviderTestBody, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, 'device:admin')
        limit_provider_attempts(device_id)
        models = runtime.get('models')
        if models is None or not callable(getattr(models, 'test_owner_provider', None)):
            raise HTTPException(503, 'Provider connection testing is unavailable')
        try:
            result = models.test_owner_provider(body.provider_id, body.api_key.get_secret_value())
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from exc
        return result

    @router.post('/owner/ai-providers')
    def owner_provider_connect(body: OwnerProviderConnectBody, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, 'device:admin')
        limit_provider_attempts(device_id)
        models = runtime.get('models')
        if models is None or not callable(getattr(models, 'connect_owner_provider', None)):
            raise HTTPException(503, 'Encrypted provider configuration is unavailable')
        try:
            result = models.connect_owner_provider(body.provider_id, body.api_key.get_secret_value(), body.model)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from exc
        audit('model.provider.connected', device_id=device_id, provider_id=result['provider'], model=result['model'])
        return {'ok': True, **result, 'model_status': models.status()}

    @router.get('/owner/ai-providers/{provider_id}/models')
    def owner_provider_models(provider_id: str, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, 'device:admin')
        limit_provider_attempts(device_id)
        models = runtime.get('models')
        if models is None or not callable(getattr(models, 'owner_provider_models', None)):
            raise HTTPException(503, 'Provider model discovery is unavailable')
        try:
            return models.owner_provider_models(provider_id)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from exc

    @router.patch('/owner/ai-providers/{provider_id}/model')
    def owner_provider_model_update(provider_id: str, body: OwnerProviderModelBody, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, 'device:admin')
        limit_provider_attempts(device_id)
        models = runtime.get('models')
        if models is None or not callable(getattr(models, 'set_owner_provider_model', None)):
            raise HTTPException(503, 'Provider model configuration is unavailable')
        try:
            result = models.set_owner_provider_model(provider_id, body.model)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from exc
        audit('model.provider.model_changed', device_id=device_id, provider_id=result['provider'], model=result['model'])
        return {'ok': True, **result, 'model_status': models.status()}

    @router.delete('/owner/ai-providers/{provider_id}')
    def owner_provider_disconnect(provider_id: str, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, 'device:admin')
        models = runtime.get('models')
        if models is None or not callable(getattr(models, 'disconnect_owner_provider', None)):
            raise HTTPException(503, 'Provider configuration is unavailable')
        try:
            result = models.disconnect_owner_provider(provider_id)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from exc
        audit('model.provider.disconnected', device_id=device_id, provider_id=result['provider'])
        return {'ok': True, **result, 'model_status': models.status()}

    @router.post('/system/model-evaluation')
    def run_model_evaluation(
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token, 'qualification:record')
        result = runtime['model_evaluation'].run()
        audit('model.evaluation.requested', device_id=device_id, run_id=result['id'])
        return result

    return router
