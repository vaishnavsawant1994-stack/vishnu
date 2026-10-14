from __future__ import annotations

from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class MemoryCreateBody(BaseModel):
    type: str = Field(default='note', min_length=1, max_length=60)
    subject: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1, max_length=20000)
    source: str = Field(default='explicit-owner', max_length=240)
    confidence: float = Field(default=1.0, ge=0, le=1)
    verified: bool = True
    sensitivity: Literal['normal', 'sensitive', 'secret', 'never_store'] = 'normal'
    tags: list[str] = Field(default_factory=list, max_length=50)
    importance: float = Field(default=.7, ge=0, le=1)
    occurred_at: str | None = None
    parent_id: str | None = None
    scope: Literal['personal', 'project'] = 'personal'
    project_id: str | None = None


class MemoryUpdateBody(BaseModel):
    type: str | None = Field(default=None, max_length=60)
    subject: str | None = Field(default=None, max_length=240)
    content: str | None = Field(default=None, max_length=20000)
    confidence: float | None = Field(default=None, ge=0, le=1)
    verified: bool | None = None
    sensitivity: Literal['normal', 'sensitive', 'secret', 'never_store'] | None = None
    tags: list[str] | None = Field(default=None, max_length=50)
    importance: float | None = Field(default=None, ge=0, le=1)
    occurred_at: str | None = None
    parent_id: str | None = None
    scope: Literal['personal', 'project'] | None = None
    project_id: str | None = None
    pinned: bool | None = None


class RetentionBody(BaseModel):
    older_than_days: int = Field(ge=1, le=36500)
    sensitivity: Literal['normal', 'sensitive', 'secret'] | None = None
    confirm_delete: bool = False


class MemoryPreferencesBody(BaseModel):
    memory_enabled: bool | None = None
    review_before_saving: bool | None = None


class KnowledgeAvailabilityBody(BaseModel):
    available_to_vishnu: bool


class KnowledgeCollectionBody(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default='', max_length=500)


class KnowledgeCollectionUpdateBody(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)


class KnowledgeUploadBody(BaseModel):
    filename: str = Field(min_length=1, max_length=180)
    title: str | None = Field(default=None, max_length=240)
    media_type: str = Field(default='application/octet-stream', max_length=160)
    source: str = Field(default='owner-upload', max_length=500)
    access_class: Literal['owner', 'trusted-devices', 'private'] = 'owner'
    item_kind: Literal['document', 'note', 'link'] = 'document'
    collection_id: str | None = None
    link_url: str | None = Field(default=None, max_length=2048)
    content_base64: str | None = Field(default=None, max_length=14_000_000)
    text: str | None = Field(default=None, max_length=10_000_000)
    metadata: dict = Field(default_factory=dict)


class KnowledgeUpdateBody(BaseModel):
    title: str | None = Field(default=None, max_length=240)
    source: str | None = Field(default=None, max_length=500)
    access_class: Literal['owner', 'trusted-devices', 'private'] | None = None
    collection_id: str | None = None
    metadata: dict | None = None


class DevicePermissionsBody(BaseModel):
    scopes: list[str] = Field(max_length=30)


class ConfirmBody(BaseModel):
    confirm: Literal[True]


class DeleteAccountBody(BaseModel):
    confirm: Literal['DELETE']


class QualificationSessionBody(BaseModel):
    stage: Literal['P3.2', 'P3.3', 'P3.4', 'P3.5', 'P3.6', 'P3.7', 'P3.8']
    evidence_class: Literal['real_device', 'production_like', 'competitive']
    environment: dict = Field(default_factory=dict)


class QualificationTrialBody(BaseModel):
    task: str = Field(min_length=1, max_length=240)
    passed: bool
    latency_ms: float | None = Field(default=None, ge=0)
    metrics: dict = Field(default_factory=dict)
    evidence: dict = Field(default_factory=dict)


class QualificationFinishBody(BaseModel):
    duration_seconds: float | None = Field(default=None, ge=0)


class WorkflowCreateBody(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    trigger: dict = Field(default_factory=lambda: {'type': 'manual'})
    steps: list[dict] = Field(min_length=1, max_length=50)
    next_run_at: str | None = None
    interval_seconds: int | None = Field(default=None, ge=1)


class WorkflowPauseBody(BaseModel):
    workflow_id: str = Field(min_length=1, max_length=200)
    paused: bool


class WorkflowRunBody(BaseModel):
    context: dict = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=16, max_length=160)


class EmergencyStopBody(BaseModel):
    enabled: bool


class OwnerPermissionsBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    mode: Literal['safe', 'balanced', 'custom']
    rules: dict[str, Literal['allow', 'ask', 'never']]


class OwnerDefaultProviderBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    provider_id: str = Field(min_length=1, max_length=80, pattern=r'^[a-z0-9_-]+$')


class OwnerProviderConnectBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    provider_id: Literal['openai', 'openrouter', 'gemini']
    api_key: SecretStr = Field(min_length=16, max_length=4096)
    model: str = Field(min_length=1, max_length=200)


class OwnerProviderTestBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    provider_id: Literal['openai', 'openrouter', 'gemini']
    api_key: SecretStr = Field(min_length=16, max_length=4096)


class OwnerProviderModelBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    model: str = Field(min_length=1, max_length=200)


class UiPreferencesBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    profile_display_name: str = Field(default='', max_length=80)
    continuous_voice: bool = True
    voice_rate: float = Field(default=1.0, ge=0.75, le=1.35)
    quiet_hours: bool = True
    privacy_memory_enabled: bool = True
    privacy_review_before_saving: bool = True
    privacy_allow_project_context_general: bool = False
    privacy_save_conversations: bool = True
    privacy_retention: Literal['until_deleted'] = 'until_deleted'
    privacy_share_anonymous_usage_data: bool = False
    appearance_theme: Literal['dark', 'light', 'system'] = 'dark'
    appearance_accent: Literal['blue', 'teal', 'violet', 'amber', 'rose'] = 'blue'
    appearance_density: Literal['comfortable', 'compact'] = 'comfortable'
    appearance_motion: Literal['standard', 'reduced'] = 'standard'
    appearance_text_size: Literal['small', 'default', 'large'] = 'default'
    chat_enter_sends: bool = True
    chat_keep_composer_visible: bool = True
    chat_response_detail: Literal['concise', 'balanced', 'detailed'] = 'detailed'
    chat_response_style: Literal['clear_step_by_step', 'warm_conversational', 'technical', 'direct'] = 'clear_step_by_step'
    chat_show_sources: bool = True
    chat_show_timestamps: bool = True
    chat_show_actions: bool = True
    chat_message_spacing: Literal['comfortable', 'compact'] = 'comfortable'
    chat_new_context: Literal['general', 'project'] = 'general'
    chat_project_context_enabled: bool = False
    locale_app_language: Literal['en'] = 'en'
    locale_region: Literal['IN', 'US', 'GB', 'CA', 'AU', 'DE', 'FR', 'JP'] = 'IN'
    locale_time_zone: str = Field(default='Asia/Kolkata', min_length=1, max_length=80)
    locale_use_device_time_zone: bool = False
    locale_date_format: Literal['day_month_year', 'month_day_year', 'numeric'] = 'day_month_year'
    locale_time_format: Literal['12h', '24h'] = '12h'
    locale_week_start: Literal['monday', 'sunday'] = 'monday'
    locale_number_format: Literal['indian', 'western'] = 'indian'
    locale_temperature: Literal['celsius', 'fahrenheit'] = 'celsius'
    locale_measurement: Literal['metric', 'imperial'] = 'metric'
    pinned_sidebar_items: list[str] = Field(default_factory=list, max_length=40)

    @field_validator('locale_time_zone')
    @classmethod
    def valid_iana_time_zone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError('Time zone must be a valid IANA identifier') from exc
        return value



class ProfileAvatarBody(BaseModel):
    media_type: Literal['image/jpeg', 'image/png', 'image/webp']
    data_base64: str = Field(min_length=1, max_length=2_800_000)


class ProfileUpdateBody(BaseModel):
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    display_name: str = Field(min_length=1, max_length=80)

    @field_validator('first_name', 'last_name', 'display_name')
    @classmethod
    def non_blank_profile_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError('Name fields cannot be blank')
        return value


class NotificationEventPreference(BaseModel):
    enabled: bool
    channels: list[Literal['in_app', 'push', 'email']] = Field(max_length=3)


class NotificationQuietHours(BaseModel):
    enabled: bool
    start: str = Field(pattern=r'^([01]\d|2[0-3]):[0-5]\d$')
    end: str = Field(pattern=r'^([01]\d|2[0-3]):[0-5]\d$')
    timezone: str = Field(min_length=1, max_length=80)


class NotificationSummaryPreference(BaseModel):
    enabled: bool
    time: str = Field(pattern=r'^([01]\d|2[0-3]):[0-5]\d$')


class WeeklySummaryPreference(NotificationSummaryPreference):
    weekday: int = Field(ge=0, le=6)


class NotificationPreferencesBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    events: dict[Literal['task_reminders', 'work_completed', 'needs_review', 'blocked_work', 'workflow_updates', 'product_updates'], NotificationEventPreference]
    quiet_hours: NotificationQuietHours
    allow_urgent_reviews: bool
    daily_summary: NotificationSummaryPreference
    weekly_summary: WeeklySummaryPreference

    @classmethod
    def _check_timezone(cls, value):
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError('Choose a valid time zone') from exc
        return value

    @field_validator('quiet_hours')
    @classmethod
    def valid_timezone(cls, value):
        cls._check_timezone(value.timezone)
        return value

    @field_validator('events')
    @classmethod
    def reject_duplicate_channels(cls, value):
        for event in value.values():
            if len(event.channels) != len(set(event.channels)):
                raise ValueError('Notification channels cannot be duplicated')
        return value
