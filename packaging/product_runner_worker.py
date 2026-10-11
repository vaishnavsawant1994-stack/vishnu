from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from products.platform_jobs import REMOTE_PLATFORM_TARGETS


class WorkerError(RuntimeError):
    pass


def _module(filename: str, name: str):
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise WorkerError(f"Unable to load runner adapter {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _base_url(value: str) -> str:
    value = str(value or "").strip().rstrip("/")
    if not value:
        raise WorkerError("VISHNU_PRODUCT_RUNNER_BASE_URL or --base-url is required")
    parsed = urlparse(value)
    local = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    if parsed.scheme != "https" and not (parsed.scheme == "http" and local):
        raise WorkerError("Runner server URL must use HTTPS except for localhost development")
    if not parsed.netloc:
        raise WorkerError("Runner server URL is invalid")
    return value


def _token(value: str) -> str:
    value = str(value or "").strip()
    if len(value) < 16:
        raise WorkerError("VISHNU_PRODUCT_RUNNER_TOKEN is missing or too short")
    return value


def _safe_error(exc: Exception) -> str:
    message = str(exc).replace("\r", " ").replace("\n", " ").strip()
    return f"{type(exc).__name__}: {message[:1200]}"


class ProductRunnerWorker:
    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        target: str,
        runner_id: str,
        heartbeat_seconds: int = 60,
        request_timeout: int = 120,
    ):
        if target not in REMOTE_PLATFORM_TARGETS:
            raise WorkerError(f"Unsupported runner target: {target}")
        self.base_url = _base_url(base_url)
        self.token = _token(token)
        self.target = target
        self.runner_id = str(runner_id or "").strip()
        if not self.runner_id:
            raise WorkerError("Runner ID is required")
        self.heartbeat_seconds = max(15, min(int(heartbeat_seconds), 300))
        self.request_timeout = max(10, min(int(request_timeout), 600))
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})

    def _url(self, suffix: str) -> str:
        return f"{self.base_url}/iphone/api/products/runner{suffix}"

    def _request(self, method: str, url: str, *, attempts: int = 3, **kwargs):
        last = None
        for attempt in range(1, attempts + 1):
            try:
                response = self.session.request(method, url, timeout=self.request_timeout, **kwargs)
                if response.status_code < 500 or attempt == attempts:
                    return response
                last = WorkerError(f"Server returned {response.status_code}")
            except requests.RequestException as exc:
                last = exc
            if attempt < attempts:
                time.sleep(min(2 ** (attempt - 1), 4))
        raise WorkerError(_safe_error(last or WorkerError("request failed")))

    def claim(self) -> dict | None:
        response = self._request(
            "POST",
            self._url("/claim"),
            params={"target": self.target},
            headers={"X-Vishnu-Runner-ID": self.runner_id},
        )
        if response.status_code == 204:
            return None
        if response.status_code != 200:
            raise WorkerError(f"Claim failed with HTTP {response.status_code}: {response.text[:500]}")
        required = [
            "X-Vishnu-Product-ID",
            "X-Vishnu-Build-ID",
            "X-Vishnu-Build-Target",
            "X-Vishnu-Runner-Lease",
            "X-Vishnu-Build-Job-SHA256",
        ]
        missing = [name for name in required if not response.headers.get(name)]
        if missing:
            raise WorkerError(f"Claim response is missing required headers: {', '.join(missing)}")
        if response.headers["X-Vishnu-Build-Target"] != self.target:
            raise WorkerError("Claimed build target does not match this runner")
        digest = hashlib.sha256(response.content).hexdigest()
        if digest != response.headers["X-Vishnu-Build-Job-SHA256"].lower():
            raise WorkerError("Claimed build-job digest does not match response bytes")
        return {
            "product_id": response.headers["X-Vishnu-Product-ID"],
            "build_id": response.headers["X-Vishnu-Build-ID"],
            "target": self.target,
            "lease": response.headers["X-Vishnu-Runner-Lease"],
            "job_sha256": digest,
            "job": response.content,
        }

    def heartbeat(self, build_id: str, lease: str) -> None:
        response = self._request(
            "POST",
            self._url(f"/{build_id}/heartbeat"),
            headers={"X-Vishnu-Runner-Lease": lease},
            attempts=2,
        )
        if response.status_code != 200:
            raise WorkerError(f"Heartbeat failed with HTTP {response.status_code}")

    def _heartbeat_loop(self, build_id: str, lease: str, stop: threading.Event, failures: list[str]) -> None:
        while not stop.wait(self.heartbeat_seconds):
            try:
                self.heartbeat(build_id, lease)
            except Exception as exc:
                failures.append(_safe_error(exc))
                stop.set()
                return

    def _compile(self, job_path: Path, output_dir: Path) -> dict:
        if self.target == "android":
            module = _module("product_platform_runner.py", "_vishnu_android_worker")
            return module.build_android(job_path, output_dir, allow_unsigned_job=False, compile_artifact=True)
        if self.target in {"linux", "windows", "docker"}:
            module = _module("product_desktop_container_runner.py", "_vishnu_desktop_worker")
            if self.target == "linux":
                return module.build_linux(job_path, output_dir, allow_unsigned_job=False)
            if self.target == "windows":
                return module.build_windows(job_path, output_dir, allow_unsigned_job=False)
            return module.build_docker(job_path, output_dir, allow_unsigned_job=False)
        if self.target in {"macos", "ios"}:
            module = _module("product_apple_runner.py", "_vishnu_apple_worker")
            if self.target == "macos":
                return module.build_macos(job_path, output_dir, allow_unsigned_job=False)
            return module.build_ios(job_path, output_dir, allow_unsigned_job=False)
        raise WorkerError(f"No compiler adapter is configured for {self.target}")

    def upload(self, claim: dict, result: dict) -> dict:
        artifact = Path(str(result.get("artifact") or ""))
        evidence = result.get("evidence")
        if not artifact.is_file() or not isinstance(evidence, dict):
            raise WorkerError("Compiler did not return a valid artifact and evidence object")
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        if digest != str(result.get("sha256") or "").lower() or digest != str(evidence.get("sha256") or "").lower():
            raise WorkerError("Compiler artifact digest is inconsistent with runner evidence")
        raw_evidence = json.dumps(evidence, sort_keys=True, separators=(",", ":"))
        if len(raw_evidence) > 16 * 1024:
            raise WorkerError("Runner evidence is too large for the callback contract")
        with artifact.open("rb") as stream:
            response = self._request(
                "PUT",
                self._url(f"/{claim['build_id']}/artifact"),
                headers={
                    "X-Vishnu-Runner-Lease": claim["lease"],
                    "X-Vishnu-Artifact-Name": artifact.name,
                    "X-Vishnu-Artifact-SHA256": digest,
                    "X-Vishnu-Runner-Evidence": raw_evidence,
                    "Content-Type": "application/octet-stream",
                },
                data=stream,
            )
        if response.status_code != 200:
            raise WorkerError(f"Artifact callback failed with HTTP {response.status_code}: {response.text[:500]}")
        return response.json()

    def complete(self, build_id: str, lease: str) -> None:
        response = self._request(
            "POST",
            self._url(f"/{build_id}/complete"),
            headers={"X-Vishnu-Runner-Lease": lease},
        )
        if response.status_code != 200:
            raise WorkerError(f"Lease completion failed with HTTP {response.status_code}: {response.text[:500]}")

    def fail(self, build_id: str, lease: str, reason: str) -> None:
        response = self._request(
            "POST",
            self._url(f"/{build_id}/failed"),
            headers={"X-Vishnu-Runner-Lease": lease},
            json={"reason": reason[:2000]},
            attempts=2,
        )
        if response.status_code not in {200, 409}:
            raise WorkerError(f"Failure callback returned HTTP {response.status_code}")

    def run_once(self) -> dict:
        claim = self.claim()
        if claim is None:
            return {"status": "idle", "target": self.target, "runner_id": self.runner_id}
        stop = threading.Event()
        heartbeat_failures: list[str] = []
        thread = threading.Thread(
            target=self._heartbeat_loop,
            args=(claim["build_id"], claim["lease"], stop, heartbeat_failures),
            name="vishnu-product-runner-heartbeat",
            daemon=True,
        )
        thread.start()
        try:
            with tempfile.TemporaryDirectory(prefix=f"vishnu-product-worker-{self.target}-") as temporary:
                root = Path(temporary)
                job = root / "job.vishnu-build-job"
                output = root / "output"
                job.write_bytes(claim["job"])
                result = self._compile(job, output)
                if heartbeat_failures:
                    raise WorkerError(f"Runner lease heartbeat failed: {heartbeat_failures[-1]}")
                callback = self.upload(claim, result)
                self.complete(claim["build_id"], claim["lease"])
                return {
                    "status": "completed",
                    "target": self.target,
                    "runner_id": self.runner_id,
                    "product_id": claim["product_id"],
                    "build_id": claim["build_id"],
                    "artifact_name": Path(result["artifact"]).name,
                    "sha256": result["sha256"],
                    "distribution_ready": bool((callback.get("build") or {}).get("metadata", {}).get("artifact_ready")),
                }
        except Exception as exc:
            try:
                self.fail(claim["build_id"], claim["lease"], _safe_error(exc))
            except Exception:
                pass
            raise
        finally:
            stop.set()
            thread.join(timeout=5)


