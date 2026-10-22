from __future__ import annotations

import base64
import binascii
from datetime import date
import json
import re
from urllib.parse import urlparse

from fastapi import APIRouter, Cookie, HTTPException, Query, Response
from pydantic import BaseModel, Field, field_validator, model_validator


def _validate_iso_date(value):
    if value is None or value == '':
        return value
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('Dates must use the YYYY-MM-DD format')
    try:
        date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError('Dates must use the YYYY-MM-DD format') from exc
    return value

from projects.store import ProjectStore
from security.request_context import current_trusted_request
from integrations.gateway import ConnectorError


class ProjectCreateBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    goal: str = Field(default='', max_length=500)
    description: str = Field(default='', max_length=4000)
    target_date: str | None = Field(default=None, max_length=40)
    project_type: str = Field(default='software', pattern='^(software|business|research|writing|personal)$')
    success_criteria: str = Field(default='', max_length=500)
    instructions: str = Field(default='', max_length=500)
    context_notes: str = Field(default='', max_length=4000)
    tasks: list['ProjectTaskDraft'] = Field(default_factory=list, max_length=30)
    milestones: list['ProjectMilestoneDraft'] = Field(default_factory=list, max_length=15)

    @field_validator('target_date')
    @classmethod
    def valid_target_date(cls, value):
        return _validate_iso_date(value)

    @model_validator(mode='after')
    def validate_plan_links(self):
        milestone_ids = [item.client_id for item in self.milestones]
        if len(milestone_ids) != len(set(milestone_ids)):
            raise ValueError('Milestone identifiers in the proposed plan must be unique')
        task_ids = [item.client_id for item in self.tasks]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError('Task identifiers in the proposed plan must be unique')
        allowed = set(milestone_ids)
        if any(task.milestone_client_id and task.milestone_client_id not in allowed for task in self.tasks):
            raise ValueError('A proposed task links to a missing milestone')
        return self


class ProjectTaskDraft(BaseModel):
    client_id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=180)
    description: str = Field(default='', max_length=4000)
    context_notes: str = Field(default='', max_length=2000)
    priority: str = Field(default='medium', pattern='^(low|medium|high)$')
    owner: str = Field(default='owner', pattern='^(owner|vishnu)$')
    due_date: str | None = Field(default=None, max_length=40)
    milestone_client_id: str | None = Field(default=None, max_length=80)

    @field_validator('due_date')
    @classmethod
    def valid_due_date(cls, value):
        return _validate_iso_date(value)


class ProjectMilestoneDraft(BaseModel):
    client_id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=180)
    outcome: str = Field(min_length=1, max_length=2000)
    completion_criteria: str = Field(min_length=1, max_length=2000)
    target_date: str = Field(min_length=1, max_length=40)

    @field_validator('target_date')
    @classmethod
    def valid_target_date(cls, value):
        return _validate_iso_date(value)


ProjectCreateBody.model_rebuild()


class ProjectUpdateBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    goal: str | None = Field(default=None, max_length=2000)
    description: str | None = Field(default=None, max_length=4000)
    target_date: str | None = Field(default=None, max_length=40)
    project_type: str | None = Field(default=None, pattern='^(software|business|research|writing|personal)$')
    success_criteria: str | None = Field(default=None, max_length=500)
    instructions: str | None = Field(default=None, max_length=500)
    context_notes: str | None = Field(default=None, max_length=4000)
    status: str | None = Field(default=None, pattern='^(active|paused|completed|archived)$')

    @field_validator('target_date')
    @classmethod
    def valid_target_date(cls, value):
        return _validate_iso_date(value)


