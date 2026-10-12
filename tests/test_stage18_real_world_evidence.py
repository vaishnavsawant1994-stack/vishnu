from pathlib import Path

from training.multimodal_visual_reasoning import Stage18RealWorldMultimodalQualifier
from training.stage18_real_world_evidence import Stage18RealWorldEvidenceStore


def _records():
    tasks = ["ocr", "handwriting", "chart", "diagram", "equation", "ui"]
    captures = ["scan", "photo", "screenshot", "handwriting"]
    splits = ["train", "validation", "test"]
    rows = []
    counter = 0
    for task in tasks:
        for _ in range(2):
            truth = "hello world" if task in {"ocr", "handwriting"} else f"{task}_correct"
            rows.append(
                {
                    "task": task,
                    "truth": truth,
                    "prediction": truth,
                    "confidence": 1.0,
                    "accepted": True,
                    "should_accept": True,
                    "latency_ms": 4.0,
                    "source_fingerprint": f"real-evidence-{counter}",
                    "consent_basis": "owner_provided",
                    "split": splits[counter % len(splits)],
                    "provenance": {
                        "real_world": True,
                        "synthetic": False,
                        "simulated": False,
                        "capture_kind": captures[counter % len(captures)],
                        "license": "owner-generated",
                    },
                }
            )
            counter += 1
    return rows


def test_stage18_real_world_evidence_is_append_only_and_only_persisted_passes_are_authoritative(tmp_path: Path):
    qualifier = Stage18RealWorldMultimodalQualifier(min_source_groups=8)
    report = qualifier.qualify(_records())
    assert report.qualified is True
    assert report.public()["synthetic_evidence_can_qualify"] is False

    store = Stage18RealWorldEvidenceStore(tmp_path / "stage18-real-world.sqlite3")
    persisted = store.record(report)
    assert persisted["qualified"] is True
    assert persisted["real_world_corpus_qualified"] is True
    assert persisted["evidence_persisted"] is True
    assert store.get(report.evidence_sha256) == persisted
    assert store.latest_qualified() == persisted

    # Re-recording the exact immutable report is idempotent.
    assert store.record(report) == persisted
