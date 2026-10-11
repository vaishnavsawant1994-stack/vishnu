from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Reuse the already-qualified build-job trust parser without turning this
# repository's packaging/ directory into a Python package (which would shadow
# the third-party `packaging` dependency).
_core_path = Path(__file__).with_name("product_platform_runner.py")
_spec = importlib.util.spec_from_file_location("_vishnu_product_platform_runner", _core_path)
if _spec is None or _spec.loader is None:  # pragma: no cover - defensive
    raise RuntimeError("Unable to load the Vishnu product build-job verifier")
_core = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_core)
_load_job = _core._load_job
RunnerError = _core.RunnerError


_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe(value: str, fallback: str = "product") -> str:
    value = _SAFE.sub("-", str(value or "").strip()).strip("-._")
    return value or fallback


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run(*cmd: str, cwd: Path | None = None, env: dict | None = None, capture: bool = False):
    return subprocess.run(
        list(cmd),
        cwd=str(cwd) if cwd else None,
        env=env,
        check=True,
        text=True,
        capture_output=capture,
    )


def _result(
    payload: dict,
    artifact: Path,
    *,
    artifact_kind: str,
    variant: str,
    signing_verified: bool = False,
    metadata: dict | None = None,
) -> dict:
    digest = _sha256_file(artifact)
    evidence = {
        "schema": "vishnu.platform-runner-evidence/v1",
        "product_id": str(payload["product_id"]),
        "build_id": str(payload["build_id"]),
        "version": str(payload["version"]),
        "target": str(payload["target"]),
        "mode": "development" if payload.get("development") else "production",
        "host_os": platform.system().lower(),
        "artifact_name": artifact.name,
        "artifact_kind": artifact_kind,
        "sha256": digest,
        "compiler_verified": True,
        "signing_verified": bool(signing_verified),
        "provisioning_verified": False,
        "notarization_verified": False,
        "metadata": {"variant": variant, "runner": "vishnu-product-desktop-container", **dict(metadata or {})},
    }
    return {
        "artifact": str(artifact),
        "sha256": digest,
        "size": artifact.stat().st_size,
        "platform_signing_verified": bool(signing_verified),
        "variant": variant,
        "evidence": evidence,
    }


def _runtime_script(manifest: dict) -> str:
    serialized = json.dumps(manifest, sort_keys=True, ensure_ascii=False)
    return f'''from __future__ import annotations
import html,json,threading,webbrowser
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
MANIFEST=json.loads({serialized!r})
PAGE="""<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{{name}}</title><style>body{{background:#07101a;color:#eff6fb;font-family:system-ui;margin:0}}main{{max-width:760px;margin:auto;padding:48px 24px}}p{{color:#a8bacb;line-height:1.55}}section{{border:1px solid #263d50;border-radius:18px;padding:20px;background:#0d1924}}</style><main><small>VISHNU PRODUCT</small><h1>{{name}}</h1><p>{{description}}</p><section><b>Desktop client runtime</b><p>Version {{version}}</p><p>Owner Vishnu memory, credentials and source code are not embedded in this application. Product execution uses separately approved runtime connectors.</p></section></main>"""
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  if self.path=='/manifest.json': raw=json.dumps(MANIFEST,separators=(',',':')).encode();kind='application/json'
  elif self.path=='/health': raw=json.dumps({{'ok':True,'product_id':MANIFEST.get('product_id'),'version':MANIFEST.get('version')}}).encode();kind='application/json'
  else: raw=PAGE.format(name=html.escape(str(MANIFEST.get('name') or 'Vishnu Product')),description=html.escape(str(MANIFEST.get('description') or '')),version=html.escape(str(MANIFEST.get('version') or ''))).encode();kind='text/html; charset=utf-8'
  self.send_response(200);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
 def log_message(self,*_): pass
if __name__=='__main__':
 server=ThreadingHTTPServer(('127.0.0.1',0),Handler);url=f'http://127.0.0.1:{{server.server_port}}/';threading.Timer(.35,lambda:webbrowser.open(url)).start();server.serve_forever()
'''


def _pyinstaller(source: Path, output: Path, *, name: str, windowed: bool) -> Path:
    dist = output / "dist"
    work = output / "work"
    spec = output / "spec"
    dist.mkdir(parents=True, exist_ok=True)
    args = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        "--onefile",
        "--name",
        name,
        "--distpath",
        str(dist),
        "--workpath",
        str(work),
        "--specpath",
        str(spec),
    ]
    if windowed:
        args.append("--noconsole")
    args.append(str(source))
    _run(*args)
    suffix = ".exe" if platform.system() == "Windows" else ""
    artifact = dist / f"{name}{suffix}"
    if not artifact.is_file():
        raise RunnerError("PyInstaller completed without the expected product executable")
    return artifact


