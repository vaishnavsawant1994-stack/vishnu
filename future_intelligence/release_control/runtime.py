from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from future_intelligence.engineering.production_feedback import ProductionRegressionWorkBridge

from .controller import GovernedReleaseController, ReleaseControlError
from .http_qualification import HttpQualificationConfig, ReadOnlyHttpEnvironmentQualifier
from .policy import ReleaseOwnerPolicy
from .policy_store import ReleasePolicyStore
from .providers import ReleaseProvider
from .render_provider import RenderReleaseConfig, RenderReleaseProvider
from .store import JsonReleaseStore


@dataclass
class ReleaseControlRuntime:
    controller: GovernedReleaseController
    policy_store: ReleasePolicyStore
    providers: dict[str, ReleaseProvider]

    def policy(self) -> ReleaseOwnerPolicy:
        return self.policy_store.snapshot()

    def update_policy(self, **changes: Any) -> ReleaseOwnerPolicy:
        policy = self.policy_store.update(**changes)
        # Atomic object assignment keeps controller reads coherent; every
        # request receives one immutable ReleaseOwnerPolicy snapshot.
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


def build_release_control_runtime(*, data_dir: str | Path, work_store=None) -> ReleaseControlRuntime:
    root = Path(data_dir)
    policy_store = ReleasePolicyStore(root / "release-policy.json")
    release_store = JsonReleaseStore(root / "releases")
    providers: dict[str, ReleaseProvider] = {}
    qualifier = None

    render_values = {
        "api_token": _env("VISHNU_RELEASE_RENDER_API_TOKEN"),
        "preview_service_id": _env("VISHNU_RELEASE_RENDER_PREVIEW_SERVICE_ID"),
        "production_service_id": _env("VISHNU_RELEASE_RENDER_PRODUCTION_SERVICE_ID"),
        "preview_url": _env("VISHNU_RELEASE_RENDER_PREVIEW_URL"),
        "production_url": _env("VISHNU_RELEASE_RENDER_PRODUCTION_URL"),
    }
    configured = [bool(value) for value in render_values.values()]
    if any(configured) and not all(configured):
        # Partial credentials/configuration must never silently downgrade into a
        # different provider or unqualified deployment path.
        raise RuntimeError("Render release provider configuration is incomplete")
    if all(configured):
        render = RenderReleaseProvider(RenderReleaseConfig(**render_values))
        providers[render.name] = render
        allowed_hosts = tuple(sorted({_host(render_values["preview_url"]), _host(render_values["production_url"])} - {""}))
        qualifier = ReadOnlyHttpEnvironmentQualifier(
            HttpQualificationConfig(
                allowed_hosts=allowed_hosts,
                paths=("/", str(os.environ.get("VISHNU_RELEASE_HEALTH_PATH", "/health")).strip() or "/health"),
            )
        )

    bridge = ProductionRegressionWorkBridge(work_store) if work_store is not None else None
    controller = GovernedReleaseController(
        store=release_store,
        policy=policy_store.snapshot(),
        preview_qualifier=qualifier,
        production_smoke=qualifier,
        regression_bridge=bridge,
    )
    return ReleaseControlRuntime(controller=controller, policy_store=policy_store, providers=providers)
