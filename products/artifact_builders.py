from __future__ import annotations

import hashlib
import html
import io
import json
import re
import zipfile
from pathlib import Path
from urllib.parse import urlparse

from .build_lifecycle import ProductBuildLifecycle
from .package_export import distribution_safe_manifest
from .runtime import ProductRuntimeSpec
from .versioning import frozen_version


LOCAL_BUILD_TARGETS = ("web", "pwa", "api", "worker")
_ARTIFACT_SCHEME = "product-artifact"
_SAFE_STEM = re.compile(r"[^a-zA-Z0-9._-]+")


class ArtifactBuilderError(ValueError):
    pass


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _safe_stem(value: str, fallback: str) -> str:
    clean = _SAFE_STEM.sub("-", str(value or "").strip()).strip("-._")
    return clean or fallback


def _zip(files: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, files[name])
    return output.getvalue()


def _web_index(manifest: dict) -> bytes:
    name = html.escape(str(manifest.get("name") or "Vishnu Product"))
    description = html.escape(str(manifest.get("description") or ""))
    return f"""<!doctype html>
<html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><meta name=\"theme-color\" content=\"#09111b\"><title>{name}</title><link rel=\"stylesheet\" href=\"./runtime.css\"></head>
<body><main><header><span class=\"mark\">V</span><div><small>VISHNU PRODUCT</small><h1>{name}</h1><p>{description}</p></div></header><section id=\"status\" class=\"card\">Loading product runtime…</section><section class=\"card\"><h2>Components</h2><div id=\"components\"></div></section><footer>This client artifact contains only its product contract. Owner memory, credentials and the Vishnu source tree are not bundled.</footer></main><script src=\"./runtime.js\"></script></body></html>""".encode("utf-8")


def _web_runtime(target: str) -> bytes:
    service_worker = "if('serviceWorker' in navigator){navigator.serviceWorker.register('./service-worker.js').catch(()=>{});}" if target == "pwa" else ""
    return f"""(()=>{{'use strict';const esc=v=>String(v??'').replace(/[&<>\"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}}[c]));fetch('./manifest.json',{{cache:'no-store'}}).then(r=>{{if(!r.ok)throw new Error('manifest unavailable');return r.json()}}).then(m=>{{document.querySelector('#status').innerHTML=`<b>${{esc(m.name)}}</b><p>Version ${{esc(m.version)}} · AI ${{esc(m.ai_policy?.mode||'disabled')}} · target {target}</p>`;const rows=(m.components||[]).map(c=>`<article><b>${{esc(c.name)}}</b><span>${{esc(c.component_type)}}</span></article>`).join('');document.querySelector('#components').innerHTML=rows||'<p>No product components are declared.</p>';}}).catch(e=>{{document.querySelector('#status').textContent=`Runtime error: ${{e.message}}`;}});{service_worker}}})();""".encode("utf-8")


def _web_css() -> bytes:
    return b"""*{box-sizing:border-box}body{margin:0;background:#07101a;color:#eef6ff;font-family:Inter,system-ui,sans-serif}main{max-width:900px;margin:auto;padding:48px 22px}header{display:flex;gap:18px;align-items:flex-start;margin-bottom:30px}.mark{display:grid;place-items:center;width:46px;height:46px;border:1px solid #35506d;border-radius:15px;background:#101e2d;font-weight:800}small{color:#7f9bb7;letter-spacing:.15em}h1{margin:.2rem 0;font-size:clamp(2rem,6vw,4rem)}p{color:#a9bbcc;line-height:1.55}.card{border:1px solid #22394e;border-radius:18px;background:#0b1622;padding:20px;margin:16px 0}.card article{display:flex;justify-content:space-between;gap:16px;padding:12px 0;border-bottom:1px solid #1b2c3d}.card article:last-child{border-bottom:0}.card span{color:#8ba4ba}footer{margin-top:34px;color:#668096;font-size:.85rem}"""


