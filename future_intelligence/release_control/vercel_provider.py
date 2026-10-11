from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any
from urllib import error, parse, request

from .contracts import ReleaseEnvironment, ReleasePlan
from .providers import ReleaseDeployment


class VercelProviderError(RuntimeError):
    pass


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise VercelProviderError("Vercel API redirects are not accepted")


@dataclass(frozen=True)
class VercelReleaseConfig:
    api_token: str = field(repr=False)
    project_id: str = ""
    project_name: str = ""
    github_org: str = ""
    github_repo: str = ""
    git_ref: str = "main"
    production_url: str = ""
    team_id: str = ""
    poll_interval_seconds: float = 2.0
    deployment_timeout_seconds: float = 900.0

    def __post_init__(self) -> None:
        for label, value in (
            ("api_token", self.api_token),
            ("project_id", self.project_id),
            ("project_name", self.project_name),
            ("github_org", self.github_org),
            ("github_repo", self.github_repo),
            ("git_ref", self.git_ref),
            ("production_url", self.production_url),
        ):
            if not str(value).strip():
                raise ValueError(f"Vercel release config requires {label}")
        if not self.production_url.startswith("https://"):
            raise ValueError("Vercel production URL must use HTTPS")
        if self.poll_interval_seconds <= 0 or self.deployment_timeout_seconds <= 0:
            raise ValueError("Vercel polling values must be positive")


