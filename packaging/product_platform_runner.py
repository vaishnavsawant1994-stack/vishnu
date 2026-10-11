from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

# This file is an executable runner entry point. Add the repository root before
# importing Vishnu's product-signing module so `python packaging/...py` works
# from a clean CI checkout as well as from an installed environment.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from products.signing import canonical_json, verify_payload


_EXPECTED_JOB_FILES = {"job.json", "manifest.json", "checksums.json"}
_PRODUCT_PUBLIC_KEY_ENV = "VISHNU_PRODUCT_SIGNING_PUBLIC_KEY_B64"
_FORBIDDEN_CREDENTIAL_KEYS = {
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "password",
    "private_key",
    "secret",
    "secret_ref",
    "credential_ref",
    "credentials_ref",
    "vault_ref",
}


class RunnerError(RuntimeError):
    pass


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _run(*cmd: str, cwd: Path | None = None) -> None:
    subprocess.check_call(list(cmd), cwd=str(cwd) if cwd else None)


def _assert_no_credentials(value, path: tuple[str, ...] = ()) -> None:
    """Reject credential-bearing fields without false-positive scanning values.

    Product descriptions/instructions may legitimately mention words such as
    "password". The distribution boundary is concerned with credential fields,
    not ordinary prose values.
    """
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).strip().lower()
            if normalized in _FORBIDDEN_CREDENTIAL_KEYS or normalized.endswith("_secret_ref"):
                raise RunnerError(f"Platform build manifest contains forbidden credential field: {'.'.join((*path, str(key)))}")
            _assert_no_credentials(item, (*path, str(key)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_no_credentials(item, (*path, str(index)))


def _load_job(path: Path, *, allow_unsigned: bool) -> tuple[dict, dict]:
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        if names != _EXPECTED_JOB_FILES:
            raise RunnerError("Build job contains unexpected files")
        job_bytes = archive.read("job.json")
        manifest_bytes = archive.read("manifest.json")
        checksums = json.loads(archive.read("checksums.json"))
    if checksums.get("job.json") != _sha256(job_bytes):
        raise RunnerError("Build job checksum mismatch")
    if checksums.get("manifest.json") != _sha256(manifest_bytes):
        raise RunnerError("Build manifest checksum mismatch")
    envelope = json.loads(job_bytes)
    manifest = json.loads(manifest_bytes)
    payload = envelope.get("payload") or {}
    if payload.get("schema") != "vishnu.product-build-job/v1":
        raise RunnerError("Unsupported platform build job schema")
    if payload.get("manifest_sha256") != _sha256(manifest_bytes):
        raise RunnerError("Build job does not bind the supplied manifest")
    signature = envelope.get("signature")
    if signature is None:
        if not allow_unsigned or not payload.get("development"):
            raise RunnerError("Unsigned platform build jobs are allowed only in explicit development mode")
    else:
        if not verify_payload(canonical_json(payload), signature):
            raise RunnerError("Platform build job signature is invalid")
        trusted = os.environ.get(_PRODUCT_PUBLIC_KEY_ENV, "").strip()
        if trusted:
            try:
                trusted_raw = base64.b64decode(trusted, validate=True)
                embedded_raw = base64.b64decode(str(signature.get("public_key_b64", "")), validate=True)
            except Exception as exc:
                raise RunnerError("Configured or embedded product signing public key is invalid") from exc
            if trusted_raw != embedded_raw:
                raise RunnerError("Platform build job signer does not match the pinned product signing key")
    for field in ("product_id", "build_id", "version", "target"):
        if not str(payload.get(field) or "").strip():
            raise RunnerError(f"Platform build job is missing {field}")
    if manifest.get("product_id") != payload.get("product_id") or str(manifest.get("version")) != str(payload.get("version")):
        raise RunnerError("Platform build job identity does not match its manifest")
    _assert_no_credentials(manifest)
    return payload, manifest


def _android_identifier(product_id: str) -> str:
    digest = hashlib.sha256(product_id.encode("utf-8")).hexdigest()[:16]
    return f"ai.vishnu.product.p{digest}"


def _android_project(root: Path, payload: dict, manifest: dict) -> Path:
    application_id = _android_identifier(str(payload["product_id"]))
    app_name = str(manifest.get("name") or "Vishnu Product")[:80]
    escaped_name = app_name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    package_path = Path(*application_id.split("."))
    java_dir = root / "app" / "src" / "main" / "java" / package_path
    assets = root / "app" / "src" / "main" / "assets"
    java_dir.mkdir(parents=True, exist_ok=True)
    assets.mkdir(parents=True, exist_ok=True)

    (root / "settings.gradle.kts").write_text(
        'pluginManagement { repositories { google(); mavenCentral(); gradlePluginPortal() } }\n'
        'dependencyResolutionManagement { repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS); repositories { google(); mavenCentral() } }\n'
        'rootProject.name = "VishnuProduct"\ninclude(":app")\n',
        encoding="utf-8",
    )
    (root / "build.gradle.kts").write_text(
        'plugins { id("com.android.application") version "8.7.3" apply false }\n',
        encoding="utf-8",
    )
    (root / "gradle.properties").write_text(
        "org.gradle.jvmargs=-Xmx2048m -Dfile.encoding=UTF-8\nandroid.useAndroidX=true\n",
        encoding="utf-8",
    )
    (root / "app" / "build.gradle.kts").write_text(
        f'''plugins {{ id("com.android.application") }}
android {{
    namespace = "{application_id}"
    compileSdk = 35
    defaultConfig {{ applicationId = "{application_id}"; minSdk = 26; targetSdk = 35; versionCode = 1; versionName = {json.dumps(str(payload["version"]))} }}
    val keystorePath = System.getenv("VISHNU_ANDROID_KEYSTORE_PATH")
    val keyAlias = System.getenv("VISHNU_ANDROID_KEY_ALIAS")
    val storePassword = System.getenv("VISHNU_ANDROID_KEYSTORE_PASSWORD")
    val keyPassword = System.getenv("VISHNU_ANDROID_KEY_PASSWORD")
    if (!keystorePath.isNullOrBlank() && !keyAlias.isNullOrBlank() && !storePassword.isNullOrBlank() && !keyPassword.isNullOrBlank()) {{
        signingConfigs {{ create("productRelease") {{ storeFile = file(keystorePath); this.storePassword = storePassword; this.keyAlias = keyAlias; this.keyPassword = keyPassword }} }}
        buildTypes {{ getByName("release") {{ isMinifyEnabled = false; signingConfig = signingConfigs.getByName("productRelease") }} }}
    }}
}}
''',
        encoding="utf-8",
    )
    manifest_xml = root / "app" / "src" / "main" / "AndroidManifest.xml"
    manifest_xml.write_text(
        f'''<manifest xmlns:android="http://schemas.android.com/apk/res/android">
  <application android:theme="@style/AppTheme" android:label="{escaped_name}" android:usesCleartextTraffic="false">
    <activity android:name=".MainActivity" android:exported="true">
      <intent-filter><action android:name="android.intent.action.MAIN"/><category android:name="android.intent.category.LAUNCHER"/></intent-filter>
    </activity>
  </application>
</manifest>''',
        encoding="utf-8",
    )
    values = root / "app" / "src" / "main" / "res" / "values"
    values.mkdir(parents=True, exist_ok=True)
    (values / "styles.xml").write_text(
        '<resources><style name="AppTheme" parent="android:style/Theme.Material.Light.NoActionBar"><item name="android:fontFamily">sans</item><item name="android:windowLightStatusBar">true</item><item name="android:statusBarColor">#F7F9FC</item></style></resources>',
        encoding="utf-8",
    )
    (java_dir / "MainActivity.java").write_text(
        f'''package {application_id};
import android.app.Activity;
import android.os.Bundle;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
public final class MainActivity extends Activity {{
  @Override public void onCreate(Bundle state) {{ super.onCreate(state); WebView view=new WebView(this); WebSettings settings=view.getSettings(); settings.setJavaScriptEnabled(false); settings.setAllowFileAccess(true); settings.setAllowContentAccess(false); view.setWebViewClient(new WebViewClient()); view.loadUrl("file:///android_asset/index.html"); setContentView(view); }}
}}
''',
        encoding="utf-8",
    )
    description = html.escape(str(manifest.get("description") or ""))
    components = "".join(
        f"<li><b>{html.escape(str(item.get('name') or 'Component'))}</b> · {html.escape(str(item.get('component_type') or 'custom'))}</li>"
        for item in manifest.get("components") or []
    ) or "<li>No components declared.</li>"
    (assets / "index.html").write_text(
        f'''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{{font-family:system-ui;background:#f7f9fc;color:#172033;margin:0;padding:28px}}main{{max-width:720px;margin:auto}}.card{{background:white;border:1px solid #dce3eb;border-radius:18px;padding:20px;margin:18px 0}}small{{letter-spacing:.14em;color:#718096}}li{{padding:7px 0}}</style></head><body><main><small>VISHNU PRODUCT</small><h1>{html.escape(app_name)}</h1><p>{description}</p><div class="card"><b>Version</b> {html.escape(str(payload['version']))}<br><b>AI mode</b> {html.escape(str((manifest.get('ai_policy') or {}).get('mode','disabled')))}</div><div class="card"><h2>Components</h2><ul>{components}</ul></div><p>This application contains only its product contract. Runtime credentials are provisioned separately.</p></main></body></html>''',
        encoding="utf-8",
    )
    (assets / "manifest.json").write_bytes(canonical_json(manifest))
    return root


def _find_gradle() -> str:
    value = shutil.which("gradle")
    if not value:
        raise RunnerError("Gradle is required to compile Android product artifacts")
    return value


def _find_apksigner() -> str | None:
    direct = shutil.which("apksigner")
    if direct:
        return direct
    sdk = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
    if not sdk:
        return None
    build_tools = Path(sdk) / "build-tools"
    if not build_tools.exists():
        return None
    candidates = sorted(build_tools.glob("*/apksigner*"), reverse=True)
    return str(candidates[0]) if candidates else None


def build_android(job_path: Path, output_dir: Path, *, allow_unsigned_job: bool = False, compile_artifact: bool = True) -> dict:
    payload, manifest = _load_job(job_path, allow_unsigned=allow_unsigned_job)
    if payload["target"] != "android":
        raise RunnerError("Android runner received a non-Android job")
    output_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="vishnu-product-android-"))
    try:
        project = _android_project(work, payload, manifest)
        if not compile_artifact:
            source_zip = output_dir / f"{payload['product_id']}-{payload['version']}-android-source.zip"
            shutil.make_archive(str(source_zip.with_suffix("")), "zip", project)
            raw = source_zip.read_bytes()
            return {"artifact": str(source_zip), "sha256": _sha256(raw), "size": len(raw), "platform_signing_verified": False, "variant": "source"}
        signing_env = all(
            os.environ.get(key, "").strip()
            for key in ("VISHNU_ANDROID_KEYSTORE_PATH", "VISHNU_ANDROID_KEY_ALIAS", "VISHNU_ANDROID_KEYSTORE_PASSWORD", "VISHNU_ANDROID_KEY_PASSWORD")
        )
        variant = "release" if signing_env else "debug"
        task = ":app:assembleRelease" if signing_env else ":app:assembleDebug"
        _run(_find_gradle(), task, "--stacktrace", cwd=project)
        apk = project / "app" / "build" / "outputs" / "apk" / variant / f"app-{variant}.apk"
        if not apk.exists():
            raise RunnerError("Android compiler completed without producing the expected APK")
        safe_product = re.sub(r"[^A-Za-z0-9._-]+", "-", str(manifest.get("name") or "product")).strip("-.") or "product"
        final = output_dir / f"{safe_product}-{payload['version']}-android-{variant}.apk"
        shutil.copy2(apk, final)
        signing_verified = False
        if signing_env:
            signer = _find_apksigner()
            if not signer:
                raise RunnerError("Release APK was built but apksigner is unavailable for verification")
            _run(signer, "verify", "--verbose", str(final))
            signing_verified = True
        raw = final.read_bytes()
        return {"artifact": str(final), "sha256": _sha256(raw), "size": len(raw), "platform_signing_verified": signing_verified, "variant": variant}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile a Vishnu product platform build job")
    parser.add_argument("job", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-unsigned-job", action="store_true")
    parser.add_argument("--source-only", action="store_true")
    args = parser.parse_args()
    payload, _manifest = _load_job(args.job, allow_unsigned=args.allow_unsigned_job)
    if payload["target"] == "android":
        result = build_android(args.job, args.output, allow_unsigned_job=args.allow_unsigned_job, compile_artifact=not args.source_only)
    else:
        raise RunnerError(f"No compiler adapter is implemented for {payload['target']} in this runner revision")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
