from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DEFAULT_PREFERENCES = {
    'events': {
        'task_reminders': {'enabled': False, 'channels': []},
        'work_completed': {'enabled': True, 'channels': ['in_app']},
        'needs_review': {'enabled': True, 'channels': ['in_app']},
        'blocked_work': {'enabled': True, 'channels': ['in_app']},
        'workflow_updates': {'enabled': False, 'channels': []},
        # Product-update publishing is not wired to this installation yet.
        'product_updates': {'enabled': False, 'channels': []},
    },
    'quiet_hours': {'enabled': True, 'start': '22:00', 'end': '08:00', 'timezone': 'Asia/Kolkata'},
    'allow_urgent_reviews': True,
    'daily_summary': {'enabled': True, 'time': '08:00'},
    'weekly_summary': {'enabled': False, 'weekday': 0, 'time': '08:00'},
}

EVENTS = {
    'workflow.started': ('workflow_updates', 'Workflow updates', 'A workflow has started.'),
    'workflow.completed': ('work_completed', 'Work completed', 'Vishnu completed a workflow.'),
    'automation.completed': ('work_completed', 'Work completed', 'Vishnu completed an automation.'),
    'workflow.approval_required': ('needs_review', 'Needs your review', 'A workflow is waiting for your approval.'),
    'automation.approval_required': ('needs_review', 'Needs your review', 'An automation is waiting for your approval.'),
    'workflow.failed': ('blocked_work', 'Blocked work', 'A workflow needs your attention.'),
    'automation.failed': ('blocked_work', 'Blocked work', 'An automation needs your attention.'),
}


def _inside_quiet_hours(config: dict, now: datetime) -> bool:
    quiet = config.get('quiet_hours') or {}
    if not quiet.get('enabled'):
        return False
    try:
        local = now.astimezone(ZoneInfo(quiet.get('timezone', 'UTC')))
        start = datetime.strptime(quiet.get('start', '22:00'), '%H:%M').time()
        end = datetime.strptime(quiet.get('end', '08:00'), '%H:%M').time()
    except (ValueError, ZoneInfoNotFoundError):
        return False
    current = local.time().replace(tzinfo=None)
    return start <= current or current < end if start > end else start <= current < end


