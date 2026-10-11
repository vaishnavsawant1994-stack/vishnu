from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


_REQUIREMENT = re.compile(r"^([A-Za-z0-9_.-]+)\s*([<>=!~].*)?$")
_EXACT_PIN = re.compile(r"^==\s*[^,;\s]+$")


@dataclass(frozen=True)
class DependencyFinding:
    path: str
    dependency: str
    severity: str
    reason: str

    @property
    def blocking(self) -> bool:
        return self.severity in {"high", "critical"}


@dataclass(frozen=True)
class DependencyQualificationResult:
    findings: tuple[DependencyFinding, ...]
    files_checked: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not any(item.blocking for item in self.findings)

    def to_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "files_checked": list(self.files_checked),
            "findings": [item.__dict__ | {"blocking": item.blocking} for item in self.findings],
        }


class DependencyQualifier:
    """Offline dependency-policy checks; no registry/network/package mutation authority."""

    def __init__(self, *, allow_unpinned: Iterable[str] = ()) -> None:
        self.allow_unpinned = frozenset(str(item).casefold() for item in allow_unpinned)

    def _requirements(self, path: Path, relative: str) -> list[DependencyFinding]:
        findings: list[DependencyFinding] = []
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith(("-r ", "--requirement ")):
                continue
            if line.startswith(("git+", "http://", "https://", "file:", "-e ", "--editable ")):
                findings.append(DependencyFinding(relative, line[:300], "high", "direct URL/VCS/editable dependency requires explicit review"))
                continue
            requirement = line.split(";", 1)[0].strip()
            match = _REQUIREMENT.match(requirement)
            if not match:
                findings.append(DependencyFinding(relative, requirement[:300], "review", "unrecognized requirement syntax"))
                continue
            name = match.group(1)
            specifier = (match.group(2) or "").strip()
            if name.casefold() in self.allow_unpinned:
                continue
            if not specifier:
                findings.append(DependencyFinding(relative, name, "medium", "dependency is unversioned"))
            elif not _EXACT_PIN.match(specifier):
                findings.append(DependencyFinding(relative, name + specifier, "review", "dependency uses a version range rather than an exact reproducible pin"))
        return findings

    @staticmethod
    def _package_lock(path: Path, relative: str) -> list[DependencyFinding]:
        findings: list[DependencyFinding] = []
        payload = json.loads(path.read_text(encoding="utf-8"))
        packages = payload.get("packages") if isinstance(payload, dict) else None
        if isinstance(packages, dict):
            for name, row in packages.items():
                if not isinstance(row, dict) or not name:
                    continue
                resolved = str(row.get("resolved") or "")
                integrity = str(row.get("integrity") or "")
                if resolved.startswith(("git+", "http://")):
                    findings.append(DependencyFinding(relative, str(name), "high", "lockfile dependency uses untrusted transport or VCS source"))
                if resolved.startswith("https://") and not integrity:
                    findings.append(DependencyFinding(relative, str(name), "medium", "remote package has no integrity hash"))
        return findings

    def qualify(self, root: str | Path) -> DependencyQualificationResult:
        base = Path(root).expanduser().resolve()
        if not base.is_dir():
            raise ValueError("dependency qualification root must be a directory")
        files: list[str] = []
        findings: list[DependencyFinding] = []
        for name in ("requirements.txt", "requirements-dev.txt", "package-lock.json", "npm-shrinkwrap.json"):
            path = base / name
            if not path.is_file() or path.is_symlink():
                continue
            files.append(name)
            try:
                if name.startswith("requirements"):
                    findings.extend(self._requirements(path, name))
                else:
                    findings.extend(self._package_lock(path, name))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                findings.append(DependencyFinding(name, "", "high", f"dependency manifest could not be parsed: {type(exc).__name__}"))
        return DependencyQualificationResult(tuple(findings), tuple(files))
