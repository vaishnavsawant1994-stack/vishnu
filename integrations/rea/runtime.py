from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import json
import os
import queue
import shlex
import subprocess
import threading
from typing import Any, Mapping

REA_PACKAGE_VERSION = "6.5.0"
MCP_PROTOCOL_VERSION = "2025-11-25"
_SUPPORTED_HANDSHAKE_PROTOCOLS = frozenset({"2025-11-25", "2025-06-18", "2025-03-26"})


class REAError(RuntimeError):
    """Base error for the Vishnu-owned REA MCP process."""


class REAUnavailableError(REAError):
    """Raised when the REA process cannot be started or is no longer alive."""


class REAProtocolError(REAError):
    """Raised when REA returns invalid or incompatible MCP data."""


@dataclass(frozen=True, slots=True)
class REAProcessConfig:
    command: tuple[str, ...]
    startup_timeout_seconds: float = 90.0
    request_timeout_seconds: float = 120.0
    max_message_bytes: int = 32 * 1024 * 1024

    @classmethod
    def from_environment(cls, env: Mapping[str, str] | None = None) -> "REAProcessConfig":
        source = os.environ if env is None else env
        configured = str(source.get("VISHNU_REA_COMMAND", "")).strip()
        command = tuple(shlex.split(configured)) if configured else (
            "npx",
            "-y",
            f"rea-agents@{REA_PACKAGE_VERSION}",
            "mcp",
        )
        if not command:
            raise ValueError("VISHNU_REA_COMMAND must contain an executable")
        return cls(
            command=command,
            startup_timeout_seconds=_positive_float(source.get("VISHNU_REA_STARTUP_TIMEOUT_SECONDS"), 90.0),
            request_timeout_seconds=_positive_float(source.get("VISHNU_REA_REQUEST_TIMEOUT_SECONDS"), 120.0),
            max_message_bytes=_positive_int(source.get("VISHNU_REA_MAX_MESSAGE_BYTES"), 32 * 1024 * 1024),
        )


def _positive_float(value: str | None, default: float) -> float:
    if value in (None, ""):
        return default
    parsed = float(value)
    if parsed <= 0:
        raise ValueError("REA timeout values must be positive")
    return parsed


def _positive_int(value: str | None, default: int) -> int:
    if value in (None, ""):
        return default
    parsed = int(value)
    if parsed <= 0:
        raise ValueError("REA message limits must be positive")
    return parsed


