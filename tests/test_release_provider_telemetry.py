from __future__ import annotations

import json
import time

import pytest

from future_intelligence.release_control.contracts import ReleaseEnvironment
from future_intelligence.release_control.providers import ReleaseDeployment
from future_intelligence.release_control.render_provider import RenderReleaseConfig, RenderReleaseProvider
from future_intelligence.release_control.telemetry import ProductionTelemetryError
from future_intelligence.release_control.vercel_provider import VercelReleaseConfig, VercelReleaseProvider


CANDIDATE = "b" * 40


def deployment(provider: str, deployment_id: str = "dpl_prod") -> ReleaseDeployment:
    return ReleaseDeployment(
        id=deployment_id,
        provider=provider,
        target="owner/repo",
        revision=CANDIDATE,
        environment=ReleaseEnvironment.PRODUCTION,
        url="https://production.example.test",
        state="ready",
    )


def render_config() -> RenderReleaseConfig:
    return RenderReleaseConfig(
        api_token="render-secret-token",
        preview_service_id="srv_preview",
        production_service_id="srv_production",
        preview_url="https://preview.example.test",
        production_url="https://production.example.test",
    )


def vercel_config() -> VercelReleaseConfig:
    return VercelReleaseConfig(
        api_token="vercel-secret-token",
        project_id="prj_test",
        project_name="vishnu",
        github_org="owner",
        github_repo="repo",
        production_url="https://production.example.test",
        team_id="team_test",
    )


class FakeRenderTelemetryProvider(RenderReleaseProvider):
    def __init__(self, *, wrong_service: bool = False):
        super().__init__(render_config())
        self.wrong_service = wrong_service
        self.metric_calls = []

    def _metric_series(self, path, query):
        self.metric_calls.append((path, dict(query)))
        service = "srv_wrong" if self.wrong_service else "srv_production"
        if path.endswith("http-requests"):
            return [
                {
                    "labels": [
                        {"field": "service", "value": service},
                        {"field": "statusCode", "value": "200"},
                    ],
                    "values": [{"value": 95}, {"value": 2}],
                    "unit": "requests",
                },
                {
                    "labels": [
                        {"field": "service", "value": service},
                        {"field": "statusCode", "value": "500"},
                    ],
                    "values": [{"value": 3}],
                    "unit": "requests",
                },
            ]
        if path.endswith("http-latency"):
            return [
                {
                    "labels": [{"field": "service", "value": service}],
                    "values": [{"value": 0.12}, {"value": 0.2}],
                    "unit": "seconds",
                }
            ]
        raise AssertionError(path)


class FakeVercelTelemetryProvider(VercelReleaseProvider):
    def __init__(self, rows):
        super().__init__(vercel_config())
        self.rows = tuple(rows)

    def _runtime_log_rows(self, deployment_id):
        assert deployment_id == "dpl_prod"
        return self.rows


class FakeResponse:
    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, size=-1):
        return self.payload if size < 0 else self.payload[:size]


class FakeOpener:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.requests = []

    def open(self, req, timeout=None):
        self.requests.append((req, timeout))
        return FakeResponse(self.payload)


def test_render_telemetry_aggregates_request_errors_and_p95_without_raw_data():
    provider = FakeRenderTelemetryProvider()
    observation = provider.collect_production_telemetry(deployment("render"), window_seconds=300)

    assert observation.request_count == 100
    assert observation.server_error_count == 3
    assert observation.error_rate == pytest.approx(0.03)
    assert observation.p95_latency_ms == pytest.approx(200.0)
    assert observation.metadata["service_id"] == "srv_production"
    assert observation.to_safe_dict()["raw_logs_persisted"] is False
    assert provider.metric_calls[0][1]["resource"] == "srv_production"
    assert provider.metric_calls[0][1]["aggregateBy"] == "statusCode"
    assert provider.metric_calls[1][1]["quantile"] == "0.95"
    assert "render-secret-token" not in repr(provider.config)
    assert "render-secret-token" not in json.dumps(observation.to_safe_dict(), sort_keys=True)


def test_render_telemetry_rejects_provider_scope_drift():
    provider = FakeRenderTelemetryProvider(wrong_service=True)
    with pytest.raises(ProductionTelemetryError, match="escaped the configured production service"):
        provider.collect_production_telemetry(deployment("render"))


