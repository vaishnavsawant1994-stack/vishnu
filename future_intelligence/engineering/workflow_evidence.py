from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping
from urllib import error, parse, request

from .contracts import EngineeringSpec
from .qualification import VerificationObservation
from .verification import observation_from_dict, observation_to_dict


class WorkflowEvidenceError(RuntimeError):
    pass


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise WorkflowEvidenceError("GitHub workflow evidence redirects are not accepted")


@dataclass(frozen=True)
class PhysicalDeviceWorkflowRun:
    platform: str
    run_id: int

    def __post_init__(self) -> None:
        platform = str(self.platform).strip().lower()
        if platform not in {"ios", "android"}:
            raise ValueError("physical-device platform must be ios or android")
        if int(self.run_id) < 1:
            raise ValueError("GitHub workflow run_id must be positive")
        object.__setattr__(self, "platform", platform)
        object.__setattr__(self, "run_id", int(self.run_id))

    def to_dict(self) -> dict[str, object]:
        return {"platform": self.platform, "run_id": self.run_id}


@dataclass(frozen=True)
class GitHubWorkflowEvidenceConfig:
    repository: str
    token: str = field(default="", repr=False)
    timeout_seconds: float = 20.0
    max_response_bytes: int = 1_000_000

    def __post_init__(self) -> None:
        repository = str(self.repository).strip().strip("/")
        parts = repository.split("/")
        if len(parts) != 2 or not all(parts):
            raise ValueError("GitHub workflow evidence repository must be owner/name")
        if self.timeout_seconds <= 0:
            raise ValueError("GitHub workflow evidence timeout must be positive")
        if not 10_000 <= self.max_response_bytes <= 5_000_000:
            raise ValueError("GitHub workflow evidence response bound is invalid")
        object.__setattr__(self, "repository", repository)