class VercelReleaseProvider:
    """Exact-artifact Vercel release authority.

    Vercel's safe manual-promotion model requires a Production-target build that
    is *staged* without assigning production domains. Vishnu therefore first
    proves that the project has automatic custom-domain assignment disabled,
    builds the exact qualified Git SHA with ``target=production``, qualifies its
    immutable deployment URL, and only then promotes that same deployment.

    ``create_preview`` is retained for the generic ReleaseProvider protocol. For
    Vercel it means the pre-production qualification gate, backed by a staged
    Production deployment so promotion cannot switch environment variables or
    rebuild a different artifact.

    The Vercel token remains only in this provider object and is excluded from
    repr, plans, evidence, model context and API responses.
    """

    name = "vercel"
    _BASE = "https://api.vercel.com"
    _READY = {"READY"}
    _FAILURE = {"ERROR", "CANCELED", "BLOCKED"}

    def __init__(self, config: VercelReleaseConfig) -> None:
        self.config = config
        self._opener = request.build_opener(_NoRedirect())

    def _query(self, values: dict[str, str] | None = None) -> str:
        data = dict(values or {})
        if self.config.team_id:
            data.setdefault("teamId", self.config.team_id)
        return f"?{parse.urlencode(data)}" if data else ""

    def _call(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        query: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        payload = None if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8")
        req = request.Request(
            f"{self._BASE}{path}{self._query(query)}",
            data=payload,
            method=method,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.api_token}",
                "User-Agent": "Vishnu-Governed-Release/1",
            },
        )
        try:
            with self._opener.open(req, timeout=30) as response:
                raw = response.read(1_000_001)
                if len(raw) > 1_000_000:
                    raise VercelProviderError("Vercel API response exceeded the safety bound")
                value = json.loads(raw.decode("utf-8")) if raw else {}
        except (error.HTTPError, error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            code = getattr(exc, "code", None)
            raise VercelProviderError(f"Vercel API request failed{f' ({code})' if code else ''}") from exc
        if not isinstance(value, dict):
            raise VercelProviderError("Vercel API returned an unexpected payload")
        return value

    @staticmethod
    def _same_revision(left: str, right: str) -> bool:
        left = str(left).strip().lower()
        right = str(right).strip().lower()
        if len(left) < 7 or len(right) < 7:
            return False
        return left == right or left.startswith(right) or right.startswith(left)

    @staticmethod
    def _revision(payload: dict[str, Any]) -> str:
        git_source = payload.get("gitSource")
        if isinstance(git_source, dict) and git_source.get("sha"):
            return str(git_source["sha"]).strip()
        meta = payload.get("meta")
        if isinstance(meta, dict):
            for key in ("githubCommitSha", "gitCommitSha", "commitSha"):
                if meta.get(key):
                    return str(meta[key]).strip()
        return ""

    @staticmethod
    def _deployment_url(payload: dict[str, Any]) -> str:
        value = str(payload.get("url") or "").strip()
        if not value:
            raise VercelProviderError("Vercel deployment did not expose a deployment URL")
        return value if value.startswith("https://") else f"https://{value}"

    @staticmethod
    def _assert_production_target(payload: dict[str, Any]) -> None:
        if str(payload.get("target") or "").strip().lower() != "production":
            raise VercelProviderError(
                "Vercel release deployment is not a staged Production-target artifact"
            )

    def _project(self) -> dict[str, Any]:
        return self._call(
            "GET",
            f"/v9/projects/{parse.quote(self.config.project_id, safe='')}",
        )

    def _assert_staged_production_is_safe(self) -> None:
        project = self._project()
        project_id = str(project.get("id") or "").strip()
        if project_id and project_id != self.config.project_id:
            raise VercelProviderError("Vercel project identity does not match release configuration")
        if project.get("autoAssignCustomDomains") is not False:
            raise VercelProviderError(
                "Vercel staged production requires autoAssignCustomDomains=false before release control can deploy"
            )

    def _inspect(self, deployment_id: str) -> dict[str, Any]:
        return self._call(
            "GET",
            f"/v13/deployments/{parse.quote(deployment_id, safe='')}",
            query={"withGitRepoInfo": "true"},
        )

    def _wait(self, deployment_id: str, expected_revision: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.config.deployment_timeout_seconds
        while time.monotonic() < deadline:
            payload = self._inspect(deployment_id)
            revision = self._revision(payload)
            if revision and not self._same_revision(revision, expected_revision):
                raise VercelProviderError("Vercel deployment revision drifted from the release plan")
            state = str(payload.get("readyState") or payload.get("state") or "").upper()
            if state in self._READY:
                if not revision or not self._same_revision(revision, expected_revision):
                    raise VercelProviderError("Vercel ready deployment did not prove the exact candidate revision")
                return payload
            if state in self._FAILURE:
                raise VercelProviderError(f"Vercel deployment failed with state {state}")
            time.sleep(self.config.poll_interval_seconds)
        raise VercelProviderError("Vercel deployment timed out before reaching READY")

    def create_preview(self, plan: ReleasePlan) -> ReleaseDeployment:
        self._assert_staged_production_is_safe()
        payload = self._call(
            "POST",
            "/v13/deployments",
            {
                "name": self.config.project_name,
                "project": self.config.project_id,
                "target": "production",
                "gitSource": {
                    "type": "github",
                    "org": self.config.github_org,
                    "repo": self.config.github_repo,
                    "ref": self.config.git_ref,
                    "sha": plan.candidate_revision,
                },
                "meta": {
                    "vishnuReleaseId": plan.id,
                    "vishnuCandidateRevision": plan.candidate_revision,
                    "vishnuStagedProduction": "true",
                },
            },
        )
        deployment_id = str(payload.get("id") or "").strip()
        if not deployment_id:
            raise VercelProviderError("Vercel did not return a deployment id")
        revision = self._revision(payload)
        if revision and not self._same_revision(revision, plan.candidate_revision):
            raise VercelProviderError("Vercel accepted a different revision than requested")
        ready = self._wait(deployment_id, plan.candidate_revision)
        self._assert_production_target(ready)
        return ReleaseDeployment(
            id=deployment_id,
            provider=self.name,
            target=plan.target,
            revision=plan.candidate_revision,
            environment=ReleaseEnvironment.PREVIEW,
            url=self._deployment_url(ready),
            state="ready",
            metadata={
                "project_id": self.config.project_id,
                "staged_production": True,
                "production_domains_assigned": False,
                "promotion_rebuilds": False,
            },
        )

    def promote(self, plan: ReleasePlan) -> ReleaseDeployment:
        if not plan.preview_deployment_id or not plan.preview_url:
            raise VercelProviderError("Vercel production promotion requires the qualified staged deployment")
        inspected = self._wait(plan.preview_deployment_id, plan.candidate_revision)
        # Protect restarts/upgrades: a release created by older code might point
        # at a Preview-environment artifact with the same SHA. Never promote it.
        self._assert_production_target(inspected)
        self._call(
            "POST",
            f"/v10/projects/{parse.quote(self.config.project_id, safe='')}/promote/{parse.quote(plan.preview_deployment_id, safe='')}",
            {},
        )
        promoted = self._inspect(plan.preview_deployment_id)
        self._assert_production_target(promoted)
        revision = self._revision(promoted) or self._revision(inspected)
        if not revision or not self._same_revision(revision, plan.candidate_revision):
            raise VercelProviderError("Vercel promotion did not prove the bound candidate revision")
        return ReleaseDeployment(
            id=plan.preview_deployment_id,
            provider=self.name,
            target=plan.target,
            revision=plan.candidate_revision,
            environment=ReleaseEnvironment.PRODUCTION,
            url=self.config.production_url,
            state="ready",
            metadata={
                "project_id": self.config.project_id,
                "promoted_from_staged_production": True,
                "promotion_rebuilds": False,
            },
        )

    def observe(self, deployment: ReleaseDeployment) -> ReleaseDeployment:
        payload = self._inspect(deployment.id)
        revision = self._revision(payload)
        if not revision or not self._same_revision(revision, deployment.revision):
            raise VercelProviderError("observed Vercel deployment revision does not match recorded evidence")
        state = str(payload.get("readyState") or payload.get("state") or deployment.state).upper()
        return ReleaseDeployment(
            id=deployment.id,
            provider=deployment.provider,
            target=deployment.target,
            revision=deployment.revision,
            environment=deployment.environment,
            url=deployment.url,
            state="ready" if state == "READY" else state.lower(),
            metadata={**dict(deployment.metadata), "vercel_ready_state": state},
        )

    def _find_deployment_for_revision(self, revision: str) -> dict[str, Any]:
        payload = self._call(
            "GET",
            "/v6/deployments",
            query={
                "projectId": self.config.project_id,
                "sha": revision,
                "target": "production",
                "limit": "20",
            },
        )
        deployments = payload.get("deployments")
        if not isinstance(deployments, list):
            raise VercelProviderError("Vercel deployment history returned an unexpected payload")
        for item in deployments:
            if not isinstance(item, dict):
                continue
            item_revision = self._revision(item)
            if item_revision and self._same_revision(item_revision, revision) and item.get("id"):
                inspected = self._inspect(str(item["id"]))
                inspected_revision = self._revision(inspected)
                if inspected_revision and self._same_revision(inspected_revision, revision):
                    self._assert_production_target(inspected)
                    return inspected
        raise VercelProviderError("no immutable Vercel deployment was found for the rollback revision")

    def rollback(self, plan: ReleasePlan, deployment: ReleaseDeployment) -> ReleaseDeployment:
        baseline = self._find_deployment_for_revision(plan.base_revision)
        baseline_id = str(baseline.get("id") or "").strip()
        if not baseline_id:
            raise VercelProviderError("rollback baseline deployment has no id")
        self._call(
            "POST",
            f"/v1/projects/{parse.quote(self.config.project_id, safe='')}/rollback/{parse.quote(baseline_id, safe='')}",
            {"description": f"Vishnu governed rollback for {plan.id}"},
        )
        checked = self._inspect(baseline_id)
        self._assert_production_target(checked)
        checked_revision = self._revision(checked)
        if not checked_revision or not self._same_revision(checked_revision, plan.base_revision):
            raise VercelProviderError("Vercel rollback target no longer matches the bound base revision")
        return ReleaseDeployment(
            id=baseline_id,
            provider=self.name,
            target=plan.target,
            revision=plan.base_revision,
            environment=ReleaseEnvironment.PRODUCTION,
            url=self.config.production_url,
            state="ready",
            metadata={"rollback_of": deployment.id, "project_id": self.config.project_id},
        )
