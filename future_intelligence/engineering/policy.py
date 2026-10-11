from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterable

from evolution.code_policy import evaluate_code_change


_ALWAYS_DENIED = (
    ".git/",
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "id_rsa",
    "id_ed25519",
)
_SECRET_NAME = re.compile(r"(^|[._-])(secret|secrets|credential|credentials|private[_-]?key)([._-]|$)", re.I)


@dataclass(frozen=True)
class EngineeringPathDecision:
    allowed: bool
    path: str
    reason: str
    authority_sensitive: bool = False


def normalize_repository_path(raw: str) -> str:
    candidate = PurePosixPath(str(raw or "").strip())
    if not candidate.parts or candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("repository path must be a safe relative path")
    value = candidate.as_posix()
    if value.startswith("./"):
        value = value[2:]
    return value


def _matches_prefix(path: str, rule: str) -> bool:
    raw = str(rule or "").strip().replace("\\", "/")
    if raw in {".", "./", "*", "**", "**/*"}:
        return True
    normalized = raw.lstrip("./")
    if not normalized:
        return False
    if any(char in normalized for char in "*?["):
        return fnmatch.fnmatch(path, normalized)
    if normalized.endswith("/"):
        root = normalized.rstrip("/")
        return path == root or path.startswith(root + "/")
    return path == normalized or path.startswith(normalized.rstrip("/") + "/")


def evaluate_engineering_path(
    raw: str,
    *,
    allowed_paths: Iterable[str] = (),
    prohibited_paths: Iterable[str] = (),
    allow_authority_paths: bool = False,
) -> EngineeringPathDecision:
    try:
        path = normalize_repository_path(raw)
    except ValueError as exc:
        return EngineeringPathDecision(False, str(raw), str(exc))
    lower = path.lower()
    name = PurePosixPath(path).name
    for rule in _ALWAYS_DENIED:
        if fnmatch.fnmatch(lower, rule.lower()) or (rule.endswith("/") and lower.startswith(rule.lower())):
            return EngineeringPathDecision(False, path, "secret-bearing or repository-control path is denied")
    if _SECRET_NAME.search(name) and not name.lower().endswith((".example", ".sample", ".template")):
        return EngineeringPathDecision(False, path, "secret-bearing filename is denied")
    if any(_matches_prefix(path, rule) for rule in prohibited_paths):
        return EngineeringPathDecision(False, path, "path is prohibited by EngineeringSpec")
    allowed = tuple(str(rule) for rule in allowed_paths if str(rule).strip())
    if allowed and not any(_matches_prefix(path, rule) for rule in allowed):
        return EngineeringPathDecision(False, path, "path is outside EngineeringSpec allowed_paths")
    evolution = evaluate_code_change((path,))
    authority_sensitive = not evolution.allowed
    if authority_sensitive and not allow_authority_paths:
        return EngineeringPathDecision(False, path, "path is protected by canonical code-authority policy", True)
    return EngineeringPathDecision(True, path, "path is within governed engineering scope", authority_sensitive)


def require_engineering_path(raw: str, **kwargs) -> str:
    decision = evaluate_engineering_path(raw, **kwargs)
    if not decision.allowed:
        raise PermissionError(f"{decision.path}: {decision.reason}")
    return decision.path
