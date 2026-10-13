from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath
from typing import Any, Callable
from urllib.parse import urlparse

from tools.registry import Risk, Tool, VerificationResult


_FORBIDDEN_CALLS = {
    "__import__", "open", "exec", "eval", "compile", "input", "breakpoint",
    "globals", "locals", "vars", "dir", "getattr", "setattr", "delattr", "help",
}
_FORBIDDEN_NAMES = {
    "os", "sys", "subprocess", "socket", "pathlib", "shutil", "ctypes",
    "importlib", "builtins", "marshal", "pickle", "multiprocessing", "threading",
}
_FORBIDDEN_NODES = (
    ast.Import, ast.ImportFrom, ast.ClassDef, ast.Global, ast.Nonlocal,
)
_MAX_INPUT_BYTES = 256_000
_MAX_OUTPUT_BYTES = 1_000_000
_MAX_JSON_DEPTH = 32
_MAX_JSON_NODES = 20_000
_MAX_DELEGATED_CALLS = 16
_GENERATED_VERIFICATION_METHODS = {
    "qualified_generated_runtime",
    "qualified_generated_toolchain_runtime",
}

_RUNNER = r'''
import json, sys

SAFE_BUILTINS = {
    "abs": abs, "all": all, "any": any, "bool": bool, "dict": dict,
    "enumerate": enumerate, "float": float, "int": int, "isinstance": isinstance,
    "len": len, "list": list, "max": max, "min": min, "range": range,
    "round": round, "set": set, "sorted": sorted, "str": str, "sum": sum,
    "tuple": tuple, "zip": zip, "Exception": Exception, "ValueError": ValueError,
    "TypeError": TypeError, "KeyError": KeyError,
}
source_path, function_name = sys.argv[1], sys.argv[2]
with open(source_path, "r", encoding="utf-8") as handle:
    source = handle.read()
scope = {"__builtins__": SAFE_BUILTINS}
exec(compile(source, source_path, "exec"), scope, scope)
fn = scope.get(function_name)
if not callable(fn):
    raise RuntimeError("generated capability entrypoint is not callable")
payload = json.loads(sys.stdin.read() or "{}")
result = fn(payload)
sys.stdout.write(json.dumps(result, separators=(",", ":"), ensure_ascii=False))
'''


class GeneratedCapabilitySecurityError(PermissionError):
    pass


def _manifest_bytes(path: Path) -> bytes:
    raw = path.read_bytes()
    if len(raw) > 256_000:
        raise ValueError("generated capability manifest exceeds size limit")
    return raw


def _validate_json_shape(value: Any) -> None:
    nodes = 0
    stack: list[tuple[Any, int]] = [(value, 0)]
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > _MAX_JSON_NODES:
            raise ValueError("generated capability JSON exceeds structural limit")
        if depth > _MAX_JSON_DEPTH:
            raise ValueError("generated capability JSON exceeds nesting limit")
        if isinstance(current, dict):
            if any(not isinstance(key, str) for key in current):
                raise ValueError("generated capability JSON object keys must be strings")
            stack.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, (list, tuple)):
            stack.extend((item, depth + 1) for item in current)
        elif current is not None and not isinstance(current, (str, int, float, bool)):
            raise ValueError("generated capability values must be JSON-compatible")


def _json_bytes(value: Any) -> bytes:
    _validate_json_shape(value)
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _bounded_string_tuple(value: Any, *, limit: int = 64, item_limit: int = 1000) -> tuple[str, ...]:
    if value is None:
        raw = ()
    elif isinstance(value, str):
        raw = (value,)
    elif isinstance(value, (list, tuple)):
        raw = value
    else:
        raise GeneratedCapabilitySecurityError("generated capability permission list is invalid")
    out: list[str] = []
    for item in raw:
        clean = str(item or "").strip()
        if not clean or len(clean) > item_limit:
            raise GeneratedCapabilitySecurityError("generated capability contains an invalid permission value")
        if clean not in out:
            out.append(clean)
        if len(out) > limit:
            raise GeneratedCapabilitySecurityError("generated capability permission list exceeds limit")
    return tuple(out)