def build_linux(job_path: Path, output_dir: Path, *, allow_unsigned_job: bool = False) -> dict:
    if platform.system() != "Linux":
        raise RunnerError("Linux product compilation must run on a Linux host")
    payload, manifest = _load_job(job_path, allow_unsigned=allow_unsigned_job)
    if payload["target"] != "linux":
        raise RunnerError("Linux runner received a non-Linux job")
    output_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="vishnu-product-linux-"))
    try:
        name = _safe(manifest.get("name") or "vishnu-product").lower()
        source = work / "runtime.py"
        source.write_text(_runtime_script(manifest), encoding="utf-8")
        executable = _pyinstaller(source, work, name=name, windowed=False)
        package_root = work / "deb" / f"{name}-{payload['version']}"
        (package_root / "DEBIAN").mkdir(parents=True)
        (package_root / "opt" / "vishnu-products" / name).mkdir(parents=True)
        (package_root / "usr" / "bin").mkdir(parents=True)
        installed = package_root / "opt" / "vishnu-products" / name / name
        shutil.copy2(executable, installed)
        installed.chmod(0o755)
        launcher = package_root / "usr" / "bin" / name
        launcher.write_text(f'#!/bin/sh\nexec /opt/vishnu-products/{name}/{name} "$@"\n', encoding="utf-8")
        launcher.chmod(0o755)
        control = (
            f"Package: {name}\n"
            f"Version: {payload['version']}\n"
            "Section: utils\nPriority: optional\nArchitecture: amd64\n"
            "Maintainer: Vishnu Products\n"
            f"Description: {str(manifest.get('name') or 'Vishnu client product')[:120]}\n"
        )
        (package_root / "DEBIAN" / "control").write_text(control, encoding="utf-8")
        final = output_dir / f"{name}-{payload['version']}-linux-amd64.deb"
        dpkg = shutil.which("dpkg-deb")
        if not dpkg:
            raise RunnerError("dpkg-deb is required to build the Linux client package")
        _run(dpkg, "--build", str(package_root), str(final))
        if not final.is_file():
            raise RunnerError("Linux package compiler did not produce a DEB artifact")
        return _result(payload, final, artifact_kind="deb", variant="amd64")
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _find_signtool() -> str | None:
    direct = shutil.which("signtool") or shutil.which("signtool.exe")
    if direct:
        return direct
    roots = [os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")]
    candidates: list[Path] = []
    for root in roots:
        if root:
            candidates.extend(Path(root).glob("Windows Kits/10/bin/*/x64/signtool.exe"))
    return str(sorted(candidates, reverse=True)[0]) if candidates else None


def _windows_sign(executable: Path, work: Path) -> bool:
    cert_path = os.environ.get("VISHNU_WINDOWS_SIGNING_CERT_PATH", "").strip()
    cert_b64 = os.environ.get("VISHNU_WINDOWS_SIGNING_CERT_B64", "").strip()
    password = os.environ.get("VISHNU_WINDOWS_SIGNING_PASSWORD", "").strip()
    if not password or not (cert_path or cert_b64):
        return False
    if cert_b64:
        certificate = work / "product-signing.pfx"
        try:
            certificate.write_bytes(base64.b64decode(cert_b64, validate=True))
        except Exception as exc:
            raise RunnerError("VISHNU_WINDOWS_SIGNING_CERT_B64 is not valid base64") from exc
    else:
        certificate = Path(cert_path)
    if not certificate.is_file():
        raise RunnerError("Configured Windows product signing certificate is unavailable")
    signtool = _find_signtool()
    if not signtool:
        raise RunnerError("Windows product signing is configured but signtool is unavailable")
    timestamp = os.environ.get("VISHNU_WINDOWS_TIMESTAMP_URL", "https://timestamp.digicert.com").strip()
    _run(signtool, "sign", "/fd", "SHA256", "/f", str(certificate), "/p", password, "/tr", timestamp, "/td", "SHA256", str(executable))
    _run(signtool, "verify", "/pa", "/all", str(executable))
    return True


def build_windows(job_path: Path, output_dir: Path, *, allow_unsigned_job: bool = False) -> dict:
    if platform.system() != "Windows":
        raise RunnerError("Windows product compilation must run on a Windows host")
    payload, manifest = _load_job(job_path, allow_unsigned=allow_unsigned_job)
    if payload["target"] != "windows":
        raise RunnerError("Windows runner received a non-Windows job")
    output_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="vishnu-product-windows-"))
    try:
        name = _safe(manifest.get("name") or "VishnuProduct")
        source = work / "runtime.py"
        source.write_text(_runtime_script(manifest), encoding="utf-8")
        executable = _pyinstaller(source, work, name=name, windowed=True)
        signed = _windows_sign(executable, work)
        final = output_dir / f"{name}-{payload['version']}-windows-x64.exe"
        shutil.copy2(executable, final)
        return _result(payload, final, artifact_kind="exe", variant="x64", signing_verified=signed)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _docker_context(root: Path, manifest: dict) -> None:
    serialized = json.dumps(manifest, sort_keys=True, ensure_ascii=False)
    runtime = f'''from __future__ import annotations
import json
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
MANIFEST=json.loads({serialized!r})
class Handler(BaseHTTPRequestHandler):
 def out(self,status,value):
  raw=json.dumps(value,separators=(',',':')).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
 def do_GET(self):
  if self.path=='/health': return self.out(200,{{'ok':True,'product_id':MANIFEST.get('product_id'),'version':MANIFEST.get('version')}})
  if self.path=='/product': return self.out(200,MANIFEST)
  return self.out(404,{{'error':'not_found'}})
 def do_POST(self): return self.out(501,{{'error':'runtime_connector_required'}})
 def log_message(self,*_): pass
ThreadingHTTPServer(('0.0.0.0',8080),Handler).serve_forever()
'''
    (root / "runtime.py").write_text(runtime, encoding="utf-8")
    (root / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    (root / "Dockerfile").write_text(
        'FROM python:3.12-slim\nWORKDIR /app\nCOPY runtime.py manifest.json /app/\nUSER 65532:65532\nEXPOSE 8080\nCMD ["python","/app/runtime.py"]\n',
        encoding="utf-8",
    )


def _cosign_attest(image_tar: Path, bundle_dir: Path) -> tuple[bool, dict]:
    key = os.environ.get("VISHNU_DOCKER_COSIGN_KEY", "").strip()
    if not key:
        return False, {}
    cosign = shutil.which("cosign")
    if not cosign:
        raise RunnerError("Docker attestation is configured but cosign is unavailable")
    signature = bundle_dir / "image.tar.sig"
    public_key = bundle_dir / "cosign.pub"
    env = dict(os.environ)
    _run(cosign, "sign-blob", "--yes", "--key", key, "--output-signature", str(signature), str(image_tar), env=env)
    pub = _run(cosign, "public-key", "--key", key, env=env, capture=True).stdout
    public_key.write_text(pub, encoding="utf-8")
    _run(cosign, "verify-blob", "--key", str(public_key), "--signature", str(signature), str(image_tar), env=env)
    return True, {"cosign_public_key_sha256": _sha256_file(public_key)}


def build_docker(job_path: Path, output_dir: Path, *, allow_unsigned_job: bool = False) -> dict:
    payload, manifest = _load_job(job_path, allow_unsigned=allow_unsigned_job)
    if payload["target"] != "docker":
        raise RunnerError("Docker runner received a non-Docker job")
    docker = shutil.which("docker")
    if not docker:
        raise RunnerError("Docker is required to build OCI product artifacts")
    output_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="vishnu-product-docker-"))
    try:
        context = work / "context"
        context.mkdir()
        _docker_context(context, manifest)
        tag = f"vishnu-product-{hashlib.sha256(str(payload['product_id']).encode()).hexdigest()[:12]}:{_safe(str(payload['version']), 'latest').lower()}"
        _run(docker, "build", "--pull=false", "-t", tag, str(context))
        inspect = _run(docker, "image", "inspect", "--format", "{{.Id}}", tag, capture=True).stdout.strip()
        image_tar = work / "image.tar"
        _run(docker, "save", "-o", str(image_tar), tag)
        bundle = work / "bundle"
        bundle.mkdir()
        shutil.copy2(image_tar, bundle / "image.tar")
        (bundle / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2), encoding="utf-8")
        (bundle / "image.sha256").write_text(f"{_sha256_file(image_tar)}  image.tar\n", encoding="utf-8")
        attested, attestation_meta = _cosign_attest(bundle / "image.tar", bundle)
        final = output_dir / f"{_safe(manifest.get('name') or 'product')}-{payload['version']}-oci.zip"
        with zipfile.ZipFile(final, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in sorted(bundle.iterdir()):
                archive.write(path, path.name)
        result = _result(
            payload,
            final,
            artifact_kind="oci-archive",
            variant="linux-container",
            signing_verified=False,
            metadata={"image_id": inspect, "attestation_verified": attested, **attestation_meta},
        )
        result["attestation_verified"] = attested
        return result
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile Vishnu desktop/container product build jobs")
    parser.add_argument("job", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-unsigned-job", action="store_true")
    args = parser.parse_args()
    payload, _manifest = _load_job(args.job, allow_unsigned=args.allow_unsigned_job)
    target = payload["target"]
    if target == "linux":
        result = build_linux(args.job, args.output, allow_unsigned_job=args.allow_unsigned_job)
    elif target == "windows":
        result = build_windows(args.job, args.output, allow_unsigned_job=args.allow_unsigned_job)
    elif target == "docker":
        result = build_docker(args.job, args.output, allow_unsigned_job=args.allow_unsigned_job)
    else:
        raise RunnerError(f"This runner does not implement target {target}")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
