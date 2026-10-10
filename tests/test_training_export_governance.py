from __future__ import annotations

import json
from pathlib import Path

from training import TrainingCandidateFactory, TrainingCandidateStore, TrainingDatasetExporter


def _approved(store, *, source_id: str, privacy_level: str, consent_basis: str | None = None):
    candidate = TrainingCandidateFactory().create(
        source_type='explicit_owner_feedback',
        source_id=source_id,
        prompt=f'prompt {source_id}',
        response=f'answer {source_id}',
        privacy_level=privacy_level,
        provenance=f'owner-feedback:{source_id}',
        consent_basis=consent_basis,
        verifier_score=.95,
    )
    store.save(candidate)
    return store.approve(candidate.candidate_id)


def _records(path: str):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line]


def test_public_safe_export_is_independent_from_private_export_and_never_publishes(tmp_path):
    store = TrainingCandidateStore(tmp_path / 'candidates.sqlite3')
    internal = _approved(store, source_id='internal', privacy_level='internal')
    public_without_export_consent = _approved(store, source_id='public-no-consent', privacy_level='public')
    public_with_export_consent = _approved(
        store,
        source_id='public-consented',
        privacy_level='public',
        consent_basis='owner_public_training_export',
    )
    exporter = TrainingDatasetExporter(store, tmp_path / 'exports')

    private_export = exporter.export(dataset_name='private-owner-copy')
    private_ids = {row['id'] for row in _records(private_export.dataset_path)}
    assert {internal.candidate_id, public_without_export_consent.candidate_id, public_with_export_consent.candidate_id} <= private_ids
    assert private_export.scope == 'private'

    public_export = exporter.export(dataset_name='public-safe-preparation', scope='public')
    public_rows = _records(public_export.dataset_path)
    assert [row['id'] for row in public_rows] == [public_with_export_consent.candidate_id]
    assert public_export.scope == 'public'
    manifest = json.loads(Path(public_export.manifest_path).read_text(encoding='utf-8'))
    assert manifest['automatic_publication'] is False
    assert manifest['public_upload_performed'] is False
    assert manifest['huggingface_upload_performed'] is False
    store.close()
