from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import platform
import plistlib
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

_core_path = Path(__file__).with_name("product_platform_runner.py")
_spec = importlib.util.spec_from_file_location("_vishnu_product_platform_runner", _core_path)
if _spec is None or _spec.loader is None:  # pragma: no cover
    raise RuntimeError("Unable to load the Vishnu product build-job verifier")
_core = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_core)
_load_job = _core._load_job
RunnerError = _core.RunnerError

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe(value: str, fallback: str = "product") -> str:
    token = _SAFE.sub("-", str(value or "").strip()).strip("-._")
    return token or fallback


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run(*cmd: str, cwd: Path | None = None, capture: bool = False):
    return subprocess.run(
        list(cmd),
        cwd=str(cwd) if cwd else None,
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
    provisioning_verified: bool = False,
    notarization_verified: bool = False,
    metadata: dict | None = None,
) -> dict:
    digest = _sha256(artifact)
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
        "provisioning_verified": bool(provisioning_verified),
        "notarization_verified": bool(notarization_verified),
        "metadata": {"variant": variant, "runner": "vishnu-product-apple", **dict(metadata or {})},
    }
    return {
        "artifact": str(artifact),
        "sha256": digest,
        "size": artifact.stat().st_size,
        "platform_signing_verified": bool(signing_verified),
        "provisioning_verified": bool(provisioning_verified),
        "notarization_verified": bool(notarization_verified),
        "variant": variant,
        "evidence": evidence,
    }


def _require_darwin() -> None:
    if platform.system() != "Darwin":
        raise RunnerError("Apple product compilation must run on a macOS host")
    if not shutil.which("xcrun"):
        raise RunnerError("Xcode command-line tools are required for Apple product compilation")


def _bundle_id(product_id: str) -> str:
    digest = hashlib.sha256(str(product_id).encode("utf-8")).hexdigest()[:20]
    return f"ai.vishnu.product.p{digest}"


def _macos_source(name: str, description: str) -> str:
    title = json.dumps(name)
    body = json.dumps(description or "This Vishnu product contains only its portable product contract.")
    return f'''import AppKit

let app = NSApplication.shared
app.setActivationPolicy(.regular)
let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 760, height: 520), styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
window.title = {title}
let label = NSTextField(wrappingLabelWithString: {body})
label.font = NSFont.systemFont(ofSize: 18)
label.frame = NSRect(x: 48, y: 80, width: 664, height: 360)
window.contentView?.addSubview(label)
window.center()
window.makeKeyAndOrderFront(nil)
app.activate(ignoringOtherApps: true)
app.run()
'''


def _macos_sign(app: Path) -> bool:
    identity = os.environ.get("VISHNU_MACOS_SIGNING_IDENTITY", "").strip()
    if not identity:
        return False
    _run("codesign", "--force", "--deep", "--options", "runtime", "--timestamp", "--sign", identity, str(app))
    _run("codesign", "--verify", "--deep", "--strict", "--verbose=2", str(app))
    return True


def _macos_notarize(dmg: Path) -> bool:
    profile = os.environ.get("VISHNU_MACOS_NOTARY_KEYCHAIN_PROFILE", "").strip()
    if not profile:
        return False
    _run("xcrun", "notarytool", "submit", str(dmg), "--keychain-profile", profile, "--wait")
    _run("xcrun", "stapler", "staple", str(dmg))
    _run("xcrun", "stapler", "validate", str(dmg))
    return True