class NotificationService:
    """Persisted, owner-scoped in-app notifications with optional APNs delivery."""

    def __init__(self, path: Path, registry, apns=None, events=None, *, owner_preferences=None, start_scheduler: bool = True):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.registry, self.apns, self.events = registry, apns, events
        self.owner_preferences = owner_preferences
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._unsubscribers = []
        with self._connect() as con:
            con.execute('''CREATE TABLE IF NOT EXISTS notifications(
                id TEXT PRIMARY KEY, device_id TEXT NOT NULL, dedupe_key TEXT NOT NULL,
                category TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL,
                created_at TEXT NOT NULL, read_at TEXT,
                UNIQUE(device_id, dedupe_key))''')
        # Own schema only: additive, versioned migration; no second notification store.
        with self._lock, self._connect() as con:
            version = con.execute('PRAGMA user_version').fetchone()[0]
            if version > 2:
                raise RuntimeError('Unsupported future NotificationService schema')
            existing = {row[1] for row in con.execute('PRAGMA table_info(notifications)')}
            for column in ('pinned_at', 'dismissed_at', 'event_type', 'source_type',
                           'source_id', 'project_id', 'workspace_id', 'priority'):
                if column not in existing:
                    con.execute(f'ALTER TABLE notifications ADD COLUMN {column} TEXT')
            con.execute('CREATE INDEX IF NOT EXISTS idx_notifications_device_recent ON notifications(device_id, created_at DESC, id DESC)')
            con.execute('PRAGMA user_version=2')
        self._scheduler = threading.Thread(target=self._schedule_loop, name='notification-scheduler', daemon=True)
        if start_scheduler:
            self._scheduler.start()
        if events:
            for name in EVENTS:
                self._unsubscribers.append(events.subscribe(name, lambda event, event_name=name: self._on_event(event_name, event)))

    def _connect(self):
        con = sqlite3.connect(self.path, timeout=30)
        con.row_factory = sqlite3.Row
        return con

    def preferences(self, device_id: str) -> dict:
        if self.owner_preferences is not None:
            stored = self.owner_preferences.get('notifications_preferences', {})
        else:
            try:
                stored = json.loads(self.registry.metadata(device_id).get('notifications.preferences', '{}'))
            except (TypeError, ValueError):
                stored = {}
        if not isinstance(stored, dict):
            stored = {}
        return {**json.loads(json.dumps(DEFAULT_PREFERENCES)), **stored,
                'events': {**json.loads(json.dumps(DEFAULT_PREFERENCES['events'])), **(stored.get('events') or {})},
                'quiet_hours': {**DEFAULT_PREFERENCES['quiet_hours'], **(stored.get('quiet_hours') or {})},
                'daily_summary': {**DEFAULT_PREFERENCES['daily_summary'], **(stored.get('daily_summary') or {})},
                'weekly_summary': {**DEFAULT_PREFERENCES['weekly_summary'], **(stored.get('weekly_summary') or {})}}

    def save_preferences(self, device_id: str, config: dict) -> dict:
        if self.owner_preferences is not None:
            self.owner_preferences.set('notifications_preferences', config)
        else:
            value = json.dumps(config, separators=(',', ':'), sort_keys=True)
            if not self.registry.set_metadata(device_id, 'notifications.preferences', value):
                raise KeyError('Active device not found')
        return config

    def _on_event(self, event_name: str, event: dict):
        category, title, body = EVENTS[event_name]
        event_key = str(event.get('event_id') or event.get('run_id') or event.get('automation_id') or uuid.uuid4())[:180]
        for device in self.registry.list():
            device_id = device['id']
            if device.get('revoked'):
                continue
            config = self.preferences(device_id)
            rule = config['events'].get(category, {})
            if not rule.get('enabled'):
                continue
            urgent = category == 'needs_review'
            if _inside_quiet_hours(config, datetime.now(timezone.utc)) and not (urgent and config.get('allow_urgent_reviews')):
                continue
            channels = set(rule.get('channels') or [])
            if 'in_app' in channels:
                # Preserve only bounded IDs, not raw event parameters or credentials.
                source_type = 'work' if event_name.startswith('work.') else 'workflow' if event_name.startswith(('workflow.', 'automation.')) else 'system'
                self._insert(device_id, event_key, category, title, body,
                             event_type=event_name, source_type=source_type,
                             source_id=event.get('work_order_id') or event.get('run_id') or event.get('automation_id'),
                             project_id=event.get('project_id'), workspace_id=event.get('workspace_id'),
                             priority='high' if category in ('needs_review','blocked_work') else 'normal')
            if 'push' in channels and self.apns and self.apns.configured and device.get('metadata', {}).get('push.apns.token'):
                # Keep lock-screen text generic; never include project or conversation content.
                self.apns.send_device(device_id, title, body, data={'category': category, 'notification_id': event_key})

    def _insert(self, device_id, key, category, title, body, *, event_type=None,
                source_type=None, source_id=None, project_id=None, workspace_id=None, priority=None):
        def bounded(value):
            return str(value)[:120] if value is not None else None
        with self._lock, self._connect() as con:
            con.execute('''INSERT OR IGNORE INTO notifications
                (id,device_id,dedupe_key,category,title,body,created_at,read_at,
                event_type,source_type,source_id,project_id,workspace_id,priority)
                VALUES(?,?,?,?,?,?,?,NULL,?,?,?,?,?,?)''',
                (str(uuid.uuid4()), device_id, str(key)[:180], category, title[:120], body[:500],
                 datetime.now(timezone.utc).isoformat(), bounded(event_type), bounded(source_type),
                 bounded(source_id), bounded(project_id), bounded(workspace_id), bounded(priority)))

    _LIST_FIELDS = ('id,category,title,body,created_at,read_at,pinned_at,dismissed_at,'
                    'event_type,source_type,source_id,project_id,workspace_id,priority')

    def list(self, device_id: str, limit: int = 100, *, include_dismissed=False) -> list[dict]:
        with self._connect() as con:
            extra = '' if include_dismissed else ' AND dismissed_at IS NULL'
            rows = con.execute(f'SELECT {self._LIST_FIELDS} FROM notifications WHERE device_id=?'
                               + extra + ' ORDER BY created_at DESC,id DESC LIMIT ?',
                               (device_id, max(1, min(limit, 200)))).fetchall()
        return [dict(row) for row in rows]

    def detail(self, device_id: str, notification_id: str) -> dict | None:
        with self._connect() as con:
            row = con.execute(f'SELECT {self._LIST_FIELDS} FROM notifications WHERE device_id=?'
                              ' AND id=? AND dismissed_at IS NULL', (device_id, notification_id)).fetchone()
        return dict(row) if row else None

    def mark_all_read(self, device_id: str, ids: list[str] | None = None) -> int:
        # Device scoped, transactional and idempotent. Never operates on approvals.
        with self._lock, self._connect() as con:
            if ids is None:
                cursor = con.execute('UPDATE notifications SET read_at=? WHERE device_id=?'
                                     ' AND read_at IS NULL AND dismissed_at IS NULL',
                                     (datetime.now(timezone.utc).isoformat(), device_id))
            elif not ids:
                return 0
            else:
                safe_ids = [str(item) for item in ids[:200]]
                slots = ','.join('?' for _ in safe_ids)
                cursor = con.execute('UPDATE notifications SET read_at=? WHERE device_id=?'
                                     f' AND id IN ({slots}) AND read_at IS NULL AND dismissed_at IS NULL',
                                     (datetime.now(timezone.utc).isoformat(), device_id, *safe_ids))
            return cursor.rowcount

    def pin(self, device_id: str, notification_id: str, pinned: bool) -> bool:
        with self._lock, self._connect() as con:
            result = con.execute('UPDATE notifications SET pinned_at=? WHERE device_id=?'
                                 ' AND id=? AND dismissed_at IS NULL',
                                 (datetime.now(timezone.utc).isoformat() if pinned else None,
                                  device_id, notification_id))
            return result.rowcount == 1

    def dismiss(self, device_id: str, notification_id: str) -> bool:
        with self._lock, self._connect() as con:
            result = con.execute('UPDATE notifications SET dismissed_at=COALESCE(dismissed_at,?)'
                                 ' WHERE device_id=? AND id=?',
                                 (datetime.now(timezone.utc).isoformat(), device_id, notification_id))
            return result.rowcount == 1

    def mark_read(self, device_id: str, notification_id: str) -> bool:
        with self._connect() as con:
            return con.execute('UPDATE notifications SET read_at=? WHERE id=? AND device_id=? AND dismissed_at IS NULL', (datetime.now(timezone.utc).isoformat(), notification_id, device_id)).rowcount == 1

    def status(self, device_id: str | None = None) -> dict:
        push_ready = bool(self.apns and self.apns.configured)
        if push_ready and device_id:
            push_ready = bool(self.registry.metadata(device_id).get('push.apns.token'))
        return {'in_app': True, 'push': push_ready, 'email': False, 'scheduler': True,
                'supported_events': sorted({category for category, _, _ in EVENTS.values()})}

    def _schedule_loop(self):
        while not self._stop.wait(20):
            try:
                self._deliver_due_summaries()
            except Exception:
                # A transient scheduler error is retried on the next tick.
                continue

    def _deliver_due_summaries(self):
        now = datetime.now(timezone.utc)
        with self._connect() as con:
            con.execute('CREATE TABLE IF NOT EXISTS notification_schedule_receipts(device_id TEXT NOT NULL, schedule_key TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(device_id,schedule_key))')
        for device in self.registry.list():
            if device.get('revoked'):
                continue
            device_id = device['id']
            config = self.preferences(device_id)
            try:
                local = now.astimezone(ZoneInfo(config['quiet_hours'].get('timezone', 'UTC')))
            except (ZoneInfoNotFoundError, ValueError):
                continue
            if _inside_quiet_hours(config, now):
                continue
            for kind, schedule in (('daily', config['daily_summary']), ('weekly', config['weekly_summary'])):
                if not schedule.get('enabled'):
                    continue
                if kind == 'weekly' and local.weekday() != int(schedule.get('weekday', 0)):
                    continue
                if local.strftime('%H:%M') < schedule.get('time', '08:00'):
                    continue
                key = f'{kind}:{local.date().isoformat()}'
                with self._connect() as con:
                    receipt = con.execute('SELECT 1 FROM notification_schedule_receipts WHERE device_id=? AND schedule_key=?', (device_id, key)).fetchone()
                if receipt:
                    continue
                title = 'Daily summary' if kind == 'daily' else 'Weekly summary'
                self._insert(device_id, key, f'{kind}_summary', title, 'Your Vishnu progress summary is ready. Open the app to review it.')
                with self._connect() as con:
                    con.execute('INSERT OR IGNORE INTO notification_schedule_receipts VALUES(?,?,?)', (device_id, key, now.isoformat()))

    def close(self):
        self._stop.set()
        if self._scheduler.is_alive():
            self._scheduler.join(timeout=1.0)
        for unsubscribe in self._unsubscribers:
            try:
                unsubscribe()
            except Exception:
                pass