def _posix_resource_limiter(timeout_seconds: int):
    if os.name != "posix":
        return None
    try:
        import resource
    except Exception:
        return None

    def apply_limits():
        cpu = max(1, min(int(timeout_seconds) + 1, 31))
        memory = 256 * 1024 * 1024
        file_size = 2 * 1024 * 1024
        try:
            resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
        except Exception:
            pass
        try:
            resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
        except Exception:
            pass
        try:
            resource.setrlimit(resource.RLIMIT_FSIZE, (file_size, file_size))
        except Exception:
            pass
        try:
            resource.setrlimit(resource.RLIMIT_NOFILE, (16, 16))
        except Exception:
            pass
        try:
            resource.setrlimit(resource.RLIMIT_NPROC, (1, 1))
        except Exception:
            pass

    return apply_limits


def load_generated_manifest(package_path: str | Path, *, expected_digest: str | None = None) -> dict[str, Any]:
    root = Path(package_path).resolve()
    manifest_path = root / "manifest.json"
    raw = _manifest_bytes(manifest_path)
    digest = hashlib.sha256(raw).hexdigest()
    if expected_digest is not None and digest != str(expected_digest):
        raise GeneratedCapabilitySecurityError("generated capability manifest digest mismatch")
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict) or payload.get("type") != "generated_capability":
        raise ValueError("invalid generated capability manifest")
    _validate_json_shape(payload)
    return payload


def _allowed_tools(permissions: dict[str, Any]) -> tuple[str, ...]:
    return _bounded_string_tuple(permissions.get("allowed_tools"), limit=32, item_limit=200)


def validate_generated_manifest_authority(manifest: dict[str, Any]) -> None:
    runtime = str(manifest.get("runtime") or "")
    if runtime not in {"pure_python_v1", "governed_toolchain_v1"}:
        raise GeneratedCapabilitySecurityError("unsupported generated capability runtime")
    if str(manifest.get("risk")) != "read":
        raise GeneratedCapabilitySecurityError("generated local runtime is limited to read-only capabilities")
    permissions = dict(manifest.get("permissions") or {})
    if permissions.get("background_allowed") or permissions.get("ui_required"):
        raise GeneratedCapabilitySecurityError("background/UI generated capabilities are not enabled in this runtime")
    forge = dict(manifest.get("forge") or {})
    if not forge.get("qualified") or forge.get("review_decision") != "approved":
        raise GeneratedCapabilitySecurityError("generated capability is not independently qualified and approved")

    if runtime == "pure_python_v1":
        forbidden = (
            "network_hosts", "filesystem_read", "filesystem_write", "secret_names",
            "connector_ids", "side_effects", "allowed_tools",
        )
        if any(permissions.get(key) for key in forbidden):
            raise GeneratedCapabilitySecurityError("pure generated runtime cannot receive external authority")
        return

    allowed = _allowed_tools(permissions)
    if not allowed:
        raise GeneratedCapabilitySecurityError("governed generated toolchain requires an explicit tool allowlist")
    if permissions.get("filesystem_write") or permissions.get("secret_names") or permissions.get("side_effects"):
        raise GeneratedCapabilitySecurityError("governed generated toolchain cannot receive raw secrets, write authority, or side effects")
    _bounded_string_tuple(permissions.get("network_hosts"), limit=64, item_limit=500)
    _bounded_string_tuple(permissions.get("filesystem_read"), limit=64, item_limit=1000)
    _bounded_string_tuple(permissions.get("connector_ids"), limit=64, item_limit=200)


