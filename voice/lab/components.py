"""Completeness registry for the Voice Lab implementation itself."""
from __future__ import annotations

from pathlib import Path


LAB_COMPONENT_PATHS = (
    "voice/lab/benchmarks.py",
    "voice/lab/catalog.py",
    "voice/lab/comparison.py",
    "voice/lab/components.py",
    "voice/lab/dashboard.py",
    "voice/lab/devices.py",
    "voice/lab/evaluation.py",
    "voice/lab/evidence.py",
    "voice/lab/experiments.py",
    "voice/lab/fixtures.py",
    "voice/lab/promotion.py",
    "voice/lab/regression.py",
    "voice/lab/release.py",
    "voice/lab/runner.py",
    "voice/lab/subprocess_adapter.py",
    "voice/lab/telephony.py",
)


def unregistered_modules(package_dir: Path | None = None) -> tuple[str, ...]:
    directory = package_dir or Path(__file__).resolve().parent
    actual = {
        f"voice/lab/{path.name}"
        for path in directory.glob("*.py")
        if path.name != "__init__.py"
    }
    registered = set(LAB_COMPONENT_PATHS)
    return tuple(sorted(actual - registered))


def missing_modules(package_dir: Path | None = None) -> tuple[str, ...]:
    directory = package_dir or Path(__file__).resolve().parent
    actual = {f"voice/lab/{path.name}" for path in directory.glob("*.py")}
    return tuple(sorted(set(LAB_COMPONENT_PATHS) - actual))