def build_macos(job_path: Path, output_dir: Path, *, allow_unsigned_job: bool = False) -> dict:
    _require_darwin()
    payload, manifest = _load_job(job_path, allow_unsigned=allow_unsigned_job)
    if payload["target"] != "macos":
        raise RunnerError("macOS runner received a non-macOS job")
    output_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="vishnu-product-macos-"))
    try:
        name = _safe(manifest.get("name") or "VishnuProduct", "VishnuProduct")
        app = work / f"{name}.app"
        macos_dir = app / "Contents" / "MacOS"
        resources = app / "Contents" / "Resources"
        macos_dir.mkdir(parents=True)
        resources.mkdir(parents=True)
        source = work / "main.swift"
        source.write_text(_macos_source(str(manifest.get("name") or name), str(manifest.get("description") or "")), encoding="utf-8")
        executable = macos_dir / name
        _run("xcrun", "swiftc", str(source), "-o", str(executable), "-framework", "AppKit")
        executable.chmod(0o755)
        (resources / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2), encoding="utf-8")
        info = {
            "CFBundleDevelopmentRegion": "en",
            "CFBundleExecutable": name,
            "CFBundleIdentifier": _bundle_id(str(payload["product_id"])),
            "CFBundleInfoDictionaryVersion": "6.0",
            "CFBundleName": str(manifest.get("name") or name),
            "CFBundlePackageType": "APPL",
            "CFBundleShortVersionString": str(payload["version"]),
            "CFBundleVersion": "1",
            "LSMinimumSystemVersion": "13.0",
            "NSHighResolutionCapable": True,
        }
        (app / "Contents" / "Info.plist").write_bytes(plistlib.dumps(info))
        signing_verified = _macos_sign(app)
        final = output_dir / f"{name}-{payload['version']}-macos.dmg"
        _run("hdiutil", "create", "-volname", name, "-srcfolder", str(app), "-ov", "-format", "UDZO", str(final))
        notarized = _macos_notarize(final) if signing_verified else False
        if not payload.get("development") and (not signing_verified or not notarized):
            raise RunnerError("Production macOS products require verified code signing and notarization")
        return _result(
            payload,
            final,
            artifact_kind="dmg",
            variant="universal-host",
            signing_verified=signing_verified,
            notarization_verified=notarized,
            metadata={"bundle_id": info["CFBundleIdentifier"]},
        )
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _ios_source(name: str, description: str) -> str:
    title = json.dumps(name)
    body = json.dumps(description or "This Vishnu product contains only its portable product contract.")
    return f'''import UIKit

final class AppDelegate: UIResponder, UIApplicationDelegate {{
    var window: UIWindow?
    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {{
        let window = UIWindow(frame: UIScreen.main.bounds)
        let controller = UIViewController()
        controller.view.backgroundColor = .systemBackground
        let label = UILabel(frame: controller.view.bounds.insetBy(dx: 28, dy: 80))
        label.numberOfLines = 0
        label.textAlignment = .center
        label.font = .systemFont(ofSize: 19, weight: .medium)
        label.text = {title} + "\\n\\n" + {body}
        controller.view.addSubview(label)
        window.rootViewController = controller
        window.makeKeyAndVisible()
        self.window = window
        return true
    }}
}}
UIApplicationMain(CommandLine.argc, CommandLine.unsafeArgv, nil, NSStringFromClass(AppDelegate.self))
'''


def _profile_entitlements(profile: Path) -> dict:
    try:
        decoded = subprocess.check_output(["security", "cms", "-D", "-i", str(profile)])
        plist = plistlib.loads(decoded)
    except Exception as exc:
        raise RunnerError("Unable to decode the configured iOS provisioning profile") from exc
    entitlements = plist.get("Entitlements") if isinstance(plist, dict) else None
    if not isinstance(entitlements, dict):
        raise RunnerError("The iOS provisioning profile does not contain entitlements")
    return dict(entitlements)


def _ios_sign(app: Path, bundle_id: str, work: Path) -> tuple[bool, bool]:
    identity = os.environ.get("VISHNU_IOS_SIGNING_IDENTITY", "").strip()
    profile_value = os.environ.get("VISHNU_IOS_PROVISIONING_PROFILE", "").strip()
    if not identity and not profile_value:
        return False, False
    if not identity or not profile_value:
        raise RunnerError("iOS signing identity and provisioning profile must be configured together")
    profile = Path(profile_value)
    if not profile.is_file():
        raise RunnerError("Configured iOS provisioning profile is unavailable")
    entitlements = _profile_entitlements(profile)
    application_id = str(entitlements.get("application-identifier") or "")
    if not application_id.endswith(f".{bundle_id}"):
        raise RunnerError("The configured iOS provisioning profile does not authorize this product bundle ID")
    shutil.copy2(profile, app / "embedded.mobileprovision")
    entitlements_path = work / "entitlements.plist"
    entitlements_path.write_bytes(plistlib.dumps(entitlements))
    _run("codesign", "--force", "--sign", identity, "--entitlements", str(entitlements_path), "--timestamp=none", str(app))
    _run("codesign", "--verify", "--deep", "--strict", "--verbose=2", str(app))
    return True, True


