from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

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


def validate_generated_manifest_authority(manifest: dict[str, Any]) -> None:
    if manifest.get("runtime") != "pure_python_v1":
        raise GeneratedCapabilitySecurityError("unsupported generated capability runtime")
    if str(manifest.get("risk")) != "read":
        raise GeneratedCapabilitySecurityError("generated local runtime is limited to read-only capabilities")
    permissions = dict(manifest.get("permissions") or {})
    forbidden = (
        "network_hosts", "filesystem_read", "filesystem_write", "secret_names",
        "connector_ids", "side_effects",
    )
    if any(permissions.get(key) for key in forbidden):
        raise GeneratedCapabilitySecurityError("generated local runtime cannot receive external authority")
    if permissions.get("background_allowed") or permissions.get("ui_required"):
        raise GeneratedCapabilitySecurityError("background/UI generated capabilities are not enabled in this runtime")
    forge = dict(manifest.get("forge") or {})
    if not forge.get("qualified") or forge.get("review_decision") != "approved":
        raise GeneratedCapabilitySecurityError("generated capability is not independently qualified and approved")


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
        entrypoint = dict(self.manifest.get("entrypoint") or {})
        rel = Path(str(entrypoint.get("file") or ""))
        function = str(entrypoint.get("function") or "")
        if not function or rel.is_absolute() or ".." in rel.parts:
            raise ValueError("invalid generated capability entrypoint")
        self.source_path = (self.package_path / rel).resolve()
        if self.package_path not in self.source_path.parents or not self.source_path.is_file():
            raise GeneratedCapabilitySecurityError("generated capability entrypoint escapes package root")
        self.function = function
        self.timeout_seconds = max(1, min(int(timeout_seconds), 30))
        self.on_invocation = on_invocation
        self._source = self.source_path.read_text(encoding="utf-8")
        validate_pure_python_source(self._source)

    def invoke(self, parameters: dict[str, Any]) -> Any:
        if not isinstance(parameters, dict):
            raise ValueError("generated capability parameters must be an object")
        _validate_json_shape(parameters)
        serialized = json.dumps(parameters, separators=(",", ":"), ensure_ascii=False)
        if len(serialized.encode("utf-8")) > _MAX_INPUT_BYTES:
            raise ValueError("generated capability input exceeds size limit")
        started = time.perf_counter()
        ok = False
        error_code = None
        try:
            kwargs = {
                "input": serialized,
                "text": True,
                "capture_output": True,
                "cwd": str(self.package_path),
                "env": {"PYTHONIOENCODING": "utf-8"},
                "timeout": self.timeout_seconds,
                "check": False,
            }
            limiter = _posix_resource_limiter(self.timeout_seconds)
            if limiter is not None:
                kwargs["preexec_fn"] = limiter
            completed = subprocess.run(
                [sys.executable, "-I", "-S", "-c", _RUNNER, str(self.source_path), self.function],
                **kwargs,
            )
            if completed.returncode != 0:
                error_code = "generated_runtime_failed"
                raise RuntimeError("generated capability execution failed")
            if len(completed.stdout.encode("utf-8")) > _MAX_OUTPUT_BYTES:
                error_code = "generated_output_too_large"
                raise RuntimeError("generated capability output exceeds size limit")
            result = json.loads(completed.stdout or "null")
            _validate_json_shape(result)
            ok = True
            return result
        except subprocess.TimeoutExpired as exc:
            error_code = "generated_timeout"
            raise TimeoutError("generated capability execution timed out") from exc
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
    runtime = PurePythonGeneratedCapability(
        package_path,
        expected_digest=str(capability.get("manifest_digest") or ""),
        on_invocation=on_invocation,
    )
    manifest = runtime.manifest
    if str(manifest.get("id")) != str(capability.get("id")) or str(manifest.get("version")) != str(capability.get("version")):
        raise GeneratedCapabilitySecurityError("catalog identity does not match generated package")
    tool = Tool(
        name=str(capability["id"]),
        description=f"Generated capability: {capability.get('name') or capability['id']}",
        handler=runtime.invoke,
        risk=Risk.READ_ONLY,
        verifier=lambda _parameters, _result: VerificationResult(
            True,
            "qualified pure generated capability returned contract-valid output",
            {"manifest_digest": str(capability.get("manifest_digest") or "")},
        ),
        verification_required=True,
        capability=str(capability["id"]),
        input_schema=dict(capability.get("input_schema") or {}),
        output_schema=dict(capability.get("output_schema") or {}),
        verification_method="qualified_generated_runtime",
    )
    existing = getattr(tools, "_tools", {}).get(tool.name)
    if existing is None:
        tools.register(tool)
    elif (
        getattr(existing, "verification_method", None) == "qualified_generated_runtime"
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
        getattr(existing, "verification_method", None) != "qualified_generated_runtime"
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
