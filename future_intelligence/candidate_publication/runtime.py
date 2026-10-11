from __future__ import annotations

import os

from future_intelligence.work_orchestration.repository import LocalGitRepositoryProvider

from .provider import GitHubCandidatePublicationConfig, GitHubDraftCandidatePublisher
from .service import GovernedCandidatePublicationService


def candidate_publication_enabled() -> bool:
    return str(os.environ.get("VISHNU_CANDIDATE_PUBLICATION_ENABLED", "")).strip().lower() in {
        "1", "true", "yes", "on"
    }


def build_candidate_publication_service(*, engineering_runtime, engineering_finalizer):
    """Build the manual-only publication authority when explicitly enabled.

    There is deliberately no permissive partial configuration: publication is
    absent unless the owner explicitly enables it and supplies a GitHub API
    token. Git branch publication still relies on the configured local Git
    remote credentials; the token is used only for draft PR lookup/creation.
    """
    if not candidate_publication_enabled():
        return None
    if engineering_runtime is None or engineering_finalizer is None:
        raise RuntimeError("candidate publication requires governed engineering and final qualification")
    provider = getattr(engineering_runtime, "repository_provider", None)
    if not isinstance(provider, LocalGitRepositoryProvider):
        raise RuntimeError("candidate publication requires the isolated local Git repository provider")
    token = str(os.environ.get("VISHNU_CANDIDATE_GITHUB_TOKEN", "") or "").strip()
    if not token:
        raise RuntimeError("candidate publication is enabled but VISHNU_CANDIDATE_GITHUB_TOKEN is missing")
    config = GitHubCandidatePublicationConfig(
        repository=provider.repository,
        token=token,
        remote_name=str(os.environ.get("VISHNU_CANDIDATE_GIT_REMOTE", "origin") or "origin").strip(),
        base_branch=str(os.environ.get("VISHNU_CANDIDATE_PR_BASE", "main") or "main").strip(),
    )
    publisher = GitHubDraftCandidatePublisher(repository_provider=provider, config=config)
    return GovernedCandidatePublicationService(
        finalizer=engineering_finalizer,
        publisher=publisher,
    )


__all__ = ["build_candidate_publication_service", "candidate_publication_enabled"]
