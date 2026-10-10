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
