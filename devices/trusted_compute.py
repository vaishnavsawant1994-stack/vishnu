from __future__ import annotations

from dataclasses import dataclass
import json
import time
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit, urlunsplit


PROTOCOL = "vishnu.trusted-compute/v1"
CAPABILITY = "intelligence_compute_v1"
ACTION = "intelligence_compute_v1"
MAX_PROMPT_CHARS = 12000
MAX_CONTEXT_BYTES = 64 * 1024
MAX_RESULT_CHARS = 64000


def _bounded_json_object(value: Any, *, max_bytes: int = MAX_CONTEXT_BYTES) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("trusted compute context must be an object")
    candidate = dict(value)
    nodes = 0
    stack: list[tuple[Any, int]] = [(candidate, 0)]
    while stack:
        current, depth = stack.pop()
        if depth > 8:
            raise ValueError("trusted compute context nesting exceeds limit")
        if isinstance(current, Mapping):
            if len(current) > 256:
                raise ValueError("trusted compute context contains too many fields")
            for key, child in current.items():
                if len(str(key)) > 256:
                    raise ValueError("trusted compute context key is too long")
                stack.append((child, depth + 1))
        elif isinstance(current, (list, tuple)):
            if len(current) > 256:
                raise ValueError("trusted compute context collection is too large")
            for child in current:
                stack.append((child, depth + 1))
        elif isinstance(current, str) and len(current) > 12000:
            raise ValueError("trusted compute context string is too long")
        nodes += 1
        if nodes > 4096:
            raise ValueError("trusted compute context is too complex")
    try:
        encoded = json.dumps(candidate, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("trusted compute context contains unsupported values") from exc
    if len(encoded) > max_bytes:
        raise ValueError("trusted compute context exceeds size limit")
    return candidate


def sanitize_compute_request(parameters: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(parameters, Mapping):
        raise ValueError("trusted compute parameters must be an object")
    prompt = str(parameters.get("prompt") or "").strip()
    if not 1 <= len(prompt) <= MAX_PROMPT_CHARS:
        raise ValueError("trusted compute prompt is outside the allowed length")
    mode = str(parameters.get("mode") or "smart").strip().lower()
    if mode not in {"fast", "smart", "deep"}:
        raise ValueError("trusted compute mode must be fast, smart, or deep")
    sensitivity = str(parameters.get("sensitivity") or "internal").strip().lower()
    if sensitivity not in {"public", "internal"}:
        raise PermissionError("remote trusted compute accepts only public/internal data")
    max_tokens = int(parameters.get("max_tokens") or 2048)
    if not 1 <= max_tokens <= 8192:
        raise ValueError("trusted compute max_tokens must be between 1 and 8192")
    timeout_seconds = float(parameters.get("timeout_seconds") or 45.0)
    if not 1.0 <= timeout_seconds <= 120.0:
        raise ValueError("trusted compute timeout must be between 1 and 120 seconds")
    device_id = str(parameters.get("device_id") or "").strip()
    if not 1 <= len(device_id) <= 200:
        raise ValueError("trusted compute device_id is required")
    destination = str(parameters.get("destination") or "").strip()
    expected_destination = f"device:{device_id}"
    if destination != expected_destination:
        raise ValueError("trusted compute destination must bind to the target device")
    return {
        "protocol": PROTOCOL,
        "prompt": prompt,
        "context": _bounded_json_object(parameters.get("context") or {}),
        "mode": mode,
        "sensitivity": sensitivity,
        "max_tokens": max_tokens,
        "timeout_seconds": timeout_seconds,
        "task_id": str(parameters.get("task_id") or "")[:200],
    }


def validate_compute_result(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("trusted compute result must be an object")
    if str(value.get("protocol") or "") != PROTOCOL:
        raise ValueError("trusted compute result protocol mismatch")
    content = str(value.get("content") or "")
    if not content or len(content) > MAX_RESULT_CHARS:
        raise ValueError("trusted compute result content is invalid")
    mode = str(value.get("mode") or "").lower()
    if mode not in {"fast", "smart", "deep"}:
        raise ValueError("trusted compute result mode is invalid")
    return {
        "protocol": PROTOCOL,
        "content": content,
        "mode": mode,
        "model_target": str(value.get("model_target") or "")[:300],
        "latency_ms": max(0.0, float(value.get("latency_ms") or 0.0)),
        "verified": bool(value.get("verified", False)),
        "worker_id": str(value.get("worker_id") or "")[:200],
    }


@dataclass(frozen=True)
class TrustedComputeRequest:
    prompt: str
    context: dict[str, Any]
    mode: str
    sensitivity: str
    max_tokens: int
    task_id: str = ""


class TrustedComputeWorker:
    """Device-side bounded compute protocol handler.

    The worker owns no provider credentials itself. A host injects its existing
    governed Vishnu reasoning callback. The protocol cannot execute shell/code,
    use tools, or receive secret-classified payloads.
    """

    def __init__(
        self,
        reasoner: Callable[[TrustedComputeRequest], Any],
        *,
        worker_id: str = "trusted-compute-worker",
    ):
        if not callable(reasoner):
            raise TypeError("trusted compute reasoner callback is required")
        self.reasoner = reasoner
        self.worker_id = str(worker_id)[:200]

    def handle(self, action: str, parameters: Mapping[str, Any]) -> dict[str, Any]:
        if str(action) != ACTION:
            raise ValueError("unsupported trusted compute action")
        clean = sanitize_compute_request(
            {
                **dict(parameters),
                "device_id": str(parameters.get("device_id") or "worker"),
                "destination": str(parameters.get("destination") or f"device:{parameters.get('device_id') or 'worker'}"),
            }
        )
        request = TrustedComputeRequest(
            prompt=clean["prompt"],
            context=clean["context"],
            mode=clean["mode"],
            sensitivity=clean["sensitivity"],
            max_tokens=clean["max_tokens"],
            task_id=clean["task_id"],
        )
        started = time.perf_counter()
        result = self.reasoner(request)
        if isinstance(result, Mapping):
            content = str(result.get("content") or result.get("answer") or "")
            model_target = str(result.get("model_target") or result.get("model") or "")
        else:
            content = str(result or "")
            model_target = ""
        if not content:
            raise RuntimeError("trusted compute reasoner returned no content")
        return validate_compute_result(
            {
                "protocol": PROTOCOL,
                "content": content[:MAX_RESULT_CHARS],
                "mode": request.mode,
                "model_target": model_target,
                "latency_ms": (time.perf_counter() - started) * 1000.0,
                "verified": True,
                "worker_id": self.worker_id,
            }
        )


class TrustedComputeWebSocketWorker:
    """Synchronous device worker for a separately enrolled trusted machine."""

    def __init__(
        self,
        base_url: str,
        device_id: str,
        bearer_token: str,
        worker: TrustedComputeWorker,
        *,
        connect_timeout: float = 15.0,
    ):
        self.base_url = str(base_url).strip()
        self.device_id = str(device_id).strip()
        self.bearer_token = str(bearer_token).strip()
        self.worker = worker
        self.connect_timeout = max(1.0, min(float(connect_timeout), 60.0))
        if len(self.device_id) < 1 or len(self.bearer_token) < 16:
            raise ValueError("trusted compute worker requires paired device credentials")

    def websocket_url(self) -> str:
        parsed = urlsplit(self.base_url)
        if parsed.scheme not in {"https", "wss"}:
            raise ValueError("trusted compute worker requires secure HTTPS/WSS transport")
        scheme = "wss"
        path = parsed.path.rstrip("/") + f"/device/ws/{self.device_id}"
        return urlunsplit((scheme, parsed.netloc, path, "", ""))

    def serve_forever(self) -> None:
        # websocket-client is a project runtime dependency. Import lazily so
        # protocol/unit tests do not require a live transport.
        import websocket

        ws = websocket.create_connection(
            self.websocket_url(),
            header=[f"Authorization: Bearer {self.bearer_token}"],
            timeout=self.connect_timeout,
        )
        try:
            ws.send(
                json.dumps(
                    {
                        "type": "hello",
                        "device_id": self.device_id,
                        "platform": "trusted-compute-worker",
                        "capabilities": [CAPABILITY],
                    },
                    separators=(",", ":"),
                )
            )
            while True:
                raw = ws.recv()
                if raw in (None, ""):
                    raise RuntimeError("trusted compute transport closed")
                message = json.loads(raw)
                if not isinstance(message, Mapping) or message.get("type") != "command":
                    continue
                request_id = str(message.get("request_id") or "")
                action = str(message.get("action") or "")
                parameters = dict(message.get("parameters") or {})
                parameters["device_id"] = self.device_id
                parameters["destination"] = f"device:{self.device_id}"
                try:
                    result = self.worker.handle(action, parameters)
                    reply = {"type": "result", "request_id": request_id, "ok": True, "result": result}
                except Exception as exc:
                    reply = {
                        "type": "result",
                        "request_id": request_id,
                        "ok": False,
                        "error": type(exc).__name__,
                    }
                ws.send(json.dumps(reply, separators=(",", ":"), default=str))
        finally:
            ws.close()
