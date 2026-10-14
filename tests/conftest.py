"""Deterministic test-only key authority for standalone local data stores."""

from __future__ import annotations

import base64
import os


def pytest_configure() -> None:
    # Production continues to require the configured owner root-key authority.
    # CI has no OS keychain, so tests use a fixed, non-secret fixture key unless
    # a test deliberately overrides/removes it.
    os.environ.setdefault(
        "PERSONAL_AI_ROOT_KEY",
        base64.b64encode(b"T" * 32).decode("ascii"),
    )
