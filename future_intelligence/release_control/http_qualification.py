from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
from urllib import error, request
from urllib.parse import urljoin, urlsplit

from future_intelligence.engineering.release_qualification import EnvironmentQualificationResult


class HttpQualificationError(RuntimeError):
    pass


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HttpQualificationError("environment qualification does not follow redirects")


@dataclass(frozen=True)
class HttpQualificationConfig:
    allowed_hosts: tuple[str, ...]
    paths: tuple[str, ...] = ("/", "/health")
    timeout_seconds: float = 15.0
    max_response_bytes: int = 512_000

    def __post_init__(self) -> None:
        if not self.allowed_hosts:
            raise ValueError("at least one allowed qualification host is required")
        if not self.paths:
            raise ValueError("at least one qualification path is required")
        if self.timeout_seconds <= 0:
            raise ValueError("qualification timeout must be positive")
        if not 1024 <= self.max_response_bytes <= 5_000_000:
            raise ValueError("qualification response bound is outside the supported range")
        for path in self.paths:
            if not path.startswith("/") or "?" in path or "#" in path:
                raise ValueError("qualification paths must be absolute path-only values")


class ReadOnlyHttpEnvironmentQualifier:
    """Credential-free GET-only preview and production smoke qualification."""

    def __init__(self, config: HttpQualificationConfig) -> None:
        self.config = config
        self._allowed = {host.strip().lower() for host in config.allowed_hosts if host.strip()}
        self._opener = request.build_opener(_NoRedirect())

    def _validate_target(self, target: str) -> str:
        parsed = urlsplit(target)
        if parsed.scheme != "https" or not parsed.hostname:
            raise HttpQualificationError("qualification target must use HTTPS")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise HttpQualificationError("qualification target must not contain credentials, query, or fragment")
        if parsed.hostname.lower() not in self._allowed:
            raise HttpQualificationError("qualification target host is not allowlisted")
        return target.rstrip("/") + "/"

    def _run(self, *, environment: str, target: str, revision: str, extra_check: tuple[str, bool]) -> EnvironmentQualificationResult:
        root = self._validate_target(target)
        checks: dict[str, bool] = {extra_check[0]: bool(extra_check[1])}
        evidence: list[str] = []
        for path in self.config.paths:
            url = urljoin(root, path.lstrip("/"))
            req = request.Request(url, method="GET", headers={"Accept": "text/html,application/json;q=0.9,*/*;q=0.1", "User-Agent": "Vishnu-Release-Qualification/1"})
            key = f"GET {path}"
            try:
                with self._opener.open(req, timeout=self.config.timeout_seconds) as response:
                    status = int(getattr(response, "status", 0) or 0)
                    body = response.read(self.config.max_response_bytes + 1)
                    bounded = len(body) <= self.config.max_response_bytes
                    checks[key] = 200 <= status < 400 and bounded
                    evidence.append(f"{url} status={status} bytes={min(len(body), self.config.max_response_bytes + 1)}")
            except (error.HTTPError, error.URLError, TimeoutError, HttpQualificationError) as exc:
                checks[key] = False
                code = getattr(exc, "code", None)
                evidence.append(f"{url} failed{f' status={code}' if code else ''}")
        healthy = bool(checks) and all(checks.values())
        return EnvironmentQualificationResult(
            environment=environment,
            target=target,
            healthy=healthy,
            checks=checks,
            evidence=tuple(evidence),
            summary=(
                f"{environment} read-only HTTP qualification passed for revision {revision}."
                if healthy
                else f"{environment} read-only HTTP qualification failed for revision {revision}."
            ),
        )

    def qualify_preview(self, *, target: str, spec_id: str, candidate_revision: str) -> EnvironmentQualificationResult:
        return self._run(
            environment="preview",
            target=target,
            revision=candidate_revision,
            extra_check=("spec_id_present", bool(spec_id.strip())),
        )

    def smoke_production(self, *, target: str, release_revision: str) -> EnvironmentQualificationResult:
        return self._run(
            environment="production",
            target=target,
            revision=release_revision,
            extra_check=("release_revision_present", bool(release_revision.strip())),
        )
