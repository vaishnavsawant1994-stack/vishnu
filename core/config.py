from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv

load_dotenv()

_TRUE_VALUES = {'1', 'true', 'yes', 'on'}
_FALSE_VALUES = {'0', 'false', 'no', 'off'}


class ConfigurationError(ValueError):
    """Raised when strict runtime configuration is invalid."""


def _hosted_runtime() -> bool:
    return bool(os.getenv('RAILWAY_ENVIRONMENT_ID') or os.getenv('RAILWAY_PROJECT_ID'))


def _strict_config_enabled() -> bool:
    if _hosted_runtime():
        return True
    raw = os.getenv('PERSONAL_AI_STRICT_CONFIG')
    if raw is None:
        return False
    normalized = raw.lower().strip()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise ConfigurationError(
        'PERSONAL_AI_STRICT_CONFIG must be a boolean '
        '(1/0, true/false, yes/no, on/off)'
    )


STRICT_CONFIGURATION = _strict_config_enabled()


def env_bool(name: str, default: bool = False, *, strict: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.lower().strip()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    if strict and STRICT_CONFIGURATION:
        raise ConfigurationError(
            f'{name} must be a boolean (1/0, true/false, yes/no, on/off)'
        )
    # Preserve the historical local-development behavior: any non-truthy
    # explicit value is treated as false when strict validation is disabled.
    return False


def env_int(
    name: str,
    default: int = 0,
    *,
    strict: bool = False,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        if strict and STRICT_CONFIGURATION:
            raise ConfigurationError(f'{name} must be an integer') from exc
        return default
    if strict and STRICT_CONFIGURATION:
        if minimum is not None and value < minimum:
            raise ConfigurationError(f'{name} must be >= {minimum}')
        if maximum is not None and value > maximum:
            raise ConfigurationError(f'{name} must be <= {maximum}')
    return value


def env_float(
    name: str,
    default: float = 0.0,
    *,
    strict: bool = False,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        if strict and STRICT_CONFIGURATION:
            raise ConfigurationError(f'{name} must be a number') from exc
        return default
    if strict and STRICT_CONFIGURATION:
        if minimum is not None and value < minimum:
            raise ConfigurationError(f'{name} must be >= {minimum}')
        if maximum is not None and value > maximum:
            raise ConfigurationError(f'{name} must be <= {maximum}')
    return value


@dataclass(frozen=True)
class Settings:
    base_dir: Path = Path(__file__).resolve().parent.parent
    data_dir: Path = Path(os.getenv('PERSONAL_AI_DATA_DIR', str(Path.home() / '.personal_ai'))).expanduser().resolve()
    hosted_runtime: bool = _hosted_runtime()
    strict_configuration: bool = STRICT_CONFIGURATION

    ai_provider: str = os.getenv('AI_PROVIDER', 'local').lower().strip()
    local_ai_url: str = os.getenv('LOCAL_AI_URL', 'http://127.0.0.1:11434/v1').rstrip('/')
    local_ai_model: str = os.getenv('LOCAL_AI_MODEL', 'llama3.2')
    local_ai_explicit: bool = bool(os.getenv('LOCAL_AI_URL') or os.getenv('SELF_HOSTED_AI_URL'))
    self_hosted_ai_url: str = os.getenv('SELF_HOSTED_AI_URL', os.getenv('LOCAL_AI_URL', '')).rstrip('/')
    self_hosted_ai_api_key: str = os.getenv('SELF_HOSTED_AI_API_KEY', '')
    self_hosted_ai_model: str = os.getenv('SELF_HOSTED_AI_MODEL', os.getenv('LOCAL_AI_MODEL', 'llama3.2'))

    model_fallback_providers: tuple[str, ...] = tuple(x.strip().lower() for x in os.getenv('MODEL_FALLBACK_PROVIDERS', '').split(',') if x.strip())
    model_disabled_providers: tuple[str, ...] = tuple(x.strip().lower() for x in os.getenv('MODEL_DISABLED_PROVIDERS', '').split(',') if x.strip())
    model_allowed_providers: tuple[str, ...] = tuple(x.strip().lower() for x in os.getenv('MODEL_ALLOWED_PROVIDERS', '').split(',') if x.strip())
    model_privacy_mode: str = os.getenv('MODEL_PRIVACY_MODE', 'local_preferred').lower().strip()
    model_request_timeout_seconds: float = env_float('MODEL_REQUEST_TIMEOUT_SECONDS', 120.0)
    model_health_timeout_seconds: float = env_float('MODEL_HEALTH_TIMEOUT_SECONDS', 5.0)
    model_retry_attempts: int = max(0, min(3, env_int('MODEL_RETRY_ATTEMPTS', 1, strict=True, minimum=0, maximum=3)))
    model_retry_backoff_seconds: float = max(0.0, min(2.0, env_float('MODEL_RETRY_BACKOFF_SECONDS', 0.05, strict=True, minimum=0.0, maximum=2.0)))
    model_max_failovers: int = max(0, min(12, env_int('MODEL_MAX_FAILOVERS', 5, strict=True, minimum=0, maximum=12)))
    model_local_first: bool = env_bool('MODEL_LOCAL_FIRST', True, strict=True)
    allow_external_for_sensitive: bool = env_bool('ALLOW_EXTERNAL_FOR_SENSITIVE', False, strict=True)
    model_evaluation_on_startup: bool = env_bool('MODEL_EVALUATION_ON_STARTUP', False)

    intelligence_fabric_enabled: bool = env_bool('INTELLIGENCE_FABRIC_ENABLED', True)
    multi_provider_routing_enabled: bool = env_bool('MULTI_PROVIDER_ROUTING_ENABLED', True)
    parallel_agents_enabled: bool = env_bool('PARALLEL_AGENTS_ENABLED', False)
    model_handoff_enabled: bool = env_bool('MODEL_HANDOFF_ENABLED', True)
    multi_model_deliberation_enabled: bool = env_bool('MULTI_MODEL_DELIBERATION_ENABLED', False)
    ai_budgets_enabled: bool = env_bool('AI_BUDGETS_ENABLED', True, strict=True)

    model_global_max_cost: float = max(0.0, env_float('MODEL_GLOBAL_MAX_COST', 0.0, strict=True, minimum=0.0))
    model_global_max_input_tokens: int = max(0, env_int('MODEL_GLOBAL_MAX_INPUT_TOKENS', 0, strict=True, minimum=0))
    model_global_max_output_tokens: int = max(0, env_int('MODEL_GLOBAL_MAX_OUTPUT_TOKENS', 0, strict=True, minimum=0))
    model_global_max_requests: int = max(0, env_int('MODEL_GLOBAL_MAX_REQUESTS', 0, strict=True, minimum=0))
    model_global_max_retries: int = max(0, env_int('MODEL_GLOBAL_MAX_RETRIES', 0, strict=True, minimum=0))
    model_max_parallel_calls: int = max(1, min(32, env_int('MODEL_MAX_PARALLEL_CALLS', 4, strict=True, minimum=1, maximum=32)))
    model_max_parallel_agents: int = max(1, min(32, env_int('MODEL_MAX_PARALLEL_AGENTS', 4, strict=True, minimum=1, maximum=32)))

    openrouter_api_key: str = os.getenv('OPENROUTER_API_KEY', '')
    openrouter_model: str = os.getenv('OPENROUTER_MODEL', 'meta-llama/llama-3.3-70b-instruct')
    openai_api_key: str = os.getenv('OPENAI_API_KEY', '')
    openai_base_url: str = os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1').rstrip('/')
    openai_model: str = os.getenv('OPENAI_MODEL', 'gpt-5-mini')
    gemini_api_key: str = os.getenv('GEMINI_API_KEY', '')
    gemini_base_url: str = os.getenv('GEMINI_BASE_URL', 'https://generativelanguage.googleapis.com/v1beta/openai').rstrip('/')
    gemini_model: str = os.getenv('GEMINI_MODEL', 'gemini-3.5-flash-lite')

    deepseek_api_key: str = os.getenv('DEEPSEEK_API_KEY', '')
    deepseek_base_url: str = os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com').rstrip('/')
    deepseek_model: str = os.getenv('DEEPSEEK_MODEL', 'deepseek-flash')
    xai_api_key: str = os.getenv('XAI_API_KEY', '')
    xai_base_url: str = os.getenv('XAI_BASE_URL', 'https://api.x.ai/v1').rstrip('/')
    xai_model: str = os.getenv('XAI_MODEL', 'grok-4.7')
    groq_api_key: str = os.getenv('GROQ_API_KEY', '')
    groq_base_url: str = os.getenv('GROQ_BASE_URL', 'https://api.groq.com/openai/v1').rstrip('/')
    groq_model: str = os.getenv('GROQ_MODEL', 'openai/gpt-oss-120b')
    cerebras_api_key: str = os.getenv('CEREBRAS_API_KEY', '')
    cerebras_base_url: str = os.getenv('CEREBRAS_BASE_URL', 'https://api.cerebras.ai/v1').rstrip('/')
    cerebras_model: str = os.getenv('CEREBRAS_MODEL', '')
    mistral_api_key: str = os.getenv('MISTRAL_API_KEY', '')
    mistral_base_url: str = os.getenv('MISTRAL_BASE_URL', 'https://api.mistral.ai/v1').rstrip('/')
    mistral_model: str = os.getenv('MISTRAL_MODEL', '')
    custom_ai_api_key: str = os.getenv('CUSTOM_AI_API_KEY', '')
    custom_ai_base_url: str = os.getenv('CUSTOM_AI_BASE_URL', '').rstrip('/')
    custom_ai_model: str = os.getenv('CUSTOM_AI_MODEL', '')
    custom_ai_private: bool = env_bool('CUSTOM_AI_PRIVATE', False, strict=True)

    realtime_provider: str = os.getenv('REALTIME_PROVIDER', 'auto').lower().strip()
    realtime_model: str = os.getenv('REALTIME_MODEL', 'gpt-realtime-2.1')
    realtime_voice: str = os.getenv('REALTIME_VOICE', 'marin')
    realtime_reasoning_effort: str = os.getenv('REALTIME_REASONING_EFFORT', 'low').lower().strip()
    realtime_safety_identifier: str = os.getenv('REALTIME_SAFETY_IDENTIFIER', '')
    realtime_instructions: str = os.getenv('REALTIME_INSTRUCTIONS', 'You are Vishnu. Be concise, natural, context-aware, and ask before taking consequential actions.')
    realtime_sample_rate: int = env_int('REALTIME_SAMPLE_RATE', 24000)
    voice_personality: str = os.getenv('VOICE_PERSONALITY', 'calm, concise, warm and direct')
    voice_speaking_rate: float = env_float('VOICE_SPEAKING_RATE', 1.0)
    voice_min_endpoint_ms: int = env_int('VOICE_MIN_ENDPOINT_MS', 420)
    voice_max_endpoint_ms: int = env_int('VOICE_MAX_ENDPOINT_MS', 1100)
    voice_noise_multiplier: float = env_float('VOICE_NOISE_MULTIPLIER', 2.4)
    voice_min_threshold: float = env_float('VOICE_MIN_THRESHOLD', 0.008)
    voice_max_utterance_seconds: float = env_float('VOICE_MAX_UTTERANCE_SECONDS', 45.0)
    voice_input_device: str = os.getenv('VOICE_INPUT_DEVICE', '').strip()
    voice_output_device: str = os.getenv('VOICE_OUTPUT_DEVICE', '').strip()
    vision_model: str = os.getenv('VISION_MODEL', '')
    embedding_model: str = os.getenv('EMBEDDING_MODEL', 'text-embedding-3-small')
    stt_model: str = os.getenv('STT_MODEL', 'whisper-1')
    tts_model: str = os.getenv('TTS_MODEL', 'tts-1')
    tts_voice: str = os.getenv('TTS_VOICE', 'alloy')

    autonomy_mode: str = os.getenv('AUTONOMY_MODE', 'ask').lower().strip()
    control_server_enabled: bool = env_bool('CONTROL_SERVER_ENABLED', False, strict=True)
    control_server_host: str = os.getenv('CONTROL_SERVER_HOST', '127.0.0.1')
    control_server_port: int = env_int('CONTROL_SERVER_PORT', 8766, strict=True, minimum=1, maximum=65535)
    pairing_ttl_seconds: int = env_int('PAIRING_TTL_SECONDS', 300, strict=True, minimum=1)
    cloud_runtime_enabled: bool = env_bool('CLOUD_RUNTIME_ENABLED', False, strict=True)
    cloud_owner_secret: str = os.getenv('PERSONAL_AI_CLOUD_OWNER_SECRET', '')
    cloud_session_ttl_seconds: int = env_int('CLOUD_SESSION_TTL_SECONDS', 900, strict=True, minimum=1)
    cloud_allowed_origins: tuple[str, ...] = tuple(x.strip().rstrip('/') for x in os.getenv('CLOUD_ALLOWED_ORIGINS', '').split(',') if x.strip())
    iphone_owner_enrollment_code: str = os.getenv('PERSONAL_AI_IPHONE_ENROLLMENT_CODE', '').strip()
    iphone_pwa_allow_insecure: bool = env_bool('PERSONAL_AI_IPHONE_ALLOW_INSECURE', False, strict=True)
    iphone_device_cookie_days: int = env_int('PERSONAL_AI_DEVICE_COOKIE_DAYS', 365, strict=True, minimum=1)
    google_signin_client_id: str = os.getenv('GOOGLE_SIGNIN_CLIENT_ID', os.getenv('GOOGLE_CLIENT_ID', '')).strip()
    owner_google_email: str = os.getenv('PERSONAL_AI_OWNER_GOOGLE_EMAIL', '').strip().casefold()

    browser_headless: bool = env_bool('BROWSER_HEADLESS', False)
    file_roots: tuple[Path, ...] = tuple(
        Path(item.strip()).expanduser().resolve()
        for item in os.getenv('PERSONAL_AI_FILE_ROOTS', str(Path.home() / '.personal_ai' / 'workspace')).split(os.pathsep)
        if item.strip()
    )
    vault_password: str = os.getenv('PERSONAL_AI_VAULT_PASSWORD', '')
    google_client_id: str = os.getenv('GOOGLE_CLIENT_ID', '')
    google_client_secret: str = os.getenv('GOOGLE_CLIENT_SECRET', '')
    slack_client_id: str = os.getenv('SLACK_CLIENT_ID', '')
    slack_client_secret: str = os.getenv('SLACK_CLIENT_SECRET', '')
    gmail_token: str = os.getenv('GMAIL_ACCESS_TOKEN', '')
    calendar_token: str = os.getenv('GOOGLE_CALENDAR_ACCESS_TOKEN', '')
    slack_token: str = os.getenv('SLACK_BOT_TOKEN', '')
    home_assistant_url: str = os.getenv('HOME_ASSISTANT_URL', '')
    home_assistant_token: str = os.getenv('HOME_ASSISTANT_TOKEN', '')

    apns_team_id: str = os.getenv('APNS_TEAM_ID', '')
    apns_key_id: str = os.getenv('APNS_KEY_ID', '')
    apns_topic: str = os.getenv('APNS_TOPIC', 'ai.personal.companion.ios')
    apns_private_key_b64: str = os.getenv('APNS_PRIVATE_KEY_B64', '')
    apns_environment: str = os.getenv('APNS_ENVIRONMENT', 'development').lower().strip()
    release_public_key_b64: str = os.getenv('RELEASE_PUBLIC_KEY_B64', '')
    release_private_key_b64: str = os.getenv('PERSONAL_AI_RELEASE_PRIVATE_KEY_B64', '')
    windows_signing_cert_b64: str = os.getenv('WINDOWS_SIGNING_CERT_B64', '')
    windows_signing_password: str = os.getenv('WINDOWS_SIGNING_PASSWORD', '')
    apple_signing_identity: str = os.getenv('APPLE_SIGNING_IDENTITY', '')
    apple_team_id: str = os.getenv('APPLE_TEAM_ID', '')
    apple_notary_profile: str = os.getenv('APPLE_NOTARY_PROFILE', '')

    proactive_enabled: bool = env_bool('PROACTIVE_ENABLED', True)
    proactive_interruptions_per_hour: int = env_int('PROACTIVE_INTERRUPTION_BUDGET_PER_HOUR', 3)
    proactive_default_cooldown_seconds: int = env_int('PROACTIVE_DEFAULT_COOLDOWN_SECONDS', 1800)
    workflow_default_timeout_seconds: int = env_int('WORKFLOW_DEFAULT_TIMEOUT_SECONDS', 120, strict=True, minimum=1)
    workflow_default_retries: int = env_int('WORKFLOW_DEFAULT_RETRIES', 2, strict=True, minimum=0)


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
