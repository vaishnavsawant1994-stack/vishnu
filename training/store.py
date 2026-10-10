from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from threading import RLock

from training.candidates import CandidateStatus, PrivacyLevel, TrainingCandidate


class TrainingCandidateStore:
    """Persistent candidate registry with source-level deletion lineage.

    This is intentionally separate from Vishnu Memory/Knowledge. Rows are
    sanitized candidates, not raw connected-service data, and only APPROVED +
    eligible rows are available to dataset export.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.path), check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self._lock = RLock()
        self.connection.execute(
            '''
            CREATE TABLE IF NOT EXISTS training_candidates (
                candidate_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_fingerprint TEXT NOT NULL,
                prompt TEXT NOT NULL,
                response TEXT NOT NULL,
                provider_id TEXT,
                model_id TEXT,
                privacy_level TEXT NOT NULL,
                provenance TEXT,
                consent_basis TEXT,
                verifier_score REAL,
                contains_secret INTEGER NOT NULL,
                training_eligible INTEGER NOT NULL,
                status TEXT NOT NULL,
                reason_codes_json TEXT NOT NULL
            )
            '''
        )
        self.connection.execute(
            'CREATE INDEX IF NOT EXISTS idx_training_source ON training_candidates(source_fingerprint)'
        )
        self.connection.execute(
            'CREATE INDEX IF NOT EXISTS idx_training_status ON training_candidates(status, training_eligible)'
        )
        self.connection.commit()

    @staticmethod
    def source_fingerprint(source_type: str, source_id: str) -> str:
        payload = f'{str(source_type).strip().lower() or "unknown"}\0{source_id}'.encode('utf-8', errors='replace')
        return sha256(payload).hexdigest()

    @staticmethod
    def _from_row(row: sqlite3.Row) -> TrainingCandidate:
        return TrainingCandidate(
            candidate_id=row['candidate_id'],
            created_at=row['created_at'],
            source_type=row['source_type'],
            source_fingerprint=row['source_fingerprint'],
            prompt=row['prompt'],
            response=row['response'],
            provider_id=row['provider_id'],
            model_id=row['model_id'],
            privacy_level=PrivacyLevel(row['privacy_level']),
            provenance=row['provenance'],
            consent_basis=row['consent_basis'],
            verifier_score=row['verifier_score'],
            contains_secret=bool(row['contains_secret']),
            training_eligible=bool(row['training_eligible']),
            status=CandidateStatus(row['status']),
            reason_codes=tuple(json.loads(row['reason_codes_json'] or '[]')),
        )

    @staticmethod
    def public(candidate: TrainingCandidate, *, include_content: bool = False) -> dict:
        value = {
            'candidate_id': candidate.candidate_id,
            'created_at': candidate.created_at,
            'source_type': candidate.source_type,
            'source_fingerprint': candidate.source_fingerprint,
            'provider_id': candidate.provider_id,
            'model_id': candidate.model_id,
            'privacy_level': candidate.privacy_level.value,
            'provenance': candidate.provenance,
            'consent_basis': candidate.consent_basis,
            'verifier_score': candidate.verifier_score,
            'contains_secret': candidate.contains_secret,
            'training_eligible': candidate.training_eligible,
            'status': candidate.status.value,
            'reason_codes': list(candidate.reason_codes),
        }
        if include_content:
            value['prompt'] = candidate.prompt
            value['response'] = candidate.response
        return value

    def save(self, candidate: TrainingCandidate) -> TrainingCandidate:
        with self._lock:
            self.connection.execute(
                '''
                INSERT OR REPLACE INTO training_candidates (
                    candidate_id, created_at, source_type, source_fingerprint,
                    prompt, response, provider_id, model_id, privacy_level,
                    provenance, consent_basis, verifier_score, contains_secret,
                    training_eligible, status, reason_codes_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    candidate.candidate_id, candidate.created_at, candidate.source_type,
                    candidate.source_fingerprint, candidate.prompt, candidate.response,
                    candidate.provider_id, candidate.model_id, candidate.privacy_level.value,
                    candidate.provenance, candidate.consent_basis, candidate.verifier_score,
                    int(candidate.contains_secret), int(candidate.training_eligible),
                    candidate.status.value, json.dumps(list(candidate.reason_codes)),
                ),
            )
            self.connection.commit()
        return candidate

    def get(self, candidate_id: str) -> TrainingCandidate | None:
        with self._lock:
            row = self.connection.execute(
                'SELECT * FROM training_candidates WHERE candidate_id = ?', (str(candidate_id),)
            ).fetchone()
        return None if row is None else self._from_row(row)

    def list(
        self,
        *,
        status: CandidateStatus | str | None = None,
        eligible: bool | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> tuple[TrainingCandidate, ...]:
        bounded_limit = max(1, min(1000, int(limit)))
        bounded_offset = max(0, int(offset))
        clauses: list[str] = []
        params: list[object] = []
        if status not in (None, ''):
            try:
                status_value = status.value if isinstance(status, CandidateStatus) else CandidateStatus(str(status)).value
            except ValueError as exc:
                raise ValueError('unsupported candidate status') from exc
            clauses.append('status=?')
            params.append(status_value)
        if eligible is not None:
            clauses.append('training_eligible=?')
            params.append(int(bool(eligible)))
        where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
        with self._lock:
            rows = self.connection.execute(
                f'SELECT * FROM training_candidates{where} ORDER BY created_at DESC LIMIT ? OFFSET ?',
                (*params, bounded_limit, bounded_offset),
            ).fetchall()
        return tuple(self._from_row(row) for row in rows)

    def stats(self) -> dict:
        with self._lock:
            total = int(self.connection.execute('SELECT COUNT(*) FROM training_candidates').fetchone()[0])
            rows = self.connection.execute(
                'SELECT status, training_eligible, COUNT(*) AS count FROM training_candidates GROUP BY status, training_eligible'
            ).fetchall()
        by_status = {status.value: 0 for status in CandidateStatus}
        eligible = 0
        for row in rows:
            by_status[str(row['status'])] = by_status.get(str(row['status']), 0) + int(row['count'])
            if int(row['training_eligible']):
                eligible += int(row['count'])
        return {
            'total': total,
            'eligible': eligible,
            'by_status': by_status,
            'approved_for_export': by_status.get(CandidateStatus.APPROVED.value, 0),
            'raw_source_data_stored': False,
            'automatic_publication': False,
        }

    def approve(self, candidate_id: str) -> TrainingCandidate:
        candidate = self.get(candidate_id)
        if candidate is None:
            raise KeyError(candidate_id)
        return self.save(candidate.approve())

    def reject(self, candidate_id: str, reason: str = 'owner_or_policy_rejected') -> TrainingCandidate:
        candidate = self.get(candidate_id)
        if candidate is None:
            raise KeyError(candidate_id)
        return self.save(candidate.reject(reason))

    def tombstone(self, candidate_id: str, reason: str = 'source_deleted_or_consent_revoked') -> TrainingCandidate:
        candidate = self.get(candidate_id)
        if candidate is None:
            raise KeyError(candidate_id)
        return self.save(candidate.tombstone(reason))

    def tombstone_source(self, source_type: str, source_id: str, reason: str = 'source_deleted_or_consent_revoked') -> int:
        fingerprint = self.source_fingerprint(source_type, source_id)
        with self._lock:
            rows = self.connection.execute(
                'SELECT * FROM training_candidates WHERE source_fingerprint = ?', (fingerprint,)
            ).fetchall()
            for row in rows:
                candidate = self._from_row(row).tombstone(reason)
                self.connection.execute(
                    '''UPDATE training_candidates
                       SET prompt='', response='', training_eligible=0, status=?, reason_codes_json=?
                       WHERE candidate_id=?''',
                    (candidate.status.value, json.dumps(list(candidate.reason_codes)), candidate.candidate_id),
                )
            self.connection.commit()
        return len(rows)

    def approved(self, *, limit: int = 1000) -> tuple[TrainingCandidate, ...]:
        bounded = max(1, min(10000, int(limit)))
        with self._lock:
            rows = self.connection.execute(
                '''SELECT * FROM training_candidates
                   WHERE status=? AND training_eligible=1
                   ORDER BY created_at ASC LIMIT ?''',
                (CandidateStatus.APPROVED.value, bounded),
            ).fetchall()
        return tuple(self._from_row(row) for row in rows)

    def close(self) -> None:
        with self._lock:
            self.connection.close()
