from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Mapping
from urllib import error, parse, request

from .contracts import EngineeringSpec
from .workflow_evidence import (
    GitHubPhysicalDeviceEvidenceVerifier,
    PhysicalDeviceWorkflowRun,
    WorkflowEvidenceError,
)


@dataclass(frozen=True)
class GitHubPhysicalDeviceOrchestrationConfig:
    """Configuration for the narrow Actions dispatch authority.

    This authority can dispatch only the two allowlisted real-device workflows.
    It cannot create refs, push source, merge pull requests, deploy, roll back, or
    manufacture qualification evidence. The candidate must already exist as the
    exact tip of a remote branch before a workflow can be dispatched.
    """

    repository: str
    token: str = field(repr=False)
    poll_interval_seconds: float = 5.0
    timeout_seconds: float = 3600.0
    max_response_bytes: int = 1_000_000
    max_branch_pages: int = 10

    def __post_init__(self) -> None:
        repository = str(self.repository).strip().strip("/")
        parts = repository.split("/")
        if len(parts) != 2 or not all(parts):
            raise ValueError("GitHub physical-device orchestration repository must be owner/name")
        if not str(self.token).strip():
            raise ValueError("GitHub physical-device orchestration requires a dispatch token")
        if not 1 <= float(self.poll_interval_seconds) <= 60:
            raise ValueError("physical-device orchestration poll interval is outside the safe range")
        if not 30 <= float(self.timeout_seconds) <= 7200:
            raise ValueError("physical-device orchestration timeout is outside the safe range")
        if not 10_000 <= int(self.max_response_bytes) <= 5_000_000:
            raise ValueError("physical-device orchestration response bound is invalid")
        if not 1 <= int(self.max_branch_pages) <= 20:
            raise ValueError("physical-device orchestration branch page bound is invalid")
        object.__setattr__(self, "repository", repository)


