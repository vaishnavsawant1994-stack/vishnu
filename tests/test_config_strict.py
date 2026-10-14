from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]

_BASE_CONFIG = {
    'PERSONAL_AI_STRICT_CONFIG': '0',
    'RAILWAY_ENVIRONMENT_ID': '',
    'RAILWAY_PROJECT_ID': '',
    'MODEL_RETRY_ATTEMPTS': '1',
    'MODEL_RETRY_BACKOFF_SECONDS': '0.05',
    'MODEL_MAX_FAILOVERS': '5',
    'MODEL_LOCAL_FIRST': 'true',
    'ALLOW_EXTERNAL_FOR_SENSITIVE': 'false',
    'AI_BUDGETS_ENABLED': 'true',
    'MODEL_GLOBAL_MAX_COST': '0',
    'MODEL_GLOBAL_MAX_INPUT_TOKENS': '0',
    'MODEL_GLOBAL_MAX_OUTPUT_TOKENS': '0',
    'MODEL_GLOBAL_MAX_REQUESTS': '0',
    'MODEL_GLOBAL_MAX_RETRIES': '0',
    'MODEL_MAX_PARALLEL_CALLS': '4',
    'MODEL_MAX_PARALLEL_AGENTS': '4',
    'CUSTOM_AI_PRIVATE': 'false',
    'CONTROL_SERVER_ENABLED': 'false',
    'CONTROL_SERVER_PORT': '8766',
    'PAIRING_TTL_SECONDS': '300',
    'CLOUD_RUNTIME_ENABLED': 'false',
    'CLOUD_SESSION_TTL_SECONDS': '900',
    'PERSONAL_AI_IPHONE_ALLOW_INSECURE': 'false',
    'PERSONAL_AI_DEVICE_COOKIE_DAYS': '365',
    'WORKFLOW_DEFAULT_TIMEOUT_SECONDS': '120',
    'WORKFLOW_DEFAULT_RETRIES': '2',
}


def _run_config(tmp_path: Path, **overrides: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(_BASE_CONFIG)
    env['PERSONAL_AI_DATA_DIR'] = str(tmp_path / 'data')
    env.update(overrides)
    code = (
        'from core.config import settings; '
        'print(settings.control_server_port); '
        'print(settings.strict_configuration); '
        'print(settings.hosted_runtime)'
    )
    return subprocess.run(
        [sys.executable, '-c', code],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_local_development_preserves_malformed_integer_fallback(tmp_path):
    result = _run_config(tmp_path, CONTROL_SERVER_PORT='not-a-number')

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ['8766', 'False', 'False']


def test_explicit_strict_mode_rejects_malformed_integer(tmp_path):
    result = _run_config(
        tmp_path,
        PERSONAL_AI_STRICT_CONFIG='1',
        CONTROL_SERVER_PORT='not-a-number',
    )

    assert result.returncode != 0
    assert 'CONTROL_SERVER_PORT must be an integer' in result.stderr


def test_hosted_runtime_enables_strict_validation_automatically(tmp_path):
    result = _run_config(
        tmp_path,
        RAILWAY_PROJECT_ID='test-project',
        CONTROL_SERVER_PORT='not-a-number',
    )

    assert result.returncode != 0
    assert 'CONTROL_SERVER_PORT must be an integer' in result.stderr


def test_hosted_runtime_rejects_out_of_range_port(tmp_path):
    result = _run_config(
        tmp_path,
        RAILWAY_PROJECT_ID='test-project',
        CONTROL_SERVER_PORT='70000',
    )

    assert result.returncode != 0
    assert 'CONTROL_SERVER_PORT must be <= 65535' in result.stderr


def test_hosted_runtime_rejects_invalid_security_boolean(tmp_path):
    result = _run_config(
        tmp_path,
        RAILWAY_PROJECT_ID='test-project',
        CONTROL_SERVER_ENABLED='maybe',
    )

    assert result.returncode != 0
    assert 'CONTROL_SERVER_ENABLED must be a boolean' in result.stderr


def test_hosted_runtime_rejects_malformed_budget_limit(tmp_path):
    result = _run_config(
        tmp_path,
        RAILWAY_PROJECT_ID='test-project',
        MODEL_GLOBAL_MAX_REQUESTS='unlimited-ish',
    )

    assert result.returncode != 0
    assert 'MODEL_GLOBAL_MAX_REQUESTS must be an integer' in result.stderr


def test_hosted_runtime_rejects_non_finite_budget_limit(tmp_path):
    result = _run_config(
        tmp_path,
        RAILWAY_PROJECT_ID='test-project',
        MODEL_GLOBAL_MAX_COST='nan',
    )

    assert result.returncode != 0
    assert 'MODEL_GLOBAL_MAX_COST must be a finite number' in result.stderr


def test_hosted_runtime_rejects_nonpositive_session_ttl(tmp_path):
    result = _run_config(
        tmp_path,
        RAILWAY_PROJECT_ID='test-project',
        CLOUD_SESSION_TTL_SECONDS='0',
    )

    assert result.returncode != 0
    assert 'CLOUD_SESSION_TTL_SECONDS must be >= 1' in result.stderr


def test_valid_hosted_configuration_starts_normally(tmp_path):
    result = _run_config(
        tmp_path,
        RAILWAY_PROJECT_ID='test-project',
        CONTROL_SERVER_PORT='9000',
        PAIRING_TTL_SECONDS='120',
        CLOUD_SESSION_TTL_SECONDS='600',
        MODEL_MAX_PARALLEL_CALLS='8',
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ['9000', 'True', 'True']


def test_invalid_explicit_strict_mode_value_fails_closed(tmp_path):
    result = _run_config(tmp_path, PERSONAL_AI_STRICT_CONFIG='sometimes')

    assert result.returncode != 0
    assert 'PERSONAL_AI_STRICT_CONFIG must be a boolean' in result.stderr
