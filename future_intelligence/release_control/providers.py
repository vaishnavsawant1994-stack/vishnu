from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol
from urllib.parse import urlsplit

from .contracts import ReleaseEnvironment, ReleasePlan


@dataclass(frozen=True)
class ReleaseDeployment:
    id: str
    provider: str
    target: str
    revision: str
    environment: ReleaseEnvironment
    url: str
    state: str = "ready"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for label, value in (
            ("id", self.id),
            ("provider", self.provider),
            ("target", self.target),
            ("revision", self.revision),
            ("state", self.state),
        ):
            if not str(value).strip():
                raise ValueError(f"deployment {label} is required")
        parsed = urlsplit(self.url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("deployment URL must be credential-free HTTPS")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "provider": self.provider,
            "target": self.target,
            "revision": self.revision,
            "environment": self.environment.value,
            "url": self.url,
            "state": self.state,
            "metadata": dict(self.metadata),
        }


class ReleaseProvider(Protocol):
    """Explicit release authority implemented outside the model layer.

    Implementations may wrap Vercel, Render, a GitHub deployment workflow, or
    another approved provider. Credentials stay inside the provider and are
    never passed through ReleasePlan or a model prompt.
    """

    name: str

    def create_preview(self, plan: ReleasePlan) -> ReleaseDeployment: ...

    def promote(self, plan: ReleasePlan) -> ReleaseDeployment: ...

    def observe(self, deployment: ReleaseDeployment) -> ReleaseDeployment: ...

    def rollback(self, plan: ReleasePlan, deployment: ReleaseDeployment) -> ReleaseDeployment: ...


class InMemoryReleaseProvider:
    """Deterministic provider used for qualification and offline development."""

    name = "memory"

    def __init__(self, *, host: str = "release.invalid") -> None:
        self.host = host
        self._deployments: dict[str, ReleaseDeployment] = {}

    def _deployment(self, plan: ReleasePlan, environment: ReleaseEnvironment) -> ReleaseDeployment:
        suffix = "preview" if environment is ReleaseEnvironment.PREVIEW else "production"
        deployment = ReleaseDeployment(
            id=f"{plan.id}-{suffix}",
            provider=self.name,
            target=plan.target,
            revision=plan.candidate_revision,
            environment=environment,
            url=f"https://{self.host}/{plan.id}/{suffix}",
            state="ready",
            metadata={"test_provider": True},
        )
        self._deployments[deployment.id] = deployment
        return deployment

    def create_preview(self, plan: ReleasePlan) -> ReleaseDeployment:
        return self._deployment(plan, ReleaseEnvironment.PREVIEW)

    def promote(self, plan: ReleasePlan) -> ReleaseDeployment:
        return self._deployment(plan, ReleaseEnvironment.PRODUCTION)

    def observe(self, deployment: ReleaseDeployment) -> ReleaseDeployment:
        return self._deployments.get(deployment.id, deployment)

    def rollback(self, plan: ReleasePlan, deployment: ReleaseDeployment) -> ReleaseDeployment:
        rolled_back = ReleaseDeployment(
            id=f"{deployment.id}-rollback",
            provider=self.name,
            target=deployment.target,
            revision=plan.base_revision,
            environment=deployment.environment,
            url=deployment.url,
            state="rolled_back",
            metadata={"rollback_of": deployment.id, "test_provider": True},
        )
        self._deployments[rolled_back.id] = rolled_back
        return rolled_back
