"""Vishnu Intelligence Lab.

An opt-in experimental cognition runtime that is intentionally isolated from the
stable Vishnu runtime. Importing this package has no side effects and never
changes stable runtime configuration, memory, permissions, or tool authority.
"""

from .config import CapabilityLevel, LabSettings
from .runtime import IntelligenceLabRuntime
from .bootstrap import attach_intelligence_lab, build_intelligence_lab

__all__ = [
    "CapabilityLevel",
    "LabSettings",
    "IntelligenceLabRuntime",
    "attach_intelligence_lab",
    "build_intelligence_lab",
]
