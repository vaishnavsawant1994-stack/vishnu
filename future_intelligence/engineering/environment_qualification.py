from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urljoin, urlparse

import requests

from .release_qualification import EnvironmentQualificationResult


@dataclass(frozen=True)
class HttpQualificationProbe:
    name: str
    path: str
    expected_statuses: tuple[int, ...] = (200,)
    max_latency_ms: int = 10_000
    required_text: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("qualification probe name is required")
        if not self.path.startswith("/"):
            raise ValueError("qualification probe path must be absolute within the target origin")
        if not self.expected_statuses or any(not 100 <= int(value) <= 599 for value in self.expected_statuses):
            raise ValueError("qualification probe expected statuses are invalid")
        if not 100 <= int(self.max_latency_ms) <= 120_000:
            raise ValueError("qualification probe latency budget is invalid")


class ReadOnlyHttpQualificationProvider:
    """Bounded GET-only, explicitly origin-scoped environment observer."""

    def __init__(
        self,
        probes: Iterable[HttpQualificationProbe],
        *,
        timeout_seconds: float = 12.0,
        max_response_bytes: int = 2_000_000,
        allowed_hosts: Iterable[str],
        session: requests.Session | None = None,
    ) -> None:
        self.probes = tuple(probes)
        if not self.probes:
            raise ValueError("at least one environment qualification probe is required")
        self.timeout_seconds = max(1.0, min(float(timeout_seconds), 120.0))
        self.max_response_bytes = max(1024, min(int(max_response_bytes), 10_000_000))
        self.allowed_hosts = frozenset(str(item).strip().casefold() for item in allowed_hosts if str(item).strip())
        if not self.allowed_hosts:
            raise ValueError("environment qualification requires at least one explicitly allowed host")
        self.session = session or requests.Session()

    def _target(self, target: str) -> tuple[str, str]:
        raw = str(target or "").strip().rstrip("/") + "/"
        parsed = urlparse(raw)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("qualification target must be an http(s) origin")
        host = parsed.hostname.casefold()
        if host not in self.allowed_hosts:
            raise PermissionError("qualification target host is outside the configured observer scope")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("qualification target must not embed credentials, query data, or fragments")
        origin = f"{parsed.scheme}://{parsed.netloc}"
        return origin, host

    def _run(self, *, environment: str, target: str, binding: str) -> EnvironmentQualificationResult:
        origin, host = self._target(target)
        checks: dict[str, bool] = {}
        evidence: list[str] = []
        summaries: list[str] = []
        for probe in self.probes:
            url = urljoin(origin + "/", probe.path.lstrip("/"))
            parsed = urlparse(url)
            if parsed.hostname is None or parsed.hostname.casefold() != host:
                raise PermissionError("qualification probe escaped the configured target origin")
            started = time.perf_counter()
            try:
                response = self.session.get(
                    url,
                    timeout=self.timeout_seconds,
                    allow_redirects=False,
                    stream=True,
                    headers={"Accept": "text/html,application/json;q=0.9,*/*;q=0.5", "User-Agent": "VishnuQualification/1"},
                )
                body = bytearray()
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    body.extend(chunk)
                    if len(body) > self.max_response_bytes:
                        raise ValueError("qualification response exceeded byte limit")
                latency_ms = int((time.perf_counter() - started) * 1000)
                text = bytes(body).decode(response.encoding or "utf-8", errors="replace")
                passed = (
                    int(response.status_code) in probe.expected_statuses
                    and latency_ms <= probe.max_latency_ms
                    and (not probe.required_text or probe.required_text in text)
                )
                checks[probe.name] = bool(passed)
                digest = hashlib.sha256(bytes(body)).hexdigest()
                evidence.append(
                    f"{probe.name}:status={response.status_code};latency_ms={latency_ms};sha256={digest};bytes={len(body)}"
                )
                summaries.append(f"{probe.name}={'pass' if passed else 'fail'}")
            except (requests.RequestException, ValueError) as exc:
                checks[probe.name] = False
                evidence.append(f"{probe.name}:error={type(exc).__name__}")
                summaries.append(f"{probe.name}=fail")
        healthy = bool(checks.get("health", next(iter(checks.values()), False)))
        evidence.append(f"binding={binding}")
        return EnvironmentQualificationResult(
            environment=str(environment),
            target=origin,
            healthy=healthy,
            checks=checks,
            evidence=tuple(evidence),
            summary="; ".join(summaries),
        )

    def qualify_preview(self, *, target: str, spec_id: str) -> EnvironmentQualificationResult:
        return self._run(environment="preview", target=target, binding=f"spec:{spec_id}")

    def smoke_production(self, *, target: str, release_revision: str) -> EnvironmentQualificationResult:
        return self._run(environment="production", target=target, binding=f"revision:{release_revision}")