def validate_pure_python_source(source: str) -> None:
    if len(source.encode("utf-8")) > 500_000:
        raise GeneratedCapabilitySecurityError("generated capability source exceeds size limit")
    tree = ast.parse(source, mode="exec")
    for node in ast.walk(tree):
        if isinstance(node, _FORBIDDEN_NODES):
            raise GeneratedCapabilitySecurityError(f"forbidden generated-code construct: {type(node).__name__}")
        if isinstance(node, ast.Attribute) and str(node.attr).startswith("__"):
            raise GeneratedCapabilitySecurityError("dunder attribute access is forbidden")
        if isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES:
            raise GeneratedCapabilitySecurityError(f"forbidden generated-code name: {node.id}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FORBIDDEN_CALLS:
            raise GeneratedCapabilitySecurityError(f"forbidden generated-code call: {node.func.id}")


def _entrypoint(package_path: Path, descriptor: dict[str, Any], *, label: str) -> tuple[Path, str, str]:
    rel = Path(str(descriptor.get("file") or ""))
    function = str(descriptor.get("function") or "")
    if not function or rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"invalid generated capability {label}")
    source_path = (package_path / rel).resolve()
    if package_path not in source_path.parents or not source_path.is_file():
        raise GeneratedCapabilitySecurityError(f"generated capability {label} escapes package root")
    source = source_path.read_text(encoding="utf-8")
    validate_pure_python_source(source)
    return source_path, function, source


def _invoke_isolated(source_path: Path, function: str, parameters: Any, *, package_path: Path, timeout_seconds: int) -> Any:
    serialized = _json_bytes(parameters).decode("utf-8")
    if len(serialized.encode("utf-8")) > _MAX_INPUT_BYTES:
        raise ValueError("generated capability input exceeds size limit")
    kwargs: dict[str, Any] = {
        "input": serialized,
        "text": True,
        "capture_output": True,
        "cwd": str(package_path),
        "env": {"PYTHONIOENCODING": "utf-8"},
        "timeout": timeout_seconds,
        "check": False,
    }
    limiter = _posix_resource_limiter(timeout_seconds)
    if limiter is not None:
        kwargs["preexec_fn"] = limiter
    completed = subprocess.run(
        [sys.executable, "-I", "-S", "-c", _RUNNER, str(source_path), function],
        **kwargs,
    )
    if completed.returncode != 0:
        raise RuntimeError("generated capability execution failed")
    if len(completed.stdout.encode("utf-8")) > _MAX_OUTPUT_BYTES:
        raise RuntimeError("generated capability output exceeds size limit")
    result = json.loads(completed.stdout or "null")
    _validate_json_shape(result)
    return result


class PurePythonGeneratedCapability:
    def __init__(
        self,
        package_path: str | Path,
        *,
        expected_digest: str,
        timeout_seconds: int = 10,
        on_invocation: Callable[..., None] | None = None,
    ) -> None:
        self.package_path = Path(package_path).resolve()
        self.manifest = load_generated_manifest(self.package_path, expected_digest=expected_digest)
        validate_generated_manifest_authority(self.manifest)
        if self.manifest.get("runtime") != "pure_python_v1":
            raise GeneratedCapabilitySecurityError("manifest is not a pure generated capability")
        self.source_path, self.function, self._source = _entrypoint(
            self.package_path, dict(self.manifest.get("entrypoint") or {}), label="entrypoint"
        )
        self.timeout_seconds = max(1, min(int(timeout_seconds), 30))
        self.on_invocation = on_invocation

    def invoke(self, parameters: dict[str, Any]) -> Any:
        if not isinstance(parameters, dict):
            raise ValueError("generated capability parameters must be an object")
        started = time.perf_counter()
        ok = False
        error_code = None
        try:
            result = _invoke_isolated(
                self.source_path,
                self.function,
                parameters,
                package_path=self.package_path,
                timeout_seconds=self.timeout_seconds,
            )
            ok = True
            return result
        except subprocess.TimeoutExpired as exc:
            error_code = "generated_timeout"
            raise TimeoutError("generated capability execution timed out") from exc
        except Exception:
            error_code = "generated_runtime_failed"
            raise
        finally:
            if self.on_invocation is not None:
                duration_ms = (time.perf_counter() - started) * 1000.0
                try:
                    self.on_invocation(ok=ok, duration_ms=duration_ms, error_code=error_code)
                except Exception:
                    pass


