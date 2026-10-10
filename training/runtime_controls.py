from __future__ import annotations

import math
from pathlib import Path
import time
from typing import Any

from training.governance import GovernedLocalPeftTrainerBackend
from training.self_improvement import TrainingArtifact, TrainingMethod


class BoundedLocalPeftTrainerBackend(GovernedLocalPeftTrainerBackend):
    """Local PEFT trainer that enforces owner hyperparameters and runtime limits.

    The base training implementation provides real LoRA/QLoRA/full fine-tuning.
    This stricter backend validates the owner-provided tuning surface, applies
    only an allowlisted set of bounded hyperparameters and installs a Trainer
    callback that stops the job once the owner runtime ceiling is reached.
    It never downloads executable remote code and never publishes artifacts.
    """

    backend_id = 'local_peft'

    _BOUNDS: dict[str, tuple[type, float, float]] = {
        'num_train_epochs': (float, 0.1, 20.0),
        'per_device_train_batch_size': (int, 1, 64),
        'per_device_eval_batch_size': (int, 1, 64),
        'gradient_accumulation_steps': (int, 1, 128),
        'learning_rate': (float, 1e-8, 1.0),
        'logging_steps': (int, 1, 10000),
        'max_length': (int, 128, 8192),
        'lora_r': (int, 1, 256),
        'lora_alpha': (int, 1, 2048),
        'lora_dropout': (float, 0.0, 0.5),
    }

    @classmethod
    def normalized_hyperparameters(cls, settings) -> dict[str, Any]:
        raw = getattr(settings, 'hyperparameters', {}) or {}
        if not isinstance(raw, dict):
            raise ValueError('hyperparameters must be an object')
        unknown = sorted(set(raw) - set(cls._BOUNDS))
        if unknown:
            raise ValueError(f'unsupported training hyperparameter(s): {unknown}')
        values: dict[str, Any] = {}
        for key, value in raw.items():
            kind, minimum, maximum = cls._BOUNDS[key]
            if isinstance(value, bool):
                raise ValueError(f'{key} must be numeric')
            try:
                parsed = kind(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f'{key} must be numeric') from exc
            if not minimum <= float(parsed) <= maximum:
                raise ValueError(f'{key} must be between {minimum} and {maximum}')
            values[key] = parsed
        return values

    def train(self, snapshot, settings, output_dir: Path) -> TrainingArtifact:
        ok, reason = self.available()
        if not ok:
            raise RuntimeError(reason or 'local training backend unavailable')
        if not str(getattr(settings, 'base_model', '') or '').strip():
            raise ValueError('base_model is required for local training')

        hp = self.normalized_hyperparameters(settings)
        from datasets import load_dataset
        from peft import LoraConfig, TaskType, get_peft_model, prepare_model_for_kbit_training
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            BitsAndBytesConfig,
            DataCollatorForLanguageModeling,
            Trainer,
            TrainerCallback,
            TrainingArguments,
        )

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        files = {'train': snapshot.train_path}
        if snapshot.validation_records:
            files['validation'] = snapshot.validation_path
        dataset = load_dataset('json', data_files=files)

        tokenizer = AutoTokenizer.from_pretrained(settings.base_model, trust_remote_code=False)
        if tokenizer.pad_token_id is None:
            tokenizer.pad_token = tokenizer.eos_token
        max_length = int(hp.get('max_length', 2048))

        def tokenize(batch):
            texts = [
                f"### Instruction\n{instruction}\n\n### Response\n{response}{tokenizer.eos_token or ''}"
                for instruction, response in zip(batch['instruction'], batch['response'])
            ]
            return tokenizer(texts, truncation=True, max_length=max_length)

        tokenized = dataset.map(tokenize, batched=True, remove_columns=dataset['train'].column_names)
        model_kwargs: dict[str, Any] = {'trust_remote_code': False}
        if settings.method is TrainingMethod.QLORA:
            model_kwargs['quantization_config'] = BitsAndBytesConfig(load_in_4bit=True)
        model = AutoModelForCausalLM.from_pretrained(settings.base_model, **model_kwargs)

        if settings.method in {TrainingMethod.LORA, TrainingMethod.QLORA}:
            if settings.method is TrainingMethod.QLORA:
                model = prepare_model_for_kbit_training(model)
            model = get_peft_model(
                model,
                LoraConfig(
                    r=int(hp.get('lora_r', 16)),
                    lora_alpha=int(hp.get('lora_alpha', 32)),
                    lora_dropout=float(hp.get('lora_dropout', 0.05)),
                    bias='none',
                    task_type=TaskType.CAUSAL_LM,
                ),
            )

        max_runtime = int(getattr(settings, 'max_runtime_seconds', 6 * 3600) or 6 * 3600)
        max_runtime = max(60, min(7 * 24 * 3600, max_runtime))
        started = time.monotonic()

        class RuntimeCeilingCallback(TrainerCallback):
            timed_out = False

            def _check(self, control):
                if time.monotonic() - started >= max_runtime:
                    self.timed_out = True
                    control.should_training_stop = True
                return control

            def on_step_end(self, args, state, control, **kwargs):
                return self._check(control)

            def on_epoch_end(self, args, state, control, **kwargs):
                return self._check(control)

        runtime_callback = RuntimeCeilingCallback()
        learning_rate = float(
            hp.get('learning_rate', 2e-4 if settings.method is not TrainingMethod.FULL else 2e-5)
        )
        args = TrainingArguments(
            output_dir=str(output_dir / 'runs'),
            num_train_epochs=float(hp.get('num_train_epochs', 1.0)),
            per_device_train_batch_size=int(hp.get('per_device_train_batch_size', 1)),
            per_device_eval_batch_size=int(hp.get('per_device_eval_batch_size', 1)),
            gradient_accumulation_steps=int(hp.get('gradient_accumulation_steps', 4)),
            learning_rate=learning_rate,
            logging_steps=int(hp.get('logging_steps', 10)),
            save_strategy='epoch',
            report_to=[],
            remove_unused_columns=False,
        )
        trainer = Trainer(
            model=model,
            args=args,
            train_dataset=tokenized['train'],
            eval_dataset=tokenized.get('validation'),
            data_collator=DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False),
            callbacks=[runtime_callback],
        )
        train_result = trainer.train()
        runtime_seconds = max(0.0, time.monotonic() - started)
        if runtime_callback.timed_out or runtime_seconds > max_runtime + 5:
            raise TimeoutError('training exceeded owner maximum runtime')

        metrics: dict[str, Any] = {
            'train_loss': float(getattr(train_result, 'training_loss', 0.0)),
            'runtime_seconds': runtime_seconds,
            'estimated_cost': 0.0,
            'hyperparameters': hp,
            'resource': {
                'backend': self.backend_id,
                'training_records': int(snapshot.train_records),
                'validation_records': int(snapshot.validation_records),
            },
        }
        if 'validation' in tokenized and len(tokenized['validation']):
            evaluated = trainer.evaluate(tokenized['validation'])
            eval_loss = float(evaluated.get('eval_loss', math.inf))
            metrics['eval_loss'] = eval_loss
            metrics['quality_score'] = 0.0 if not math.isfinite(eval_loss) else 1.0 / (1.0 + max(0.0, eval_loss))

        checkpoint = output_dir / 'checkpoint'
        model.save_pretrained(str(checkpoint))
        tokenizer.save_pretrained(str(checkpoint))
        return TrainingArtifact(
            checkpoint_ref=str(checkpoint),
            backend_id=self.backend_id,
            base_model=settings.base_model,
            method=settings.method.value,
            metrics=metrics,
        )
