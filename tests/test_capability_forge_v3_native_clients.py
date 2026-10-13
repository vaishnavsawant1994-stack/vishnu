from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_android_forge_v3_is_native_session_scoped_fail_closed_and_not_exported():
    manifest = _text("android-companion/app/src/main/AndroidManifest.xml")
    main = _text("android-companion/app/src/main/java/ai/personal/companion/MainActivity.kt")
    forge = _text("android-companion/app/src/main/java/ai/personal/companion/ForgeV3Activity.kt")
    application = _text("android-companion/app/src/main/java/ai/personal/companion/VishnuApplication.kt")

    assert 'android:name=".VishnuApplication"' in manifest
    assert 'android:name=".ForgeV3Activity" android:exported="false"' in manifest
    assert 'const val API_BASE = ""' in main
    assert 'const val NATIVE_REDIRECT = ""' in main
    assert 'prefs.getString("native_access_token", null)' in forge
    assert 'MainActivity.API_BASE.isBlank()' in forge
    assert 'followRedirects(false)' in forge and 'followSslRedirects(false)' in forge
    assert '"/owner/forge/v3/readiness"' in forge
    assert '"/owner/forge/v3/oauth/providers"' in forge
    assert '"/native/sessions/reauth"' in forge
    assert '"/owner/forge/v3/providers/verify"' in forge
    assert '/rollout/' in forge and '/canary' in forge and '/promotion' in forge and '/health/' in forge
    assert 'production activation' in forge.casefold()
    assert 'ForgeV3Activity::class.java' in application
    assert 'vishnu-capability-forge-v3' in application
    assert "railway" not in (main + forge + application).casefold()


def test_ios_forge_v3_reuses_keychain_session_blocks_redirects_and_has_no_production_host():
    plist = _text("ios-companion/PersonalAICompanion/Info.plist")
    forge = _text("ios-companion/PersonalAICompanion/NativeForgeV3.swift")
    app = _text("ios-companion/PersonalAICompanion/PersonalAICompanionApp.swift")

    assert '<key>VishnuCapabilityHost</key><string></string>' in plist
    assert 'NativeForgeV3View()' in app
    assert 'keychain.get("native.capabilities.token")' in forge
    assert 'keychain.get("native.capabilities.expiry")' in forge
    assert 'Bundle.main.object(forInfoDictionaryKey: "VishnuCapabilityHost")' in forge
    assert '"/owner/forge/v3/readiness"' in forge
    assert '"/owner/forge/v3/oauth/providers"' in forge
    assert '"/native/sessions/reauth"' in forge
    assert '"/owner/forge/v3/providers/verify"' in forge
    assert '/rollout/' in forge and '/canary' in forge and '/promotion' in forge and '/health/' in forge
    assert 'ForgeV3RedirectBlocker' in forge
    assert 'completionHandler(nil)' in forge
    assert 'Production activation is not available here' in forge
    assert "railway" not in (plist + forge + app).casefold()


def test_native_forge_v3_surfaces_do_not_define_approval_or_production_activation_endpoints():
    android = _text("android-companion/app/src/main/java/ai/personal/companion/ForgeV3Activity.kt")
    ios = _text("ios-companion/PersonalAICompanion/NativeForgeV3.swift")
    combined = android + "\n" + ios

    # Native surfaces may submit an already-approved rollout ticket, but they do
    # not expose a canonical approval-decision endpoint or a production release API.
    assert '/approvals/' not in combined
    assert '/approve' not in combined
    assert '/deploy' not in combined
    assert '/release' not in combined
    assert '/production/activate' not in combined
