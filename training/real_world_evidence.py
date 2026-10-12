from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Iterable

from training.continuous_content_models import _canonical, _now, _read_jsonl
from training.document_vision import RealWorldCorpusQualifier, RealWorldQualificationReport


class Stage15RealWorldEvidenceStore:
    """Append-only Stage 15 real-world qualification evidence."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, report: RealWorldQualificationReport) -> dict[str, Any]:
        public = report.public()
        recorded_at = _now()
        payload = {
            "report": public,
            "recorded_at": recorded_at,
        }
        payload["record_sha256"] = hashlib.sha256(
            _canonical(payload).encode("utf-8")
        ).hexdigest()
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(_canonical(payload) + "\n")
        return payload

    def latest(self) -> dict[str, Any] | None:
        rows = _read_jsonl(self.path)
        return rows[-1] if rows else None

    def qualified(self) -> bool:
        latest = self.latest()
        return bool(
            latest
            and dict(latest.get("report") or {}).get("real_world_corpus_qualified") is True
        )


class Stage15RealWorldQualificationCoordinator:
    """Runs and persists the genuine-corpus gate without modifying model artifacts."""

    def __init__(
        self,
        evidence_path: str | Path,
        *,
        qualifier: RealWorldCorpusQualifier | None = None,
    ):
        self.qualifier = qualifier or RealWorldCorpusQualifier()
        self.evidence = Stage15RealWorldEvidenceStore(evidence_path)

    def qualify(self, records: Iterable[dict[str, Any]]) -> dict[str, Any]:
        report = self.qualifier.qualify(records)
        return self.evidence.record(report)

    def assert_qualified(self) -> dict[str, Any]:
        latest = self.evidence.latest()
        if not latest:
            raise ValueError("Stage 15 has no real-world corpus qualification evidence")
        report = dict(latest.get("report") or {})
        if report.get("real_world_corpus_qualified") is not True:
            raise ValueError(
                "Stage 15 real-world corpus is not qualified; synthetic evidence cannot satisfy this gate"
            )
        return latest
