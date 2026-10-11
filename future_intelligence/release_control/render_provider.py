from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Mapping
from urllib import error, parse, request

from .contracts import ReleaseEnvironment, ReleasePlan
from .providers import ReleaseDeployment
from .telemetry import ProductionTelemetryError, ProductionTelemetryObservation


class RenderProviderError(RuntimeError):
    pass


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RenderProviderError("Render API redirects are not accepted")


@dataclass(frozen=True)
class RenderReleaseConfig:
    api_token: str = field(repr=False)
    preview_service_id: str = ""
    production_service_id: str = ""
    preview_url: str = ""
    production_url: str = ""
    poll_interval_seconds: float = 2.0
    deployment_timeout_seconds: float = 900.0

    def __post_init__(self) -> None:
        for label, value in (
            ("api_token", self.api_token),
            ("preview_service_id", self.preview_service_id),
            ("production_service_id", self.production_service_id),
            ("preview_url", self.preview_url),
            ("production_url", self.production_url),
        ):
            if not str(value).strip():
                raise ValueError(f"Render release config requires {label}")
        if self.poll_interval_seconds <= 0 or self.deployment_timeout_seconds <= 0:
            raise ValueError("Render polling values must be positive")
        if self.preview_service_id == self.production_service_id:
            raise ValueError("Render preview and production must use distinct services")