def main() -> None:
    parser = argparse.ArgumentParser(description="Autonomous Vishnu product platform runner worker")
    parser.add_argument("--target", choices=REMOTE_PLATFORM_TARGETS, required=True)
    parser.add_argument("--base-url", default=os.environ.get("VISHNU_PRODUCT_RUNNER_BASE_URL", ""))
    parser.add_argument("--token", default=os.environ.get("VISHNU_PRODUCT_RUNNER_TOKEN", ""))
    parser.add_argument("--runner-id", default=os.environ.get("VISHNU_PRODUCT_RUNNER_ID", ""))
    parser.add_argument("--heartbeat-seconds", type=int, default=int(os.environ.get("VISHNU_PRODUCT_RUNNER_HEARTBEAT_SECONDS", "60")))
    parser.add_argument("--poll-seconds", type=int, default=int(os.environ.get("VISHNU_PRODUCT_RUNNER_POLL_SECONDS", "30")))
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    runner_id = args.runner_id.strip() or f"{socket.gethostname()}:{args.target}"
    worker = ProductRunnerWorker(
        base_url=args.base_url,
        token=args.token,
        target=args.target,
        runner_id=runner_id,
        heartbeat_seconds=args.heartbeat_seconds,
    )
    if args.once:
        print(json.dumps(worker.run_once(), sort_keys=True))
        return
    poll = max(5, min(args.poll_seconds, 300))
    while True:
        try:
            result = worker.run_once()
            print(json.dumps(result, sort_keys=True), flush=True)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            print(json.dumps({"status": "error", "target": args.target, "error": _safe_error(exc)}, sort_keys=True), flush=True)
        time.sleep(poll)


if __name__ == "__main__":
    main()