def build_ios(job_path: Path, output_dir: Path, *, allow_unsigned_job: bool = False) -> dict:
    _require_darwin()
    payload, manifest = _load_job(job_path, allow_unsigned=allow_unsigned_job)
    if payload["target"] != "ios":
        raise RunnerError("iOS runner received a non-iOS job")
    output_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="vishnu-product-ios-"))
    try:
        name = _safe(manifest.get("name") or "VishnuProduct", "VishnuProduct")
        bundle_id = _bundle_id(str(payload["product_id"]))
        production = not bool(payload.get("development"))
        sdk = "iphoneos" if production else "iphonesimulator"
        sdk_path = _run("xcrun", "--sdk", sdk, "--show-sdk-path", capture=True).stdout.strip()
        if not sdk_path:
            raise RunnerError(f"Unable to resolve Xcode SDK {sdk}")
        arch = "arm64" if production or platform.machine().lower() in {"arm64", "aarch64"} else "x86_64"
        target = f"{arch}-apple-ios17.0" + ("-simulator" if not production else "")
        app = work / f"{name}.app"
        app.mkdir()
        source = work / "main.swift"
        source.write_text(_ios_source(str(manifest.get("name") or name), str(manifest.get("description") or "")), encoding="utf-8")
        executable = app / name
        _run("xcrun", "--sdk", sdk, "swiftc", "-sdk", sdk_path, "-target", target, str(source), "-o", str(executable), "-framework", "UIKit")
        executable.chmod(0o755)
        info = {
            "CFBundleDevelopmentRegion": "en",
            "CFBundleDisplayName": str(manifest.get("name") or name),
            "CFBundleExecutable": name,
            "CFBundleIdentifier": bundle_id,
            "CFBundleInfoDictionaryVersion": "6.0",
            "CFBundleName": name,
            "CFBundlePackageType": "APPL",
            "CFBundleShortVersionString": str(payload["version"]),
            "CFBundleVersion": "1",
            "LSRequiresIPhoneOS": True,
            "MinimumOSVersion": "17.0",
            "UILaunchScreen": {},
            "UISupportedInterfaceOrientations": ["UIInterfaceOrientationPortrait"],
        }
        (app / "Info.plist").write_bytes(plistlib.dumps(info))
        (app / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2), encoding="utf-8")
        signing_verified, provisioning_verified = _ios_sign(app, bundle_id, work) if production else (False, False)
        if production and (not signing_verified or not provisioning_verified):
            raise RunnerError("Production iOS products require a verified signing identity and matching provisioning profile")
        if production:
            payload_dir = work / "Payload"
            payload_dir.mkdir()
            shutil.move(str(app), str(payload_dir / app.name))
            final = output_dir / f"{name}-{payload['version']}-ios.ipa"
            with zipfile.ZipFile(final, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
                for item in sorted(payload_dir.rglob("*")):
                    if item.is_file():
                        archive.write(item, item.relative_to(work).as_posix())
            artifact_kind = "ipa"
            variant = "device"
        else:
            final = output_dir / f"{name}-{payload['version']}-ios-simulator.zip"
            with zipfile.ZipFile(final, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
                for item in sorted(app.rglob("*")):
                    if item.is_file():
                        archive.write(item, item.relative_to(work).as_posix())
            artifact_kind = "ios-simulator-app"
            variant = "simulator"
        return _result(
            payload,
            final,
            artifact_kind=artifact_kind,
            variant=variant,
            signing_verified=signing_verified,
            provisioning_verified=provisioning_verified,
            metadata={"bundle_id": bundle_id, "sdk": sdk, "architecture": arch},
        )
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile Vishnu Apple product build jobs")
    parser.add_argument("job", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-unsigned-job", action="store_true")
    args = parser.parse_args()
    payload, _manifest = _load_job(args.job, allow_unsigned=args.allow_unsigned_job)
    if payload["target"] == "macos":
        result = build_macos(args.job, args.output, allow_unsigned_job=args.allow_unsigned_job)
    elif payload["target"] == "ios":
        result = build_ios(args.job, args.output, allow_unsigned_job=args.allow_unsigned_job)
    else:
        raise RunnerError(f"Apple runner does not implement target {payload['target']}")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
