from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from future_intelligence.engineering.production_feedback import ProductionRegressionWorkBridge

from .controller import GovernedReleaseController, ReleaseControlError
from .feedback import RegressionAwareProductionSmokeProvider
from .http_qualification import HttpQualificationConfig, ReadOnlyHttpEnvironmentQualifier
from .policy import ReleaseOwnerPolicy
from .policy_store import ReleasePolicyStore
from .providers import ReleaseProvider
from .render_provider import RenderReleaseConfig, RenderReleaseProvider
from .store import JsonReleaseStore
from .vercel_provider import VercelReleaseConfig, VercelReleaseProvider


@dataclass
class ReleaseControlRuntime:
    controller: GovernedReleaseController
    policy_store: ReleasePolicyStore
    providers: dict[str, ReleaseProvider]

    def policy(self) -> ReleaseOwnerPolicy:
        return self.policy_store.snapshot()

    def update_policy(self, **changes: Any) -> ReleaseOwnerPolicy:
        policy = self.policy_store.update(**changes)
        self.controller.policy = policy
        return policy

    def provider(self, name: str):
        value = self.providers.get(str(name).strip())
        if value is None:
            raise ReleaseControlError(f"release provider is not configured: {name}")
        return value

    def summary(self) -> dict[str, Any]:
        return {
            "policy": self.policy().to_dict(),
            "providers": sorted(self.providers),
            "releases": [item.to_dict() for item in self.controller.store.list()[:50]],
        }


def _env(name: str) -> str:
    return str(os.environ.get(name, "")).strip()


def _host(url: str) -> str:
    return str(urlsplit(url).hostname or "").lower()


def _require_complete_provider(name: str, values: dict[str, str]) -> bool:
    configured = [bool(value) for value in values.values()]
    if any(configured) and not all(configured):
        missing = sorted(key for key, value in values.items() if not value)
        raise RuntimeError(f"{name} release provider configuration is incomplete: {', '.join(missing)}")
    return bool(configured) and all(configured)


def build_release_control_runtime(*, data_dir: str | Path, work_store=None) -> ReleaseControlRuntime:
    root = Path(data_dir)
    policy_store = ReleasePolicyStore(root / "release-policy.json")
    release_store = JsonReleaseStore(root / "releases")
    providers: dict[str, ReleaseProvider] = {}
    allowed_hosts: set[str] = set()
    allowed_suffixes: set[str] = set()

    render_values = {
        "api_token": _env("VISHNU_RELEASE_RENDER_API_TOKEN"),
        "preview_service_id": _env("VISHNU_RELEASE_RENDER_PREVIEW_SERVICE_ID"),
        "production_service_id": _env("VISHNU_RELEASE_RENDER_PRODUCTION_SERVICE_ID"),
        "preview_url": _env("VISHNU_RELEASE_RENDER_PREVIEW_URL"),
        "production_url": _env("VISHNU_RELEASE_RENDER_PRODUCTION_URL"),
    }
    if _require_complete_provider("Render", render_values):
        render = RenderReleaseProvider(RenderReleaseConfig(**render_values))
        providers[render.name] = render
        allowed_hosts.update(
            host for host in (_host(render_values["preview_url"]), _host(render_values["production_url"])) if host
        )

    vercel_required = {
        "api_token": _env("VISHNU_RELEASE_VERCEL_API_TOKEN"),
        "project_id": _env("VISHNU_RELEASE_VERCEL_PROJECT_ID"),
        "project_name": _env("VISHNU_RELEASE_VERCEL_PROJECT_NAME"),
        "github_org": _env("VISHNU_RELEASE_VERCEL_GITHUB_ORG"),
        "github_repo": _env("VISHNU_RELEASE_VERCEL_GITHUB_REPO"),
        "production_url": _env("VISHNU_RELEASE_VERCEL_PRODUCTION_URL"),
    }
    if _require_complete_provider("Vercel", vercel_required):
        vercel = VercelReleaseProvider(
            VercelReleaseConfig(
                **vercel_required,
                git_ref=_env("VISHNU_RELEASE_VERCEL_GIT_REF") or "main",
                team_id=_env("VISHNU_RELEASE_VERCEL_TEAM_ID"),
            )
        )
        providers[vercel.name] = vercel
        production_host = _host(vercel_required["production_url"])
        if production_host:
            allowed_hosts.add(production_host)
        preview_suffix = _env("VISHNU_RELEASE_VERCEL_PREVIEW_HOST_SUFFIX") or ".vercel.app"
        allowed_suffixes.add(preview_suffix.lower())

    qualifier = None
    if allowed_hosts or allowed_suffixes:
        qualifier = ReadOnlyHttpEnvironmentQualifier(
            HttpQualificationConfig(
                allowed_hosts=tuple(sorted(allowed_hosts)),
                allowed_host_suffixes=tuple(sorted(allowed_suffixes)),
                paths=("/", _env("VISHNU_RELEASE_HEALTH_PATH") or "/health"),
            )
        )

    bridge = ProductionRegressionWorkBridge(work_store) if work_store is not None else None
    production_smoke = (
        RegressionAwareProductionSmokeProvider(qualifier, bridge)
        if qualifier is not None and bridge is not None
        else qualifier
    )
    controller = GovernedReleaseController(
        store=release_store,
        policy=policy_store.snapshot(),
        preview_qualifier=qualifier,
        production_smoke=production_smoke,
        regression_bridge=bridge,
    )
    return ReleaseControlRuntime(controller=controller, policy_store=policy_store, providers=providers)
