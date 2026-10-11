from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence
from urllib import error, parse, request

from future_intelligence.work_orchestration.repository import (
    LocalGitRepositoryProvider,
    RepositoryWorkspaceSession,
)

from .contracts import CandidatePublicationPlan, CandidatePublicationResult


class CandidatePublicationError(RuntimeError):
    pass


_REMOTE_NAME = re.compile(r"^[A-Za-z0-9._-]{1,80}$")
_BRANCH = re.compile(r"^[A-Za-z0-9._/-]{1,180}$")


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise CandidatePublicationError("GitHub candidate publication redirects are not accepted")


@dataclass(frozen=True)
class GitHubCandidatePublicationConfig:
    repository: str
    token: str = field(default="", repr=False)
    remote_name: str = "origin"
    base_branch: str = "main"
    timeout_seconds: float = 30.0
    max_response_bytes: int = 1_000_000

    def __post_init__(self) -> None:
        repository = str(self.repository or "").strip().strip("/")
        parts = repository.split("/")
        if len(parts) != 2 or not all(parts):
            raise ValueError("candidate publication repository must be owner/name")
        if not _REMOTE_NAME.fullmatch(str(self.remote_name or "")):
            raise ValueError("candidate publication remote name is invalid")
        branch = str(self.base_branch or "").strip()
        if not _BRANCH.fullmatch(branch) or ".." in branch or branch.startswith(("/", "-")):
            raise ValueError("candidate publication base branch is invalid")
        if branch.startswith("vishnu/candidate/"):
            raise ValueError("candidate publication base branch cannot use the candidate prefix")
        if self.timeout_seconds <= 0:
            raise ValueError("candidate publication timeout must be positive")
        if not 10_000 <= int(self.max_response_bytes) <= 5_000_000:
            raise ValueError("candidate publication response bound is invalid")
        object.__setattr__(self, "repository", repository)
        object.__setattr__(self, "base_branch", branch)


