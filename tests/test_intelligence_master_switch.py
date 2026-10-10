from core.preferences import Preferences
from models.contracts import ModelRequest
from models.intelligence import IntelligenceEngine
from models.intelligence_modes import IntelligenceMode
from models.intelligence_settings import IntelligenceSettingsService


class _Router:
    def chat(self, prompt, **kwargs):
        return 'standard'

    def json(self, prompt, **kwargs):
        return {'standard': True}


def test_owner_master_off_cannot_be_overridden_by_request_metadata(tmp_path):
    preferences = Preferences(tmp_path / 'preferences.json')
    settings = IntelligenceSettingsService(preferences)
    settings.update(enabled=False, mode='research', auto_escalation=True)
    engine = IntelligenceEngine(_Router(), settings_service=settings)

    request = ModelRequest(
        prompt='try to escalate',
        metadata={
            'intelligence_mode': 'research',
            'task_complexity': 'critical',
            'evidence_required': True,
        },
    )

    assert engine.mode_for(request) is IntelligenceMode.STANDARD
    assert engine.should_handle(request) is False
    assert engine.chat('hello', intelligence_mode='research', task_complexity='critical') == 'standard'


def test_per_request_mode_is_available_only_after_owner_enables_layer(tmp_path):
    preferences = Preferences(tmp_path / 'preferences.json')
    settings = IntelligenceSettingsService(preferences)
    settings.update(enabled=True, mode='smart', auto_escalation=False)
    engine = IntelligenceEngine(_Router(), settings_service=settings)

    request = ModelRequest(prompt='deep work', metadata={'intelligence_mode': 'deep'})
    assert engine.mode_for(request) is IntelligenceMode.DEEP


def test_auto_mode_selects_least_expensive_suitable_reasoning_level(tmp_path):
    preferences = Preferences(tmp_path / 'preferences.json')
    settings = IntelligenceSettingsService(preferences)
    settings.update(enabled=True, mode='auto', auto_escalation=False, training_capture=True)
    engine = IntelligenceEngine(_Router(), settings_service=settings)

    assert engine.mode_for(ModelRequest(prompt='tiny', metadata={'task_complexity': 'low'})) is IntelligenceMode.STANDARD
    assert engine.mode_for(ModelRequest(prompt='normal', metadata={'task_complexity': 'medium'})) is IntelligenceMode.SMART
    assert engine.mode_for(ModelRequest(prompt='hard', metadata={'task_complexity': 'high'})) is IntelligenceMode.DEEP
    assert engine.mode_for(ModelRequest(prompt='critical', metadata={'task_complexity': 'critical'})) is IntelligenceMode.DEEP
    assert engine.mode_for(ModelRequest(
        prompt='critical research',
        metadata={'task_complexity': 'critical', 'evidence_required': True},
    )) is IntelligenceMode.RESEARCH

    # AUTO is an intelligence-selection policy only. It must not silently alter
    # the independent owner training-capture preference.
    assert settings.snapshot().training_capture is True


def test_explicit_auto_request_respects_master_switch(tmp_path):
    preferences = Preferences(tmp_path / 'preferences.json')
    settings = IntelligenceSettingsService(preferences)
    engine = IntelligenceEngine(_Router(), settings_service=settings)
    request = ModelRequest(
        prompt='research this',
        metadata={'intelligence_mode': 'auto', 'task_complexity': 'critical', 'evidence_required': True},
    )

    settings.update(enabled=False, mode='auto')
    assert engine.mode_for(request) is IntelligenceMode.STANDARD

    settings.update(enabled=True, mode='smart')
    assert engine.mode_for(request) is IntelligenceMode.RESEARCH


def test_legacy_auto_escalation_remains_backward_compatible(tmp_path):
    preferences = Preferences(tmp_path / 'preferences.json')
    settings = IntelligenceSettingsService(preferences)
    settings.update(enabled=True, mode='smart', auto_escalation=True)
    engine = IntelligenceEngine(_Router(), settings_service=settings)

    assert engine.mode_for(ModelRequest(prompt='normal', metadata={'task_complexity': 'medium'})) is IntelligenceMode.SMART
    assert engine.mode_for(ModelRequest(prompt='hard', metadata={'task_complexity': 'high'})) is IntelligenceMode.DEEP