def _server_runtime(target: str) -> bytes:
    # Standard-library-only host: the artifact can boot anywhere Python 3 is
    # available. Product-specific agent/tool execution is deliberately delegated
    # to a separately configured runtime connector; this bundle never imports
    # the owner's Vishnu installation.
    return f'''from __future__ import annotations
import argparse,json
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path

ROOT=Path(__file__).resolve().parent
MANIFEST=json.loads((ROOT/'manifest.json').read_text(encoding='utf-8'))
TARGET={target!r}

def summary():
    return {{'ok':True,'schema':'vishnu.client-runtime/v1','product_id':MANIFEST.get('product_id'),'name':MANIFEST.get('name'),'version':MANIFEST.get('version'),'target':TARGET,'ai_mode':(MANIFEST.get('ai_policy') or {{}}).get('mode','disabled'),'component_count':len(MANIFEST.get('components') or []),'component_execution':'runtime-connector-required'}}

class Handler(BaseHTTPRequestHandler):
    def _json(self,status,payload):
        raw=json.dumps(payload,separators=(',',':')).encode('utf-8');self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        if self.path=='/health':return self._json(200,summary())
        if self.path=='/product':return self._json(200,MANIFEST)
        return self._json(404,{{'error':'not_found'}})
    def do_POST(self):
        if self.path!='/invoke':return self._json(404,{{'error':'not_found'}})
        return self._json(501,{{'error':'runtime_connector_required','message':'This artifact is a verified product runtime contract. Connect an approved component executor/model runtime before invoking product work.'}})
    def log_message(self,*_):pass

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--port',type=int,default=8080);args=parser.parse_args()
    if args.check:print(json.dumps(summary(),sort_keys=True))
    else:ThreadingHTTPServer((args.host,args.port),Handler).serve_forever()
'''.encode("utf-8")


