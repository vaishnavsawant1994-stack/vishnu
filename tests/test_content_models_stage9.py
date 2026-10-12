from __future__ import annotations

import json

import pytest

from training.content_models import (
    ContentDatasetBuilder,
    ContentModelCoordinator,
    ContentModelEvaluator,
    ContentModelStatus,
    ContentModelTask,
    NaiveBayesDocumentClassifierTrainer,
    VishnuDocumentClassifier,
)


def _source_for(builder: ContentDatasetBuilder, target: str, prefix: str) -> str:
    for index in range(10000):
        value = f"{prefix}-{index}"
        if builder._split(value) == target:
            return value
    raise AssertionError(f"could not find {target} source")


def _samples(builder: ContentDatasetBuilder, suffix: str = ""):
    train = _source_for(builder, "train", f"train{suffix}")
    validation = _source_for(builder, "validation", f"validation{suffix}")
    test = _source_for(builder, "test", f"test{suffix}")
    rows = []
    for source, prefix in ((train, "tr"), (validation, "va"), (test, "te")):
        rows.extend(
            [
                {
                    "id": f"{prefix}-invoice{suffix}",
                    "input": "invoice billing amount total payment due invoice",
                    "label": "invoice",
                    "source_fingerprint": source,
                    "provenance": {"kind": "owner_fixture"},
                    "consent_basis": "owner_provided",
                },
                {
                    "id": f"{prefix}-contract{suffix}",
                    "input": "contract agreement clauses parties terms contract",
                    "label": "contract",
                    "source_fingerprint": source,
                    "provenance": {"kind": "owner_fixture"},
                    "consent_basis": "owner_provided",
                },
            ]
        )
    return rows


def test_content_dataset_is_immutable_and_source_grouped(tmp_path):
    builder = ContentDatasetBuilder(tmp_path / "datasets")
    samples = _samples(builder)
    first = builder.build(ContentModelTask.DOCUMENT_CLASSIFICATION, samples)
    second = builder.build(ContentModelTask.DOCUMENT_CLASSIFICATION, list(reversed(samples)))
    assert first.snapshot_id == second.snapshot_id
    assert first.sha256 == second.sha256
    split_sources = []
    for path in (first.train_path, first.validation_path, first.test_path):
        rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
        split_sources.append({row["source_fingerprint"] for row in rows})
    assert split_sources[0]
    assert split_sources[1]
    assert split_sources[2]
    assert not (split_sources[0] & split_sources[1])
    assert not (split_sources[0] & split_sources[2])
    assert not (split_sources[1] & split_sources[2])
    manifest = json.loads(open(first.manifest_path, encoding="utf-8").read())
    assert manifest["contains_hidden_chain_of_thought"] is False
    assert manifest["automatic_publication"] is False
    assert manifest["immutable"] is True


def test_real_vishnu_document_classifier_training_artifact_and_prediction(tmp_path):
    helper = ContentDatasetBuilder(tmp_path / "helper")
    coordinator = ContentModelCoordinator(
        datasets_root=tmp_path / "datasets",
        artifacts_root=tmp_path / "artifacts",
        registry_path=tmp_path / "models.sqlite3",
    )
    model = coordinator.train(
        ContentModelTask.DOCUMENT_CLASSIFICATION,
        _samples(helper),
        NaiveBayesDocumentClassifierTrainer(),
        metadata={"purpose": "stage9-test"},
    )
    assert model["status"] == ContentModelStatus.CANDIDATE.value
    assert model["evaluation"]["passed"] is True
    assert model["metrics"]["accuracy"] >= 0.85
    assert model["artifact_id"].startswith("artifact-")
    classifier = VishnuDocumentClassifier(model["checkpoint_ref"])
    assert classifier.predict("invoice payment billing total") == "invoice"
    assert classifier.predict("contract agreement parties clauses") == "contract"


def test_content_model_activation_requires_evaluation_and_explicit_owner_authority(tmp_path):
    helper = ContentDatasetBuilder(tmp_path / "helper")
    coordinator = ContentModelCoordinator(
        datasets_root=tmp_path / "datasets",
        artifacts_root=tmp_path / "artifacts",
        registry_path=tmp_path / "models.sqlite3",
    )
    model = coordinator.train(ContentModelTask.DOCUMENT_CLASSIFICATION, _samples(helper), NaiveBayesDocumentClassifierTrainer())
    with pytest.raises(PermissionError):
        coordinator.registry.activate(model["model_id"], owner_authorized=False)
    with pytest.raises(ValueError):
        coordinator.registry.activate(model["model_id"], owner_authorized=True)
    approved = coordinator.registry.approve(model["model_id"], owner_id="owner-test")
    assert approved["status"] == ContentModelStatus.OWNER_APPROVED.value
    active = coordinator.registry.activate(model["model_id"], owner_authorized=True, actor="release_controller")
    assert active["status"] == ContentModelStatus.ACTIVE.value
    assert active["owner_approved_by"] == "owner-test"
    assert active["metadata"]["activation_actor"] == "release_controller"


def test_task_specific_evaluation_supports_future_owned_content_models_fail_closed():
    evaluator = ContentModelEvaluator()
    assert evaluator.evaluate_metrics(ContentModelTask.OCR, {"cer": 0.08, "word_accuracy": 0.93}).passed
    assert not evaluator.evaluate_metrics(ContentModelTask.OCR, {"cer": 0.08}).passed
    assert evaluator.evaluate_metrics(ContentModelTask.HANDWRITING, {"cer": 0.20, "word_accuracy": 0.75}).passed
    assert evaluator.evaluate_metrics(ContentModelTask.LAYOUT, {"f1": 0.90}).passed
    assert evaluator.evaluate_metrics(ContentModelTask.TABLE, {"cell_f1": 0.90}).passed
    assert evaluator.evaluate_metrics(ContentModelTask.DOCUMENT_CLASSIFICATION, {"accuracy": 0.90}).passed


def test_dataset_rejects_missing_provenance_fingerprint(tmp_path):
    builder = ContentDatasetBuilder(tmp_path / "datasets")
    with pytest.raises(ValueError, match="source_fingerprint"):
        builder.build(
            ContentModelTask.OCR,
            [
                {"id": "1", "input": "a", "label": "a"},
                {"id": "2", "input": "b", "label": "b"},
                {"id": "3", "input": "c", "label": "c"},
            ],
        )