class GovernedToolchainGeneratedCapability:
    """Generated planner whose only external access is brokered through ToolRegistry.

    The generated Python process can produce a JSON call plan and optionally
    reduce verified results. It never receives ToolRegistry, credentials, sockets,
    filesystem handles, or process environment. The host executes each call only
    after existing owner policy, risk, destination, input/output and verification
    checks succeed. Side-effecting or generated tools are never delegated.
    """

    def __init__(
        self,
        package_path: str | Path,
        *,
        expected_digest: str,
        tools,
        capability_id: str,
        timeout_seconds: int = 10,
        on_invocation: Callable[..., None] | None = None,
    ) -> None:
        self.package_path = Path(package_path).resolve()
        self.manifest = load_generated_manifest(self.package_path, expected_digest=expected_digest)
        validate_generated_manifest_authority(self.manifest)
        if self.manifest.get("runtime") != "governed_toolchain_v1":
            raise GeneratedCapabilitySecurityError("manifest is not a governed generated toolchain")
        self.source_path, self.function, self._source = _entrypoint(
            self.package_path, dict(self.manifest.get("entrypoint") or {}), label="entrypoint"
        )
        reducer = self.manifest.get("reducer")
        self.reducer_path = None
        self.reducer_function = None
        if reducer is not None:
            self.reducer_path, self.reducer_function, _ = _entrypoint(
                self.package_path, dict(reducer or {}), label="reducer"
            )
        permissions = dict(self.manifest.get("permissions") or {})
        self.allowed_tools = frozenset(_allowed_tools(permissions))
        self.network_hosts = tuple(value.lower().strip(".") for value in _bounded_string_tuple(permissions.get("network_hosts"), limit=64, item_limit=500))
        self.filesystem_read = _bounded_string_tuple(permissions.get("filesystem_read"), limit=64, item_limit=1000)
        self.connector_ids = frozenset(_bounded_string_tuple(permissions.get("connector_ids"), limit=64, item_limit=200))
        self.tools = tools
        self.capability_id = str(capability_id)
        self.timeout_seconds = max(1, min(int(timeout_seconds), 30))
        self.on_invocation = on_invocation

    @staticmethod
    def _path_within(value: str, allowed_roots: tuple[str, ...]) -> bool:
        raw = str(value or "").strip().replace("\\", "/")
        if not raw or "://" in raw:
            return False
        candidate = PurePosixPath(raw)
        if ".." in candidate.parts:
            return False
        candidate_text = candidate.as_posix().lstrip("./")
        for root_raw in allowed_roots:
            root = PurePosixPath(str(root_raw).replace("\\", "/")).as_posix().lstrip("./").rstrip("/")
            if root and (candidate_text == root or candidate_text.startswith(root + "/")):
                return True
        return False

    def _validate_declared_scope(self, tool, parameters: dict[str, Any]) -> None:
        connector_id = str(getattr(tool, "connector_id", None) or "").strip()
        if connector_id and connector_id not in self.connector_ids:
            raise GeneratedCapabilitySecurityError("delegated connector is outside the Forge specification")

        for key in ("file_path", "path"):
            value = parameters.get(key)
            if value in (None, ""):
                continue
            if not self.filesystem_read or not self._path_within(str(value), self.filesystem_read):
                raise GeneratedCapabilitySecurityError("delegated file path is outside the Forge read scope")

        network_value = parameters.get("url") or parameters.get("domain")
        if network_value not in (None, ""):
            raw = str(network_value).strip()
            parsed = urlparse(raw if "://" in raw else f"https://{raw}")
            host = (parsed.hostname or "").lower().strip(".")
            if not host or not self.network_hosts or not any(host == allowed or host.endswith("." + allowed) for allowed in self.network_hosts):
                raise GeneratedCapabilitySecurityError("delegated network destination is outside the Forge host scope")

    def _delegated_tool(self, name: str, parameters: dict[str, Any]):
        if name not in self.allowed_tools:
            raise GeneratedCapabilitySecurityError("generated capability requested a tool outside its immutable allowlist")
        if name == self.capability_id:
            raise GeneratedCapabilitySecurityError("generated capability cannot recursively invoke itself")
        try:
            tool = self.tools.get(name)
        except (KeyError, TypeError) as exc:
            raise GeneratedCapabilitySecurityError("allowlisted delegated tool is unavailable") from exc
        if getattr(tool, "verification_method", None) in _GENERATED_VERIFICATION_METHODS:
            raise GeneratedCapabilitySecurityError("generated capabilities cannot delegate to generated capabilities")
        if Risk(int(getattr(tool, "risk", Risk.CRITICAL))) is not Risk.READ_ONLY:
            raise GeneratedCapabilitySecurityError("generated toolchain can delegate only to read-only tools")
        minimum = getattr(tool, "minimum_risk", None)
        if minimum is not None and Risk(int(minimum)) is not Risk.READ_ONLY:
            raise GeneratedCapabilitySecurityError("delegated tool has a higher minimum risk")
        self._validate_declared_scope(tool, parameters)
        effective = self.tools.effective_risk(tool, parameters=parameters, data_classification="internal") if hasattr(self.tools, "effective_risk") else Risk.READ_ONLY
        if Risk(int(effective)) is not Risk.READ_ONLY:
            raise GeneratedCapabilitySecurityError("delegated tool effective risk is not read-only")
        decision = self.tools.authorize(tool, confirmed=False, parameters=parameters, data_classification="internal")
        if not getattr(decision, "allowed", False) or getattr(decision, "requires_confirmation", False):
            raise PermissionError(getattr(decision, "reason", "delegated tool requires owner approval"))
        return tool

    def invoke(self, parameters: dict[str, Any]) -> Any:
        if not isinstance(parameters, dict):
            raise ValueError("generated capability parameters must be an object")
        started = time.perf_counter()
        ok = False
        error_code = None
        try:
            plan = _invoke_isolated(
                self.source_path,
                self.function,
                parameters,
                package_path=self.package_path,
                timeout_seconds=self.timeout_seconds,
            )
            if not isinstance(plan, dict) or not isinstance(plan.get("calls"), list):
                raise ValueError("governed generated toolchain must return an object with a calls array")
            calls = plan["calls"]
            if len(calls) > _MAX_DELEGATED_CALLS:
                raise GeneratedCapabilitySecurityError("generated capability requested too many delegated calls")
            results: list[dict[str, Any]] = []
            aggregate_bytes = 0
            for index, call in enumerate(calls):
                if not isinstance(call, dict):
                    raise ValueError("delegated call must be an object")
                name = str(call.get("tool") or "").strip()
                call_parameters = call.get("parameters", {})
                if not name or not isinstance(call_parameters, dict):
                    raise ValueError("delegated call requires tool and object parameters")
                tool = self._delegated_tool(name, call_parameters)
                result = self.tools.dispatch(tool, call_parameters)
                verification = self.tools.verify_result(tool, call_parameters, result)
                if not getattr(verification, "verified", False):
                    raise RuntimeError("delegated read-only tool result was not verified")
                encoded = _json_bytes(result)
                aggregate_bytes += len(encoded)
                if aggregate_bytes > _MAX_OUTPUT_BYTES:
                    raise RuntimeError("delegated results exceed generated capability size limit")
                results.append({"index": index, "tool": name, "result": result})
            reduction_input = {"input": parameters, "results": results}
            if self.reducer_path is not None and self.reducer_function is not None:
                output = _invoke_isolated(
                    self.reducer_path,
                    self.reducer_function,
                    reduction_input,
                    package_path=self.package_path,
                    timeout_seconds=self.timeout_seconds,
                )
            else:
                output = {"results": results}
            ok = True
            return output
        except subprocess.TimeoutExpired as exc:
            error_code = "generated_timeout"
            raise TimeoutError("generated capability execution timed out") from exc
        except PermissionError:
            error_code = "generated_policy_denied"
            raise
        except Exception:
            error_code = "generated_runtime_failed"
            raise
        finally:
            if self.on_invocation is not None:
                duration_ms = (time.perf_counter() - started) * 1000.0
                try:
                    self.on_invocation(ok=ok, duration_ms=duration_ms, error_code=error_code)
                except Exception:
                    pass


