from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _runner_module():
    spec = importlib.util.spec_from_file_location(
        "vishnu_test_product_runner_worker",
        ROOT / "packaging" / "product_runner_worker.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, status_code: int, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


class ReplaySession:
    def __init__(self):
        self.headers = {}
        self.payloads = []

    def put(self, _url, *, headers, data, timeout):
        assert headers["X-Vishnu-Artifact-SHA256"]
        assert timeout >= 10
        self.payloads.append(data.read())
        if len(self.payloads) == 1:
            return FakeResponse(503, text="retry")
        return FakeResponse(200, {"accepted": True, "build": {"metadata": {"artifact_ready": True}}})


def test_upload_reopens_artifact_for_transient_retry(tmp_path, monkeypatch):
    runner = _runner_module()
    worker = runner.ProductRunnerWorker(
        base_url="http://localhost:8000",
        token="qualification-runner-token",
        target="linux",
        runner_id="linux-worker-1",
    )
    session = ReplaySession()
    worker.session = session
    monkeypatch.setattr(runner.time, "sleep", lambda _seconds: None)

    artifact = tmp_path / "qualified.deb"
    artifact.write_bytes(b"same-artifact-bytes-on-every-retry")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    evidence = {
        "schema": "vishnu.platform-runner-evidence/v1",
        "product_id": "product-1",
        "build_id": "build-1",
        "version": "1.0.0",
        "target": "linux",
        "mode": "production",
        "host_os": "linux",
        "artifact_name": artifact.name,
        "artifact_kind": "deb",
        "sha256": digest,
        "compiler_verified": True,
        "signing_verified": False,
        "provisioning_verified": False,
        "notarization_verified": False,
        "metadata": {},
    }
    result = worker.upload(
        {"build_id": "build-1", "lease": "lease-token"},
        {"artifact": str(artifact), "sha256": digest, "evidence": evidence},
    )
    assert result["accepted"] is True
    assert session.payloads == [artifact.read_bytes(), artifact.read_bytes()]


def test_worker_rejects_non_https_remote_server():
    runner = _runner_module()
    try:
        runner.ProductRunnerWorker(
            base_url="http://runner.example.com",
            token="qualification-runner-token",
            target="linux",
            runner_id="runner-1",
        )
    except runner.WorkerError as exc:
        assert "HTTPS" in str(exc)
    else:
        raise AssertionError("Remote plaintext runner URL must be rejected")


def test_worker_never_accepts_short_bearer_token():
    runner = _runner_module()
    try:
        runner.ProductRunnerWorker(
            base_url="https://runner.example.com",
            token="short",
            target="linux",
            runner_id="runner-1",
        )
    except runner.WorkerError as exc:
        assert "too short" in str(exc)
    else:
        raise AssertionError("Short runner bearer token must be rejected")