class REAMCPRuntime:
    """Own one long-lived local REA MCP process and preserve its native session state.

    REA itself remains authoritative for provider selection, active-target state,
    Evidence, result metadata, limitations and cleanup. Vishnu only owns the
    subprocess/MCP transport and applies its existing ToolRegistry governance at
    the call boundary.
    """

    def __init__(self, config: REAProcessConfig | None = None, *, env: Mapping[str, str] | None = None):
        self.config = config or REAProcessConfig.from_environment(env)
        self._environment = dict(os.environ if env is None else env)
        self._process: subprocess.Popen[bytes] | None = None
        self._pending: dict[int | str, queue.Queue[dict[str, Any]]] = {}
        self._pending_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._lifecycle_lock = threading.RLock()
        self._next_request_id = 1
        self._reader_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._stderr = deque(maxlen=100)
        self._notifications = deque(maxlen=200)
        self._server_info: dict[str, Any] = {}
        self._server_capabilities: dict[str, Any] = {}
        self._instructions: str | None = None
        self._protocol_version: str | None = None
        self._initialized = False
        self._closed = False
        self._terminal_error: Exception | None = None

    @classmethod
    def from_environment(cls, env: Mapping[str, str] | None = None) -> "REAMCPRuntime":
        return cls(REAProcessConfig.from_environment(env), env=env)

    @property
    def server_info(self) -> dict[str, Any]:
        return dict(self._server_info)

    @property
    def protocol_version(self) -> str | None:
        return self._protocol_version

    @property
    def instructions(self) -> str | None:
        return self._instructions

    def status(self) -> dict[str, Any]:
        process = self._process
        return {
            "available": bool(self._initialized and process is not None and process.poll() is None),
            "initialized": self._initialized,
            "package_version": REA_PACKAGE_VERSION,
            "protocol_version": self._protocol_version,
            "server_info": dict(self._server_info),
            "server_capabilities": dict(self._server_capabilities),
            "instructions": self._instructions,
            "command": list(self.config.command),
            "pid": process.pid if process is not None and process.poll() is None else None,
            "recent_stderr": list(self._stderr)[-10:],
            "recent_notifications": list(self._notifications)[-20:],
            "error": str(self._terminal_error) if self._terminal_error is not None else None,
        }

    def start(self) -> dict[str, Any]:
        with self._lifecycle_lock:
            if self._closed:
                raise REAUnavailableError("REA runtime has been closed")
            if self._initialized and self._process is not None and self._process.poll() is None:
                return self.status()
            self._spawn()
            try:
                result = self._request(
                    "initialize",
                    {
                        "protocolVersion": MCP_PROTOCOL_VERSION,
                        "capabilities": {},
                        "clientInfo": {"name": "vishnu", "version": "1"},
                    },
                    timeout=self.config.startup_timeout_seconds,
                )
                if not isinstance(result, dict):
                    raise REAProtocolError("REA initialize result must be an object")
                negotiated = str(result.get("protocolVersion") or "")
                if negotiated not in _SUPPORTED_HANDSHAKE_PROTOCOLS:
                    raise REAProtocolError(f"REA negotiated unsupported MCP protocol {negotiated!r}")
                server_info = result.get("serverInfo") or {}
                capabilities = result.get("capabilities") or {}
                if not isinstance(server_info, dict) or not isinstance(capabilities, dict):
                    raise REAProtocolError("REA initialize metadata is malformed")
                self._protocol_version = negotiated
                self._server_info = dict(server_info)
                self._server_capabilities = dict(capabilities)
                instructions = result.get("instructions")
                self._instructions = instructions if isinstance(instructions, str) else None
                self._notify("notifications/initialized", {})
                self._initialized = True
                return self.status()
            except Exception:
                self.close()
                self._closed = False
                raise

    def list_tools(self) -> list[dict[str, Any]]:
        self.start()
        tools: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            params = {} if cursor is None else {"cursor": cursor}
            result = self._request("tools/list", params)
            if not isinstance(result, dict) or not isinstance(result.get("tools"), list):
                raise REAProtocolError("REA tools/list result is malformed")
            for item in result["tools"]:
                if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                    raise REAProtocolError("REA advertised an invalid tool descriptor")
                tools.append(dict(item))
            next_cursor = result.get("nextCursor")
            if not isinstance(next_cursor, str) or not next_cursor:
                break
            cursor = next_cursor
        return tools

    def call_tool(self, name: str, arguments: Mapping[str, Any] | None = None) -> dict[str, Any]:
        if not isinstance(name, str) or not name:
            raise ValueError("REA tool name must be a non-empty string")
        self.start()
        result = self._request("tools/call", {"name": name, "arguments": dict(arguments or {})})
        if not isinstance(result, dict):
            raise REAProtocolError(f"REA tool {name} returned a non-object MCP result")
        return result

    def close(self) -> None:
        with self._lifecycle_lock:
            process = self._process
            self._initialized = False
            self._closed = True
            if process is None:
                return
            try:
                if process.stdin is not None:
                    process.stdin.close()
            except OSError:
                pass
            try:
                process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=3.0)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3.0)
            finally:
                self._process = None
                self._fail_pending(REAUnavailableError("REA MCP process closed"))

    def _spawn(self) -> None:
        if self._process is not None and self._process.poll() is None:
            return
        self._closed = False
        self._terminal_error = None
        try:
            self._process = subprocess.Popen(
                list(self.config.command),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=self._environment,
                bufsize=0,
            )
        except (FileNotFoundError, OSError) as exc:
            self._terminal_error = exc
            raise REAUnavailableError(f"Could not start REA with {self.config.command[0]!r}: {exc}") from exc
        self._reader_thread = threading.Thread(target=self._read_stdout, name="vishnu-rea-mcp", daemon=True)
        self._stderr_thread = threading.Thread(target=self._read_stderr, name="vishnu-rea-stderr", daemon=True)
        self._reader_thread.start()
        self._stderr_thread.start()

    def _request(self, method: str, params: Mapping[str, Any] | None = None, *, timeout: float | None = None) -> Any:
        process = self._process
        if process is None or process.poll() is not None:
            raise REAUnavailableError("REA MCP process is not running")
        with self._pending_lock:
            request_id = self._next_request_id
            self._next_request_id += 1
            response_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
            self._pending[request_id] = response_queue
        self._write({"jsonrpc": "2.0", "id": request_id, "method": method, "params": dict(params or {})})
        deadline = self.config.request_timeout_seconds if timeout is None else timeout
        try:
            message = response_queue.get(timeout=deadline)
        except queue.Empty as exc:
            with self._pending_lock:
                self._pending.pop(request_id, None)
            try:
                self._notify("notifications/cancelled", {"requestId": request_id, "reason": "Vishnu REA request deadline exceeded"})
            except REAError:
                pass
            raise REAUnavailableError(f"REA request {method} timed out after {deadline:g}s") from exc
        if "error" in message:
            error = message.get("error")
            raise REAProtocolError(f"REA MCP {method} failed: {json.dumps(error, ensure_ascii=False, sort_keys=True)}")
        if "result" not in message:
            raise REAProtocolError(f"REA MCP {method} response has no result")
        return message["result"]

    def _notify(self, method: str, params: Mapping[str, Any] | None = None) -> None:
        self._write({"jsonrpc": "2.0", "method": method, "params": dict(params or {})})

    def _write(self, message: Mapping[str, Any]) -> None:
        process = self._process
        if process is None or process.stdin is None or process.poll() is not None:
            raise REAUnavailableError("REA MCP process is not writable")
        payload = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
        if len(payload) > self.config.max_message_bytes:
            raise REAProtocolError("outbound REA MCP message exceeds configured byte limit")
        with self._write_lock:
            try:
                process.stdin.write(payload)
                process.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                self._terminal_error = exc
                raise REAUnavailableError("REA MCP stdin closed") from exc

    def _read_stdout(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return
        try:
            while True:
                line = process.stdout.readline(self.config.max_message_bytes + 1)
                if not line:
                    break
                if len(line) > self.config.max_message_bytes:
                    raise REAProtocolError("REA MCP message exceeds configured byte limit")
                try:
                    message = json.loads(line.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise REAProtocolError("REA wrote a non-JSON message to MCP stdout") from exc
                if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
                    raise REAProtocolError("REA wrote an invalid JSON-RPC message")
                self._route_message(message)
        except Exception as exc:
            self._terminal_error = exc
        finally:
            self._initialized = False
            self._fail_pending(self._terminal_error or REAUnavailableError("REA MCP stdout closed"))

    def _route_message(self, message: dict[str, Any]) -> None:
        response_id = message.get("id")
        if ("result" in message or "error" in message) and isinstance(response_id, (int, str)):
            with self._pending_lock:
                waiter = self._pending.pop(response_id, None)
            if waiter is not None:
                waiter.put(message)
            return
        method = message.get("method")
        if isinstance(method, str) and "id" in message:
            self._write(
                {
                    "jsonrpc": "2.0",
                    "id": response_id,
                    "error": {"code": -32601, "message": f"Vishnu REA client does not implement {method}"},
                }
            )
            return
        if isinstance(method, str):
            self._notifications.append(message)

    def _read_stderr(self) -> None:
        process = self._process
        if process is None or process.stderr is None:
            return
        while True:
            line = process.stderr.readline(16 * 1024)
            if not line:
                return
            self._stderr.append(line.decode("utf-8", errors="replace").rstrip())

    def _fail_pending(self, error: Exception) -> None:
        with self._pending_lock:
            pending = list(self._pending.values())
            self._pending.clear()
        message = {"jsonrpc": "2.0", "error": {"code": -32000, "message": str(error)}}
        for waiter in pending:
            try:
                waiter.put_nowait(message)
            except queue.Full:
                pass

    def __enter__(self) -> "REAMCPRuntime":
        self.start()
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        self.close()
