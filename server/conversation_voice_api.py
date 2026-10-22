from __future__ import annotations

import asyncio
import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from agent.executor import ConfirmationRequired, ExecutionCancelled
from models.router import ModelError
from security.request_context import current_trusted_request
from server.logical_request import validate_request_id
from server.logical_request_middleware import current_logical_request_id
from server.request_aware_pwa_state import RequestAwareIphonePwaState


class CanonicalVoiceTurnBody(BaseModel):
    # Keep the Stage 1 qualified logical-turn body contract exactly intact.
    # Modality is non-authoritative transport metadata and is read from a header.
    request_id: str = Field(min_length=36, max_length=64)
    transcript: str = Field(min_length=1, max_length=8000)
    conversation_id: str | None = Field(default=None, max_length=80)
    workspace_id: str | None = Field(default=None, max_length=80)

    @field_validator('request_id')
    @classmethod
    def request_id_is_safe(cls, value: str) -> str:
        return validate_request_id(value)


class VoiceBargeBody(BaseModel):
    speaking: bool = True
    request_id: str | None = Field(default=None, max_length=64)

    @field_validator('request_id')
    @classmethod
    def request_id_is_safe(cls, value: str | None) -> str | None:
        return validate_request_id(value) if value else None


class VoiceClientEventBody(BaseModel):
    event: Literal[
        'listening_started',
        'tts_started',
        'tts_completed',
        'tts_error',
        'playback_interrupted',
    ]
    request_id: str | None = Field(default=None, max_length=64)
    detail: str = Field(default='', max_length=160)

    @field_validator('request_id')
    @classmethod
    def request_id_is_safe(cls, value: str | None) -> str | None:
        return validate_request_id(value) if value else None


class CanonicalCancelBody(BaseModel):
    request_id: str = Field(min_length=36, max_length=64)

    @field_validator('request_id')
    @classmethod
    def request_id_is_safe(cls, value: str) -> str:
        return validate_request_id(value)


