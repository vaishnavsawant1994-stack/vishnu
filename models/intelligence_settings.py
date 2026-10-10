from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from models.intelligence_modes import IntelligenceMode


@dataclass(frozen=True)
class IntelligenceSettingsSnapshot:
    enabled: bool
    mode: IntelligenceMode
    auto_escalation: bool
    verification_enabled: bool
    training_capture: bool
    performance_learning: bool
    max_models: int
    latency_preference: str
    max_cost_per_request: float | None

    def public(self) -> dict[str, Any]:
        return {
            'enabled': self.enabled,
            'mode': self.mode.value,
            'auto_escalation': self.auto_escalation,
            'verification_enabled': self.verification_enabled,
            'training_capture': self.training_capture,
            'performance_learning': self.performance_learning,
            'max_models': self.max_models,
            'latency_preference': self.latency_preference,
            'max_cost_per_request': self.max_cost_per_request,
            'model_output_authority': False,
        }


class IntelligenceSettingsService:
    """Validated owner settings for Vishnu's optional intelligence layer.

    The service persists through the existing Preferences authority. These
    settings only constrain/recommend model reasoning. They cannot grant tools,
    permissions, approvals, execution authority, or bypass privacy policy.
    """

    MODES = tuple(mode.value for mode in IntelligenceMode)
    LATENCY_PREFERENCES = ('fast', 'balanced', 'quality')

    def __init__(self, preferences, *, events=None) -> None:
        self.preferences = preferences
        self.events = events

    @staticmethod
    def _bool(value: Any, *, field: str) -> bool:
        if not isinstance(value, bool):
            raise ValueError(f'{field} must be boolean')
        return value

    @staticmethod
    def _max_models(value: Any) -> int:
        if isinstance(value, bool):
            raise ValueError('max_models must be an integer between 1 and 5')
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError('max_models must be an integer between 1 and 5') from exc
        if not 1 <= parsed <= 5:
            raise ValueError('max_models must be between 1 and 5')
        return parsed

    @staticmethod
    def _cost(value: Any) -> float | None:
        if value in (None, ''):
            return None
        if isinstance(value, bool):
            raise ValueError('max_cost_per_request must be a positive number or null')
        try:
            parsed = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError('max_cost_per_request must be a positive number or null') from exc
        if parsed <= 0 or parsed > 10000:
            raise ValueError('max_cost_per_request must be between 0 and 10000')
        return parsed

    def snapshot(self) -> IntelligenceSettingsSnapshot:
        raw_mode = str(self.preferences.get('intelligence_mode', IntelligenceMode.STANDARD.value)).strip().lower()
        if raw_mode == 'focused':
            raw_mode = IntelligenceMode.SMART.value
        try:
            mode = IntelligenceMode(raw_mode)
        except ValueError:
            mode = IntelligenceMode.STANDARD
        raw_latency = str(self.preferences.get('intelligence_latency_preference', 'balanced')).strip().lower()
        if raw_latency not in self.LATENCY_PREFERENCES:
            raw_latency = 'balanced'
        raw_cost = self.preferences.get('intelligence_max_cost_per_request', None)
        try:
            max_cost = self._cost(raw_cost)
        except ValueError:
            max_cost = None
        try:
            max_models = self._max_models(self.preferences.get('intelligence_max_models', 5))
        except ValueError:
            max_models = 5
        return IntelligenceSettingsSnapshot(
            enabled=bool(self.preferences.get('advanced_intelligence_enabled', False)),
            mode=mode,
            auto_escalation=bool(self.preferences.get('intelligence_auto_escalation', False)),
            verification_enabled=bool(self.preferences.get('intelligence_verification_enabled', True)),
            training_capture=bool(self.preferences.get('intelligence_training_capture', True)),
            performance_learning=bool(self.preferences.get('intelligence_performance_learning', True)),
            max_models=max_models,
            latency_preference=raw_latency,
            max_cost_per_request=max_cost,
        )

    def update(self, **values: Any) -> IntelligenceSettingsSnapshot:
        allowed = {
            'enabled', 'mode', 'auto_escalation', 'verification_enabled',
            'training_capture', 'performance_learning', 'max_models',
            'latency_preference', 'max_cost_per_request',
        }
        unknown = set(values) - allowed
        if unknown:
            raise ValueError(f'unsupported intelligence setting(s): {sorted(unknown)}')
        updates: dict[str, Any] = {}
        if 'enabled' in values:
            updates['advanced_intelligence_enabled'] = self._bool(values['enabled'], field='enabled')
        if 'mode' in values:
            raw = str(values['mode']).strip().lower()
            if raw == 'focused':
                raw = IntelligenceMode.SMART.value
            try:
                updates['intelligence_mode'] = IntelligenceMode(raw).value
            except ValueError as exc:
                raise ValueError('unsupported intelligence mode') from exc
        if 'auto_escalation' in values:
            updates['intelligence_auto_escalation'] = self._bool(values['auto_escalation'], field='auto_escalation')
        if 'verification_enabled' in values:
            updates['intelligence_verification_enabled'] = self._bool(values['verification_enabled'], field='verification_enabled')
        if 'training_capture' in values:
            updates['intelligence_training_capture'] = self._bool(values['training_capture'], field='training_capture')
        if 'performance_learning' in values:
            updates['intelligence_performance_learning'] = self._bool(values['performance_learning'], field='performance_learning')
        if 'max_models' in values:
            updates['intelligence_max_models'] = self._max_models(values['max_models'])
        if 'latency_preference' in values:
            latency = str(values['latency_preference']).strip().lower()
            if latency not in self.LATENCY_PREFERENCES:
                raise ValueError('latency_preference must be fast, balanced, or quality')
            updates['intelligence_latency_preference'] = latency
        if 'max_cost_per_request' in values:
            updates['intelligence_max_cost_per_request'] = self._cost(values['max_cost_per_request'])
        if updates:
            self.preferences.update(**updates)
            if self.events is not None:
                self.events.emit('intelligence.settings_updated', **self.snapshot().public())
        return self.snapshot()
