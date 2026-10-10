from __future__ import annotations

from types import SimpleNamespace

import pytest

from evolution.automation import AutomaticCodeEvolution, ModelFileImplementationProvider
from evolution.code_body import CodeBodyRunStatus


class _Models:
    def __init__(self, payload):
        self.payload = payload

    def json(self, *args, **kwargs):
        return self.payload


def _candidate():
    return SimpleNamespace(
        id='candidate-1',
        title='Improve ordinary feature',
        rationale='Observed repeated friction',
        proposed_change='Improve ordinary UI helper',
        expected_benefit='Less friction',
        affected_scope=('ui/example.py',),
        test_plan=('unit tests pass',),
    )


def test_model_file_implementation_rejects_protected_evolution_scope_before_write(tmp_path):
    provider = ModelFileImplementationProvider(_Models({
        'summary': 'unsafe change',
        'files': [{'path': 'security/policy_gateway.py', 'content': 'BYPASS = True\n'}],
    }))
    with pytest.raises(PermissionError, match='protected scope'):
        provider.implement(candidate=_candidate(), workspace=tmp_path)
    assert not (tmp_path / 'security' / 'policy_gateway.py').exists()


def test_model_file_implementation_writes_only_safe_bounded_relative_files(tmp_path):
    provider = ModelFileImplementationProvider(_Models({
        'summary': 'safe improvement',
        'files': [{'path': 'ui/example.py', 'content': 'VALUE = 2\n'}],
    }))
    result = provider.implement(candidate=_candidate(), workspace=tmp_path)
    assert result.changed_paths == ('ui/example.py',)
    assert (tmp_path / 'ui' / 'example.py').read_text(encoding='utf-8') == 'VALUE = 2\n'


class _MissingHandoffCodeBody:
    def prepare(self, candidate_id, **kwargs):
        raise ValueError('candidate has no owner-approved handoff')


def test_automatic_code_evolution_cannot_create_or_bypass_owner_handoff():
    automatic = AutomaticCodeEvolution(
        code_body=_MissingHandoffCodeBody(),
        implementation=SimpleNamespace(implement=lambda **kwargs: None),
    )
    with pytest.raises(ValueError, match='owner-approved handoff'):
        automatic.run('candidate-1', runtime_epoch=1)


class _CodeBody:
    def __init__(self, root):
        self.root = root
        self.committed = False
        self.verified = False
        self.handoffs = SimpleNamespace(
            evolution_store=SimpleNamespace(get_candidate=lambda candidate_id: _candidate()),
        )
        self.run = SimpleNamespace(candidate_id='candidate-1', status=CodeBodyRunStatus.PREPARED)

    def prepare(self, candidate_id, **kwargs):
        return self.run

    def _session(self, run):
        return SimpleNamespace(local_path=self.root)

    def commit(self, candidate_id, *, message):
        self.committed = True
        return SimpleNamespace(candidate_id=candidate_id, status=CodeBodyRunStatus.COMMITTED)

    def verify(self, candidate_id):
        self.verified = True
        return SimpleNamespace(candidate_id=candidate_id, status=CodeBodyRunStatus.VERIFIED)


def test_automatic_code_evolution_stops_at_verified_without_adoption_or_deploy(tmp_path):
    code_body = _CodeBody(tmp_path)
    provider = ModelFileImplementationProvider(_Models({
        'summary': 'safe improvement',
        'files': [{'path': 'ui/example.py', 'content': 'VALUE = 3\n'}],
    }))
    automatic = AutomaticCodeEvolution(code_body=code_body, implementation=provider)
    result = automatic.run('candidate-1', runtime_epoch=1)
    assert result.status is CodeBodyRunStatus.VERIFIED
    assert code_body.committed is True
    assert code_body.verified is True
    status = automatic.status()
    assert status['automatic_review_approval'] is False
    assert status['automatic_adoption'] is False
    assert status['automatic_merge'] is False
    assert status['automatic_deploy'] is False
    assert status['automatic_activation'] is False