class TaskCreateBody(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    description: str = Field(default='', max_length=4000)
    context_notes: str = Field(default='', max_length=2000)
    priority: str = Field(default='medium', pattern='^(low|medium|high)$')
    status: str = Field(default='planned', pattern='^(planned|in_progress|blocked|needs_review|paused|done|failed)$')
    owner: str = Field(default='vishnu', pattern='^(owner|vishnu)$')
    due_date: str | None = Field(default=None, max_length=40)
    milestone_id: str | None = Field(default=None, max_length=80)
    file_ids: list[str] = Field(default_factory=list, max_length=30)

    @field_validator('due_date')
    @classmethod
    def valid_due_date(cls, value):
        return _validate_iso_date(value)


class TaskUpdateBody(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=180)
    description: str | None = Field(default=None, max_length=4000)
    context_notes: str | None = Field(default=None, max_length=2000)
    status: str | None = Field(default=None, pattern='^(planned|in_progress|blocked|needs_review|paused|done|failed)$')
    priority: str | None = Field(default=None, pattern='^(low|medium|high)$')
    owner: str | None = Field(default=None, pattern='^(owner|vishnu)$')
    due_date: str | None = Field(default=None, max_length=40)
    milestone_id: str | None = Field(default=None, max_length=80)
    file_ids: list[str] | None = Field(default=None, max_length=30)

    @field_validator('due_date')
    @classmethod
    def valid_due_date(cls, value):
        return _validate_iso_date(value)


class MilestoneCreateBody(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    outcome: str = Field(min_length=1, max_length=2000)
    target_date: str = Field(min_length=1, max_length=40)
    completion_criteria: str = Field(min_length=1, max_length=2000)
    task_ids: list[str] = Field(default_factory=list, max_length=100)

    @field_validator('target_date')
    @classmethod
    def valid_target_date(cls, value):
        return _validate_iso_date(value)


class MilestoneUpdateBody(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=180)
    outcome: str | None = Field(default=None, min_length=1, max_length=2000)
    status: str | None = Field(default=None, pattern='^(planned|in_progress|blocked|done)$')
    target_date: str | None = Field(default=None, min_length=1, max_length=40)
    completion_criteria: str | None = Field(default=None, min_length=1, max_length=2000)
    task_ids: list[str] | None = Field(default=None, max_length=100)

    @field_validator('target_date')
    @classmethod
    def valid_target_date(cls, value):
        return _validate_iso_date(value)


class FileLinkBody(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    url: str = Field(min_length=1, max_length=2000)
    kind: str = Field(default='link', pattern='^(link|knowledge|upload)$')
    knowledge_id: str | None = Field(default=None, max_length=100)


class ProjectFileUploadBody(BaseModel):
    filename: str = Field(min_length=1, max_length=240)
    media_type: str = Field(min_length=1, max_length=120)
    content_base64: str = Field(min_length=1, max_length=16_800_000)


class ProjectFileUpdateBody(BaseModel):
    is_pinned: bool


class DeliverableBody(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    content: str = Field(min_length=1, max_length=1_000_000)
    file_id: str | None = Field(default=None, max_length=100)


class ProjectFileSearchBody(BaseModel):
    q: str = Field(min_length=1, max_length=200)


class DriveImportBody(BaseModel):
    export_mime: str = Field(default='text/plain', max_length=100)


class DiscussionCreateBody(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    content: str = Field(min_length=1, max_length=4000)
    linked_item_type: str = Field(default='', pattern='^(|project_brief|task|file|milestone|proposal)$')
    linked_item_id: str | None = Field(default=None, max_length=100)


class DiscussionUpdateBody(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=180)
    status: str | None = Field(default=None, pattern='^(open|resolved)$')
    linked_item_type: str | None = Field(default=None, pattern='^(|project_brief|task|file|milestone|proposal)$')
    linked_item_id: str | None = Field(default=None, max_length=100)
    pinned_reply_id: str | None = Field(default=None, max_length=100)
    followed: bool | None = None


class DiscussionReplyBody(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class ProjectConversationCreateBody(BaseModel):
    title: str = Field(default='New Project Conversation', min_length=1, max_length=120)


class ProjectApprovalBody(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    summary: str = Field(min_length=1, max_length=4000)
    impact_summary: str = Field(min_length=1, max_length=2000)
    scope_summary: str = Field(min_length=1, max_length=2000)
    task_ids: list[str] = Field(default_factory=list, max_length=100)
    file_ids: list[str] = Field(default_factory=list, max_length=100)


class ProjectApprovalDecisionBody(BaseModel):
    decision: str = Field(pattern='^(approved|changes_requested)$')
    comments: str = Field(default='', max_length=4000)


def projects_router(runtime, store: ProjectStore):
    router = APIRouter(prefix='/iphone/api/projects', tags=['projects-workspace'])
    registry = runtime['device_registry']
    continuity = runtime.get('continuity')

    def authenticate(device_id: str | None, token: str | None, *, write=False):
        if not device_id or not token or not registry.authenticate(device_id, token):
            raise HTTPException(401, 'This browser is not trusted or its session was revoked')
        if hasattr(registry, 'authorize') and not registry.authorize(device_id, 'ai:chat'):
            raise HTTPException(403, 'This device is not permitted to use the project workspace')
        context = current_trusted_request()
        if write and (context is None or context.device_id != device_id):
            raise HTTPException(401, 'A current trusted owner session is required to change project data')
        return device_id

    def project_or_404(project_id):
        value = store.get(project_id)
        if not value:
            raise HTTPException(404, 'Project not found')
        return value

    @router.get('')
    def list_projects(q: str = Query(default='', max_length=120),
                      status: str = Query(default='all', pattern='^(all|active|paused|needs_review|completed|archived)$'),
                      sort: str = Query(default='recent', pattern='^(recent|name|created)$'),
                      pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token)
        return {'projects': store.list(q, status=status, sort=sort)}

    @router.post('', status_code=201)
    def create_project(body: ProjectCreateBody,
                       pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, write=True)
        name = body.name.strip()
        if not name:
            raise HTTPException(422, 'A project name is required')
        draft = body.model_dump()
        draft['tasks'] = [item.model_dump() for item in body.tasks]
        draft['milestones'] = [item.model_dump() for item in body.milestones]
        return {'project': store.create(**draft)}

    @router.post('/walkthrough', status_code=201)
    def create_walkthrough_project(pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, write=True)
        return {'project': store.create_walkthrough()}

    @router.get('/timeline')
    def project_tasks_for_day(day: date = Query(), limit: int = Query(default=500, ge=1, le=500),
                              pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token)
        return {'items': store.tasks_for_day(day.isoformat(), limit=limit)}

    @router.get('/{project_id}')
    def get_project(project_id: str,
                    pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token)
        return {'project': project_or_404(project_id)}

    @router.patch('/{project_id}')
    def update_project(project_id: str, body: ProjectUpdateBody,
                       pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, write=True)
        try:
            fields = body.model_dump(exclude_unset=True)
            fields = {key: value for key, value in fields.items() if value is not None or key == 'target_date'}
            value = store.update(project_id, fields)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if not value:
            raise HTTPException(404, 'Project not found')
        return {'project': value}

    @router.delete('/{project_id}', status_code=204)
    def archive_project(project_id: str,
                        pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, write=True)
        if not store.archive(project_id):
            raise HTTPException(404, 'Project not found')

    @router.post('/{project_id}/restore')
    def restore_project(project_id: str,
                        pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, write=True)
        if not store.restore(project_id):
            raise HTTPException(404, 'Archived project not found')
        return {'project': project_or_404(project_id)}

    @router.post('/{project_id}/tasks', status_code=201)
    def add_task(project_id: str, body: TaskCreateBody,
                 pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, write=True)
        try:
            value = store.add_task(project_id, **body.model_dump())
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if not value:
            raise HTTPException(404, 'Project not found')
        return {'project': value}

    @router.patch('/{project_id}/tasks/{task_id}')
    def update_task(project_id: str, task_id: str, body: TaskUpdateBody,
                    pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, write=True)
        try:
            fields = body.model_dump(exclude_unset=True)
            fields = {key: value for key, value in fields.items() if value is not None or key in {'milestone_id', 'due_date'}}
            value = store.update_task(project_id, task_id, fields)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if not value:
            raise HTTPException(404, 'Task or project not found')
        return {'project': value}

    @router.post('/{project_id}/tasks/{task_id}/execution', status_code=202)
    def start_project_task_execution(project_id: str, task_id: str,
                                     pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, write=True)
        project = project_or_404(project_id)
        task = next((row for row in project['tasks'] if row['id'] == task_id), None)
        if not task:
            raise HTTPException(404, 'Project task not found')
        if task.get('owner') != 'vishnu':
            raise HTTPException(409, 'Assign this task to Vishnu before starting it')
        engine = runtime.get('automations')
        if engine is None or runtime.get('executor') is None:
            raise HTTPException(503, 'Background task execution is not available on this installation')
        context = current_trusted_request()
        if context is None or context.device_id != pa_device:
            raise HTTPException(401, 'A current trusted owner session is required to start work')
        if task.get('execution_run_id') and task.get('status') == 'in_progress':
            return {'project': project, 'run_id': task['execution_run_id'], 'workflow_id': task.get('execution_workflow_id'), 'status': 'already_running'}
        indexed_files = []
        for file_id in task.get('file_ids', []):
            file_context = store.file_index(project_id, file_id)
            if file_context and file_context['state'] == 'indexed':
                indexed_files.append(f"[{file_context['title']}]\n{file_context['extracted_text'][:12000]}")
        prompt = (
            'Work only on the owner-approved project task described below. Use the project context included here. '
            'Do not perform external or destructive actions without the existing approval system. '
            'Produce a concise reviewable result and list any blockers.\n\n'
            f"Project: {project['name']}\nGoal: {project.get('goal') or 'Not provided'}\n"
            f"Task: {task['title']}\nDescription: {task.get('description') or 'Not provided'}\n"
            f"Owner instructions: {project.get('instructions') or 'None'}\n"
            f"Attached project files: {', '.join(next((f['title'] for f in project['files'] if f['id']==fid), fid) for fid in task.get('file_ids', [])) or 'None'}\n"
            f"Indexed attached-file context:\n{chr(10).join(indexed_files) if indexed_files else 'No attached file has an available text index.'}"
        )[:12000]
        try:
            workflow_id = engine.create_workflow(
                f"Project task: {task['title']}", {'type': 'manual', 'source': 'project_task', 'project_id': project_id, 'task_id': task_id},
                [{'kind': 'prompt', 'prompt': prompt, 'timeout_seconds': 900, 'retries': 1}],
            )
            run_id = engine.run_workflow(workflow_id, context={'project_id': project_id, 'task_id': task_id},
                background=True, owner_id='owner', device_id=pa_device, session_id=context.session_id,
                reauthenticated_at=context.reauthenticated_at, idempotency_key=f'project-task:{task_id}:{task.get("updated_at", "")}'
            )
        except Exception as exc:
            raise HTTPException(503, 'The task could not be started by the background worker') from exc
        value = store.set_task_execution(project_id, task_id, workflow_id=workflow_id, run_id=run_id, status='in_progress')
        return {'project': value, 'run_id': run_id, 'workflow_id': workflow_id, 'status': 'queued'}

    @router.get('/{project_id}/tasks/{task_id}/execution')
    def project_task_execution(project_id: str, task_id: str,
                               pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token)
        project = project_or_404(project_id)
        task = next((row for row in project['tasks'] if row['id'] == task_id), None)
        if not task:
            raise HTTPException(404, 'Project task not found')
        run_id, workflow_id = task.get('execution_run_id'), task.get('execution_workflow_id')
        if not run_id or not workflow_id:
            return {'status': 'not_started', 'task': task}
        engine = runtime.get('automations')
        binding = engine.run_binding(run_id) if engine else None
        trusted = current_trusted_request()
        if not binding or binding.get('owner_id') != 'owner' or binding.get('device_id') != pa_device or not trusted or binding.get('session_id') != trusted.session_id:
            raise HTTPException(404, 'Task execution not found')
        run = next((row for row in engine.runs(workflow_id, 100) if row['id'] == run_id), None)
        if not run:
            raise HTTPException(404, 'Task execution not found')
        status = run.get('status', 'queued')
        result = ''
        try:
            payload = json.loads(run.get('result_json') or '{}')
            steps = payload.get('completed_steps') or []
            result = str((steps[-1].get('result') or {}).get('reply') or '') if steps else ''
        except (ValueError, TypeError, AttributeError):
            pass
        if status == 'completed' and result and (task.get('status') != 'needs_review' or task.get('execution_result') != result):
            project = store.set_task_execution(project_id, task_id, result=result, status='needs_review') or project
        elif status in {'failed', 'budget_exceeded'} and task.get('status') != 'failed':
            project = store.set_task_execution(project_id, task_id, result=run.get('error') or status, status='failed') or project
        return {'status': status, 'run_id': run_id, 'workflow_id': workflow_id,
                'current_step': run.get('current_step', 0), 'started_at': run.get('started_at'),
                'updated_at': run.get('updated_at'), 'error': run.get('error'), 'result': result,
                'task': next(row for row in project['tasks'] if row['id'] == task_id)}

    @router.post('/{project_id}/milestones', status_code=201)
    def add_milestone(project_id: str, body: MilestoneCreateBody,
                      pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, write=True)
        try:
            value = store.add_milestone(project_id, **body.model_dump())
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if not value:
            raise HTTPException(404, 'Project not found')
        return {'project': value}

    @router.patch('/{project_id}/milestones/{milestone_id}')
    def update_milestone(project_id: str, milestone_id: str, body: MilestoneUpdateBody,
                         pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, write=True)
        value = store.update_milestone(project_id, milestone_id, body.model_dump(exclude_unset=True, exclude_none=True))
        if not value:
            raise HTTPException(404, 'Milestone or project not found')
        return {'project': value}

    @router.post('/{project_id}/approvals', status_code=201)
    def create_project_approval(project_id: str, body: ProjectApprovalBody,
                                pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, write=True)
        try:
            value = store.add_approval(project_id, **body.model_dump())
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if not value:
            raise HTTPException(404, 'Project not found')
        return {'project': value}

    @router.post('/{project_id}/approvals/{approval_id}/decision')
    def decide_project_approval(project_id: str, approval_id: str, body: ProjectApprovalDecisionBody,
                                pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, write=True)
        try:
            value = store.decide_approval(project_id, approval_id, **body.model_dump())
        except ValueError as exc:
            raise HTTPException(409 if 'already' in str(exc) else 422, str(exc)) from exc
        if not value:
            raise HTTPException(404, 'Proposal not found')
        return {'project': value, 'execution_started': False}

    @router.post('/{project_id}/approvals/{approval_id}/resubmit')
    def resubmit_project_approval(project_id: str, approval_id: str, body: ProjectApprovalBody,
                                  pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, write=True)
        try:
            value = store.revise_approval(project_id, approval_id, **body.model_dump())
        except ValueError as exc:
            raise HTTPException(409 if 'Only proposals' in str(exc) else 422, str(exc)) from exc
        if not value:
            raise HTTPException(404, 'Proposal not found')
        return {'project': value}

    @router.post('/{project_id}/files', status_code=201)
    def add_file(project_id: str, body: FileLinkBody,
                 pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, write=True)
        parsed = urlparse(body.url)
        if body.kind == 'link' and parsed.scheme not in {'https', 'http'}:
            raise HTTPException(422, 'Project links must use http or https')
        if body.kind == 'knowledge' and not body.knowledge_id:
            raise HTTPException(422, 'A Knowledge document id is required')
        value = store.add_file(project_id, **body.model_dump())
        if not value:
            raise HTTPException(404, 'Project not found')
        return {'project': value}

    @router.post('/{project_id}/files/upload', status_code=201)
    def upload_project_file(project_id: str, body: ProjectFileUploadBody,
                            pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, write=True)
        try:
            content = base64.b64decode(body.content_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise HTTPException(422, 'The uploaded file is not valid base64 data') from exc
        if not content or len(content) > 12 * 1024 * 1024:
            raise HTTPException(413, 'Project files must be smaller than 12 MB')
        suffix = body.filename.rsplit('.', 1)[-1].lower() if '.' in body.filename else ''
        supported = {'pdf', 'docx', 'xlsx', 'csv', 'txt', 'md', 'png', 'jpg', 'jpeg', 'webp'}
        if suffix not in supported:
            raise HTTPException(415, 'Supported files: PDF, DOCX, XLSX, CSV, TXT, Markdown, PNG, JPG and WebP')
        value = store.add_upload(project_id, title=body.filename, media_type=body.media_type, content=content)
        if not value:
            raise HTTPException(404, 'Project not found')
        return {'project': value}

    @router.get('/{project_id}/files/{file_id}/download')
    def download_project_file(project_id: str, file_id: str,
                              pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token)
        blob = store.file_blob(project_id, file_id)
        if not blob:
            raise HTTPException(404, 'Project file not found')
        filename = blob['title'].replace('"', '')
        return Response(blob['content'], media_type=blob['media_type'], headers={
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Content-Length': str(blob['size_bytes']),
            'X-Content-Type-Options': 'nosniff',
            'Cache-Control': 'no-store',
        })

    @router.get('/{project_id}/files/{file_id}/index')
    def read_project_file_index(project_id: str, file_id: str,
                                pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token)
        project_or_404(project_id)
        result = store.file_index(project_id, file_id)
        if not result:
            raise HTTPException(404, 'Project file not found')
        result['extracted_text'] = result['extracted_text'][:100_000]
        return result

    @router.patch('/{project_id}/files/{file_id}')
    def update_project_file(project_id: str, file_id: str, body: ProjectFileUpdateBody,
                            pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, write=True)
        value = store.update_file(project_id, file_id, body.model_dump())
        if not value:
            raise HTTPException(404, 'Project file not found')
        return {'project': value}

    @router.get('/{project_id}/files/search')
    def search_project_files(project_id: str, q: str = Query(min_length=1, max_length=200),
                             pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token)
        project_or_404(project_id)
        return {'files': store.search_files(project_id, q)}

    @router.get('/{project_id}/files/{file_id}/versions')
    def project_file_versions(project_id: str, file_id: str,
                              pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token)
        project_or_404(project_id)
        versions = store.file_versions(project_id, file_id)
        if versions is None:
            raise HTTPException(404, 'Project file not found')
        return {'versions': versions}

    @router.get('/{project_id}/files/{file_id}/versions/{version}/download')
    def project_file_version_download(project_id: str, file_id: str, version: int,
                                      pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token)
        blob = store.file_version_blob(project_id, file_id, version)
        if not blob:
            raise HTTPException(404, 'Project file version not found')
        return Response(blob['content'], media_type=blob['media_type'], headers={
            'Content-Disposition': f'attachment; filename="{blob["title"].replace(chr(34), "")}"',
            'Content-Length': str(blob['size_bytes']), 'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store'})

    @router.post('/{project_id}/deliverables', status_code=201)
    def save_project_deliverable(project_id: str, body: DeliverableBody,
                                 pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, write=True)
        try:
            value = store.save_deliverable(project_id, title=body.title, content=body.content, file_id=body.file_id)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if not value:
            raise HTTPException(404, 'Project or deliverable not found')
        return {'project': value}

    @router.get('/{project_id}/sources/drive')
    def list_project_drive_sources(project_id: str, q: str = Query(default='', max_length=200),
                                  pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token)
        project_or_404(project_id)
        adapter = (runtime.get('integration_adapters') or {}).get('drive')
        if adapter is None:
            raise HTTPException(409, 'Google Drive is not connected. Configure the Google OAuth client and connect Drive in Integrations first.')
        context = current_trusted_request()
        try:
            result = adapter.list_files(q=q, page_size=50, owner_id='owner', device_id=pa_device,
                                        session_id=context.session_id if context else None)
            return {'files': result.get('files', []), 'next_page_token': result.get('nextPageToken')}
        except ConnectorError as exc:
            raise HTTPException(exc.http_status, exc.safe_message) from exc

    @router.post('/{project_id}/sources/drive/{source_id}', status_code=201)
    def import_project_drive_source(project_id: str, source_id: str, body: DriveImportBody,
                                    pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, write=True)
        project_or_404(project_id)
        adapter = (runtime.get('integration_adapters') or {}).get('drive')
        if adapter is None:
            raise HTTPException(409, 'Google Drive is not connected. Configure OAuth and connect Drive first.')
        context = current_trusted_request()
        try:
            item = adapter.read_file(source_id, export_mime=body.export_mime, owner_id='owner', device_id=pa_device,
                                     session_id=context.session_id if context else None)
            meta = item.get('metadata') or {}
            value = store.add_drive_source(project_id, title=item['filename'], media_type=item['media_type'],
                content=item['content'], provider_file_id=source_id, modified_at=meta.get('modifiedTime') or '')
        except ConnectorError as exc:
            raise HTTPException(exc.http_status, exc.safe_message) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if not value:
            raise HTTPException(404, 'Project not found')
        return {'project': value, 'source_state': 'imported_snapshot'}

    @router.post('/{project_id}/discussions', status_code=201)
    def add_discussion(project_id: str, body: DiscussionCreateBody,
                       pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, write=True)
        value = store.add_thread(project_id, **body.model_dump())
        if not value:
            raise HTTPException(404, 'Project not found')
        return {'project': value}

    @router.post('/{project_id}/discussions/{thread_id}/replies', status_code=201)
    def add_discussion_reply(project_id: str, thread_id: str, body: DiscussionReplyBody,
                             pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, write=True)
        author = 'owner'
        if not store.add_reply(project_id, thread_id, author=author, content=body.content):
            raise HTTPException(404, 'Discussion not found')
        return {'project': project_or_404(project_id)}

    @router.patch('/{project_id}/discussions/{thread_id}')
    def update_discussion(project_id: str, thread_id: str, body: DiscussionUpdateBody,
                          pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, write=True)
        project_or_404(project_id)
        try:
            value = store.update_thread(project_id, thread_id, body.model_dump(exclude_unset=True))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if not value:
            raise HTTPException(404, 'Discussion not found')
        return {'project': value}

    def project_thread(project_id: str, conversation_id: str):
        if continuity is None:
            raise HTTPException(503, 'Conversation service is unavailable')
        thread = continuity.thread(conversation_id)
        if not thread or thread.get('closed_at'):
            raise HTTPException(404, 'Project conversation not found')
        meta = thread.get('context') or {}
        # Only the historic primary conversation is allowed without metadata.
        project = project_or_404(project_id)
        is_legacy_primary = project.get('conversation_id') == conversation_id
        if meta.get('project_id') not in (None, project_id) or (
            meta.get('project_id') is None and not is_legacy_primary
        ):
            raise HTTPException(404, 'Project conversation not found')
        if meta.get('conversation_kind') not in (None, 'project', ''):
            raise HTTPException(409, 'Conversation belongs to a different context')
        return thread

    @router.get('/{project_id}/conversations')
    def list_project_conversations(
        project_id: str, limit: int = Query(default=50, ge=1, le=100),
        pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None),
    ):
        authenticate(pa_device, pa_token)
        project = project_or_404(project_id)
        if continuity is None:
            raise HTTPException(503, 'Conversation service is unavailable')
        # SQL project predicate applies before limit, unlike a global history page.
        rows = continuity.list_threads(limit=limit, project_id=project_id)
        primary_id = project.get('conversation_id')
        if primary_id and all(row['id'] != primary_id for row in rows):
            legacy = continuity.thread(primary_id)
            if legacy and not legacy.get('closed_at'):
                meta = legacy.get('context') or {}
                if meta.get('project_id') in (None, project_id) and meta.get('conversation_kind') in (None, '', 'project'):
                    rows.insert(0, legacy)
        return {'project_id': project_id, 'primary_conversation_id': primary_id,
                'conversations': rows[:limit]}

    @router.post('/{project_id}/conversations', status_code=201)
    def new_project_conversation(
        project_id: str, body: ProjectConversationCreateBody,
        pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token, write=True)
        project = project_or_404(project_id)
        if continuity is None:
            raise HTTPException(503, 'Conversation service is unavailable')
        # One canonical ledger; Project IDs are validated by ProjectStore.
        thread_id = continuity.create_thread(
            body.title.strip(), device_id=device_id,
            context={'conversation_kind': 'project', 'project_id': project_id},
        )
        old_primary = project.get('conversation_id')
        if not old_primary or not continuity.thread(old_primary) or continuity.thread(old_primary).get('closed_at'):
            store.update(project_id, {'conversation_id': thread_id})
        if runtime.get('events'):
            runtime['events'].emit('project.conversation.created', project_id=project_id,
                                   conversation_id=thread_id, device_id=device_id)
        return {'conversation': continuity.thread(thread_id),
                'project_id': project_id, 'primary_conversation_id': project_or_404(project_id).get('conversation_id')}

    @router.get('/{project_id}/conversations/{conversation_id}')
    def get_project_conversation(
        project_id: str, conversation_id: str,
        pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None),
    ):
        authenticate(pa_device, pa_token)
        thread = project_thread(project_id, conversation_id)
        return {'conversation': thread, 'events': continuity.events_for_thread(thread['id'], limit=200)}

    @router.post('/{project_id}/conversation', status_code=201)
    def project_conversation(project_id: str,
                             pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        # Preserve the pre-P2-02C primary conversation contract.
        device_id = authenticate(pa_device, pa_token, write=True)
        project = project_or_404(project_id)
        if continuity is None:
            raise HTTPException(503, 'Conversation service is unavailable')
        conversation_id = project.get('conversation_id')
        previous = continuity.thread(conversation_id) if conversation_id else None
        if previous is None or previous.get('closed_at'):
            conversation_id = continuity.create_thread(
                f"Project · {project['name']} · Vishnu", device_id=device_id,
                context={'conversation_kind': 'project', 'project_id': project_id},
            )
            store.update(project_id, {'conversation_id': conversation_id})
        else:
            project_thread(project_id, conversation_id)
            if not (previous.get('context') or {}).get('project_id'):
                continuity.update_context(conversation_id, {
                    'conversation_kind': 'project', 'project_id': project_id,
                })
        return {'conversation_id': conversation_id, 'project': project_or_404(project_id)}

    @router.post('/{project_id}/activity', status_code=201)
    def record_project_activity(project_id: str, body: DiscussionReplyBody,
                                pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, write=True)
        if not store.record(project_id, actor='owner', action='asked Vishnu', target_type='conversation', detail=body.content):
            raise HTTPException(404, 'Project not found')
        return {'project': project_or_404(project_id)}

    return router