class GitHubDraftCandidatePublisher:
    """Separate owner-approved authority for branch publication + draft PR creation.

    This provider has deliberately narrow remote authority. It can publish one
    exact already-qualified commit to a deterministic `vishnu/candidate/*`
    branch without force and create/reuse a draft pull request to one configured
    base branch. It exposes no merge, tag, release, deploy, delete-branch, or
    force-push operation.
    """

    def __init__(
        self,
        *,
        repository_provider: LocalGitRepositoryProvider,
        config: GitHubCandidatePublicationConfig,
    ) -> None:
        if repository_provider.repository != config.repository:
            raise ValueError("candidate publisher repository does not match engineering repository")
        self.repository_provider = repository_provider
        self.config = config
        self._opener = request.build_opener(_NoRedirect())

    def _git(self, args: Sequence[str], *, cwd=None) -> str:
        process = subprocess.run(
            [self.repository_provider.git_binary, *map(str, args)],
            cwd=str(cwd) if cwd is not None else None,
            check=False,
            capture_output=True,
            text=True,
            timeout=max(30.0, min(float(self.config.timeout_seconds) * 4.0, 180.0)),
        )
        if process.returncode != 0:
            details = (process.stderr or process.stdout or "git publication command failed").strip()
            raise CandidatePublicationError(details[:2000])
        return process.stdout

    @staticmethod
    def _repository_from_remote_url(value: str) -> str:
        raw = str(value or "").strip()
        if raw.startswith("git@github.com:"):
            path = raw[len("git@github.com:") :]
        elif raw.startswith("ssh://git@github.com/"):
            path = raw[len("ssh://git@github.com/") :]
        else:
            parsed = parse.urlparse(raw)
            if parsed.scheme != "https" or parsed.hostname != "github.com" or parsed.username or parsed.password:
                return ""
            path = parsed.path.lstrip("/")
        if path.endswith(".git"):
            path = path[:-4]
        parts = path.strip("/").split("/")
        return "/".join(parts) if len(parts) == 2 and all(parts) else ""

    def _assert_remote_identity(self, session: RepositoryWorkspaceSession) -> None:
        remote_url = self._git(
            ("remote", "get-url", self.config.remote_name),
            cwd=session.local_path,
        ).strip()
        if self._repository_from_remote_url(remote_url) != self.config.repository:
            raise CandidatePublicationError("configured Git remote does not match the governed repository")

    def _remote_branch_revision(self, session: RepositoryWorkspaceSession, branch: str) -> str:
        raw = self._git(
            ("ls-remote", "--heads", self.config.remote_name, f"refs/heads/{branch}"),
            cwd=session.local_path,
        ).strip()
        if not raw:
            return ""
        rows = [line.split() for line in raw.splitlines() if line.strip()]
        matches = [parts[0] for parts in rows if len(parts) >= 2 and parts[1] == f"refs/heads/{branch}"]
        if len(matches) != 1:
            raise CandidatePublicationError("remote candidate branch identity is ambiguous")
        return str(matches[0]).strip()

    def publish_branch(
        self,
        plan: CandidatePublicationPlan,
        *,
        session: RepositoryWorkspaceSession,
    ) -> tuple[str, str, bool]:
        if plan.repository != self.config.repository or session.repository != self.config.repository:
            raise CandidatePublicationError("candidate publication repository mismatch")
        if plan.base_branch != self.config.base_branch:
            raise CandidatePublicationError("candidate publication base branch drifted from provider policy")
        if plan.local_branch != session.branch_ref:
            raise CandidatePublicationError("candidate publication local branch drifted from workspace metadata")
        if not plan.remote_branch.startswith("vishnu/candidate/") or plan.remote_branch == plan.base_branch:
            raise CandidatePublicationError("candidate publication remote branch is outside the governed prefix")
        status = self.repository_provider.status(session)
        if status.dirty:
            raise CandidatePublicationError("candidate workspace is dirty and cannot be published")
        if status.revision != plan.candidate_revision:
            raise CandidatePublicationError("candidate workspace revision drifted before publication")
        self._assert_remote_identity(session)
        local_revision = self._git(
            ("rev-parse", "--verify", f"{plan.candidate_revision}^{{commit}}"),
            cwd=session.local_path,
        ).strip()
        if local_revision != plan.candidate_revision:
            raise CandidatePublicationError("local repository did not prove the exact qualified candidate")
        existing = self._remote_branch_revision(session, plan.remote_branch)
        if existing:
            if existing != plan.candidate_revision:
                raise CandidatePublicationError("remote candidate branch already exists at a different revision")
            reused = True
        else:
            # No force flag, no ref deletion, no base-branch target. The exact
            # candidate commit is pushed to one new governed branch only.
            self._git(
                (
                    "push",
                    "--porcelain",
                    self.config.remote_name,
                    f"{plan.candidate_revision}:refs/heads/{plan.remote_branch}",
                ),
                cwd=session.local_path,
            )
            reused = False
        remote_revision = self._remote_branch_revision(session, plan.remote_branch)
        if remote_revision != plan.candidate_revision:
            raise CandidatePublicationError("remote branch did not prove the exact qualified candidate revision")
        branch_url = f"https://github.com/{self.config.repository}/tree/{parse.quote(plan.remote_branch, safe='/')}"
        return remote_revision, branch_url, reused

    def _github_json(
        self,
        method: str,
        path: str,
        body: Mapping[str, object] | None = None,
        *,
        query: Mapping[str, str] | None = None,
    ) -> Any:
        if not self.config.token:
            raise CandidatePublicationError("GitHub candidate publication token is not configured")
        suffix = "?" + parse.urlencode(dict(query)) if query else ""
        payload = None if body is None else json.dumps(dict(body), separators=(",", ":")).encode("utf-8")
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Vishnu-Candidate-Publication/1",
            "Authorization": f"Bearer {self.config.token}",
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
            with self._opener.open(req, timeout=self.config.timeout_seconds) as response:
                raw = response.read(self.config.max_response_bytes + 1)
                if len(raw) > self.config.max_response_bytes:
                    raise CandidatePublicationError("GitHub candidate publication response exceeded the safety bound")
                value = json.loads(raw.decode("utf-8")) if raw else {}
        except (error.HTTPError, error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            code = getattr(exc, "code", None)
            raise CandidatePublicationError(
                f"GitHub candidate publication request failed{f' ({code})' if code else ''}"
            ) from exc
        return value

    def ensure_draft_pull_request(
        self,
        plan: CandidatePublicationPlan,
        *,
        title: str,
        body: str,
    ) -> tuple[int, str, bool]:
        owner, repo = self.config.repository.split("/", 1)
        pulls_path = f"/repos/{parse.quote(owner, safe='')}/{parse.quote(repo, safe='')}/pulls"
        existing = self._github_json(
            "GET",
            pulls_path,
            query={
                "state": "open",
                "head": f"{owner}:{plan.remote_branch}",
                "base": plan.base_branch,
                "per_page": "20",
            },
        )
        if not isinstance(existing, list):
            raise CandidatePublicationError("GitHub pull request lookup returned an unexpected payload")
        if existing:
            if len(existing) != 1 or not isinstance(existing[0], Mapping):
                raise CandidatePublicationError("candidate publication found ambiguous open pull requests")
            row = existing[0]
            if not bool(row.get("draft", False)):
                raise CandidatePublicationError("existing candidate pull request is no longer a draft")
            head = row.get("head")
            head_sha = str(head.get("sha") or "") if isinstance(head, Mapping) else ""
            if head_sha and head_sha != plan.candidate_revision:
                raise CandidatePublicationError("existing draft pull request head drifted from the qualified candidate")
            number = int(row.get("number") or 0)
            url = str(row.get("html_url") or "")
            if number < 1 or not url.startswith(f"https://github.com/{self.config.repository}/pull/"):
                raise CandidatePublicationError("existing draft pull request identity is invalid")
            return number, url, True
        created = self._github_json(
            "POST",
            pulls_path,
            {
                "title": str(title or "Qualified Vishnu candidate")[:240],
                "head": plan.remote_branch,
                "base": plan.base_branch,
                "body": str(body or "")[:60_000],
                "draft": True,
                "maintainer_can_modify": True,
            },
        )
        if not isinstance(created, Mapping):
            raise CandidatePublicationError("GitHub draft pull request creation returned an unexpected payload")
        if not bool(created.get("draft", False)):
            raise CandidatePublicationError("GitHub did not create the candidate pull request as a draft")
        head = created.get("head")
        head_sha = str(head.get("sha") or "") if isinstance(head, Mapping) else ""
        if head_sha and head_sha != plan.candidate_revision:
            raise CandidatePublicationError("created draft pull request head does not match the qualified candidate")
        number = int(created.get("number") or 0)
        url = str(created.get("html_url") or "")
        if number < 1 or not url.startswith(f"https://github.com/{self.config.repository}/pull/"):
            raise CandidatePublicationError("created draft pull request identity is invalid")
        return number, url, False

    def publish(
        self,
        plan: CandidatePublicationPlan,
        *,
        session: RepositoryWorkspaceSession,
        title: str,
        body: str,
    ) -> CandidatePublicationResult:
        remote_revision, branch_url, reused_branch = self.publish_branch(plan, session=session)
        number, pr_url, reused_pr = self.ensure_draft_pull_request(plan, title=title, body=body)
        return CandidatePublicationResult(
            plan=plan,
            remote_revision=remote_revision,
            branch_url=branch_url,
            pull_request_number=number,
            pull_request_url=pr_url,
            draft=True,
            reused_branch=reused_branch,
            reused_pull_request=reused_pr,
        )
