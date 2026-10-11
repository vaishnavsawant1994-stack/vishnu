from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Mapping


_SHA = re.compile(r"^[0-9a-fA-F]{40,64}$")
_BRANCH = re.compile(r"^[A-Za-z0-9._/-]{1,180}$")


@dataclass(frozen=True)
class CandidatePublicationPlan:
    id: str
    work_order_id: str
    attempt_id: str
    engineering_spec_id: str
    repository: str
    base_revision: str
    candidate_revision: str
    local_branch: str
    remote_branch: str
    base_branch: str
    changed_paths: tuple[str, ...]
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.work_order_id.strip() or not self.attempt_id.strip():
            raise ValueError("candidate publication identity is required")
        parts = self.repository.strip().split("/")
        if len(parts) != 2 or not all(parts):
            raise ValueError("candidate publication repository must be owner/name")
        if not _SHA.fullmatch(self.base_revision) or not _SHA.fullmatch(self.candidate_revision):
            raise ValueError("candidate publication revisions must be full Git commit ids")
        for label, value in (("local_branch", self.local_branch), ("remote_branch", self.remote_branch), ("base_branch", self.base_branch)):
            if not _BRANCH.fullmatch(value) or ".." in value or value.startswith(("/", "-")) or value.endswith("/"):
                raise ValueError(f"invalid candidate publication {label}")
        if self.remote_branch == self.base_branch:
            raise ValueError("candidate publication branch must not be the base branch")
        if not self.remote_branch.startswith("vishnu/candidate/"):
            raise ValueError("candidate publication branch must use the governed vishnu/candidate prefix")
        if not self.changed_paths:
            raise ValueError("candidate publication requires changed source paths")

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "work_order_id": self.work_order_id,
            "attempt_id": self.attempt_id,
            "engineering_spec_id": self.engineering_spec_id,
            "repository": self.repository,
            "base_revision": self.base_revision,
            "candidate_revision": self.candidate_revision,
            "local_branch": self.local_branch,
            "remote_branch": self.remote_branch,
            "base_branch": self.base_branch,
            "changed_paths": list(self.changed_paths),
            "metadata": dict(self.metadata),
            "force_push_authority": False,
            "merge_authority": False,
            "deploy_authority": False,
            "release_authority": False,
            "body_activation_authority": False,
        }


@dataclass(frozen=True)
class CandidatePublicationResult:
    plan: CandidatePublicationPlan
    remote_revision: str
    branch_url: str
    pull_request_number: int
    pull_request_url: str
    draft: bool
    reused_branch: bool = False
    reused_pull_request: bool = False

    def __post_init__(self) -> None:
        if self.remote_revision != self.plan.candidate_revision:
            raise ValueError("published remote revision is not the qualified candidate")
        if self.pull_request_number < 1 or not self.pull_request_url.startswith("https://github.com/"):
            raise ValueError("candidate publication requires a GitHub draft pull request")
        if not self.draft:
            raise ValueError("candidate publication may only create or reuse a draft pull request")

    def to_dict(self) -> dict[str, object]:
        return {
            "plan": self.plan.to_dict(),
            "remote_revision": self.remote_revision,
            "branch_url": self.branch_url,
            "pull_request_number": self.pull_request_number,
            "pull_request_url": self.pull_request_url,
            "draft": self.draft,
            "reused_branch": self.reused_branch,
            "reused_pull_request": self.reused_pull_request,
            "merge_authority": False,
            "deploy_authority": False,
        }
