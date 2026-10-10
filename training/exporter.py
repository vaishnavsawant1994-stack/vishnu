from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
from uuid import uuid4

from training.store import TrainingCandidateStore


@dataclass(frozen=True)
class TrainingExport:
    export_id: str
    created_at: str
    dataset_path: str
    manifest_path: str
    records: int
    sha256: str

    def public(self) -> dict:
        return {
            'export_id': self.export_id,
            'created_at': self.created_at,
            'dataset_path': self.dataset_path,
            'manifest_path': self.manifest_path,
            'records': self.records,
            'sha256': self.sha256,
            'public_upload_performed': False,
        }


class TrainingDatasetExporter:
    """Create owner-local, versioned JSONL from approved eligible candidates.

    The exporter never uploads a dataset and never reads Memory/Knowledge or
    connector stores directly. Its only source is the governed approved view.
    """

    _NAME = re.compile(r'[^A-Za-z0-9_.-]+')

    def __init__(self, store: TrainingCandidateStore, export_root: str | Path) -> None:
        self.store = store
        self.export_root = Path(export_root)
        self.export_root.mkdir(parents=True, exist_ok=True)

    @classmethod
    def _dataset_name(cls, value: str) -> str:
        clean = cls._NAME.sub('-', str(value or 'vishnu-general').strip()).strip('.-')
        return clean[:80] or 'vishnu-general'

    def export(self, *, dataset_name: str = 'vishnu-general', limit: int = 10000) -> TrainingExport:
        candidates = self.store.approved(limit=limit)
        export_id = f'train_{datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")}_{uuid4().hex[:8]}'
        root = self.export_root / export_id
        root.mkdir(parents=True, exist_ok=False)
        dataset = root / f'{self._dataset_name(dataset_name)}.jsonl'
        records = []
        for candidate in candidates:
            # No hidden reasoning traces are representable by TrainingCandidate;
            # candidates are sanitized instruction/response material only.
            records.append({
                'id': candidate.candidate_id,
                'instruction': candidate.prompt,
                'response': candidate.response,
                'source_type': candidate.source_type,
                'source_fingerprint': candidate.source_fingerprint,
                'provenance': candidate.provenance,
                'consent_basis': candidate.consent_basis,
                'privacy_level': candidate.privacy_level.value,
                'provider_id': candidate.provider_id,
                'model_id': candidate.model_id,
                'verifier_score': candidate.verifier_score,
            })
        payload = ''.join(json.dumps(record, sort_keys=True, ensure_ascii=False) + '\n' for record in records)
        dataset.write_text(payload, encoding='utf-8')
        digest = sha256(payload.encode('utf-8')).hexdigest()
        created_at = datetime.now(timezone.utc).isoformat()
        manifest = {
            'schema_version': 1,
            'export_id': export_id,
            'created_at': created_at,
            'dataset_name': self._dataset_name(dataset_name),
            'records': len(records),
            'dataset_sha256': digest,
            'selection': 'status=approved AND training_eligible=true',
            'source': 'governed_training_candidate_store',
            'contains_hidden_chain_of_thought': False,
            'automatic_publication': False,
        }
        manifest_path = root / 'manifest.json'
        manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2), encoding='utf-8')
        return TrainingExport(
            export_id=export_id,
            created_at=created_at,
            dataset_path=str(dataset),
            manifest_path=str(manifest_path),
            records=len(records),
            sha256=digest,
        )
