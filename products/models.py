from __future__ import annotations

from enum import StrEnum


class ProductType(StrEnum):
    AI_EMPLOYEE = "ai_employee"
    AGENT = "agent"
    AGENT_TEAM = "agent_team"
    AUTOMATION = "automation"
    WORKFLOW = "workflow"
    TOOL = "tool"
    KNOWLEDGE_ASSISTANT = "knowledge_assistant"
    INTEGRATION = "integration"
    BUSINESS_SYSTEM = "business_system"
    CUSTOM = "custom"


class ProductStatus(StrEnum):
    DRAFT = "draft"
    DESIGNING = "designing"
    DEVELOPMENT = "development"
    TESTING = "testing"
    BLOCKED = "blocked"
    READY = "ready"
    BUILDING = "building"
    QUALIFIED = "qualified"
    RELEASED = "released"
    LIVE = "live"
    PAUSED = "paused"
    NEEDS_ATTENTION = "needs_attention"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class AIMode(StrEnum):
    DISABLED = "disabled"
    CLIENT_API = "client_api"
    MANAGED = "managed"
    LOCAL = "local"
    HYBRID = "hybrid"


class PlatformTarget(StrEnum):
    WEB = "web"
    PWA = "pwa"
    ANDROID = "android"
    IOS = "ios"
    WINDOWS = "windows"
    MACOS = "macos"
    LINUX = "linux"
    DOCKER = "docker"
    API = "api"
    WORKER = "worker"


PRODUCT_TYPES = tuple(item.value for item in ProductType)
PRODUCT_STATUSES = tuple(item.value for item in ProductStatus)
AI_MODES = tuple(item.value for item in AIMode)
PLATFORM_TARGETS = tuple(item.value for item in PlatformTarget)


def ensure_choice(value: str, allowed: tuple[str, ...], field: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in allowed:
        raise ValueError(f"Unsupported {field}: {value}")
    return normalized
