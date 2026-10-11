from __future__ import annotations

import hashlib
import html
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .package_export import distribution_safe_manifest
from .runtime import ProductRuntimeSpec


NATIVE_PLATFORM_TARGETS = ("android", "ios", "windows", "macos", "linux", "docker")
SIGNED_PLATFORM_TARGETS = {"android", "ios", "windows", "macos"}
PROVISIONED_PLATFORM_TARGETS = {"ios"}
NOTARIZED_PLATFORM_TARGETS = {"macos"}
_SAFE = re.compile(r"[^a-zA-Z0-9._-]+")


class PlatformRunnerError(ValueError):
    pass


def canonical_json(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_stem(value: str, fallback: str = "product") -> str:
    value = _SAFE.sub("-", str(value or "").strip()).strip("-._")
    return value or fallback


def java_identifier(value: str) -> str:
    token = re.sub(r"[^a-zA-Z0-9_]", "_", str(value or "product")).lower().strip("_") or "product"
    if token[0].isdigit():
        token = f"p_{token}"
    return token[:50]


@dataclass(frozen=True)
class PlatformRunnerEvidence:
    schema: str
    product_id: str
    build_id: str
    version: str
    target: str
    mode: str
    host_os: str
    artifact_name: str
    artifact_kind: str
    sha256: str
    compiler_verified: bool
    signing_verified: bool = False
    provisioning_verified: bool = False
    notarization_verified: bool = False
    metadata: dict = field(default_factory=dict)

    @property
    def production_ready(self) -> bool:
        if self.schema != "vishnu.platform-runner-evidence/v1":
            return False
        if self.mode != "production" or not self.compiler_verified:
            return False
        if not self.artifact_name or not re.fullmatch(r"[0-9a-f]{64}", self.sha256 or ""):
            return False
        if self.target in SIGNED_PLATFORM_TARGETS and not self.signing_verified:
            return False
        if self.target in PROVISIONED_PLATFORM_TARGETS and not self.provisioning_verified:
            return False
        if self.target in NOTARIZED_PLATFORM_TARGETS and not self.notarization_verified:
            return False
        return self.target in NATIVE_PLATFORM_TARGETS

    def as_dict(self) -> dict:
        value = asdict(self)
        value["production_ready"] = self.production_ready
        return value


def validate_runner_evidence(value: dict) -> PlatformRunnerEvidence:
    if not isinstance(value, dict):
        raise PlatformRunnerError("Runner evidence must be an object")
    if value.get("schema") != "vishnu.platform-runner-evidence/v1":
        raise PlatformRunnerError("Unsupported platform runner evidence schema")
    target = str(value.get("target") or "").strip().lower()
    if target not in NATIVE_PLATFORM_TARGETS:
        raise PlatformRunnerError(f"Unsupported native platform target: {target}")
    mode = str(value.get("mode") or "").strip().lower()
    if mode not in {"development", "production"}:
        raise PlatformRunnerError("Runner evidence mode must be development or production")
    sha = str(value.get("sha256") or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", sha):
        raise PlatformRunnerError("Runner evidence requires a SHA-256 artifact digest")
    artifact_name = Path(str(value.get("artifact_name") or "")).name
    if not artifact_name or artifact_name != str(value.get("artifact_name") or ""):
        raise PlatformRunnerError("Runner evidence artifact name must be a filename, not a path")
    return PlatformRunnerEvidence(
        schema="vishnu.platform-runner-evidence/v1",
        product_id=str(value.get("product_id") or "").strip(),
        build_id=str(value.get("build_id") or "").strip(),
        version=str(value.get("version") or "").strip(),
        target=target,
        mode=mode,
        host_os=str(value.get("host_os") or "").strip(),
        artifact_name=artifact_name,
        artifact_kind=str(value.get("artifact_kind") or "").strip(),
        sha256=sha,
        compiler_verified=bool(value.get("compiler_verified")),
        signing_verified=bool(value.get("signing_verified")),
        provisioning_verified=bool(value.get("provisioning_verified")),
        notarization_verified=bool(value.get("notarization_verified")),
        metadata=dict(value.get("metadata") or {}),
    )


def _web_assets(manifest: dict) -> dict[str, bytes]:
    name = html.escape(str(manifest.get("name") or "Vishnu Product"))
    description = html.escape(str(manifest.get("description") or ""))
    index = f"""<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1,viewport-fit=cover\"><meta name=\"theme-color\" content=\"#07101a\"><title>{name}</title><style>*{{box-sizing:border-box}}body{{margin:0;background:#07101a;color:#f2f7fb;font-family:-apple-system,BlinkMacSystemFont,Inter,system-ui,sans-serif}}main{{max-width:760px;margin:auto;padding:40px 22px}}small{{color:#829ab0;letter-spacing:.16em}}h1{{font-size:clamp(2rem,8vw,4rem);margin:.3rem 0}}p{{color:#a8bacb;line-height:1.55}}.card{{margin-top:22px;padding:18px;border:1px solid #20384d;border-radius:18px;background:#0c1722}}button{{border:1px solid #385a72;border-radius:12px;background:#132536;color:#eef6ff;padding:11px 15px}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}</style></head><body><main><small>VISHNU PRODUCT</small><h1>{name}</h1><p>{description}</p><section class=\"card\"><b>Client runtime shell</b><p id=\"status\">Loading product contract…</p><button id=\"invoke\" type=\"button\">Run product action</button><pre id=\"result\"></pre></section></main><script src=\"runtime.js\"></script></body></html>""".encode("utf-8")
    runtime = """(()=>{'use strict';const q=s=>document.querySelector(s);fetch('manifest.json').then(r=>r.json()).then(m=>{q('#status').textContent=`${m.name} · ${m.version} · AI ${(m.ai_policy||{}).mode||'disabled'}`}).catch(e=>q('#status').textContent=e.message);q('#invoke').addEventListener('click',()=>{q('#result').textContent='This thin client is ready for an approved product runtime connector. Owner Vishnu state is not embedded in this application.'});})();""".encode("utf-8")
    return {"web/index.html": index, "web/runtime.js": runtime, "web/manifest.json": canonical_json(manifest)}


def _desktop_runtime(manifest: dict) -> bytes:
    payload = json.dumps(manifest, sort_keys=True, ensure_ascii=False)
    return f'''from __future__ import annotations
import html,json,threading,webbrowser
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
MANIFEST=json.loads({payload!r})
PAGE="""<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{{name}}</title><style>body{{background:#07101a;color:#eff6fb;font-family:system-ui;margin:0}}main{{max-width:760px;margin:auto;padding:48px 24px}}p{{color:#a8bacb;line-height:1.55}}section{{border:1px solid #263d50;border-radius:18px;padding:20px;background:#0d1924}}</style><main><small>VISHNU PRODUCT</small><h1>{{name}}</h1><p>{{description}}</p><section><b>Desktop client runtime</b><p>Version {{version}}</p><p>This application contains only its product contract. Connect the approved client runtime to execute agents, workflows or AI calls.</p></section></main>"""
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  if self.path=='/manifest.json': raw=json.dumps(MANIFEST,separators=(',',':')).encode();kind='application/json'
  else: raw=PAGE.format(name=html.escape(str(MANIFEST.get('name') or 'Vishnu Product')),description=html.escape(str(MANIFEST.get('description') or '')),version=html.escape(str(MANIFEST.get('version') or ''))).encode();kind='text/html; charset=utf-8'
  self.send_response(200);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
 def log_message(self,*_):pass
if __name__=='__main__':
 server=ThreadingHTTPServer(('127.0.0.1',0),Handler);url=f'http://127.0.0.1:{{server.server_port}}/';threading.Timer(.4,lambda:webbrowser.open(url)).start();server.serve_forever()
'''.encode("utf-8")


def _android_files(manifest: dict) -> dict[str, bytes]:
    product_id = java_identifier(manifest.get("product_id") or manifest.get("name"))
    package = f"com.vishnu.products.{product_id}"
    app_name = str(manifest.get("name") or "Vishnu Product").replace('"', '')[:80]
    web = _web_assets(manifest)
    build_gradle = f'''plugins {{ id("com.android.application") }}
android {{
    namespace = "{package}"
    compileSdk = 35
    defaultConfig {{ applicationId = "{package}"; minSdk = 26; targetSdk = 35; versionCode = 1; versionName = "{str(manifest.get('version') or '0.1.0')}" }}
    signingConfigs {{
        create("release") {{
            val store = System.getenv("VISHNU_ANDROID_KEYSTORE")
            if (!store.isNullOrBlank()) {{
                storeFile = file(store); storePassword = System.getenv("VISHNU_ANDROID_STORE_PASSWORD")
                keyAlias = System.getenv("VISHNU_ANDROID_KEY_ALIAS"); keyPassword = System.getenv("VISHNU_ANDROID_KEY_PASSWORD")
            }}
        }}
    }}
    buildTypes {{
        getByName("release") {{ isMinifyEnabled = false; signingConfig = signingConfigs.getByName("release") }}
    }}
}}
'''
    activity = f'''package {package};
import android.app.Activity;
import android.os.Bundle;
import android.webkit.WebSettings;
import android.webkit.WebView;
public final class MainActivity extends Activity {{
  private WebView web;
  @Override public void onCreate(Bundle state) {{ super.onCreate(state); web=new WebView(this); WebSettings settings=web.getSettings(); settings.setJavaScriptEnabled(true); settings.setAllowFileAccess(true); web.loadUrl("file:///android_asset/index.html"); setContentView(web); }}
  @Override public void onBackPressed() {{ if(web!=null && web.canGoBack()) web.goBack(); else super.onBackPressed(); }}
}}
'''
    android_manifest = f'''<manifest xmlns:android="http://schemas.android.com/apk/res/android"><uses-permission android:name="android.permission.INTERNET"/><application android:theme="@style/AppTheme" android:label="{html.escape(app_name, quote=True)}" android:usesCleartextTraffic="false"><activity android:name=".MainActivity" android:exported="true"><intent-filter><action android:name="android.intent.action.MAIN"/><category android:name="android.intent.category.LAUNCHER"/></intent-filter></activity></application></manifest>'''
    return {
        "settings.gradle.kts": b'pluginManagement { repositories { google(); mavenCentral(); gradlePluginPortal() } }\ndependencyResolutionManagement { repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS); repositories { google(); mavenCentral() } }\nrootProject.name = "VishnuProduct"\ninclude(":app")\n',
        "build.gradle.kts": b'plugins { id("com.android.application") version "8.7.3" apply false }\n',
        "gradle.properties": b'org.gradle.jvmargs=-Xmx2048m -Dfile.encoding=UTF-8\nandroid.useAndroidX=true\n',
        "app/build.gradle.kts": build_gradle.encode("utf-8"),
        "app/src/main/AndroidManifest.xml": android_manifest.encode("utf-8"),
        f"app/src/main/java/{package.replace('.', '/')}/MainActivity.java": activity.encode("utf-8"),
        "app/src/main/res/values/styles.xml": b'<resources><style name="AppTheme" parent="android:style/Theme.Material.Light.NoActionBar"><item name="android:fontFamily">sans</item><item name="android:colorAccent">#4F8CFF</item><item name="android:windowLightStatusBar">false</item><item name="android:statusBarColor">#07101A</item></style></resources>',
        "app/src/main/assets/index.html": web["web/index.html"],
        "app/src/main/assets/runtime.js": web["web/runtime.js"],
        "app/src/main/assets/manifest.json": web["web/manifest.json"],
    }


def _ios_files(manifest: dict) -> dict[str, bytes]:
    product_id = java_identifier(manifest.get("product_id") or manifest.get("name"))
    bundle = f"com.vishnu.products.{product_id}"
    name = str(manifest.get("name") or "Vishnu Product")[:80]
    web = _web_assets(manifest)
    swift = '''import SwiftUI\nimport WebKit\n\nstruct ProductWebView: UIViewRepresentable {\n    func makeUIView(context: Context) -> WKWebView {\n        let web = WKWebView()\n        if let url = Bundle.main.url(forResource: "index", withExtension: "html", subdirectory: "web") {\n            web.loadFileURL(url, allowingReadAccessTo: url.deletingLastPathComponent())\n        }\n        return web\n    }\n    func updateUIView(_ uiView: WKWebView, context: Context) {}\n}\n\n@main struct ProductApp: App { var body: some Scene { WindowGroup { ProductWebView().ignoresSafeArea() } } }\n'''
    project = f'''name: VishnuProduct
options:
  bundleIdPrefix: com.vishnu.products
settings:
  base:
    SWIFT_VERSION: 5.0
targets:
  VishnuProduct:
    type: application
    platform: iOS
    deploymentTarget: "17.0"
    sources:
      - Sources
      - Resources
    settings:
      base:
        PRODUCT_BUNDLE_IDENTIFIER: {bundle}
        PRODUCT_NAME: "{name.replace(chr(34), '')}"
        GENERATE_INFOPLIST_FILE: YES
        INFOPLIST_KEY_CFBundleDisplayName: "{name.replace(chr(34), '')}"
        INFOPLIST_KEY_UIApplicationSceneManifest_Generation: YES
        INFOPLIST_KEY_UILaunchScreen_Generation: YES
        CODE_SIGN_STYLE: Automatic
'''
    return {
        "project.yml": project.encode("utf-8"),
        "Sources/ProductApp.swift": swift.encode("utf-8"),
        "Resources/web/index.html": web["web/index.html"],
        "Resources/web/runtime.js": web["web/runtime.js"],
        "Resources/web/manifest.json": web["web/manifest.json"],
    }


def _docker_files(manifest: dict) -> dict[str, bytes]:
    payload = json.dumps(manifest, sort_keys=True, ensure_ascii=False)
    runtime = f'''from __future__ import annotations
import json
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
MANIFEST=json.loads({payload!r})
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
    return {
        "Dockerfile": b'FROM python:3.12-slim\nWORKDIR /app\nCOPY runtime.py manifest.json /app/\nUSER 65532:65532\nEXPOSE 8080\nCMD ["python","/app/runtime.py"]\n',
        ".dockerignore": b"*\n!runtime.py\n!manifest.json\n!Dockerfile\n",
        "runtime.py": runtime.encode("utf-8"),
        "manifest.json": canonical_json(manifest),
    }


def platform_source_kit(spec: ProductRuntimeSpec, target: str) -> dict[str, bytes]:
    target = str(target or "").strip().lower()
    if target not in NATIVE_PLATFORM_TARGETS:
        raise PlatformRunnerError(f"Unsupported native platform target: {target}")
    if target not in spec.targets:
        raise PlatformRunnerError(f"Target {target} is not enabled in product version {spec.version}")
    manifest = distribution_safe_manifest(spec.manifest)
    files: dict[str, bytes] = {
        "manifest.json": canonical_json(manifest),
        "RUNNER-BOUNDARY.txt": (
            "This platform source kit is generated from a frozen Vishnu product manifest.\n"
            "It excludes owner memory, owner credentials and the full Vishnu source tree.\n"
            "Production readiness requires target-specific compiler and signing/provisioning evidence.\n"
        ).encode("utf-8"),
    }
    if target in {"windows", "macos", "linux"}:
        files["desktop_runtime.py"] = _desktop_runtime(manifest)
        files.update(_web_assets(manifest))
    elif target == "android":
        files.update(_android_files(manifest))
    elif target == "ios":
        files.update(_ios_files(manifest))
    elif target == "docker":
        files.update(_docker_files(manifest))
    return files


def write_platform_source_kit(spec: ProductRuntimeSpec, target: str, destination: Path) -> Path:
    root = Path(destination).resolve()
    root.mkdir(parents=True, exist_ok=True)
    for relative, payload in platform_source_kit(spec, target).items():
        parts = Path(relative).parts
        if any(part in {".", ".."} for part in parts):
            raise PlatformRunnerError("Platform source kit contains an unsafe path")
        path = (root / relative).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise PlatformRunnerError("Platform source kit escaped the destination root") from exc
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    return root