class GitHubPhysicalDeviceWorkflowOrchestrator:
    """Dispatch exact-revision physical-device workflows without source authority.

    GitHub's workflow_dispatch API accepts a branch/tag ref, not an arbitrary
    unpublished local commit. To preserve exact-revision qualification this
    orchestrator first proves that the candidate is already the exact tip of a
    remote branch. It never creates or updates that branch. It then dispatches
    only the allowlisted iOS/Android workflows, waits for the newly-created run,
    and returns run IDs to the existing independent evidence verifier.
    """

    _WORKFLOWS: Mapping[str, str] = {
        "ios": "ios-physical-device.yml",
        "android": "android-real-device.yml",
    }

    def __init__(self, config: GitHubPhysicalDeviceOrchestrationConfig) -> None:
        self.config = config
        self._opener = request.build_opener(_NoRedirect())

    @property
    def repository(self) -> str:
        return self.config.repository

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, str] | None = None,
        body: Mapping[str, Any] | None = None,
        allow_empty: bool = False,
    ) -> Any:
        suffix = ""
        if query:
            suffix = "?" + parse.urlencode(dict(query))
        payload = None if body is None else json.dumps(dict(body), separators=(",", ":")).encode("utf-8")
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Authorization": f"Bearer {self.config.token}",
            "User-Agent": "Vishnu-Physical-Device-Orchestrator/1",
        }
        if payload is not None:
            headers["Content-Type"] = "application/json"
        req = request.Request(
            f"https://api.github.com{path}{suffix}",
            data=payload,
            method=method,
            headers=headers,
        )
        try:
            with self._opener.open(req, timeout=30) as response:
                raw = response.read(self.config.max_response_bytes + 1)
                if len(raw) > self.config.max_response_bytes:
                    raise WorkflowEvidenceError("GitHub physical-device orchestration response exceeded the safety bound")
        except (error.HTTPError, error.URLError, TimeoutError) as exc:
            code = getattr(exc, "code", None)
            raise WorkflowEvidenceError(
                f"GitHub physical-device orchestration request failed{f' ({code})' if code else ''}"
            ) from exc
        if not raw:
            if allow_empty:
                return None
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise WorkflowEvidenceError("GitHub physical-device orchestration returned malformed JSON") from exc

    @staticmethod
    def _same_revision(left: str, right: str) -> bool:
        return bool(left and right and str(left).strip().lower() == str(right).strip().lower())

    @staticmethod
    def _normalize_preferred_ref(value: str) -> str:
        ref = str(value or "").strip()
        for prefix in ("refs/heads/", "origin/"):
            if ref.startswith(prefix):
                return ref[len(prefix):]
        return ref

    def _remote_candidate_branch(self, candidate_revision: str, *, preferred_ref: str = "") -> str:
        owner, repo = self.repository.split("/", 1)
        matches: list[str] = []
        for page in range(1, self.config.max_branch_pages + 1):
            rows = self._request_json(
                "GET",
                f"/repos/{parse.quote(owner, safe='')}/{parse.quote(repo, safe='')}/branches",
                query={"per_page": "100", "page": str(page)},
            )
            if not isinstance(rows, list):
                raise WorkflowEvidenceError("GitHub branch discovery returned an unexpected payload")
            for row in rows:
                if not isinstance(row, Mapping):
                    continue
                commit = row.get("commit")
                sha = str(commit.get("sha") or "") if isinstance(commit, Mapping) else ""
                name = str(row.get("name") or "").strip()
                if name and self._same_revision(sha, candidate_revision):
                    matches.append(name)
            if len(rows) < 100:
                break
        if not matches:
            raise WorkflowEvidenceError(
                "physical-device dispatch requires the exact candidate to already be published as a remote branch tip; "
                "the engineering authority will not push or create that ref"
            )
        preferred = self._normalize_preferred_ref(preferred_ref)
        if preferred and preferred in matches:
            return preferred
        # Deterministic selection prevents model/caller control over the dispatched ref.
        return sorted(set(matches))[0]

    def _workflow_runs(self, platform: str, branch: str) -> tuple[Mapping[str, Any], ...]:
        owner, repo = self.repository.split("/", 1)
        workflow = self._WORKFLOWS[platform]
        payload = self._request_json(
            "GET",
            f"/repos/{parse.quote(owner, safe='')}/{parse.quote(repo, safe='')}/actions/workflows/{parse.quote(workflow, safe='')}/runs",
            query={"event": "workflow_dispatch", "branch": branch, "per_page": "100"},
        )
        rows = payload.get("workflow_runs") if isinstance(payload, Mapping) else None
        if not isinstance(rows, list):
            raise WorkflowEvidenceError("GitHub workflow run discovery returned an unexpected payload")
        return tuple(row for row in rows if isinstance(row, Mapping))

    def _dispatch(self, platform: str, branch: str) -> None:
        owner, repo = self.repository.split("/", 1)
        workflow = self._WORKFLOWS[platform]
        self._request_json(
            "POST",
            f"/repos/{parse.quote(owner, safe='')}/{parse.quote(repo, safe='')}/actions/workflows/{parse.quote(workflow, safe='')}/dispatches",
            body={"ref": branch},
            allow_empty=True,
        )

    def _wait_for_new_run(
        self,
        *,
        platform: str,
        branch: str,
        candidate_revision: str,
        previous_ids: set[int],
    ) -> PhysicalDeviceWorkflowRun:
        deadline = time.monotonic() + self.config.timeout_seconds
        while time.monotonic() < deadline:
            for row in self._workflow_runs(platform, branch):
                try:
                    run_id = int(row.get("id") or 0)
                except (TypeError, ValueError):
                    continue
                if run_id < 1 or run_id in previous_ids:
                    continue
                if str(row.get("event") or "").lower() != "workflow_dispatch":
                    continue
                if not self._same_revision(str(row.get("head_sha") or ""), candidate_revision):
                    continue
                status = str(row.get("status") or "").lower()
                if status == "completed":
                    # Return even on failure. The existing verifier owns the
                    # completed-success decision and will fail closed.
                    return PhysicalDeviceWorkflowRun(platform=platform, run_id=run_id)
            time.sleep(self.config.poll_interval_seconds)
        raise WorkflowEvidenceError(f"timed out waiting for the dispatched {platform} physical-device workflow")

    def dispatch_required(
        self,
        *,
        spec: EngineeringSpec,
        candidate_revision: str,
        preferred_ref: str = "",
    ) -> tuple[PhysicalDeviceWorkflowRun, ...]:
        candidate = str(candidate_revision).strip()
        if len(candidate) != 40 or any(char not in "0123456789abcdefABCDEF" for char in candidate):
            raise WorkflowEvidenceError("physical-device dispatch requires a full 40-character candidate SHA")
        required = GitHubPhysicalDeviceEvidenceVerifier.required_platforms(spec)
        branch = self._remote_candidate_branch(candidate, preferred_ref=preferred_ref)
        results: list[PhysicalDeviceWorkflowRun] = []
        for platform in required:
            before = {
                int(row.get("id") or 0)
                for row in self._workflow_runs(platform, branch)
                if str(row.get("id") or "").isdigit()
            }
            self._dispatch(platform, branch)
            results.append(
                self._wait_for_new_run(
                    platform=platform,
                    branch=branch,
                    candidate_revision=candidate,
                    previous_ids=before,
                )
            )
        return tuple(results)


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise WorkflowEvidenceError("GitHub physical-device orchestration redirects are not accepted")