class GitHubPhysicalDeviceEvidenceVerifier:
    """Independently verify revision-bound real-device evidence in GitHub Actions.

    A client may supply workflow run IDs, but it cannot supply the facts that make
    them trusted. Vishnu re-reads GitHub's authoritative run and artifact metadata
    and requires the exact repository, exact candidate SHA, completed-success
    conclusion, allowlisted workflow path, workflow_dispatch event and expected
    unexpired evidence artifact.
    """

    _WORKFLOWS: Mapping[str, tuple[str, str]] = {
        "ios": (".github/workflows/ios-physical-device.yml", "iphone-physical-evidence"),
        "android": (".github/workflows/android-real-device.yml", "physical-android-evidence"),
    }

    def __init__(self, config: GitHubWorkflowEvidenceConfig) -> None:
        self.config = config
        self._opener = request.build_opener(_NoRedirect())

    @staticmethod
    def required_platforms(spec: EngineeringSpec) -> tuple[str, ...]:
        metadata = dict(spec.metadata or {})
        configured = metadata.get("physical_device_platforms")
        if isinstance(configured, str):
            configured = (configured,)
        if isinstance(configured, (list, tuple)):
            normalized = tuple(dict.fromkeys(str(item).strip().lower() for item in configured if str(item).strip()))
            if normalized:
                if any(item not in {"ios", "android"} for item in normalized):
                    raise ValueError("physical_device_platforms contains an unsupported platform")
                return normalized
        surfaces = tuple(str(item).lower() for item in spec.affected_surfaces)
        selected = []
        if any("ios" in item or "iphone" in item or "ipad" in item for item in surfaces):
            selected.append("ios")
        if any("android" in item for item in surfaces):
            selected.append("android")
        # Cross-platform or unspecified physical-device qualification defaults to
        # proving both native lanes, never to silently choosing the easier one.
        return tuple(selected) if selected else ("ios", "android")

    def _get_json(self, path: str, *, query: Mapping[str, str] | None = None) -> dict[str, Any]:
        suffix = ""
        if query:
            suffix = "?" + parse.urlencode(dict(query))
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Vishnu-Qualification-Evidence/1",
        }
        if self.config.token:
            headers["Authorization"] = f"Bearer {self.config.token}"
        req = request.Request(f"https://api.github.com{path}{suffix}", method="GET", headers=headers)
        try:
            with self._opener.open(req, timeout=self.config.timeout_seconds) as response:
                raw = response.read(self.config.max_response_bytes + 1)
                if len(raw) > self.config.max_response_bytes:
                    raise WorkflowEvidenceError("GitHub workflow evidence response exceeded the safety bound")
                value = json.loads(raw.decode("utf-8")) if raw else {}
        except (error.HTTPError, error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            code = getattr(exc, "code", None)
            raise WorkflowEvidenceError(
                f"GitHub workflow evidence request failed{f' ({code})' if code else ''}"
            ) from exc
        if not isinstance(value, dict):
            raise WorkflowEvidenceError("GitHub workflow evidence returned an unexpected payload")
        return value

    @staticmethod
    def _repo_name(run: Mapping[str, Any]) -> str:
        repository = run.get("repository")
        if isinstance(repository, Mapping) and repository.get("full_name"):
            return str(repository["full_name"]).strip()
        head_repository = run.get("head_repository")
        if isinstance(head_repository, Mapping) and head_repository.get("full_name"):
            return str(head_repository["full_name"]).strip()
        return ""

    def _verify_one(self, candidate_revision: str, item: PhysicalDeviceWorkflowRun) -> tuple[str, tuple[str, ...], dict[str, object]]:
        workflow_path, artifact_name = self._WORKFLOWS[item.platform]
        owner, repo = self.config.repository.split("/", 1)
        run = self._get_json(f"/repos/{parse.quote(owner, safe='')}/{parse.quote(repo, safe='')}/actions/runs/{item.run_id}")
        if self._repo_name(run) != self.config.repository:
            raise WorkflowEvidenceError("physical-device workflow run belongs to a different repository")
        if str(run.get("head_sha") or "").strip() != str(candidate_revision).strip():
            raise WorkflowEvidenceError("physical-device workflow run is not bound to the candidate revision")
        if str(run.get("status") or "").lower() != "completed" or str(run.get("conclusion") or "").lower() != "success":
            raise WorkflowEvidenceError("physical-device workflow run did not complete successfully")
        if str(run.get("event") or "").lower() != "workflow_dispatch":
            raise WorkflowEvidenceError("physical-device evidence must come from the dispatch-only real-device workflow")
        if str(run.get("path") or "").strip() != workflow_path:
            raise WorkflowEvidenceError("physical-device workflow path is not allowlisted")
        artifacts = self._get_json(
            f"/repos/{parse.quote(owner, safe='')}/{parse.quote(repo, safe='')}/actions/runs/{item.run_id}/artifacts",
            query={"per_page": "100"},
        )
        rows = artifacts.get("artifacts")
        if not isinstance(rows, list):
            raise WorkflowEvidenceError("physical-device workflow artifact metadata is malformed")
        match = next(
            (
                row for row in rows
                if isinstance(row, Mapping)
                and str(row.get("name") or "") == artifact_name
                and not bool(row.get("expired", False))
            ),
            None,
        )
        if match is None:
            raise WorkflowEvidenceError(f"physical-device evidence artifact is missing or expired: {artifact_name}")
        run_url = str(run.get("html_url") or "").strip()
        artifact_url = str(match.get("archive_download_url") or match.get("url") or "").strip()
        evidence = tuple(item for item in (run_url, artifact_url) if item)
        if len(evidence) < 2:
            raise WorkflowEvidenceError("physical-device run/artifact evidence references are incomplete")
        metadata: dict[str, object] = {
            "platform": item.platform,
            "run_id": item.run_id,
            "workflow_path": workflow_path,
            "artifact_name": artifact_name,
            "candidate_revision": str(candidate_revision),
            "trusted_source": "github-actions",
            "verified_by": "github-physical-device-evidence-verifier",
        }
        return item.platform, evidence, metadata

    def verify(
        self,
        *,
        spec: EngineeringSpec,
        candidate_revision: str,
        runs: Iterable[PhysicalDeviceWorkflowRun],
    ) -> VerificationObservation:
        required = self.required_platforms(spec)
        supplied = tuple(runs)
        by_platform: dict[str, PhysicalDeviceWorkflowRun] = {}
        for item in supplied:
            if item.platform in by_platform:
                raise WorkflowEvidenceError(f"duplicate physical-device workflow run for {item.platform}")
            by_platform[item.platform] = item
        missing = tuple(item for item in required if item not in by_platform)
        if missing:
            return VerificationObservation(
                gate="physical_device",
                passed=False,
                summary="missing required physical-device workflow evidence: " + ", ".join(missing),
                evidence=(),
                metadata={
                    "candidate_revision": str(candidate_revision),
                    "required_platforms": list(required),
                    "verified_platforms": [],
                    "trusted_source": "github-actions",
                    "verified_by": "github-physical-device-evidence-verifier",
                },
            )
        evidence: list[str] = []
        details = []
        for platform in required:
            verified_platform, refs, metadata = self._verify_one(candidate_revision, by_platform[platform])
            evidence.extend(refs)
            details.append(metadata)
            if verified_platform != platform:  # pragma: no cover - defensive
                raise WorkflowEvidenceError("physical-device verifier platform mismatch")
        return VerificationObservation(
            gate="physical_device",
            passed=True,
            summary="verified exact-revision physical-device qualification: " + ", ".join(required),
            evidence=tuple(dict.fromkeys(evidence)),
            metadata={
                "candidate_revision": str(candidate_revision),
                "required_platforms": list(required),
                "verified_platforms": list(required),
                "runs": details,
                "trusted_source": "github-actions",
                "verified_by": "github-physical-device-evidence-verifier",
            },
        )


def record_trusted_external_observation(*, work_store, work_order_id: str, attempt_id: str, observation: VerificationObservation) -> None:
    metadata = dict(observation.metadata or {})
    if metadata.get("trusted_source") != "github-actions" or metadata.get("verified_by") != "github-physical-device-evidence-verifier":
        raise PermissionError("external qualification observation did not come from the trusted workflow verifier")
    work_store.append_work_event(
        str(work_order_id),
        "engineering.external_evidence.verified",
        {"observation": observation_to_dict(observation)},
        attempt_id=str(attempt_id),
    )


def load_trusted_external_observations(
    *,
    work_store,
    work_order_id: str,
    attempt_id: str,
    candidate_revision: str,
) -> tuple[VerificationObservation, ...]:
    """Load only observations previously written by a trusted verifier.

    Work events are durable/auditable and attempt-bound. Re-validate the trust
    markers and exact candidate revision when reading so a stale or malformed
    event can never satisfy final qualification.
    """
    result: list[VerificationObservation] = []
    for event in work_store.list_work_events(str(work_order_id)):
        if event.attempt_id != str(attempt_id) or event.event_type != "engineering.external_evidence.verified":
            continue
        raw = event.payload.get("observation") if isinstance(event.payload, Mapping) else None
        if not isinstance(raw, Mapping):
            continue
        observation = observation_from_dict(raw)
        metadata = dict(observation.metadata or {})
        if metadata.get("trusted_source") != "github-actions":
            continue
        if metadata.get("verified_by") != "github-physical-device-evidence-verifier":
            continue
        if str(metadata.get("candidate_revision") or "").strip() != str(candidate_revision).strip():
            continue
        if observation.gate != "physical_device":
            continue
        result.append(observation)
    return tuple(result)