class ProductArtifactBuilder:
    """Generate and verify bounded client artifacts from immutable product versions.

    These adapters build actual downloadable Web/PWA/API/Worker runtime bundles.
    They do not pretend to compile native mobile/desktop binaries and they never
    copy the owner Vishnu tree into a client artifact.
    """

    def __init__(self, store, lifecycle: ProductBuildLifecycle, artifact_root: Path):
        self.store = store
        self.lifecycle = lifecycle
        self.artifact_root = Path(artifact_root)
        self.artifact_root.mkdir(parents=True, exist_ok=True)

    def available_targets(self) -> tuple[str, ...]:
        return LOCAL_BUILD_TARGETS

    def _raw_build(self, product_id: str, build_id: str) -> dict | None:
        with self.store.con() as con:
            row = con.execute(
                "SELECT * FROM product_builds WHERE id=? AND product_id=? LIMIT 1",
                (build_id, product_id),
            ).fetchone()
        if not row:
            return None
        value = dict(row)
        try:
            value["metadata"] = json.loads(value.pop("metadata_json", "{}") or "{}")
        except (TypeError, ValueError):
            value["metadata"] = {}
        return value

    def _spec_for(self, build: dict) -> ProductRuntimeSpec:
        snapshot = frozen_version(self.store, build["product_id"], build["version"])
        if snapshot is None:
            raise ArtifactBuilderError(
                f"Version {build['version']} must be frozen before a verified artifact can be built"
            )
        spec = ProductRuntimeSpec.load(snapshot["manifest"])
        if build["target"] not in spec.targets:
            raise ArtifactBuilderError(f"Target {build['target']} is not enabled in frozen version {build['version']}")
        return spec

    def _bundle(self, spec: ProductRuntimeSpec, target: str) -> bytes:
        manifest = distribution_safe_manifest(spec.manifest)
        files: dict[str, bytes] = {
            "manifest.json": _canonical(manifest),
            "runtime-capabilities.json": _canonical(
                {
                    "schema": "vishnu.client-runtime-capabilities/v1",
                    "target": target,
                    "owner_source_bundled": False,
                    "owner_data_bundled": False,
                    "credentials_bundled": False,
                    "component_execution": "runtime-connector-required" if target in {"api", "worker"} else "presentation-shell",
                }
            ),
            "README.txt": (
                "Vishnu client product runtime artifact\n"
                "\n"
                "This bundle was generated from an immutable product manifest.\n"
                "It intentionally excludes owner memory, owner credentials and the full Vishnu source tree.\n"
                "AI credentials, when required, must be provisioned at runtime.\n"
            ).encode("utf-8"),
        }
        if target in {"web", "pwa"}:
            files.update(
                {
                    "index.html": _web_index(manifest),
                    "runtime.js": _web_runtime(target),
                    "runtime.css": _web_css(),
                }
            )
            if target == "pwa":
                files["app.webmanifest"] = _canonical(
                    {
                        "name": str(manifest.get("name") or "Vishnu Product"),
                        "short_name": str(manifest.get("name") or "Product")[:32],
                        "start_url": "./",
                        "display": "standalone",
                        "background_color": "#07101a",
                        "theme_color": "#09111b",
                    }
                )
                files["service-worker.js"] = b"const C='vishnu-product-v1';self.addEventListener('install',e=>e.waitUntil(caches.open(C).then(c=>c.addAll(['./','./index.html','./runtime.js','./runtime.css','./manifest.json']))));self.addEventListener('fetch',e=>e.respondWith(caches.match(e.request).then(r=>r||fetch(e.request))));"
        else:
            files["runtime.py"] = _server_runtime(target)
        return _zip(files)

    def execute(self, product_id: str, build_id: str) -> dict:
        raw = self._raw_build(product_id, build_id)
        if raw is None:
            raise KeyError(build_id)
        build = self.lifecycle.ensure(raw)
        target = str(build.get("target") or "")
        if target not in LOCAL_BUILD_TARGETS:
            raise ArtifactBuilderError(
                f"No verified in-process builder is configured for {target}; native/container targets require their platform build runner"
            )
        if build["status"] == "succeeded" and build.get("metadata", {}).get("artifact_ready"):
            return build
        if build["status"] in {"failed", "cancelled"}:
            build = self.lifecycle.update(product_id, build_id, status="queued")
        if build["status"] == "queued":
            build = self.lifecycle.update(product_id, build_id, status="running")
        elif build["status"] == "requested":
            build = self.lifecycle.update(product_id, build_id, status="running")
        elif build["status"] != "running":
            raise ArtifactBuilderError(f"Build {build_id} cannot execute from status {build['status']}")

        try:
            spec = self._spec_for(raw)
            payload = self._bundle(spec, target)
            stem = _safe_stem(spec.manifest.get("name", "product"), "product")
            version = _safe_stem(spec.version, "0.0.0")
            filename = f"{stem}-{version}-{target}.zip"
            directory = (self.artifact_root / product_id / build_id).resolve()
            root = self.artifact_root.resolve()
            try:
                directory.relative_to(root)
            except ValueError as exc:
                raise ArtifactBuilderError("Invalid artifact destination") from exc
            directory.mkdir(parents=True, exist_ok=True)
            final = directory / filename
            temporary = directory / f".{filename}.tmp"
            temporary.write_bytes(payload)
            temporary.replace(final)
            checksum = _sha256(payload)
            if _sha256(final.read_bytes()) != checksum:
                raise ArtifactBuilderError("Artifact checksum verification failed after write")
            uri = f"{_ARTIFACT_SCHEME}://{product_id}/{build_id}/{filename}"
            return self.lifecycle.update(
                product_id,
                build_id,
                status="succeeded",
                artifact_name=filename,
                artifact_uri=uri,
                checksum=checksum,
                signing_verified=False,
                failure_reason="",
                verified_builder=True,
            )
        except Exception as exc:
            current = self._raw_build(product_id, build_id)
            if current:
                decorated = self.lifecycle.ensure(current)
                if decorated["status"] == "running":
                    self.lifecycle.update(product_id, build_id, status="failed", failure_reason=str(exc)[:2000])
            raise

    def resolve_artifact(self, product_id: str, build_id: str) -> tuple[Path, dict]:
        raw = self._raw_build(product_id, build_id)
        if raw is None:
            raise KeyError(build_id)
        build = self.lifecycle.ensure(raw)
        uri = str(build.get("metadata", {}).get("artifact_uri") or "")
        if not build.get("metadata", {}).get("artifact_ready") or not uri:
            raise ArtifactBuilderError("Build does not have a qualified downloadable artifact")
        parsed = urlparse(uri)
        if parsed.scheme != _ARTIFACT_SCHEME or parsed.netloc != product_id:
            raise ArtifactBuilderError("Build artifact URI is not owned by this product")
        parts = tuple(part for part in parsed.path.split("/") if part)
        if len(parts) != 2 or parts[0] != build_id or any(part in {".", ".."} for part in parts):
            raise ArtifactBuilderError("Build artifact URI is invalid")
        candidate = (self.artifact_root / product_id / parts[0] / parts[1]).resolve()
        root = self.artifact_root.resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ArtifactBuilderError("Build artifact path escapes the artifact root") from exc
        if not candidate.is_file():
            raise ArtifactBuilderError("Build artifact file is unavailable")
        raw_bytes = candidate.read_bytes()
        if _sha256(raw_bytes) != build.get("checksum"):
            raise ArtifactBuilderError("Build artifact checksum no longer matches verified evidence")
        return candidate, build