def conversation_voice_router(runtime, executor):
    """Stage 3 transport adapter over the existing canonical turn/conversation runtime.

    This router intentionally owns no conversation, request, approval, tool, or
    semantic-state truth. CanonicalTurnRuntime/ContinuityService own the turn and
    ledger, Stage 2 owns governed approvals/dispatch, and RuntimeStateAuthority
    projects factual lifecycle events. Voice is input/output transport only.
    """

    router = APIRouter(prefix='/iphone/api', tags=['conversation-voice-v1'])
    registry = runtime['device_registry']
    continuity = runtime.get('continuity')
    events = runtime.get('events')
    runtime_state = runtime.get('runtime_state')
    transport_state = RequestAwareIphonePwaState(cancel_turn=executor.cancel_turn)

    def emit(name: str, **payload):
        if events:
            events.emit(name, **payload)

    def require_owner():
        context = current_trusted_request()
        if context is None:
            raise HTTPException(401, 'Trusted owner session required')
        if not registry.is_active(context.device_id):
            raise HTTPException(401, 'Trusted device is revoked')
        if hasattr(registry, 'authorize') and not registry.authorize(context.device_id, 'ai:chat'):
            raise HTTPException(403, 'This device is not permitted to use conversation or voice')
        return context

    @staticmethod
    def input_modality(request: Request) -> str:
        # This header never conveys identity/authorization. It is safe metadata
        # used only to describe how the already-authenticated owner supplied text.
        value = str(request.headers.get('x-personal-ai-input-modality') or 'text').strip().lower()
        return value if value in {'text', 'voice'} else 'text'

    def turn_snapshot(request_id: str) -> dict:
        lookup = getattr(executor, 'turn', None)
        turn = lookup(request_id) if callable(lookup) else None
        return dict(turn or {})

    def conversation_title(conversation_id: str | None, transcript: str | None = None) -> str | None:
        if not conversation_id or continuity is None:
            return None
        thread = continuity.thread(conversation_id)
        if not thread:
            return None
        if transcript and thread.get('title') in {'New conversation', 'Current context', 'Primary Vishnu Context'}:
            try:
                thread = continuity.rename_thread(conversation_id, transcript[:72])
            except Exception:
                thread = continuity.thread(conversation_id) or thread
        return str(thread.get('title') or '') or None

    def stale_output(request_id: str | None) -> bool:
        if not request_id or runtime_state is None:
            return False
        current = runtime_state.snapshot().request_id
        return bool(current and str(current) != str(request_id))

    @router.post('/voice/turn')
    async def voice_turn(body: CanonicalVoiceTurnBody, request: Request):
        context = require_owner()
        logical_request_id = current_logical_request_id()
        if not logical_request_id or logical_request_id != body.request_id:
            raise HTTPException(409, {
                'code': 'logical_request_mismatch',
                'message': 'Voice transport request identity does not match the canonical logical request.',
            })
        transcript = body.transcript.strip()
        # Server-side verified association. Workspace IDs and Project names
        # supplied in arbitrary user prompts are never an authority boundary.
        related_thread = continuity.thread(body.conversation_id) if (continuity and body.conversation_id) else None
        related_meta = (related_thread or {}).get('context') or {}
        if body.workspace_id is not None:
            if (not related_thread or related_thread.get('closed_at')
                or related_meta.get('conversation_kind') != 'workspace'
                or related_meta.get('workspace_id') != body.workspace_id
                or related_meta.get('owner_id') != 'owner'):
                raise HTTPException(404, 'Workspace conversation not found')
            workspace_store = runtime.get('workspace_store')
            workspace = workspace_store.get('owner', body.workspace_id) if workspace_store else None
            if not workspace or workspace.get('status') != 'active':
                raise HTTPException(404, 'Workspace not found or archived')
            project_store = runtime.get('base_project_store')
            project_names = []
            if project_store:
                for link in workspace_store.linked_projects('owner', body.workspace_id)[:30]:
                    project = project_store.get(link['resource_id'])
                    if project and project.get('status') != 'archived':
                        project_names.append(str(project.get('name') or '')[:100] + ' [' +
                                             str(project.get('status') or 'unknown') + ']')
            context_text = (
                'WORKSPACE REFERENCE FROM TRUSTED SERVER (not tool permission):\n'
                'Workspace name: ' + str(workspace['name'])[:120] + '\n'
                'Description: ' + str(workspace.get('description') or '')[:950] + '\n'
                'Linked Projects: ' + ('; '.join(project_names)[:2400] or 'None') + '\n'
                'Do not claim external actions completed without verified tool evidence.\n\n'
                'Owner request: ' + transcript
            )
            transcript = context_text[:8000]
        elif related_meta.get('conversation_kind') == 'workspace':
            raise HTTPException(409, 'Workspace conversation requires verified Workspace ID')
        elif related_meta.get('conversation_kind') == 'project':
            project_id = related_meta.get('project_id')
            project_store = runtime.get('base_project_store')
            project = project_store.get(project_id) if project_store and isinstance(project_id, str) else None
            if not project or project.get('status') == 'archived' or related_thread.get('closed_at'):
                raise HTTPException(404, 'Project voice context is unavailable')
            original_request = transcript
            transcript = (
                'PROJECT REFERENCE FROM TRUSTED SERVER (not execution authority):\n'
                'Project: ' + str(project.get('name') or '')[:120] + '\n'
                'Goal: ' + str(project.get('goal') or '')[:500] + '\n'
                'Owner request: ' + original_request
            )[:8000]
        modality = input_modality(request)
        try:
            metadata_reader = getattr(registry, 'metadata', None)
            metadata = metadata_reader(context.device_id) if callable(metadata_reader) else {}
            saved_preferences = json.loads(metadata.get('ui.preferences', '{}'))
        except (TypeError, ValueError, json.JSONDecodeError):
            saved_preferences = {}
        response_detail = saved_preferences.get('chat_response_detail', 'detailed')
        if response_detail not in {'concise', 'balanced', 'detailed'}:
            response_detail = 'detailed'
        response_style = saved_preferences.get('chat_response_style', 'clear_step_by_step')
        if response_style not in {'clear_step_by_step', 'warm_conversational', 'technical', 'direct'}:
            response_style = 'clear_step_by_step'
        cancel_event = transport_state.begin_turn(context.device_id)
        emit(
            'voice.transcript',
            request_id=body.request_id,
            device_id=context.device_id,
            source='iphone-pwa',
            input_modality=modality,
            text=transcript,
            final=True,
        )
        try:
            reply = await asyncio.to_thread(
                executor.chat,
                transcript,
                cancel_event=cancel_event,
                conversation_id=body.conversation_id,
                input_modality=modality,
                response_detail=response_detail,
                response_style=response_style,
            )
        except ExecutionCancelled:
            emit('voice.turn.cancelled', request_id=body.request_id, device_id=context.device_id, source='iphone-pwa')
            raise HTTPException(409, {'code': 'turn_cancelled', 'message': 'This canonical turn was cancelled.'})
        except ConfirmationRequired as exc:
            turn = turn_snapshot(body.request_id)
            conversation_id = turn.get('conversation_id') or body.conversation_id
            emit(
                'voice.approval.required',
                request_id=body.request_id,
                approval_id=exc.approval_id,
                device_id=context.device_id,
                source='iphone-pwa',
            )
            return JSONResponse(status_code=202, content={
                'status': 'approval_required',
                'request_id': body.request_id,
                'reply': f'This action needs your approval before I can use {exc.tool_name}.',
                'approval': {
                    'id': exc.approval_id,
                    'request_id': body.request_id,
                    'tool': exc.tool_name,
                    'description': exc.description or f'Use {exc.tool_name}',
                    'expires_at': exc.expires_at,
                },
                'device_id': context.device_id,
                'conversation_id': conversation_id,
                'conversation_title': conversation_title(conversation_id, transcript),
            })
        except ModelError as exc:
            emit(
                'voice.turn.transport_error',
                request_id=body.request_id,
                device_id=context.device_id,
                source='iphone-pwa',
                code=exc.code,
            )
            raise HTTPException(exc.status_code, {'code': exc.code, 'message': exc.user_message})
        except HTTPException:
            raise
        except Exception as exc:
            emit(
                'voice.turn.transport_error',
                request_id=body.request_id,
                device_id=context.device_id,
                source='iphone-pwa',
                code=type(exc).__name__,
            )
            raise HTTPException(502, {
                'code': 'turn_failed',
                'message': 'The canonical Vishnu turn could not be completed safely.',
            })
        finally:
            transport_state.finish(context.device_id, cancel_event)

        turn = turn_snapshot(body.request_id)
        conversation_id = turn.get('conversation_id') or body.conversation_id
        title = conversation_title(conversation_id, transcript)
        emit(
            'voice.reply',
            request_id=body.request_id,
            conversation_id=conversation_id,
            device_id=context.device_id,
            source='iphone-pwa',
            text=str(reply),
        )
        return {
            'status': 'completed',
            'request_id': body.request_id,
            'reply': str(reply),
            'device_id': context.device_id,
            'conversation_id': conversation_id,
            'conversation_title': title,
        }

    @router.post('/voice/barge')
    def voice_barge(body: VoiceBargeBody):
        context = require_owner()
        # Barge-in while an answer is being spoken is an output interruption.
        # It must not cancel/delete an already completed canonical turn or tool
        # operation. A genuinely new R2 will cooperatively cancel an in-flight R1
        # through begin_turn(), preserving Stage 1/Stage 2 cancellation semantics.
        emit(
            'voice.playback.interrupted',
            request_id=body.request_id,
            device_id=context.device_id,
            source='iphone-pwa',
            speaking=body.speaking,
        )
        emit(
            'voice.barge_in',
            request_id=body.request_id,
            device_id=context.device_id,
            source='iphone-pwa',
        )
        return {'ok': True, 'cancelled_server_turn': False, 'playback_interrupted': True}

    @router.post('/voice/operation/cancel')
    def cancel_canonical_operation(body: CanonicalCancelBody):
        context = require_owner()
        cooperative = transport_state.cancel(context.device_id, request_id=body.request_id)
        # Canonical cancellation is idempotent. Call the durable authority here as
        # well so the response returns the authoritative turn even when no local
        # transport lease exists (for example after a reload/process handoff).
        result = executor.cancel_turn(body.request_id)
        emit(
            'voice.operation.cancel_requested',
            request_id=body.request_id,
            device_id=context.device_id,
            source='iphone-pwa',
            cooperative_cancelled=cooperative,
        )
        return {
            'ok': True,
            'request_id': body.request_id,
            'cooperative_cancelled': cooperative,
            'turn': result,
        }

    @router.post('/voice/client-event')
    def voice_client_event(body: VoiceClientEventBody):
        context = require_owner()
        if body.request_id and stale_output(body.request_id):
            emit(
                'voice.output.stale_ignored',
                request_id=body.request_id,
                device_id=context.device_id,
                source='iphone-pwa',
                output_event=body.event,
            )
            return {'ok': True, 'stale': True}
        event_map = {
            'listening_started': 'voice.listening.started',
            'tts_started': 'voice.tts.started',
            'tts_completed': 'voice.tts.completed',
            'tts_error': 'voice.tts.failed',
            'playback_interrupted': 'voice.playback.interrupted',
        }
        emit(
            event_map[body.event],
            request_id=body.request_id,
            device_id=context.device_id,
            source='iphone-pwa',
            detail=body.detail,
        )
        return {'ok': True, 'stale': False}

    @router.get('/conversations')
    def conversation_list(
        q: str = '', limit: int = 50, include_closed: bool = False,
        kind: Literal['personal', 'work'] | None = None,
    ):
        context = require_owner()
        if continuity is None:
            raise HTTPException(503, 'Conversation continuity is unavailable')
        active = continuity.active_for_device(context.device_id)
        bounded_limit = max(1, min(limit, 100))
        # Stage-3 is the production GET authority. Keep it aligned with the
        # legacy compatibility route so Work cannot silently list Personal chats.
        # Work vs Personal is a saved owner-domain organization, not ACL isolation.
        rows = continuity.list_threads(
            q, limit=bounded_limit, include_closed=include_closed, kind=kind,
        )
        return {
            'active_conversation_id': active['id'] if active else None,
            'conversations': rows,
        }

    @router.get('/conversations/{conversation_id}')
    def conversation_get(conversation_id: str, after_sequence: int = 0, limit: int = 200):
        context = require_owner()
        if continuity is None:
            raise HTTPException(503, 'Conversation continuity is unavailable')
        thread = continuity.thread(conversation_id)
        if not thread or thread.get('closed_at'):
            raise HTTPException(404, 'Conversation not found')
        continuity.set_active(context.device_id, conversation_id)
        bounded_limit = max(1, min(int(limit), 200))
        events_page = continuity.events_for_thread(
            conversation_id,
            after_sequence=max(0, int(after_sequence)),
            limit=bounded_limit,
        )
        return {
            'conversation': continuity.thread(conversation_id),
            'events': events_page,
            'after_sequence': max(0, int(after_sequence)),
            'next_after_sequence': events_page[-1]['sequence'] if events_page else max(0, int(after_sequence)),
            'limit': bounded_limit,
        }

    return router
