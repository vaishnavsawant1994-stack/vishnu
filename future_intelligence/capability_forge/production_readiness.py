from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse


@dataclass(frozen=True)
class CapabilityForgeReadiness:
    ready: bool
    checks: dict[str, bool]
    blockers: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"ready": self.ready, "checks": dict(self.checks), "blockers": list(self.blockers)}


class CapabilityForgeProductionReadiness:
    """Fail-closed validation for externally configured production targets.

    This class deliberately does not create domains, OAuth clients, Android
    fingerprints, Apple team IDs or provider credentials. It proves that
    operator-supplied runtime configuration and active generated-capability
    lineage are complete before production capability sign-in can be enabled.
    """

    OAUTH_CALLBACK_PATH = "/iphone/capability-oauth/callback"

    @staticmethod
    def _https_url(value: str, *, allow_path: bool = True) -> bool:
        try:
            parsed = urlparse(str(value or "").strip())
        except Exception:
            return False
        if parsed.scheme != "https" or not parsed.hostname:
            return False
        if parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
            return False
        if parsed.username or parsed.password or parsed.fragment:
            return False
        if not allow_path and parsed.path not in {"", "/"}:
            return False
        return True

    @staticmethod
    def _android_valid(items: Any) -> bool:
        if not isinstance(items, list) or not items:
            return False
        for item in items:
            if not isinstance(item, dict):
                return False
            if item.get("relation") != ["delegate_permission/common.handle_all_urls"]:
                return False
            target = item.get("target")
            if not isinstance(target, dict) or target.get("namespace") != "android_app":
                return False
            package = str(target.get("package_name") or "")
            fingerprints = target.get("sha256_cert_fingerprints")
            if not package or not isinstance(fingerprints, list) or not fingerprints:
                return False
            for fp in fingerprints:
                parts = str(fp).split(":")
                if len(parts) != 32 or any(len(x) != 2 or any(ch not in "0123456789ABCDEFabcdef" for ch in x) for x in parts):
                    return False
        return True

    @staticmethod
    def _apple_valid(value: Any) -> bool:
        if not isinstance(value, dict):
            return False
        applinks = value.get("applinks")
        if not isinstance(applinks, dict) or applinks.get("apps") not in ([], None):
            return False
        details = applinks.get("details")
        if not isinstance(details, list) or not details:
            return False
        for item in details:
            if not isinstance(item, dict) or not str(item.get("appID") or "").strip():
                return False
            paths = item.get("paths") or item.get("components")
            if not isinstance(paths, list) or not paths:
                return False
        return True

    @staticmethod
    def _native_redirects(value: Any) -> bool:
        if not isinstance(value, dict) or not value:
            return False
        for client_id, redirects in value.items():
            if not str(client_id or "").strip() or not isinstance(redirects, (set, list, tuple)) or not redirects:
                return False
            for redirect in redirects:
                parsed = urlparse(str(redirect or ""))
                if not parsed.scheme or not parsed.path:
                    return False
                if parsed.scheme in {"http", "https"}:
                    if parsed.scheme != "https" or not parsed.hostname or parsed.hostname in {"localhost", "127.0.0.1"}:
                        return False
        return True

    def evaluate(self, *, public_base_url: str | None, oauth_redirect_uri: str | None,
                 android_asset_links: Any, apple_app_site_association: Any,
                 native_client_redirects: Any, provenance_available: bool,
                 provider_verification_available: bool, canary_available: bool,
                 external_oauth_available: bool, active_packages_provenanced: bool = True,
                 active_packages_broad_eligible: bool = True) -> CapabilityForgeReadiness:
        base_ok = self._https_url(str(public_base_url or ""), allow_path=False)
        callback_ok = self._https_url(str(oauth_redirect_uri or ""))
        same_origin = False
        callback_path_ok = False
        if callback_ok:
            callback = urlparse(str(oauth_redirect_uri))
            callback_path_ok = callback.path == self.OAUTH_CALLBACK_PATH and not callback.query
        if base_ok and callback_ok:
            base = urlparse(str(public_base_url))
            callback = urlparse(str(oauth_redirect_uri))
            same_origin = (base.scheme, base.hostname, base.port) == (callback.scheme, callback.hostname, callback.port)
        checks = {
            "public_https_origin": base_ok,
            "oauth_https_callback": callback_ok,
            "oauth_callback_path": callback_path_ok,
            "oauth_callback_same_origin": same_origin,
            "android_app_links": self._android_valid(android_asset_links),
            "ios_universal_links": self._apple_valid(apple_app_site_association),
            "native_pkce_clients": self._native_redirects(native_client_redirects),
            "package_provenance": bool(provenance_available),
            "active_packages_provenanced": bool(active_packages_provenanced),
            "active_packages_broad_eligible": bool(active_packages_broad_eligible),
            "provider_verification": bool(provider_verification_available),
            "canary_rollout": bool(canary_available),
            "capability_oauth": bool(external_oauth_available),
        }
        labels = {
            "public_https_origin": "production HTTPS origin is not configured",
            "oauth_https_callback": "production OAuth callback is not configured",
            "oauth_callback_path": "OAuth callback does not target the Capability Forge V3 callback route",
            "oauth_callback_same_origin": "OAuth callback is not bound to the production origin",
            "android_app_links": "Android App Link association is incomplete",
            "ios_universal_links": "iOS Universal Link association is incomplete",
            "native_pkce_clients": "native PKCE redirect registrations are incomplete",
            "package_provenance": "generated package provenance is unavailable",
            "active_packages_provenanced": "an active generated capability lacks V3 package provenance",
            "active_packages_broad_eligible": "an active generated capability lacks broad-eligible staged rollout evidence",
            "provider_verification": "live provider verification is unavailable",
            "canary_rollout": "Forge canary rollout is unavailable",
            "capability_oauth": "capability-specific OAuth is unavailable",
        }
        blockers = tuple(labels[name] for name, passed in checks.items() if not passed)
        return CapabilityForgeReadiness(not blockers, checks, blockers)