def test_vercel_telemetry_uses_only_current_status_aggregates_and_deduplicates_rows():
    stamp = int(time.time() * 1000)
    provider = FakeVercelTelemetryProvider(
        [
            {
                "rowId": "row-1",
                "responseStatusCode": 200,
                "timestampInMs": stamp,
                "message": "private payload must never persist",
                "requestPath": "/private/path",
            },
            {
                "rowId": "row-2",
                "responseStatusCode": 503,
                "timestampInMs": stamp,
                "message": "database secret text",
                "requestPath": "/admin",
            },
            {
                "rowId": "row-2",
                "responseStatusCode": 503,
                "timestampInMs": stamp,
                "message": "duplicate",
            },
            {
                "rowId": "row-3",
                "responseStatusCode": -1,
                "timestampInMs": stamp,
                "message": "crashed",
            },
            {
                "rowId": "stale-500",
                "responseStatusCode": 500,
                "timestampInMs": stamp - 600_000,
                "message": "old failure must not become a current incident",
            },
        ]
    )
    observation = provider.collect_production_telemetry(
        deployment("vercel"),
        window_seconds=300,
    )
    safe = observation.to_safe_dict()

    assert observation.request_count == 3
    assert observation.server_error_count == 2
    assert observation.p95_latency_ms is None
    assert safe["metadata"]["runtime_log_rows_sampled"] == 3
    assert safe["metadata"]["rows_ignored_outside_window"] == 1
    assert safe["metadata"]["window_filtered_by_timestamp"] is True
    serialized = json.dumps(safe, sort_keys=True)
    for forbidden in (
        "private payload",
        "database secret",
        "old failure",
        "/private/path",
        "/admin",
        "vercel-secret-token",
    ):
        assert forbidden not in serialized
    assert "vercel-secret-token" not in repr(provider.config)


def test_vercel_runtime_log_reader_is_exact_project_and_deployment_scoped():
    provider = VercelReleaseProvider(vercel_config())
    payload = json.dumps(
        [
            {
                "domain": "production.example.test",
                "level": "info",
                "message": "discard me",
                "messageTruncated": False,
                "requestMethod": "GET",
                "requestPath": "/health",
                "responseStatusCode": 200,
                "rowId": "row-1",
                "source": "serverless",
                "timestampInMs": 1,
            }
        ]
    ).encode()
    opener = FakeOpener(payload)
    provider._opener = opener

    rows = provider._runtime_log_rows("dpl_prod")
    assert rows[0]["rowId"] == "row-1"
    req, timeout = opener.requests[0]
    assert req.full_url == (
        "https://api.vercel.com/v1/projects/prj_test/deployments/dpl_prod/runtime-logs?teamId=team_test"
    )
    assert timeout == 10


def test_vercel_runtime_log_reader_rejects_oversized_stream():
    provider = VercelReleaseProvider(vercel_config())
    provider._opener = FakeOpener(b"x" * 500_001)
    with pytest.raises(ProductionTelemetryError, match="safety bound"):
        provider._runtime_log_rows("dpl_prod")


def test_vercel_telemetry_rejects_invalid_status_instead_of_manufacturing_health():
    provider = FakeVercelTelemetryProvider(
        [
            {
                "rowId": "row-1",
                "responseStatusCode": "not-a-code",
                "timestampInMs": int(time.time() * 1000),
            }
        ]
    )
    with pytest.raises(ProductionTelemetryError, match="invalid status code"):
        provider.collect_production_telemetry(deployment("vercel"))


def test_vercel_telemetry_rejects_missing_timestamp_instead_of_counting_unbounded_history():
    provider = FakeVercelTelemetryProvider(
        [{"rowId": "row-1", "responseStatusCode": 500}]
    )
    with pytest.raises(ProductionTelemetryError, match="valid timestamp"):
        provider.collect_production_telemetry(deployment("vercel"))


def test_vercel_telemetry_rejects_implausible_future_timestamp():
    provider = FakeVercelTelemetryProvider(
        [
            {
                "rowId": "row-1",
                "responseStatusCode": 200,
                "timestampInMs": int(time.time() * 1000) + 120_000,
            }
        ]
    )
    with pytest.raises(ProductionTelemetryError, match="future timestamp"):
        provider.collect_production_telemetry(deployment("vercel"))
