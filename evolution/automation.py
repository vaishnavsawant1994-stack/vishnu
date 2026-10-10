from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

from .code_body import CodeBodyRun, CodeBodyRunStatus
from .code_policy import evaluate_code_change


@dataclass(frozen=True)
class ImplementationResult:
    changed_paths: tuple[str, ...]
    summary: str


class EvolutionImplementationProvider(Protocol):
    def implement(self, *, candidate, workspace: Path) -> ImplementationResult: ...


class ModelFileImplementationProvider:
    """Bounded model-driven source editor for an already isolated workspace.

    The model does not receive git, approval, merge, deployment or tool
    authority. It may propose complete UTF-8 file replacements only. Paths are
    validated before any write, protected evolution/security surfaces are
    rejected, symlinks are rejected and total output is bounded.
    """

    def __init__(self, models, *, max_files: int = 12, max_file_bytes: int = 250_000, max_total_bytes: int = 1_000_000) -> None:
        self.models = models
        self.max_files = max(1, min(50, int(max_files)))
        self.max_file_bytes = max(1_000, min(1_000_000, int(max_file_bytes)))
        self.max_total_bytes = max(self.max_file_bytes, min(5_000_000, int(max_total_bytes)))

    @staticmethod
    def _safe_path(workspace: Path, raw: str) -> tuple[str, Path]:
        relative = PurePosixPath(str(raw or '').strip())
        if not relative.parts or relative.is_absolute() or '..' in relative.parts:
            raise ValueError('unsafe implementation path')
        normalized = relative.as_posix()
        target = workspace.joinpath(*relative.parts)
        root = workspace.resolve()
        parent = target.parent.resolve()
        if parent != root and root not in parent.parents:
            raise ValueError('implementation path escapes workspace')
        if target.exists() and target.is_symlink():
            raise ValueError('evolution implementation cannot replace symlinks')
        return normalized, target

    def implement(self, *, candidate, workspace: Path) -> ImplementationResult:
        system = (
            'You are Vishnu software engineering intelligence operating in an isolated candidate workspace. '
            'Return one JSON object only with keys files and summary. files is a list of objects with path and content. '
            'Use complete UTF-8 file contents, not patches. Make the smallest implementation that satisfies the candidate and tests. '
            'Never edit security, authority, approval, identity, evolution, tool/capability governance, CI workflows, or safety tests. '
            'Do not add credentials, secrets, network exfiltration, self-approval, auto-merge, auto-deploy or auto-activation.'
        )
        prompt = (
            f'Title: {candidate.title}\n'
            f'Rationale: {candidate.rationale}\n'
            f'Change: {candidate.proposed_change}\n'
            f'Expected benefit: {candidate.expected_benefit}\n'
            f'Affected scope: {list(candidate.affected_scope)}\n'
            f'Test plan: {list(candidate.test_plan)}\n'
            'Inspect the stated scope conceptually and return only files that must change. '
            'If the change cannot be safely implemented without protected surfaces, return files=[] and explain in summary.'
        )
        payload = self.models.json(
            prompt,
            system=system,
            sensitivity='internal',
            task_complexity='critical',
            task_domain='software_engineering',
            evidence_required=True,
        )
        files = payload.get('files') if isinstance(payload, dict) else None
        if not isinstance(files, list):
            raise ValueError('implementation model did not return a files list')
        if len(files) > self.max_files:
            raise ValueError('implementation exceeds maximum changed-file count')
        prepared: list[tuple[str, Path, str]] = []
        total = 0
        for item in files:
            if not isinstance(item, dict):
                raise ValueError('implementation file entry must be an object')
            normalized, target = self._safe_path(workspace, item.get('path'))
            content = item.get('content')
            if not isinstance(content, str):
                raise ValueError('implementation file content must be text')
            size = len(content.encode('utf-8'))
            if size > self.max_file_bytes:
                raise ValueError(f'implementation file exceeds size limit: {normalized}')
            total += size
            if total > self.max_total_bytes:
                raise ValueError('implementation exceeds total size limit')
            prepared.append((normalized, target, content))
        policy = evaluate_code_change(path for path, _, _ in prepared)
        if not policy.allowed:
            raise PermissionError(f'evolution implementation touches protected scope: {list(policy.protected_paths)}')
        for _, target, content in prepared:
            target.parent.mkdir(parents=True, exist_ok=True)
            temp = target.with_name(target.name + '.vishnu-evolution.tmp')
            temp.write_text(content, encoding='utf-8')
            temp.replace(target)
        return ImplementationResult(
            changed_paths=tuple(path for path, _, _ in prepared),
            summary=str(payload.get('summary') or candidate.title)[:1000],
        )


class AutomaticCodeEvolution:
    """Drive owner-approved safe-scope code work through verification only.

    There is intentionally no method for owner approval, external review
    approval, adoption, merge, deployment or activation. The strongest result
    this coordinator can produce is VERIFIED, which still requires an external
    approved review and the existing separate owner-adoption boundary.
    """

    def __init__(self, *, code_body, implementation: EvolutionImplementationProvider, worker_id: str = 'vishnu-code-evolution', events=None) -> None:
        self.code_body = code_body
        self.implementation = implementation
        self.worker_id = str(worker_id)
        self.events = events

    def run(self, candidate_id: str, *, runtime_epoch: int) -> CodeBodyRun:
        # prepare() itself proves an immutable owner-approved handoff exists.
        run = self.code_body.prepare(candidate_id, worker_id=self.worker_id, runtime_epoch=int(runtime_epoch))
        if run.status is not CodeBodyRunStatus.PREPARED:
            return run
        candidate = self.code_body.handoffs.evolution_store.get_candidate(candidate_id)
        if candidate is None:
            raise KeyError(candidate_id)
        session = self.code_body._session(run)
        result = self.implementation.implement(candidate=candidate, workspace=Path(session.local_path))
        if not result.changed_paths:
            raise ValueError('automatic evolution produced no safe code changes')
        policy = evaluate_code_change(result.changed_paths)
        if not policy.allowed:
            raise PermissionError('automatic evolution attempted protected code changes')
        if self.events is not None:
            self.events.emit(
                'evolution.auto_implementation.prepared',
                candidate_id=candidate_id,
                changed_paths=list(result.changed_paths),
                execution_authority=False,
                adoption_authority=False,
            )
        committed = self.code_body.commit(candidate_id, message=f'Implement evolution candidate: {candidate.title}')
        if committed.status is not CodeBodyRunStatus.COMMITTED:
            return committed
        verified = self.code_body.verify(candidate_id)
        if self.events is not None:
            self.events.emit(
                'evolution.auto_implementation.verified',
                candidate_id=candidate_id,
                status=verified.status.value,
                review_required=True,
                owner_adoption_required=True,
                merge_performed=False,
                deployment_performed=False,
            )
        return verified

    def status(self) -> dict[str, Any]:
        return {
            'available': self.code_body is not None and self.implementation is not None,
            'requires_owner_approved_handoff': True,
            'protected_scope_enforced': True,
            'automatic_review_approval': False,
            'automatic_adoption': False,
            'automatic_merge': False,
            'automatic_deploy': False,
            'automatic_activation': False,
        }