class RenderReleaseProvider:
    """Deploy exact Git revisions through Render's authenticated REST API.

    The API token is held only by this provider instance. It is never written to
    ReleasePlan, evidence, logs, model context, or API responses.

    Exact-revision release control is only sound when Render auto-deploy is off
    for the bound services. Before every authority-bearing deploy this provider
    reads service configuration and fails closed unless an explicit manual-only
    setting is visible. This prevents an unrelated branch push from racing and
    replacing the candidate that Vishnu actually qualified.
    """

    name = "render"
    _BASE = "https://api.render.com/v1"
    _SUCCESS = {"live"}
    _FAILURE = {"deactivated", "build_failed", "update_failed", "canceled", "pre_deploy_failed"}

    def __init__(self, config: RenderReleaseConfig) -> None:
        self.config = config
        self._opener = request.build_opener(_NoRedirect())

    def _call(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = None if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8")
        req = request.Request(
            f"{self._BASE}{path}",
            data=payload,
            method=method,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.api_token}",
                "User-Agent": "Vishnu-Governed-Release/1",
            },
        )
        try:
            with self._opener.open(req, timeout=30) as response:
                raw = response.read(1_000_001)
                if len(raw) > 1_000_000:
                    raise RenderProviderError("Render API response exceeded the safety bound")
                value = json.loads(raw.decode("utf-8")) if raw else {}
        except (error.HTTPError, error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            code = getattr(exc, "code", None)
            raise RenderProviderError(f"Render API request failed{f' ({code})' if code else ''}") from exc
        if not isinstance(value, dict):
            raise RenderProviderError("Render API returned an unexpected payload")
        return value

    def _metric_series(self, path: str, query: Mapping[str, str]) -> list[dict[str, Any]]:
        req = request.Request(
            f"{self._BASE}{path}?{parse.urlencode(dict(query))}",
            method="GET",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self.config.api_token}",
                "User-Agent": "Vishnu-Production-Telemetry/1",
            },
        )
        try:
            with self._opener.open(req, timeout=20) as response:
                raw = response.read(1_000_001)
                if len(raw) > 1_000_000:
                    raise ProductionTelemetryError("Render telemetry response exceeded the safety bound")
                value = json.loads(raw.decode("utf-8")) if raw else []
        except (error.HTTPError, error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            code = getattr(exc, "code", None)
            raise ProductionTelemetryError(
                f"Render telemetry request failed{f' ({code})' if code else ''}"
            ) from exc
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            raise ProductionTelemetryError("Render telemetry returned an unexpected payload")
        return value

    @staticmethod
    def _commit_id(payload: dict[str, Any]) -> str:
        commit = payload.get("commit") or {}
        return str(commit.get("id") or "").strip()

    @staticmethod
    def _same_revision(left: str, right: str) -> bool:
        left = str(left).strip().lower()
        right = str(right).strip().lower()
        if len(left) < 7 or len(right) < 7:
            return False
        return left == right or left.startswith(right) or right.startswith(left)

    @staticmethod
    def _auto_deploy_value(payload: dict[str, Any]) -> object:
        details = payload.get("serviceDetails")
        candidates = (
            payload.get("autoDeployTrigger"),
            payload.get("autoDeploy"),
            details.get("autoDeployTrigger") if isinstance(details, dict) else None,
            details.get("autoDeploy") if isinstance(details, dict) else None,
        )
        return next((value for value in candidates if value is not None), None)

    @staticmethod
    def _labels(series: Mapping[str, Any]) -> dict[str, str]:
        rows = series.get("labels")
        if not isinstance(rows, list):
            return {}
        output: dict[str, str] = {}
        for row in rows:
            if isinstance(row, Mapping):
                field = str(row.get("field") or "").strip().lower()
                value = str(row.get("value") or "").strip()
                if field and value:
                    output[field] = value
        return output

    @staticmethod
    def _numeric_values(series: Mapping[str, Any]) -> tuple[float, ...]:
        rows = series.get("values")
        if not isinstance(rows, list):
            raise ProductionTelemetryError("Render telemetry series values are malformed")
        output: list[float] = []
        for row in rows:
            if not isinstance(row, Mapping):
                raise ProductionTelemetryError("Render telemetry datapoint is malformed")
            try:
                value = float(row.get("value"))
            except (TypeError, ValueError) as exc:
                raise ProductionTelemetryError("Render telemetry datapoint is not numeric") from exc
            if value < 0:
                raise ProductionTelemetryError("Render telemetry datapoint cannot be negative")
            output.append(value)
        return tuple(output)

    def _validate_metric_scope(self, series: Mapping[str, Any]) -> dict[str, str]:
        labels = self._labels(series)
        for key in ("resource", "service"):
            if key in labels and labels[key] != self.config.production_service_id:
                raise ProductionTelemetryError("Render telemetry escaped the configured production service")
        return labels

    @staticmethod
    def _latency_ms(value: float, unit: str) -> float | None:
        normalized = str(unit or "").strip().lower()
        if normalized in {"ms", "millisecond", "milliseconds"}:
            return value
        if normalized in {"s", "sec", "second", "seconds"}:
            return value * 1000.0
        if normalized in {"us", "µs", "microsecond", "microseconds"}:
            return value / 1000.0
        if normalized in {"ns", "nanosecond", "nanoseconds"}:
            return value / 1_000_000.0
        return None

    def _require_manual_only(self, service_id: str) -> None:
        service = self._call("GET", f"/services/{service_id}")
        value = self._auto_deploy_value(service)
        normalized = str(value).strip().lower() if value is not None else ""
        if value is False:
            return
        if normalized in {"off", "no", "false", "manual", "disabled"}:
            return
        raise RenderProviderError(
            "Render auto-deploy must be disabled for exact-revision governed releases"
        )

    def _wait(self, service_id: str, deploy_id: str, expected_revision: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.config.deployment_timeout_seconds
        while time.monotonic() < deadline:
            payload = self._call("GET", f"/services/{service_id}/deploys/{deploy_id}")
            commit_id = self._commit_id(payload)
            if commit_id and not self._same_revision(commit_id, expected_revision):
                raise RenderProviderError("Render deployment revision drifted from the release plan")
            status = str(payload.get("status") or "")
            if status in self._SUCCESS:
                if not commit_id or not self._same_revision(commit_id, expected_revision):
                    raise RenderProviderError("Render live deployment did not prove the exact candidate revision")
                return payload
            if status in self._FAILURE:
                raise RenderProviderError(f"Render deployment failed with status {status}")
            time.sleep(self.config.poll_interval_seconds)
        raise RenderProviderError("Render deployment timed out before reaching live status")

    def _deploy(
        self,
        plan: ReleasePlan,
        *,
        service_id: str,
        environment: ReleaseEnvironment,
        public_url: str,
        revision: str,
    ) -> ReleaseDeployment:
        self._require_manual_only(service_id)
        payload = self._call(
            "POST",
            f"/services/{service_id}/deploys",
            {"commitId": revision, "clearCache": "do_not_clear"},
        )
        deploy_id = str(payload.get("id") or "")
        if not deploy_id:
            raise RenderProviderError("Render did not return a deployment id")
        commit_id = self._commit_id(payload)
        if commit_id and not self._same_revision(commit_id, revision):
            raise RenderProviderError("Render accepted a different revision than requested")
        live = self._wait(service_id, deploy_id, revision)
        return ReleaseDeployment(
            id=deploy_id,
            provider=self.name,
            target=plan.target,
            revision=revision,
            environment=environment,
            url=public_url,
            state="ready",
            metadata={
                "service_id": service_id,
                "render_status": str(live.get("status") or "live"),
                "trigger": str(live.get("trigger") or "api"),
                "auto_deploy_verified_off": True,
            },
        )

    def create_preview(self, plan: ReleasePlan) -> ReleaseDeployment:
        return self._deploy(
            plan,
            service_id=self.config.preview_service_id,
            environment=ReleaseEnvironment.PREVIEW,
            public_url=self.config.preview_url,
            revision=plan.candidate_revision,
        )

    def promote(self, plan: ReleasePlan) -> ReleaseDeployment:
        return self._deploy(
            plan,
            service_id=self.config.production_service_id,
            environment=ReleaseEnvironment.PRODUCTION,
            public_url=self.config.production_url,
            revision=plan.candidate_revision,
        )

    def observe(self, deployment: ReleaseDeployment) -> ReleaseDeployment:
        service_id = (
            self.config.preview_service_id
            if deployment.environment is ReleaseEnvironment.PREVIEW
            else self.config.production_service_id
        )
        payload = self._call("GET", f"/services/{service_id}/deploys/{deployment.id}")
        commit_id = self._commit_id(payload)
        if commit_id and not self._same_revision(commit_id, deployment.revision):
            raise RenderProviderError("observed Render deployment revision does not match recorded evidence")
        status = str(payload.get("status") or deployment.state)
        return ReleaseDeployment(
            id=deployment.id,
            provider=deployment.provider,
            target=deployment.target,
            revision=deployment.revision,
            environment=deployment.environment,
            url=deployment.url,
            state="ready" if status == "live" else status,
            metadata={**dict(deployment.metadata), "render_status": status},
        )

    def collect_production_telemetry(
        self,
        deployment: ReleaseDeployment,
        *,
        window_seconds: int = 300,
    ) -> ProductionTelemetryObservation:
        if deployment.provider != self.name or deployment.environment is not ReleaseEnvironment.PRODUCTION:
            raise ProductionTelemetryError("Render telemetry requires the bound production deployment")
        window = max(30, min(int(window_seconds), 3_600))
        end = datetime.now(UTC)
        start = end - timedelta(seconds=window)
        common = {
            "resource": self.config.production_service_id,
            "startTime": start.isoformat().replace("+00:00", "Z"),
            "endTime": end.isoformat().replace("+00:00", "Z"),
            "resolutionSeconds": "60",
        }
        request_series = self._metric_series(
            "/metrics/http-requests",
            {**common, "aggregateBy": "statusCode"},
        )
        request_count = 0.0
        server_error_count = 0.0
        for series in request_series:
            labels = self._validate_metric_scope(series)
            status = labels.get("statuscode") or labels.get("status")
            if not status:
                raise ProductionTelemetryError("Render request telemetry omitted the status-code aggregation label")
            values = self._numeric_values(series)
            count = sum(values)
            request_count += count
            try:
                code = int(status)
            except ValueError as exc:
                raise ProductionTelemetryError("Render request telemetry returned an invalid status code") from exc
            if 500 <= code <= 599:
                server_error_count += count

        latency_series = self._metric_series(
            "/metrics/http-latency",
            {**common, "quantile": "0.95"},
        )
        latency_values: list[float] = []
        unsupported_latency_unit = False
        for series in latency_series:
            self._validate_metric_scope(series)
            unit = str(series.get("unit") or "")
            for value in self._numeric_values(series):
                converted = self._latency_ms(value, unit)
                if converted is None:
                    unsupported_latency_unit = True
                    continue
                latency_values.append(converted)

        rounded_requests = int(round(request_count))
        rounded_errors = int(round(server_error_count))
        if abs(request_count - rounded_requests) > 1e-6 or abs(server_error_count - rounded_errors) > 1e-6:
            raise ProductionTelemetryError("Render request telemetry returned fractional request counts")
        return ProductionTelemetryObservation(
            provider=self.name,
            deployment_id=deployment.id,
            request_count=rounded_requests,
            server_error_count=rounded_errors,
            window_seconds=window,
            p95_latency_ms=max(latency_values) if latency_values else None,
            references=(
                f"render:http-requests:{self.config.production_service_id}",
                f"render:http-latency:{self.config.production_service_id}",
            ),
            metadata={
                "service_id": self.config.production_service_id,
                "aggregate_by": "statusCode",
                "latency_quantile": 0.95,
                "latency_unit_supported": not unsupported_latency_unit,
                "raw_logs_persisted": False,
            },
        )

    def rollback(self, plan: ReleasePlan, deployment: ReleaseDeployment) -> ReleaseDeployment:
        # The controller separately checks owner policy and explicit approval.
        return self._deploy(
            plan,
            service_id=self.config.production_service_id,
            environment=ReleaseEnvironment.PRODUCTION,
            public_url=self.config.production_url,
            revision=plan.base_revision,
        )