def resolve_generated_package(data_root: str | Path, package_ref: str) -> Path:
    root = Path(data_root).resolve()
    candidate = (root / str(package_ref)).resolve()
    if candidate == root or root not in candidate.parents:
        raise GeneratedCapabilitySecurityError("generated capability package escapes data root")
    return candidate


def attach_approved_generated_capability(
    capability: dict[str, Any],
    *,
    tools,
    data_root: str | Path,
    on_invocation: Callable[..., None] | None = None,
):
    if capability.get("type") != "generated_capability" or capability.get("state") != "active":
        raise ValueError("generated capability is not active")
    package_path = resolve_generated_package(data_root, str(capability.get("package_ref") or ""))
    manifest = load_generated_manifest(package_path, expected_digest=str(capability.get("manifest_digest") or ""))
    validate_generated_manifest_authority(manifest)
    runtime_name = str(manifest.get("runtime") or "")
    if runtime_name == "pure_python_v1":
        runtime = PurePythonGeneratedCapability(
            package_path,
            expected_digest=str(capability.get("manifest_digest") or ""),
            on_invocation=on_invocation,
        )
        verification_method = "qualified_generated_runtime"
    elif runtime_name == "governed_toolchain_v1":
        runtime = GovernedToolchainGeneratedCapability(
            package_path,
            expected_digest=str(capability.get("manifest_digest") or ""),
            tools=tools,
            capability_id=str(capability["id"]),
            on_invocation=on_invocation,
        )
        verification_method = "qualified_generated_toolchain_runtime"
    else:  # pragma: no cover - already rejected above
        raise GeneratedCapabilitySecurityError("unsupported generated capability runtime")
    if str(manifest.get("id")) != str(capability.get("id")) or str(manifest.get("version")) != str(capability.get("version")):
        raise GeneratedCapabilitySecurityError("catalog identity does not match generated package")
    tool = Tool(
        name=str(capability["id"]),
        description=f"Generated capability: {capability.get('name') or capability['id']}",
        handler=runtime.invoke,
        risk=Risk.READ_ONLY,
        verifier=lambda _parameters, _result: VerificationResult(
            True,
            "qualified generated capability returned contract-valid output",
            {"manifest_digest": str(capability.get("manifest_digest") or ""), "runtime": runtime_name},
        ),
        verification_required=True,
        capability=str(capability["id"]),
        input_schema=dict(capability.get("input_schema") or {}),
        output_schema=dict(capability.get("output_schema") or {}),
        verification_method=verification_method,
    )
    existing = getattr(tools, "_tools", {}).get(tool.name)
    if existing is None:
        tools.register(tool)
    elif (
        getattr(existing, "verification_method", None) in _GENERATED_VERIFICATION_METHODS
        and getattr(existing, "capability", None) == tool.capability
    ):
        tools._tools[tool.name] = tool
    else:
        raise ValueError(f"tool name collision for generated capability {tool.name}")
    return tool


def detach_generated_capability(tools, capability_id: str) -> bool:
    name = str(capability_id)
    existing = getattr(tools, "_tools", {}).get(name)
    if existing is None:
        return False
    if (
        getattr(existing, "verification_method", None) not in _GENERATED_VERIFICATION_METHODS
        or getattr(existing, "capability", None) != name
    ):
        raise PermissionError("refusing to detach a non-generated tool")
    del tools._tools[name]
    return True


def rehydrate_generated_capabilities(
    catalog,
    *,
    tools,
    data_root: str | Path,
    invocation_observer: Callable[[dict[str, Any], dict[str, Any]], Callable[..., None] | None] | None = None,
) -> list[str]:
    attached: list[str] = []
    for capability in catalog.all():
        if capability.get("type") != "generated_capability" or capability.get("state") != "active":
            continue
        observer = invocation_observer(capability, {}) if invocation_observer is not None else None
        try:
            attach_approved_generated_capability(
                capability,
                tools=tools,
                data_root=data_root,
                on_invocation=observer,
            )
            attached.append(str(capability["id"]))
        except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError, GeneratedCapabilitySecurityError):
            continue
    return attached
