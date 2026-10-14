from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from urllib.parse import urlparse

from core.preferences import Preferences
from recovery.backup import BackupError, BackupService


class SetupStatus(str, Enum):
    UNINITIALIZED = 'uninitialized'
    SETUP_IN_PROGRESS = 'setup_in_progress'
    READY = 'ready'
    RESTORING = 'restoring'
    RESTORE_FAILED = 'restore_failed'
    CONNECT_PENDING = 'connect_pending'


class SetupMode(str, Enum):
    CREATE = 'create'
    RESTORE = 'restore'
    CONNECT = 'connect'


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class FirstRunCoordinator:
    """Durable, non-secret authority for Vishnu first-run state.

    The coordinator deliberately reuses the canonical Preferences,
    OwnerAccessStore, model router, ToolRegistry and BackupService. It never
    stores reusable passwords, provider credentials, recovery codes or device
    bearer tokens in its own state file.
    """

    VERSION = 1
    STATE_FILE = 'first-run-state.json'
    PENDING_RESTORE_FILE = 'first-run-pending-restore.json'
    PROVIDERS = (
        'local', 'openai', 'gemini', 'openrouter', 'deepseek', 'xai',
        'groq', 'cerebras', 'mistral', 'custom',
    )
    PRIVACY_MODES = ('local_only', 'local_preferred', 'external_allowed')
    AUTONOMY_MODES = ('observe', 'suggest', 'ask', 'act')

    def __init__(self, data_dir: Path, *, runtime: dict | None = None):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.data_dir / self.STATE_FILE
        self.pending_restore_path = self.data_dir / self.PENDING_RESTORE_FILE
        self.runtime = runtime
        if not self.state_path.exists():
            self._write_state({
                'version': self.VERSION,
                'status': SetupStatus.UNINITIALIZED.value,
                'mode': None,
                'stage': 'welcome',
                'completed_steps': [],
                'created_at': _now(),
                'updated_at': _now(),
                'last_error': None,
                'restore': None,
                'migrated_legacy_install': False,
            })

    def bind_runtime(self, runtime: dict):
        self.runtime = runtime
        return self

    def _read_state(self) -> dict:
        try:
            value = json.loads(self.state_path.read_text(encoding='utf-8'))
        except (OSError, ValueError, TypeError):
            value = {}
        if not isinstance(value, dict):
            value = {}
        value.setdefault('version', self.VERSION)
        value.setdefault('status', SetupStatus.UNINITIALIZED.value)
        value.setdefault('mode', None)
        value.setdefault('stage', 'welcome')
        value.setdefault('completed_steps', [])
        value.setdefault('created_at', _now())
        value.setdefault('updated_at', _now())
        value.setdefault('last_error', None)
        value.setdefault('restore', None)
        value.setdefault('migrated_legacy_install', False)
        return value

    def _write_state(self, value: dict) -> dict:
        state = dict(value)
        state['version'] = self.VERSION
        state['updated_at'] = _now()
        temporary = self.state_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(state, sort_keys=True, indent=2), encoding='utf-8')
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        temporary.replace(self.state_path)
        try:
            os.chmod(self.state_path, 0o600)
        except OSError:
            pass
        return state

    def snapshot(self) -> dict:
        state = self._read_state()
        runtime = self.runtime or {}
        owner_access = runtime.get('owner_access')
        models = runtime.get('models')
        state['security'] = {
            'password_configured': bool(owner_access and owner_access.password_configured()),
            'passkey_count': len(owner_access.passkeys()) if owner_access else 0,
            'recovery_codes_remaining': owner_access.recovery_codes_remaining() if owner_access else 0,
        }
        if owner_access is not None:
            identity = owner_access.identity()
            if identity is not None:
                state['identity'] = identity
        if models is not None:
            try:
                state['model'] = models.status()
            except Exception:
                state['model'] = {'state': 'unavailable'}
        return state

    @property
    def ready(self) -> bool:
        return self._read_state().get('status') == SetupStatus.READY.value

    def _runtime_required(self) -> dict:
        if self.runtime is None:
            raise RuntimeError('Vishnu runtime is not bound to first-run setup')
        return self.runtime

    def _mark_step(self, step: str, *, stage: str | None = None, **extra) -> dict:
        state = self._read_state()
        completed = list(dict.fromkeys([*state.get('completed_steps', []), str(step)]))
        state['completed_steps'] = completed
        if stage is not None:
            state['stage'] = stage
        state.update(extra)
        return self._write_state(state)

    def _legacy_install_detected(self) -> bool:
        runtime = self.runtime or {}
        preferences = runtime.get('preferences')
        owner_access = runtime.get('owner_access')
        devices = runtime.get('device_registry')
        if preferences is not None and bool(preferences.get('onboarding_complete', False)):
            return True
        if owner_access is not None:
            if owner_access.password_configured() or owner_access.passkeys() or owner_access.recovery_codes_remaining() > 0:
                return True
        if devices is not None:
            try:
                if devices.list():
                    return True
            except Exception:
                pass
        return False

    def should_run(self) -> bool:
        state = self._read_state()
        status = state.get('status')
        if status == SetupStatus.READY.value:
            return False
        # Legacy migration is allowed only before this installation has entered
        # the new state machine. A password/device created during a partially
        # completed setup must never promote that incomplete setup to READY.
        if status == SetupStatus.UNINITIALIZED.value and self._legacy_install_detected():
            preferences = (self.runtime or {}).get('preferences')
            owner_access = (self.runtime or {}).get('owner_access')
            if owner_access is not None:
                owner_access.initialize_identity(
                    first_name=str(preferences.get('profile_first_name', '') or 'Owner') if preferences else 'Owner',
                    last_name=str(preferences.get('profile_last_name', '') or '') if preferences else '',
                    display_name=str(preferences.get('preferred_name', '') or 'Vishnu Owner') if preferences else 'Vishnu Owner',
                )
            state.update({
                'status': SetupStatus.READY.value,
                'mode': state.get('mode') or SetupMode.CREATE.value,
                'stage': 'ready',
                'migrated_legacy_install': True,
                'last_error': None,
            })
            self._write_state(state)
            if preferences is not None:
                preferences.set('onboarding_complete', True)
            return False
        return True

    def begin(self, mode: str | SetupMode) -> dict:
        try:
            selected = mode if isinstance(mode, SetupMode) else SetupMode(str(mode))
        except ValueError as exc:
            raise ValueError('Unsupported setup mode') from exc
        state = self._read_state()
        if selected is SetupMode.CREATE and state.get('status') == SetupStatus.READY.value:
            raise RuntimeError('Vishnu is already initialized. Connect this device instead.')
        state.update({
            'status': SetupStatus.CONNECT_PENDING.value if selected is SetupMode.CONNECT else SetupStatus.SETUP_IN_PROGRESS.value,
            'mode': selected.value,
            'stage': 'owner' if selected is SetupMode.CREATE else selected.value,
            'last_error': None,
        })
        return self._write_state(state)

    def configure_owner(self, *, first_name: str, last_name: str = '', display_name: str = '') -> dict:
        runtime = self._runtime_required()
        preferences = runtime['preferences']
        first = str(first_name or '').strip()[:80]
        last = str(last_name or '').strip()[:80]
        display = str(display_name or '').strip()[:120] or ' '.join(part for part in (first, last) if part).strip()
        if not first:
            raise ValueError('First name is required')
        preferences.update(
            profile_first_name=first,
            profile_last_name=last,
            preferred_name=display or first,
        )
        self._mark_step('owner', stage='security')
        return {'first_name': first, 'last_name': last, 'display_name': display or first}

    def configure_security(self, password: str) -> list[str]:
        runtime = self._runtime_required()
        owner_access = runtime['owner_access']
        owner_access.set_password(str(password or ''))
        codes = owner_access.regenerate_recovery_codes()
        state = self._read_state()
        completed = [item for item in state.get('completed_steps', []) if item != 'recovery_saved']
        state['completed_steps'] = list(dict.fromkeys([*completed, 'security']))
        state['stage'] = 'recovery'
        state['recovery_code_count'] = len(codes)
        self._write_state(state)
        return codes

    def confirm_recovery_codes_saved(self) -> dict:
        runtime = self._runtime_required()
        owner_access = runtime['owner_access']
        if not owner_access.password_configured() or owner_access.recovery_codes_remaining() <= 0:
            raise RuntimeError('Owner security and recovery codes must be created first')
        return self._mark_step('recovery_saved', stage='privacy')

    def configure_preferences(
        self,
        *,
        privacy_mode: str,
        autonomy_mode: str,
        memory_enabled: bool = True,
    ) -> dict:
        runtime = self._runtime_required()
        state = self._read_state()
        if 'recovery_saved' not in state.get('completed_steps', []):
            raise RuntimeError('Save and confirm recovery codes before continuing')
        privacy = str(privacy_mode or '').strip()
        autonomy = str(autonomy_mode or '').strip()
        if privacy not in self.PRIVACY_MODES:
            raise ValueError('Unsupported privacy mode')
        if autonomy not in self.AUTONOMY_MODES:
            raise ValueError('Unsupported autonomy mode')
        preferences = runtime['preferences']
        preferences.update(
            model_privacy_mode=privacy,
            autonomy_mode=autonomy,
            memory_enabled=bool(memory_enabled),
        )
        runtime['models'].set_owner_privacy(privacy)
        runtime['tools'].set_autonomy_mode(autonomy)
        self._mark_step('privacy', stage='model')
        return {'privacy_mode': privacy, 'autonomy_mode': autonomy, 'memory_enabled': bool(memory_enabled)}

    def configure_model(
        self,
        *,
        provider_id: str,
        model: str = '',
        api_key: str = '',
    ) -> dict:
        runtime = self._runtime_required()
        provider = str(provider_id or '').strip().lower()
        if provider not in self.PROVIDERS:
            raise ValueError('Unsupported model provider')
        service = runtime['models']
        if provider == 'local':
            result = service.set_default_provider('local')
        else:
            key = str(api_key or '').strip()
            selected_model = str(model or '').strip()
            if len(key) < 16:
                raise ValueError('Provider API key is required')
            if not selected_model:
                raise ValueError('Provider model is required')
            result = service.connect_owner_provider(provider, key, selected_model)
            service.set_default_provider(provider)
        self._mark_step('model', stage='ready')
        return result if isinstance(result, dict) else {'provider': provider, 'configured': True}

    def skip_model_configuration(self) -> dict:
        return self._mark_step('model_skipped', stage='ready')

    def schedule_restore(self, archive: str | Path) -> dict:
        runtime = self._runtime_required()
        path = Path(archive).expanduser().resolve()
        if not path.is_file():
            raise ValueError('Backup file does not exist')
        manifest = runtime['backups'].inspect(path)
        payload = {'path': str(path), 'scheduled_at': _now()}
        temporary = self.pending_restore_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding='utf-8')
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        temporary.replace(self.pending_restore_path)
        state = self._read_state()
        state.update({
            'status': SetupStatus.RESTORING.value,
            'mode': SetupMode.RESTORE.value,
            'stage': 'restart_required',
            'restore': {
                'archive': path.name,
                'encrypted': bool(manifest.get('encrypted')),
                'created_at': manifest.get('created_at'),
            },
            'last_error': None,
        })
        self._write_state(state)
        return state['restore']

    def mark_connect_pending(self, url: str) -> dict:
        value = str(url or '').strip()
        if not value:
            raise ValueError('Existing Vishnu URL is required')
        parsed = urlparse(value)
        if not parsed.hostname:
            raise ValueError('Existing Vishnu URL must include a hostname')
        if parsed.username is not None or parsed.password is not None:
            raise ValueError('Do not embed credentials in the Vishnu URL')
        local_http = parsed.scheme == 'http' and parsed.hostname in {'127.0.0.1', 'localhost', '::1'}
        if parsed.scheme != 'https' and not local_http:
            raise ValueError('Existing Vishnu URL must use HTTPS except for localhost development')
        # Persist only the origin. Paths, queries and fragments are not part of
        # device identity and can accidentally contain sensitive information.
        origin = f'{parsed.scheme}://{parsed.netloc}'.rstrip('/')
        state = self._read_state()
        state.update({
            'status': SetupStatus.CONNECT_PENDING.value,
            'mode': SetupMode.CONNECT.value,
            'stage': 'external_device_authorization',
            'connect_url': origin[:1000],
            'last_error': None,
        })
        return self._write_state(state)

    def complete(self) -> dict:
        runtime = self._runtime_required()
        preferences = runtime['preferences']
        owner_access = runtime['owner_access']
        state = self._read_state()
        completed = set(state.get('completed_steps', []))
        mode = state.get('mode')
        if mode not in {SetupMode.CREATE.value, SetupMode.RESTORE.value}:
            raise RuntimeError('Only a new or restored Vishnu can complete owner creation')
        if not str(preferences.get('preferred_name', '') or '').strip():
            raise RuntimeError('Owner profile is incomplete')
        if not owner_access.password_configured():
            raise RuntimeError('Owner security is incomplete')
        if 'recovery_saved' not in completed:
            raise RuntimeError('Recovery codes must be saved before setup can complete')
        if owner_access.recovery_codes_remaining() <= 0:
            raise RuntimeError('At least one unused recovery code must remain before setup can complete')
        if 'privacy' not in completed:
            raise RuntimeError('Privacy and autonomy preferences are incomplete')
        if not ({'model', 'model_skipped'} & completed):
            raise RuntimeError('AI configuration must be completed or explicitly skipped')
        identity, created = owner_access.initialize_identity(
            first_name=str(preferences.get('profile_first_name', '') or ''),
            last_name=str(preferences.get('profile_last_name', '') or ''),
            display_name=str(preferences.get('preferred_name', '') or ''),
        )
        if created:
            memory = runtime.get('memory')
            if memory is not None and hasattr(memory, 'audit'):
                try:
                    memory.audit(
                        'owner',
                        'identity.created',
                        {
                            'owner_id': identity['owner_id'],
                            'vishnu_id': identity['vishnu_id'],
                            'identity_version': identity['identity_version'],
                        },
                    )
                except Exception:
                    # Do not lose a durable identity because an audit sink is
                    # temporarily unavailable; still publish the lifecycle
                    # event below for any configured operational listener.
                    pass
            events = runtime.get('events')
            if events is not None:
                try:
                    events.emit(
                        'owner.identity.created',
                        owner_id=identity['owner_id'],
                        vishnu_id=identity['vishnu_id'],
                        identity_version=identity['identity_version'],
                    )
                except Exception:
                    # Audit delivery must not roll back an already durable
                    # identity; the identity store remains the source of truth.
                    pass
        preferences.set('onboarding_complete', True)
        state.update({
            'status': SetupStatus.READY.value,
            'mode': state.get('mode') or SetupMode.CREATE.value,
            'stage': 'ready',
            'identity_version': identity['identity_version'],
            'last_error': None,
        })
        return self._write_state(state)

    @classmethod
    def apply_pending_restore(cls, data_dir: Path, *, vault_password: str | None = None) -> dict | None:
        data_dir = Path(data_dir)
        pending = data_dir / cls.PENDING_RESTORE_FILE
        if not pending.exists():
            return None
        state_path = data_dir / cls.STATE_FILE
        try:
            payload = json.loads(pending.read_text(encoding='utf-8'))
            archive = Path(str(payload['path'])).expanduser().resolve()
            result = BackupService(data_dir, vault_password=vault_password).restore(archive)
            # Security authority is intentionally not restored by BackupService.
            # Force the restored installation back through fresh owner security.
            Preferences(data_dir / 'preferences.json').set('onboarding_complete', False)
            state = {
                'version': cls.VERSION,
                'status': SetupStatus.SETUP_IN_PROGRESS.value,
                'mode': SetupMode.RESTORE.value,
                'stage': 'owner',
                'completed_steps': ['restore'],
                'created_at': _now(),
                'updated_at': _now(),
                'last_error': None,
                'restore': {
                    'archive': archive.name,
                    'result': result,
                    'security_state_restored': False,
                },
                'migrated_legacy_install': False,
            }
            temporary = state_path.with_suffix('.tmp')
            temporary.write_text(json.dumps(state, sort_keys=True, indent=2), encoding='utf-8')
            temporary.replace(state_path)
            return result
        except (OSError, ValueError, KeyError, BackupError) as exc:
            failed = {
                'version': cls.VERSION,
                'status': SetupStatus.RESTORE_FAILED.value,
                'mode': SetupMode.RESTORE.value,
                'stage': 'restore',
                'completed_steps': [],
                'created_at': _now(),
                'updated_at': _now(),
                'last_error': str(exc)[:500],
                'restore': None,
                'migrated_legacy_install': False,
            }
            temporary = state_path.with_suffix('.tmp')
            temporary.write_text(json.dumps(failed, sort_keys=True, indent=2), encoding='utf-8')
            temporary.replace(state_path)
            return {'ok': False, 'error': failed['last_error']}
        finally:
            pending.unlink(missing_ok=True)
