from __future__ import annotations

from collections import Counter
import gc
import hmac
import json
import os
from pathlib import Path
import re
from types import SimpleNamespace
import threading
import time
from typing import Any

from training.deployment import DeploymentResult
from training.governance import ShadowResult
from training.self_improvement import TrainingMethod


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    return default if value is None else str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


def _token_f1(expected: str, actual: str) -> float:
    left = re.findall(r'[a-z0-9]+', str(expected or '').casefold())
    right = re.findall(r'[a-z0-9]+', str(actual or '').casefold())
    if not left or not right:
        return float(str(expected or '').strip() == str(actual or '').strip())
    a, b = Counter(left), Counter(right)
    overlap = sum((a & b).values())
    precision = overlap / max(1, len(right))
    recall = overlap / max(1, len(left))
    return 0.0 if precision + recall == 0 else (2.0 * precision * recall) / (precision + recall)


class LocalCheckpointRunner:
    """Load and serve an owner-governed trained checkpoint in the current process.

    Heavy ML dependencies are lazy imports. The runner has no approval authority;
    it only loads checkpoints that the governed deployment controller hands to it.
    Active state is an atomic pointer file so a durable mount can survive process
    restarts. On ephemeral hosts the pointer is explicitly reported as ephemeral.
    """

    def __init__(self, state_dir: str | Path, *, persistent: bool = False, events=None) -> None:
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.state_dir / 'active-model.json'
        self.persistent = bool(persistent)
        self.events = events
        self._lock = threading.RLock()
        self._loaded_key: tuple[str, str, str] | None = None
        self._tokenizer = None
        self._model = None

    @staticmethod
    def available() -> tuple[bool, str | None]:
        try:
            import torch  # noqa: F401
            import transformers  # noqa: F401
            import peft  # noqa: F401
        except Exception as exc:
            return False, f'optional local model runtime dependency unavailable: {type(exc).__name__}'
        return True, None

    @staticmethod
    def _key(model) -> tuple[str, str, str]:
        return (
            str(getattr(model, 'checkpoint_ref', '') or ''),
            str(getattr(model, 'base_model', '') or ''),
            str(getattr(model, 'method', '') or ''),
        )

    @staticmethod
    def _normalize_tokenizer(tokenizer):
        if tokenizer.pad_token_id is None:
            tokenizer.pad_token = tokenizer.eos_token
        return tokenizer

    def _release_locked(self) -> None:
        self._model = None
        self._tokenizer = None
        self._loaded_key = None
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    def _load_locked(self, model):
        key = self._key(model)
        if not key[0]:
            raise ValueError('checkpoint_ref is required')
        checkpoint = Path(key[0])
        if not checkpoint.exists():
            raise FileNotFoundError(checkpoint)
        if self._loaded_key == key and self._model is not None and self._tokenizer is not None:
            return self._tokenizer, self._model

        ok, reason = self.available()
        if not ok:
            raise RuntimeError(reason or 'local model runtime unavailable')
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self._release_locked()
        tokenizer = self._normalize_tokenizer(AutoTokenizer.from_pretrained(str(checkpoint), trust_remote_code=False))
        method = key[2].strip().lower()
        if method in {TrainingMethod.LORA.value, TrainingMethod.QLORA.value}:
            if not key[1].strip():
                raise ValueError('base_model is required for adapter checkpoints')
            base = AutoModelForCausalLM.from_pretrained(key[1], trust_remote_code=False)
            loaded = PeftModel.from_pretrained(base, str(checkpoint), is_trainable=False)
        else:
            loaded = AutoModelForCausalLM.from_pretrained(str(checkpoint), trust_remote_code=False)
        loaded.eval()
        self._tokenizer = tokenizer
        self._model = loaded
        self._loaded_key = key
        return tokenizer, loaded

    def generate(
        self,
        model,
        *,
        system: str,
        prompt: str,
        max_new_tokens: int = 96,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        with self._lock:
            tokenizer, loaded = self._load_locked(model)
            import torch

            text = f'System: {str(system or "You are Vishnu.")}\nUser: {str(prompt or "")}\nAssistant:'
            encoded = tokenizer(text, return_tensors='pt', truncation=True, max_length=2048)
            try:
                device = next(loaded.parameters()).device
                encoded = {key: value.to(device) for key, value in encoded.items()}
            except Exception:
                pass
            new_tokens = max(1, min(512, int(max_new_tokens or 96)))
            sampling = float(temperature or 0.0) > 0.0
            kwargs: dict[str, Any] = {
                'max_new_tokens': new_tokens,
                'do_sample': sampling,
                'pad_token_id': tokenizer.pad_token_id,
                'eos_token_id': tokenizer.eos_token_id,
            }
            if sampling:
                kwargs['temperature'] = max(0.05, min(2.0, float(temperature)))
            with torch.inference_mode():
                output = loaded.generate(**encoded, **kwargs)
            prompt_tokens = int(encoded['input_ids'].shape[-1])
            content = tokenizer.decode(output[0][prompt_tokens:], skip_special_tokens=True).strip()
            output_tokens = max(0, int(output[0].shape[-1]) - prompt_tokens)
        latency_ms = max(0.0, (time.perf_counter() - started) * 1000.0)
        return {
            'content': content,
            'input_tokens': prompt_tokens,
            'output_tokens': output_tokens,
            'total_tokens': prompt_tokens + output_tokens,
            'latency_ms': latency_ms,
            'estimated_cost': 0.0,
        }

    def activate(self, model) -> dict[str, Any]:
        # Loading plus one-token inference proves this exact checkpoint can run.
        self.generate(
            model,
            system='Runtime readiness probe. Return any token.',
            prompt='probe',
            max_new_tokens=1,
            temperature=0.0,
        )
        state = {
            'schema_version': 1,
            'model_id': str(getattr(model, 'model_id', '') or ''),
            'checkpoint_ref': str(getattr(model, 'checkpoint_ref', '') or ''),
            'base_model': str(getattr(model, 'base_model', '') or ''),
            'method': str(getattr(model, 'method', '') or ''),
            'deployment_ref': f'local-transformers:{str(getattr(model, "model_id", "") or "unknown")}',
            'activated_at': time.time(),
            'persistent': self.persistent,
        }
        temp = self.state_path.with_suffix('.tmp')
        temp.write_text(json.dumps(state, sort_keys=True, indent=2), encoding='utf-8')
        temp.replace(self.state_path)
        if self.events is not None:
            self.events.emit(
                'training.local_runtime_activated',
                model_id=state['model_id'],
                persistent=self.persistent,
                automatic=False,
            )
        return state

    def active_state(self) -> dict[str, Any] | None:
        if not self.state_path.exists():
            return None
        try:
            value = json.loads(self.state_path.read_text(encoding='utf-8'))
        except Exception:
            return None
        return value if isinstance(value, dict) else None

    def _state_model(self):
        state = self.active_state()
        if not state:
            raise RuntimeError('no governed trained model is active')
        return SimpleNamespace(
            model_id=state.get('model_id'),
            checkpoint_ref=state.get('checkpoint_ref'),
            base_model=state.get('base_model'),
            method=state.get('method'),
        )

    def running_checkpoint(self, deployment_ref: str) -> str | None:
        state = self.active_state()
        if not state or not hmac.compare_digest(str(state.get('deployment_ref') or ''), str(deployment_ref or '')):
            return None
        checkpoint = str(state.get('checkpoint_ref') or '')
        if not checkpoint or not Path(checkpoint).exists():
            return None
        try:
            model = self._state_model()
            # This reuses the cached model when the process is already serving it,
            # and reloads the exact checkpoint after a durable process restart.
            self.generate(model, system='Runtime verification probe.', prompt='probe', max_new_tokens=1)
        except Exception:
            return None
        return checkpoint

    def generate_active(self, messages: list[dict[str, Any]], *, max_tokens: int = 96, temperature: float = 0.0) -> dict[str, Any]:
        system_parts: list[str] = []
        dialogue: list[str] = []
        for item in messages[-64:]:
            if not isinstance(item, dict):
                continue
            role = str(item.get('role') or 'user').strip().lower()
            content = str(item.get('content') or '')
            if role == 'system':
                system_parts.append(content)
            elif role in {'user', 'assistant'}:
                dialogue.append(f'{role.title()}: {content}')
        prompt = '\n'.join(dialogue) if dialogue else ''
        return self.generate(
            self._state_model(),
            system='\n'.join(system_parts) or 'You are Vishnu.',
            prompt=prompt,
            max_new_tokens=max_tokens,
            temperature=temperature,
        )

    def status(self) -> dict[str, Any]:
        available, reason = self.available()
        state = self.active_state()
        return {
            'available': bool(available),
            'reason': reason,
            'persistent': self.persistent,
            'active': bool(state),
            'active_model_id': None if not state else state.get('model_id'),
            'deployment_ref': None if not state else state.get('deployment_ref'),
            'checkpoint_present': bool(state and Path(str(state.get('checkpoint_ref') or '')).exists()),
            'model_output_authority': False,
            'automatic_activation': False,
        }


class LocalTransformersShadowBackend:
    backend_id = 'local_transformers'

    def __init__(self, runner: LocalCheckpointRunner, *, minimum_similarity: float = 0.60) -> None:
        self.runner = runner
        self.minimum_similarity = max(0.0, min(1.0, float(minimum_similarity)))

    def available(self) -> tuple[bool, str | None]:
        return self.runner.available()

    def evaluate_shadow(self, model, request, authoritative_response) -> ShadowResult:
        candidate = self.runner.generate(
            model,
            system=str(getattr(request, 'system', '') or 'You are Vishnu.'),
            prompt=str(getattr(request, 'prompt', '') or ''),
            max_new_tokens=int(getattr(request, 'max_tokens', None) or 96),
            temperature=0.0,
        )
        authoritative = str(getattr(authoritative_response, 'content', '') or '')
        score = _token_f1(authoritative, candidate['content'])
        # The authoritative response is the live baseline. Using 1.0 here makes
        # the default no-regression shadow gate intentionally strict; an owner
        # may explicitly allow a bounded negative quality delta if desired.
        return ShadowResult(
            passed=score >= self.minimum_similarity,
            quality_score=score,
            baseline_quality_score=1.0,
            latency_ms=float(candidate['latency_ms']),
            estimated_cost=0.0,
        )


class LocalTransformersDeploymentBackend:
    backend_id = 'local_transformers'

    def __init__(
        self,
        runner: LocalCheckpointRunner,
        *,
        allow_ephemeral_activation: bool = False,
    ) -> None:
        self.runner = runner
        self.allow_ephemeral_activation = bool(allow_ephemeral_activation)

    def available(self) -> tuple[bool, str | None]:
        if not self.runner.persistent and not self.allow_ephemeral_activation:
            return False, 'local trained-model runtime is ephemeral; durable activation is required unless explicitly allowed'
        return self.runner.available()

    def deploy(self, model) -> DeploymentResult:
        ok, reason = self.available()
        if not ok:
            raise RuntimeError(reason or 'local trained-model deployment backend unavailable')
        state = self.runner.activate(model)
        return DeploymentResult(
            checkpoint_ref=str(state['checkpoint_ref']),
            deployment_ref=str(state['deployment_ref']),
            metadata={
                'runtime': self.backend_id,
                'persistent': self.runner.persistent,
                'ephemeral_activation_explicitly_allowed': self.allow_ephemeral_activation,
                'exact_checkpoint_loaded': True,
            },
        )

    def running_checkpoint(self, deployment_ref: str) -> str | None:
        return self.runner.running_checkpoint(deployment_ref)


def attach_local_model_runtime(
    runtime: dict,
    *,
    enabled: bool | None = None,
    persistent: bool | None = None,
    allow_ephemeral_activation: bool | None = None,
    state_dir: str | Path | None = None,
    runner: LocalCheckpointRunner | None = None,
) -> dict:
    """Attach real local shadow + deployment backends to an existing Vishnu runtime.

    This is intentionally an explicit release-environment attachment instead of
    a new authority layer. The existing training registry, shadow ledger, owner
    approval flow and deployment controller remain authoritative.
    """

    if enabled is None:
        enabled = _env_bool('VISHNU_LOCAL_TRAINED_MODEL_RUNTIME', False)
    if not enabled:
        runtime['trained_model_runtime'] = None
        return runtime
    if persistent is None:
        persistent = _env_bool('VISHNU_TRAINED_MODEL_RUNTIME_PERSISTENT', False)
    if allow_ephemeral_activation is None:
        allow_ephemeral_activation = _env_bool('VISHNU_ALLOW_EPHEMERAL_MODEL_ACTIVATION', False)
    if state_dir is None:
        settings = runtime.get('settings')
        data_dir = getattr(settings, 'data_dir', None)
        if data_dir is None:
            raise RuntimeError('runtime data directory is unavailable')
        state_dir = Path(data_dir) / 'trained-model-runtime'

    events = runtime.get('events')
    active_runner = runner or LocalCheckpointRunner(state_dir, persistent=bool(persistent), events=events)
    shadow = LocalTransformersShadowBackend(active_runner)
    deployment = LocalTransformersDeploymentBackend(
        active_runner,
        allow_ephemeral_activation=bool(allow_ephemeral_activation),
    )

    shadow_runtime = runtime.get('shadow_qualification')
    deployment_controller = runtime.get('model_deployment')
    if shadow_runtime is None or not hasattr(shadow_runtime, 'backends'):
        raise RuntimeError('governed shadow qualification runtime is unavailable')
    if deployment_controller is None or not hasattr(deployment_controller, 'backends'):
        raise RuntimeError('governed model deployment controller is unavailable')
    shadow_runtime.backends[shadow.backend_id] = shadow
    deployment_controller.backends[deployment.backend_id] = deployment
    runtime['trained_model_runtime'] = active_runner
    runtime['trained_model_shadow_backend'] = shadow
    runtime['trained_model_deployment_backend'] = deployment
    if events is not None:
        available, reason = active_runner.available()
        events.emit(
            'training.local_runtime_attached',
            available=bool(available),
            reason=reason,
            persistent=bool(persistent),
            ephemeral_activation_allowed=bool(allow_ephemeral_activation),
            automatic_activation=False,
        )
    return runtime
