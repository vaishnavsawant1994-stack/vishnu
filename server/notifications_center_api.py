"""P2-07 device-scoped Notification Center projection, not a new action authority."""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
from typing import Literal

from fastapi import APIRouter, Cookie, HTTPException, Query
from pydantic import BaseModel, Field

from approvals.projection import ApprovalsProjection
from security.request_context import current_trusted_request


CATEGORY = {
    'needs_review': 'approvals',
    'work_completed': 'work',
    'blocked_work': 'work',
    'workflow_updates': 'work',
    'task_reminders': 'system',
    'daily_summary': 'system',
    'weekly_summary': 'system',
    'product_updates': 'system',
}
CATEGORIES = ('all', 'messages', 'approvals', 'work', 'projects', 'security', 'system')


class BulkRead(BaseModel):
    scope: Literal['all', 'visible'] = 'visible'
    ids: list[str] = Field(default_factory=list, max_length=200)


class Pinned(BaseModel):
    pinned: bool


def notifications_center_router(runtime: dict) -> APIRouter:
    """Device-bound in-app records, with ephemeral, read-only canonical approvals."""
    router = APIRouter(prefix='/iphone/api/notifications-center', tags=['notifications-center'])
    registry = runtime['device_registry']
    service = runtime.get('notifications')
    executor = runtime.get('agent_executor')
    projection = ApprovalsProjection(executor.approvals) if executor is not None else None

    def owner(device: str | None, token: str | None) -> str:
        if not device or not token or not registry.authenticate(device, token):
            raise HTTPException(401, 'Trusted owner session required')
        if hasattr(registry, 'authorize') and not registry.authorize(device, 'ai:chat'):
            raise HTTPException(403, 'Device is not permitted to inspect notifications')
        return device

    def notification_service():
        if service is None:
            raise HTTPException(503, 'Notification service is unavailable')
        return service

    def approvals_for(device: str):
        # Read directly from the existing governed projection. Never impersonate
        # another device or invent a session when the trusted context is absent.
        context = current_trusted_request()
        if projection is None or context is None or context.device_id != device:
            return [], 'unavailable'
        if not registry.is_active(context.device_id):
            return [], 'restricted'
        try:
            records = projection.pending(owner_id='owner', device_id=device,
                                         session_id=context.session_id, limit=100)
            return records, 'partial' if len(records) >= 100 else 'available'
        except (OSError, RuntimeError, ValueError):
            return [], 'unavailable'

    def approval_row(a):
        created = a.get('created_at')
        try:
            stamp = datetime.fromtimestamp(float(created), timezone.utc).isoformat()
        except (TypeError, ValueError, OverflowError, OSError):
            stamp = ''
        tool = str(a.get('tool_id') or 'governed action')[:100].replace('_', ' ')
        return {
            'id': 'approval:' + str(a['approval_id']),
            'kind': 'approval', 'category': 'approvals', 'title': 'Approval required: ' + tool,
            'body': 'A governed action requires your decision. Review the exact scope before responding.',
            'created_at': stamp, 'read_at': None, 'pinned_at': None,
            'priority': 'high', 'source_type': 'approval',
            'source_id': str(a['approval_id']), 'project_id': '',
            'workspace_id': '', 'status': a.get('status') or 'pending',
            'read_supported': False, 'pin_supported': False, 'dismiss_supported': False,
            'source_authority': 'approval_manager',
        }

    def inbox_row(n):
        raw = str(n.get('category') or '')
        category = CATEGORY.get(raw, 'system')
        if str(n.get('source_type') or '') == 'security':
            category = 'security'
        return {
            **n, 'kind': 'notification', 'category': category,
            'native_category': raw,
            'priority': n.get('priority') or ('high' if raw in ('needs_review', 'blocked_work') else 'normal'),
            'read_supported': True, 'pin_supported': True, 'dismiss_supported': True,
            'status': 'read' if n.get('read_at') else 'unread',
            'source_authority': 'notification_service',
        }

    def snapshot(device: str):
        stored = notification_service().list(device, limit=200)
        approvals, approval_coverage = approvals_for(device)
        # Existing work-event notifications are not duplicated as approval tickets:
        # the approval projection keeps its own id and decision authority.
        return ([inbox_row(n) for n in stored] + [approval_row(a) for a in approvals],
                {'inbox': 'partial' if len(stored) >= 200 else 'available',
                 'approvals': approval_coverage})

    def matched(rows, *, q='', category='all', unread=False, priority=False,
                project_id='', workspace_id='', from_date=None, to_date=None, kind='all'):
        result = []
        term = q.casefold().strip()
        for n in rows:
            if category != 'all' and n['category'] != category:
                continue
            if kind != 'all' and n['kind'] != kind:
                continue
            if unread and (n['kind'] != 'notification' or n.get('read_at')):
                continue
            if priority and n.get('priority') not in ('high', 'critical'):
                continue
            if project_id and n.get('project_id') != project_id:
                continue
            if workspace_id and n.get('workspace_id') != workspace_id:
                continue
            if from_date and str(n.get('created_at') or '')[:10] < str(from_date):
                continue
            if to_date and str(n.get('created_at') or '')[:10] > str(to_date):
                continue
            if term and term not in (str(n['title']) + ' ' + str(n['body'])).casefold():
                continue
            result.append(n)
        return result

    @router.get('')
    def list_center(
        q: str = Query(default='', max_length=160),
        category: Literal['all','messages','approvals','work','projects','security','system'] = 'all',
        kind: Literal['all','notification','approval'] = 'all',
        unread: bool = False, priority: bool = False,
        project_id: str = Query(default='', max_length=120),
        workspace_id: str = Query(default='', max_length=120),
        date_from: date | None = None, date_to: date | None = None,
        sort: Literal['newest','oldest'] = 'newest',
        offset: int = Query(default=0, ge=0, le=500),
        limit: int = Query(default=40, ge=1, le=80),
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device = owner(pa_device, pa_token)
        if date_from and date_to and date_from > date_to:
            raise HTTPException(422, 'Invalid date range')
        all_rows, coverage = snapshot(device)
        filtered = matched(all_rows, q=q, category=category, kind=kind, unread=unread,
                           priority=priority, project_id=project_id, workspace_id=workspace_id,
                           from_date=date_from, to_date=date_to)
        total = Counter(x['category'] for x in all_rows)
        counts = {c: total[c] for c in CATEGORIES if c != 'all'}
        counts['all'] = len(all_rows)
        counts['unread'] = sum(x['kind'] == 'notification' and not x['read_at'] for x in all_rows)
        counts['pending_approvals'] = sum(x['kind'] == 'approval' and x['status'] == 'pending' for x in all_rows)
        filtered.sort(key=lambda x: (x.get('created_at') or '', x['id']),
                      reverse=(sort == 'newest'))
        return {'notifications': filtered[offset:offset+limit], 'counts': counts,
                'matched_count': len(filtered),
                'next_offset': offset+limit if offset+limit < len(filtered) else None,
                'coverage': coverage,
                'count_is_lower_bound': any(v == 'partial' for v in coverage.values()),
                'device_scoped': True, 'approval_authority': 'approval_manager'}

    @router.get('/{item_id}')
    def detail(item_id: str, pa_device: str | None = Cookie(default=None),
               pa_token: str | None = Cookie(default=None)):
        device = owner(pa_device, pa_token)
        if item_id.startswith('approval:'):
            ctx = current_trusted_request()
            if not ctx or ctx.device_id != device or not registry.is_active(device) or projection is None:
                raise HTTPException(404, 'Approval not available in this trusted session')
            approval = projection.detail(item_id.split(':', 1)[1], owner_id='owner',
                                         device_id=device, session_id=ctx.session_id)
            if not approval:
                raise HTTPException(404, 'Approval not found or no longer authorized')
            row = approval_row(approval)
            row['approval'] = approval
            return {'notification': row, 'related': [], 'authority': 'approval_manager'}
        row = notification_service().detail(device, item_id)
        if not row:
            raise HTTPException(404, 'Notification not found for this device')
        return {'notification': inbox_row(row), 'related': [], 'authority': 'notification_service'}

    @router.post('/read-bulk')
    def read_bulk(body: BulkRead, pa_device: str | None = Cookie(default=None),
                  pa_token: str | None = Cookie(default=None)):
        device = owner(pa_device, pa_token)
        store = notification_service()
        if body.scope == 'visible':
            if not body.ids:
                return {'marked_read': 0}
            rows = store.mark_all_read(device, [x for x in body.ids if not x.startswith('approval:')])
        else:
            rows = store.mark_all_read(device)
        return {'marked_read': rows, 'device_scoped': True}

    @router.post('/{item_id}/read')
    def read(item_id: str, pa_device: str | None = Cookie(default=None),
             pa_token: str | None = Cookie(default=None)):
        device = owner(pa_device, pa_token)
        if item_id.startswith('approval:'):
            raise HTTPException(409, 'Approval decisions have separate authoritative state')
        if not notification_service().mark_read(device, item_id):
            raise HTTPException(404, 'Notification not found')
        return {'marked_read': True}

    @router.post('/{item_id}/pin')
    def pin(item_id: str, body: Pinned,
            pa_device: str | None = Cookie(default=None),
            pa_token: str | None = Cookie(default=None)):
        device = owner(pa_device, pa_token)
        if item_id.startswith('approval:'):
            raise HTTPException(409, 'Approval requests cannot be pinned as notifications')
        if not notification_service().pin(device, item_id, body.pinned):
            raise HTTPException(404, 'Notification not found')
        return {'pinned': body.pinned}

    @router.post('/{item_id}/dismiss')
    def dismiss(item_id: str, pa_device: str | None = Cookie(default=None),
                pa_token: str | None = Cookie(default=None)):
        device = owner(pa_device, pa_token)
        if item_id.startswith('approval:'):
            raise HTTPException(409, 'Approval requests must be decided through ApprovalManager')
        if not notification_service().dismiss(device, item_id):
            raise HTTPException(404, 'Notification not found')
        return {'dismissed': True}

    return router
