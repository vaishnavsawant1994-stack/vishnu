from __future__ import annotations

import hmac
import json
import os
from pathlib import Path
import time

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra='ignore')
    role: str = Field(min_length=1, max_length=32)
    content: str = Field(default='', max_length=200000)


class ChatCompletionBody(BaseModel):
    model_config = ConfigDict(extra='ignore')
    model: str | None = Field(default=None, max_length=300)
    messages: list[ChatMessage] = Field(min_length=1, max_length=64)
    max_tokens: int = Field(default=96, ge=1, le=512)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)


def _secret(name: str) -> str:
    return str(os.getenv(name, '') or '').strip()


def _require_bearer(authorization: str | None, *, env_name: str, unavailable_message: str) -> None:
    expected = _secret(env_name)
    if not expected:
        raise HTTPException(503, unavailable_message)
    prefix = 'bearer '
    supplied = str(authorization or '').strip()
    if not supplied.casefold().startswith(prefix):
        raise HTTPException(401, 'Bearer authentication required')
    token = supplied[len(prefix):].strip()
    if not token or not hmac.compare_digest(token, expected):
        raise HTTPException(401, 'Invalid bearer credential')


def trained_model_runtime_router(runtime: dict) -> APIRouter:
    router = APIRouter(prefix='/trained-model', tags=['trained-model-runtime'])

    def runner():
        value = runtime.get('trained_model_runtime')
        if value is None:
            raise HTTPException(503, 'trained-model runtime is not enabled')
        return value

    def production_pipeline():
        return runtime.get('production_model_pipeline')

    @router.get('/health')
    def health():
        value = runner().status()
        deployment = runtime.get('model_deployment')
        shadow = runtime.get('shadow_qualification')
        production = production_pipeline()
        return {
            'ok': bool(value.get('available')),
            'runtime': value,
            'deployment': deployment.status() if deployment is not None else {'backends': {}},
            'shadow': shadow.status() if shadow is not None else {'backends': {}},
            'production_pipeline': production.status() if production is not None else None,
            'automatic_activation': False,
            'model_output_authority': False,
        }

    @router.get('/qualification')
    def qualification():
        settings = runtime.get('settings')
        data_dir = Path(getattr(settings, 'data_dir', '.'))
        path = data_dir / 'model-runtime-qualification' / 'qualification.json'
        if not path.exists():
            value: dict = {'qualified': False, 'reason': 'qualification_not_run'}
        else:
            try:
                loaded = json.loads(path.read_text(encoding='utf-8'))
            except Exception:
                raise HTTPException(500, 'qualification evidence is unreadable')
            value = loaded if isinstance(loaded, dict) else {'qualified': False, 'reason': 'qualification_invalid'}
        production = production_pipeline()
        return {
            **value,
            'production_pipeline': production.status() if production is not None else None,
            'canary_qualification_is_not_production_activation': True,
        }

    @router.get('/production')
    def production_status():
        production = production_pipeline()
        if production is None:
            raise HTTPException(503, 'production model pipeline is not enabled')
        return production.status()

    @router.get('/v1/models')
    def models(authorization: str | None = Header(default=None)):
        _require_bearer(
            authorization,
            env_name='VISHNU_TRAINED_MODEL_API_KEY',
            unavailable_message='trained-model inference API key is not configured',
        )
        state = runner().active_state()
        if not state:
            return {'object': 'list', 'data': []}
        return {
            'object': 'list',
            'data': [{
                'id': str(state.get('model_id') or 'vishnu-trained'),
                'object': 'model',
                'created': int(float(state.get('activated_at') or time.time())),
                'owned_by': 'vishnu-owner-governed',
            }],
        }

    @router.post('/v1/chat/completions')
    def chat_completions(body: ChatCompletionBody, authorization: str | None = Header(default=None)):
        _require_bearer(
            authorization,
            env_name='VISHNU_TRAINED_MODEL_API_KEY',
            unavailable_message='trained-model inference API key is not configured',
        )
        state = runner().active_state()
        if not state:
            raise HTTPException(503, 'no owner-approved trained model is active')
        result = runner().generate_active(
            [item.model_dump() for item in body.messages],
            max_tokens=body.max_tokens,
            temperature=body.temperature,
        )
        model_id = str(state.get('model_id') or body.model or 'vishnu-trained')
        return {
            'id': f'chatcmpl-vishnu-{int(time.time() * 1000)}',
            'object': 'chat.completion',
            'created': int(time.time()),
            'model': model_id,
            'choices': [{
                'index': 0,
                'message': {'role': 'assistant', 'content': result['content']},
                'finish_reason': 'stop',
            }],
            'usage': {
                'prompt_tokens': int(result['input_tokens']),
                'completion_tokens': int(result['output_tokens']),
                'total_tokens': int(result['total_tokens']),
            },
        }

    @router.post('/release/deploy/{model_id}')
    def deploy(model_id: str, authorization: str | None = Header(default=None)):
        _require_bearer(
            authorization,
            env_name='VISHNU_MODEL_RELEASE_TOKEN',
            unavailable_message='trained-model release controller token is not configured',
        )
        controller = runtime.get('model_deployment')
        if controller is None:
            raise HTTPException(503, 'model deployment controller unavailable')
        production = production_pipeline()
        try:
            if production is not None:
                production.assert_release_ready(model_id)
            model, result = controller.deploy(
                model_id,
                backend_id='local_transformers',
                actor='authenticated_release_controller',
            )
        except KeyError as exc:
            raise HTTPException(404, 'trained model not found') from exc
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(409, str(exc)) from exc
        return {
            'ok': True,
            'model_id': model.model_id,
            'status': model.status.value,
            'deployment_ref': result.deployment_ref,
            'checkpoint_verified': True,
            'durable_artifact_verified': production is not None,
            'automatic': False,
        }

    @router.post('/release/rollback/{active_model_id}')
    def rollback(active_model_id: str, authorization: str | None = Header(default=None)):
        _require_bearer(
            authorization,
            env_name='VISHNU_MODEL_RELEASE_TOKEN',
            unavailable_message='trained-model release controller token is not configured',
        )
        controller = runtime.get('model_deployment')
        if controller is None:
            raise HTTPException(503, 'model deployment controller unavailable')
        try:
            model, result = controller.rollback(
                active_model_id,
                backend_id='local_transformers',
                actor='authenticated_release_controller',
            )
        except KeyError as exc:
            raise HTTPException(404, 'rollback model not found') from exc
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(409, str(exc)) from exc
        return {
            'ok': True,
            'rolled_back_to_model_id': model.model_id,
            'deployment_ref': result.deployment_ref,
            'checkpoint_verified': True,
            'durable_artifact_verified': production_pipeline() is not None,
            'automatic': False,
        }

    return router
