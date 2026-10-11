from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from urllib import error, parse, request

from .contracts import EngineeringSpec
from .workflow_evidence import (
    GitHubPhysicalDeviceEvidenceVerifier,
    PhysicalDeviceWorkflowRun,
    WorkflowEvidenceError,
)


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise WorkflowEvidenceError("GitHub physical-device automation redirects are not accepted")


@dataclass(frozen=True)
class PhysicalDeviceAutomationResult:
    candidate_revision: str
    remote_branch: str
    runs: tuple[PhysicalDeviceWorkflowRun, ...]
    dispatched: bool


class GitHubPhysicalDeviceWorkflowCoordinator:
    """Coordinate real-device workflows without gaining source-control authority.

    The coordinator may discover already-completed workflow_dispatch runs or ask
    GitHub Actions to dispatch the allowlisted iOS/Android workflows. It never
    pushes a branch, creates a ref, merges code, or accepts a client claim that a
    gate passed. Dispatch is allowed only when GitHub proves an existing remote
    branch already points at the exact engineering candidate revision.

    The existing GitHubPhysicalDeviceEvidenceVerifier remains the trust boundary:
    every discovered or newly dispatched run is re-verified against repository,
    SHA, event, workflow path, conclusion and unexpired artifact metadata before
    it may be persisted by EngineeringCandidateFinalizer.
    """

    def __init__(
        self,
        verifier: GitHubPhysicalDeviceEvidenceVerifier,
        *,
        poll_interval_seconds: float = 5.0,
        dispatch_timeout_seconds: float = 3_600.0,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        if poll_interval_seconds <= 0 or dispatch_timeout_seconds <= 0:
            raise ValueError("physical-device automation polling values must be positive")
        self.verifier = verifier
        self.poll_interval_seconds = min(float(poll_interval_seconds), 60.0)
        self.dispatch_timeout_seconds = min(float(dispatch_timeout_seconds), 7_200.0)
        self._sleep = sleep_fn
        self._opener = request.build_opener(_NoRedirect())

    @property
    def repository(self) -> str:
        return self.verifier.config.repository

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, str] | None = None,
        body: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        suffix = ""
        if query:
            suffix = "?" + parse.urlencode(dict(query))
        payload = None if body is None else json.dumps(dict(body), separators=(",", ":")).encode("utf-8")
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Vishnu-Physical-Device-Automation/1",
        }
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if self.verifier.config.token:
            headers["Authorization"] = f"Bearer {self.verifier.config.token}"
        req = request.Request(
            f"https://api.github.com{path}{suffix}",
            data=payload,
            method=str(method).upper(),
            headers=headers,
        )
        try:
            with self._opener.open(req, timeout=self.verifier.config.timeout_seconds) as response:
                raw = response.read(self.verifier.config.max_response_bytes + 1)
                if len(raw) > self.verifier.config.max_response_bytes:
                    raise WorkflowEvidenceError("GitHub physical-device automation response exceeded the safety bound")
                if not raw:
                    return {}
                value = json.loads(raw.decode("utf-8"))
        except (error.HTTPError, error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            code = getattr(exc, "code", None)
            raise WorkflowEvidenceError(
                f"GitHub physical-device automation request failed{f' ({code})' if code else ''}"
            ) from exc
        if not isinstance(value, dict):
            raise WorkflowEvidenceError("GitHub physical-device automation returned an unexpected payload")
        return value

    @staticmethod
    def _run_id(row: Mapping[str, Any]) -> int:
        try:
            return int(row.get("id") or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _repo_name(row: Mapping[str, Any]) -> str:
        repository = row.get("repository")
        if isinstance(repository, Mapping):
            return str(repository.get("full_name") or "").strip()
        return ""

    def _candidate_runs(self, candidate_revision: str) -> tuple[Mapping[str, Any], ...]:
        owner, repo = self.repository.split("/", 1)
        payload = self._request_json(
            "GET",
            f"/repos/{parse.quote(owner, safe='')}/{parse.quote(repo, safe='')}/actions/runs",
            query={
                "head_sha": str(candidate_revision).strip(),
                "event": "workflow_dispatch",
                "per_page": "100",
            },
        )
        rows = payload.get("workflow_runs")
        if not isinstance(rows, list):
            raise WorkflowEvidenceError("GitHub workflow-run discovery payload is malformed")
        return tuple(row for row in rows if isinstance(row, Mapping))

    def _matches_platform(
        self,
        row: Mapping[str, Any],
        *,
        platform: str,
        candidate_revision: str,
    ) -> bool:
        workflow_path, _artifact_name = self.verifier._WORKFLOWS[platform]
        return (
            self._run_id(row) > 0
            and str(row.get("head_sha") or "").strip() == str(candidate_revision).strip()
            and str(row.get("event") or "").strip().lower() == "workflow_dispatch"
            and str(row.get("path") or "").strip() == workflow_path
            and (not self._repo_name(row) or self._repo_name(row) == self.repository)
        )

    def discover_runs(
        self,
        *,
        spec: EngineeringSpec,
        candidate_revision: str,
    ) -> tuple[PhysicalDeviceWorkflowRun, ...]:
        rows = self._candidate_runs(candidate_revision)
        discovered: list[PhysicalDeviceWorkflowRun] = []
        for platform in self.verifier.required_platforms(spec):
            candidates = [
                row
                for row in rows
                if self._matches_platform(row, platform=platform, candidate_revision=candidate_revision)
                and str(row.get("status") or "").strip().lower() == "completed"
                and str(row.get("conclusion") or "").strip().lower() == "success"
            ]
            if not candidates:
                raise WorkflowEvidenceError(
                    f"no successful exact-revision physical-device workflow run was found for {platform}"
                )
            selected = max(candidates, key=self._run_id)
            discovered.append(PhysicalDeviceWorkflowRun(platform=platform, run_id=self._run_id(selected)))
        runs = tuple(discovered)
        observation = self.verifier.verify(spec=spec, candidate_revision=candidate_revision, runs=runs)
        if not observation.passed:
            raise WorkflowEvidenceError(observation.summary or "physical-device evidence discovery did not qualify")
        return runs

    @staticmethod
    def _normalize_branch(remote_branch: str) -> str:
        branch = str(remote_branch or "").strip()
        if branch.startswith("refs/heads/"):
            branch = branch[len("refs/heads/") :]
        if not branch or len(branch) > 240:
            raise WorkflowEvidenceError("an existing remote branch is required for physical-device dispatch")
        if branch.startswith("/") or branch.endswith("/") or branch.endswith("."):
            raise WorkflowEvidenceError("remote branch is not a valid Git branch name")
        if ".." in branch or "@{" in branch or "//" in branch:
            raise WorkflowEvidenceError("remote branch is not a valid Git branch name")
        if any(char in branch for char in ("~", "^", ":", "?", "*", "[", "\\", "\n", "\r", "\t", " ")):
            raise WorkflowEvidenceError("remote branch is not a valid Git branch name")
        return branch

    def require_exact_remote_branch(self, *, remote_branch: str, candidate_revision: str) -> str:
        branch = self._normalize_branch(remote_branch)
        owner, repo = self.repository.split("/", 1)
        payload = self._request_json(
            "GET",
            f"/repos/{parse.quote(owner, safe='')}/{parse.quote(repo, safe='')}/git/ref/heads/{parse.quote(branch, safe='')}",
        )
        obj = payload.get("object")
        if not isinstance(obj, Mapping):
            raise WorkflowEvidenceError("GitHub did not return an object for the remote engineering branch")
        if str(obj.get("type") or "").strip().lower() != "commit":
            raise WorkflowEvidenceError("remote engineering branch does not directly resolve to a commit")
        if str(obj.get("sha") or "").strip() != str(candidate_revision).strip():
            raise WorkflowEvidenceError("remote engineering branch does not point to the exact candidate revision")
        return branch

    def _dispatch_workflow(self, *, platform: str, remote_branch: str) -> None:
        if not self.verifier.config.token:
            raise WorkflowEvidenceError("GitHub token is required for physical-device workflow dispatch")
        owner, repo = self.repository.split("/", 1)
        workflow_path, _artifact_name = self.verifier._WORKFLOWS[platform]
        workflow_name = workflow_path.rsplit("/", 1)[-1]
        self._request_json(
            "POST",
            f"/repos/{parse.quote(owner, safe='')}/{parse.quote(repo, safe='')}/actions/workflows/{parse.quote(workflow_name, safe='')}/dispatches",
            body={"ref": remote_branch},
        )

    def dispatch_and_wait(
        self,
        *,
        spec: EngineeringSpec,
        candidate_revision: str,
        remote_branch: str,
    ) -> PhysicalDeviceAutomationResult:
        branch = self.require_exact_remote_branch(
            remote_branch=remote_branch,
            candidate_revision=candidate_revision,
        )
        required = self.verifier.required_platforms(spec)
        before = {self._run_id(row) for row in self._candidate_runs(candidate_revision)}
        for platform in required:
            self._dispatch_workflow(platform=platform, remote_branch=branch)

        deadline = time.monotonic() + self.dispatch_timeout_seconds
        completed: dict[str, PhysicalDeviceWorkflowRun] = {}
        while time.monotonic() < deadline:
            rows = self._candidate_runs(candidate_revision)
            for platform in required:
                if platform in completed:
                    continue
                matches = [
                    row
                    for row in rows
                    if self._run_id(row) not in before
                    and self._matches_platform(row, platform=platform, candidate_revision=candidate_revision)
                ]
                if not matches:
                    continue
                selected = max(matches, key=self._run_id)
                status = str(selected.get("status") or "").strip().lower()
                conclusion = str(selected.get("conclusion") or "").strip().lower()
                if status != "completed":
                    continue
                if conclusion != "success":
                    raise WorkflowEvidenceError(
                        f"physical-device workflow failed for {platform}: {conclusion or 'unknown'}"
                    )
                completed[platform] = PhysicalDeviceWorkflowRun(platform, self._run_id(selected))
            if len(completed) == len(required):
                runs = tuple(completed[platform] for platform in required)
                observation = self.verifier.verify(
                    spec=spec,
                    candidate_revision=candidate_revision,
                    runs=runs,
                )
                if not observation.passed:
                    raise WorkflowEvidenceError(
                        observation.summary or "dispatched physical-device workflows did not qualify"
                    )
                return PhysicalDeviceAutomationResult(
                    candidate_revision=str(candidate_revision),
                    remote_branch=branch,
                    runs=runs,
                    dispatched=True,
                )
            self._sleep(self.poll_interval_seconds)
        raise WorkflowEvidenceError("physical-device workflows did not complete within the bounded dispatch window")
