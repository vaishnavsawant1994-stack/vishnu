from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from file_intelligence import (
    ContentKind,
    ContentWorker,
    ExtractionMethod,
    FileIntelligenceEngine,
    SourceReference,
    Stage18ContentWorker,
    Stage18ProductionMultimodalRuntime,
    Stage18VisualAnalyzer,
    VishnuBlock,
    VishnuDocument,
)
from file_intelligence.production import JobStatus, ProductionContentStore
from server.content_ingestion_api import content_ingestion_router
from training.content_models import ContentModelCoordinator, ContentModelEvaluator, ContentModelTask
from training.continuous_content_models import GovernedContentFeedbackStore
from training.multimodal_visual_reasoning import (
    STAGE18_MIN_F1,
    STAGE18_SUBTASKS,
    Stage18MultimodalCoordinator,
    Stage18RealWorldMultimodalQualifier,
    VishnuStage18MultimodalModel,
)


def _png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _chart_png(heights=(60, 120, 180)) -> bytes:
    image = Image.new("RGB", (420, 300), "white")
    draw = ImageDraw.Draw(image)
    for index, height in enumerate(heights):
        x1 = 60 + index * 100
        draw.rectangle((x1, 260 - height, x1 + 40, 260), fill="black")
    return _png(image)


def _diagram_png() -> bytes:
    image = Image.new("RGB", (420, 300), "white")
    draw = ImageDraw.Draw(image)
    for x in (40, 160, 280, 400):
        draw.line((x, 20, x, 280), fill="black", width=2)
    for y in (40, 150, 260):
        draw.line((20, y, 410, y), fill="black", width=2)
    return _png(image)


def _blank_png() -> bytes:
    return _png(Image.new("RGB", (420, 300), "white"))


def _image_document(document_id: str, data: bytes, *, blocks=None, metadata=None) -> VishnuDocument:
    return VishnuDocument(
        document_id=document_id,
        filename=f"{document_id}.png",
        content_kind=ContentKind.IMAGE,
        detected_mime="image/png",
        declared_mime="image/png",
        extension=".png",
        sha256=hashlib.sha256(data).hexdigest(),
        size_bytes=len(data),
        blocks=blocks or [
            VishnuBlock(
                kind="paragraph",
                text="Sales chart Q1 Q2 Q3",
                source=SourceReference(page=1, bbox=[10, 10, 240, 36]),
                extraction_method=ExtractionMethod.OCR,
                confidence=0.99,
            )
        ],
        metadata=dict(metadata or {}),
        ocr_version="vishnu-stage14-neural-ctc",
        layout_version="vishnu-layout/4-stage15",
    )


def test_stage18_analyzer_understands_chart_diagram_equation_and_ui():
    analyzer = Stage18VisualAnalyzer()
    chart_bytes = _chart_png()
    chart_graph = analyzer.analyze(_image_document("chart", chart_bytes), raw_content=chart_bytes)
    assert chart_graph.charts
    assert chart_graph.charts[0]["chart_type"] == "bar_chart"
    assert len(chart_graph.charts[0]["series"][0]["bars"]) >= 3
    assert chart_graph.real_world_corpus_qualified is False
    chart_answer = analyzer.answer(chart_graph, "Which bar is the highest in the chart?")
    assert chart_answer["answered"] is True and chart_answer["grounded"] is True
    assert chart_answer["citations"]

    diagram_bytes = _diagram_png()
    diagram_doc = _image_document(
        "diagram",
        diagram_bytes,
        blocks=[VishnuBlock(
            kind="paragraph",
            text="Architecture diagram with services and data flow",
            source=SourceReference(page=1, bbox=[10, 10, 390, 32]),
            extraction_method=ExtractionMethod.OCR,
            confidence=0.98,
        )],
    )
    diagram_graph = analyzer.analyze(diagram_doc, raw_content=diagram_bytes)
    assert diagram_graph.diagrams
    assert len(diagram_graph.diagrams[0]["nodes"]) >= 3
    diagram_answer = analyzer.answer(diagram_graph, "Explain the architecture diagram nodes")
    assert diagram_answer["answered"] is True and diagram_answer["source_kind"] == "diagram"

    screen_bytes = _blank_png()
    screen_doc = _image_document(
        "screen",
        screen_bytes,
        metadata={"capture_kind": "screenshot"},
        blocks=[
            VishnuBlock(
                kind="equation",
                text="E = mc^2",
                source=SourceReference(page=1, bbox=[40, 40, 180, 72]),
                extraction_method=ExtractionMethod.OCR,
                confidence=0.97,
            ),
            VishnuBlock(
                kind="text",
                text="Next",
                source=SourceReference(page=1, bbox=[300, 240, 380, 276]),
                extraction_method=ExtractionMethod.OCR,
                confidence=0.96,
            ),
            VishnuBlock(
                kind="text",
                text="Error: Invalid password",
                source=SourceReference(page=1, bbox=[80, 120, 330, 158]),
                extraction_method=ExtractionMethod.OCR,
                confidence=0.95,
            ),
        ],
    )
    screen_graph = analyzer.analyze(screen_doc, raw_content=screen_bytes)
    assert screen_graph.equations and screen_graph.equations[0]["text"] == "E = mc^2"
    assert any(item["action"] == "next" for item in screen_graph.ui_elements)
    assert any(item["element_type"] == "error" for item in screen_graph.ui_elements)
    assert analyzer.answer(screen_graph, "What equation or formula is shown?")["answered"] is True
    assert "Next" in analyzer.answer(screen_graph, "What should I click next?")["answer"]
    assert "Invalid password" in analyzer.answer(screen_graph, "Does the UI show an error?")["answer"]


def test_stage18_runtime_scope_isolation_reprocessing_and_visual_compare(tmp_path: Path):
    runtime = Stage18ProductionMultimodalRuntime(tmp_path / "stage18.sqlite3")
    chart_bytes = _chart_png()
    chart = _image_document("chart-a", chart_bytes)
    status = runtime.process(
        chart,
        scope_type="project",
        scope_id="project-a",
        object_sha256=chart.sha256,
        extraction_version=1,
        raw_content=chart_bytes,
    )
    assert status["state"] == "completed" and status["stage17"]["state"] == "completed"
    assert status["real_world_corpus_qualified"] is False and status["graph_sha256"]
    assert runtime.needs_reprocessing(chart, scope_type="project", scope_id="project-a", extraction_version=1) is False
    assert runtime.needs_reprocessing(chart, scope_type="project", scope_id="project-a", extraction_version=2) is True
    answer = runtime.answer_visual("Which chart bar is highest?", scope_type="project", scope_id="project-a", document_id=chart.document_id)
    assert answer["answered"] is True and answer["citations"]
    rejected = runtime.answer_visual("Which chart bar is highest?", scope_type="project", scope_id="project-b")
    assert rejected["answered"] is False and rejected["citations"] == []
    assert runtime.multimodal_graph(document_id=chart.document_id, scope_type="project", scope_id="project-b") is None

    diagram_bytes = _diagram_png()
    diagram = _image_document(
        "diagram-b",
        diagram_bytes,
        blocks=[VishnuBlock(
            kind="paragraph",
            text="Architecture diagram",
            source=SourceReference(page=1, bbox=[10, 10, 200, 30]),
            extraction_method=ExtractionMethod.OCR,
            confidence=0.99,
        )],
    )
    runtime.process(diagram, scope_type="project", scope_id="project-a", object_sha256=diagram.sha256, raw_content=diagram_bytes)
    comparison = runtime.compare_visual(
        first_document_id=chart.document_id,
        second_document_id=diagram.document_id,
        scope_type="project",
        scope_id="project-a",
    )
    assert comparison["grounded"] is True
    assert comparison["chart_count_delta"] < 0
    assert comparison["diagram_count_delta"] > 0
    assert comparison["foundation_model"] is False


class FixtureOcr:
    name = "fixture-local-ocr"
    external = False

    def extract(self, image_bytes: bytes, *, filename: str, access_class: str):
        return [{"text": "Sales chart Q1 Q2 Q3", "bbox": [10, 10, 250, 40], "confidence": 0.99}]


def test_stage18_worker_is_canonical_and_completion_requires_multimodal_state(tmp_path: Path):
    assert ContentWorker is Stage18ContentWorker
    store = ProductionContentStore(tmp_path / "content.sqlite3", tmp_path / "objects")
    chart_bytes = _chart_png()
    obj = store.object_store.put_bytes(chart_bytes)
    job = store.enqueue(
        object_sha256=obj.sha256,
        filename="chart.png",
        scope_type="project",
        scope_id="project-a",
        declared_mime="image/png",
        max_attempts=1,
    )
    worker = ContentWorker(
        store,
        worker_id="stage18-test-worker",
        engine_factory=lambda max_bytes: FileIntelligenceEngine(ocr_provider=FixtureOcr(), max_file_bytes=max_bytes),
    )
    completed = worker.process_once()
    assert completed and completed["status"] == JobStatus.COMPLETED.value
    assert completed["metadata"]["stage17_completed"] is True
    assert completed["metadata"]["stage18_completed"] is True
    assert completed["metadata"]["stage18_graph_sha256"]
    assert completed["metadata"]["real_world_corpus_qualified"] is False
    result = store.result(job["job_id"])
    runtime = Stage18ProductionMultimodalRuntime(store.path)
    graph = runtime.multimodal_graph(
        document_id=result["document"]["document_id"], scope_type="project", scope_id="project-a"
    )
    assert graph is not None and graph.charts


def test_stage18_worker_fails_closed_when_multimodal_pipeline_fails(tmp_path: Path):
    class FailingRuntime:
        def process(self, *args, **kwargs):
            raise RuntimeError("multimodal pipeline failed")

    store = ProductionContentStore(tmp_path / "content.sqlite3", tmp_path / "objects")
    obj = store.object_store.put_bytes(b"stage18 fail closed")
    job = store.enqueue(
        object_sha256=obj.sha256,
        filename="note.txt",
        scope_type="project",
        scope_id="project-failure",
        declared_mime="text/plain",
        max_attempts=1,
    )
    worker = Stage18ContentWorker(store, worker_id="failing-stage18-worker", intelligence_runtime=FailingRuntime())
    failed = worker.process_once()
    assert failed and failed["status"] == JobStatus.FAILED.value
    assert failed["error_code"] == "RuntimeError"
    assert store.result(job["job_id"]) is None


def test_stage18_real_world_qualification_rejects_synthetic_and_accepts_complete_governed_real_evidence():
    qualifier = Stage18RealWorldMultimodalQualifier(min_source_groups=8)
    synthetic = qualifier.qualify([{
        "task": "chart",
        "truth": "bar_chart",
        "prediction": "bar_chart",
        "confidence": 1.0,
        "source_fingerprint": "synthetic-one",
        "consent_basis": "owner_provided",
        "split": "test",
        "provenance": {"real_world": True, "synthetic": True, "capture_kind": "screenshot", "license": "owner-generated"},
    }])
    assert synthetic.qualified is False
    assert synthetic.public()["real_world_corpus_qualified"] is False
    assert synthetic.public()["synthetic_evidence_can_qualify"] is False
    assert any("synthetic_or_simulated_evidence_forbidden" in reason for reason in synthetic.reasons)

    tasks = ["ocr", "handwriting", "chart", "diagram", "equation", "ui"]
    captures = ["scan", "photo", "screenshot", "handwriting"]
    splits = ["train", "validation", "test"]
    records = []
    counter = 0
    for task in tasks:
        for _ in range(2):
            truth = "hello world" if task in {"ocr", "handwriting"} else f"{task}_correct"
            records.append({
                "task": task,
                "truth": truth,
                "prediction": truth,
                "confidence": 1.0,
                "accepted": True,
                "should_accept": True,
                "latency_ms": 5.0,
                "source_fingerprint": f"real-source-{counter}",
                "consent_basis": "owner_provided",
                "split": splits[counter % len(splits)],
                "provenance": {
                    "real_world": True,
                    "synthetic": False,
                    "simulated": False,
                    "capture_kind": captures[counter % len(captures)],
                    "license": "owner-generated",
                },
            })
            counter += 1
    report = qualifier.qualify(records)
    assert report.qualified is True
    public = report.public()
    assert public["real_world_corpus_qualified"] is True
    assert public["synthetic_evidence_can_qualify"] is False
    assert public["source_groups"] >= 8
    assert all(public["capture_counts"][name] > 0 for name in captures)
    assert public["recognition_metrics"]["ocr"]["word_accuracy"] == 1.0
    assert public["recognition_metrics"]["handwriting"]["word_accuracy"] == 1.0
    assert all(public["visual_metrics"][task]["accuracy"] == 1.0 for task in ("chart", "diagram", "equation", "ui"))


class BadVisualBaseline:
    baseline_id = "stage18-bad-visual-baseline"

    def predict(self, subtask: str, payload: dict) -> str:
        return "wrong"


def _source_for(builder, target: str, prefix: str) -> str:
    for index in range(50000):
        value = f"{prefix}-{index}"
        if builder._split(value) == target:
            return value
    raise AssertionError(f"could not find source for {target}")


def _examples(subtask: str):
    return {
        "stage18_chart_type": (("bar_chart", "bar chart vertical bars categories values revenue"), ("line_chart", "line chart time series trend points axis")),
        "stage18_diagram_type": (("flowchart", "flowchart process decision arrows steps workflow"), ("architecture", "architecture services database gateway components system")),
        "stage18_equation_role": (("definition", "equation definition variable equals formula expression"), ("constraint", "equation constraint inequality less greater limit bound")),
        "stage18_ui_element_type": (("button", "button next save submit clickable action control"), ("error", "error warning invalid failed message alert")),
        "stage18_visual_qa_support": (("supported", "question answer visible chart evidence supported grounded"), ("unsupported", "question asks absent information unsupported reject no evidence")),
    }[subtask]


def _submit_stage18_feedback(feedback: GovernedContentFeedbackStore, builder) -> None:
    for subtask in STAGE18_SUBTASKS:
        for label, text in _examples(subtask):
            for index in range(3):
                source = _source_for(builder, "train", f"{subtask}-{label}-train-{index}")
                row = feedback.submit(
                    task=ContentModelTask.DOCUMENT_CLASSIFICATION,
                    subtask=subtask,
                    language="multi",
                    source_fingerprint=source,
                    input_payload={"text": f"{text} {label} train {index}"},
                    label=label,
                    provenance={"license": "owner-generated", "stage18": True},
                    consent_basis="owner_provided",
                )
                feedback.approve(row["feedback_id"], reviewer="owner-reviewer")
            for split in ("validation", "test"):
                source = _source_for(builder, split, f"{subtask}-{label}-{split}")
                row = feedback.submit(
                    task=ContentModelTask.DOCUMENT_CLASSIFICATION,
                    subtask=subtask,
                    language="multi",
                    source_fingerprint=source,
                    input_payload={"text": f"{text} {label} {split}"},
                    label=label,
                    provenance={"license": "owner-generated", "stage18": True},
                    consent_basis="owner_provided",
                )
                feedback.approve(row["feedback_id"], reviewer="owner-reviewer")


def test_stage18_multimodal_model_is_governed_shadow_qualified_and_owner_gated(tmp_path: Path):
    models = ContentModelCoordinator(
        datasets_root=tmp_path / "datasets",
        artifacts_root=tmp_path / "artifacts",
        registry_path=tmp_path / "models.sqlite3",
    )
    feedback = GovernedContentFeedbackStore(tmp_path / "feedback.sqlite3")
    coordinator = Stage18MultimodalCoordinator(
        content_models=models,
        feedback=feedback,
        evidence_path=tmp_path / "stage18-evidence.sqlite3",
    )
    _submit_stage18_feedback(feedback, models.datasets)
    candidate = coordinator.train_candidate()
    assert candidate["status"] == "candidate"
    assert candidate["backend_id"] == "vishnu-stage18-multimodal-centroid-v1"
    assert candidate["metadata"]["stage"] == 18
    assert candidate["metadata"]["multimodal_evidence_graph"] is True
    assert candidate["metadata"]["foundation_model"] is False
    assert candidate["metadata"]["real_world_corpus_qualified"] is False
    assert candidate["metrics"]["accuracy"] >= 0.85
    for subtask, floor in STAGE18_MIN_F1.items():
        assert candidate["metrics"][f"{subtask}_f1"] >= floor

    model = VishnuStage18MultimodalModel(candidate["checkpoint_ref"])
    assert set(model.heads) == set(STAGE18_SUBTASKS)
    assert model.model["trained_by_vishnu"] is True
    assert model.model["foundation_model"] is False
    assert model.predict("stage18_chart_type", {"text": "bar chart vertical bars categories values revenue"}, reject_below=0.0)["label"] == "bar_chart"
    with pytest.raises(ValueError, match="shadow qualification"):
        coordinator.approve(candidate["model_id"], owner_id="owner")
    evidence = coordinator.shadow_qualify(candidate["model_id"], baseline=BadVisualBaseline())
    assert evidence["passed"] is True
    for subtask, floor in STAGE18_MIN_F1.items():
        assert evidence["candidate_metrics"][f"{subtask}_f1"] >= floor
    approved = coordinator.approve(candidate["model_id"], owner_id="owner")
    assert approved["status"] == "owner_approved"
    with pytest.raises(PermissionError):
        coordinator.activate(candidate["model_id"], owner_authorized=False)
    active = coordinator.activate(candidate["model_id"], owner_authorized=True)
    assert active["status"] == "active"
    assert active["metadata"]["activation_actor"] == "release_controller"
    loaded = coordinator.active_model()
    assert loaded.predict("stage18_ui_element_type", {"text": "error warning invalid failed message alert"}, reject_below=0.0)["label"] == "error"


def test_stage18_router_exposes_multimodal_surface(tmp_path: Path):
    class Registry:
        def is_active(self, device_id):
            return True
        def authorize(self, device_id, scope):
            return True
    class Projects:
        def get(self, project_id):
            return {"id": project_id, "status": "active"}

    store = ProductionContentStore(tmp_path / "content.sqlite3", tmp_path / "objects")
    runtime = {"device_registry": Registry(), "base_project_store": Projects()}
    router = content_ingestion_router(runtime, store)
    paths = {route.path for route in router.routes}
    assert "/iphone/api/content-ingestion/intelligence/visual-answer" in paths
    assert "/iphone/api/content-ingestion/intelligence/visual-compare" in paths
    assert "/iphone/api/content-ingestion/intelligence/{scope_type}/{scope_id}/visual-status/{document_id:path}" in paths
    assert isinstance(runtime["content_intelligence"], Stage18ProductionMultimodalRuntime)


def test_stage18_does_not_weaken_existing_content_model_thresholds():
    rules = ContentModelEvaluator.RULES
    assert rules[ContentModelTask.OCR]["max"]["cer"] == 0.15
    assert rules[ContentModelTask.OCR]["min"]["word_accuracy"] == 0.85
    assert rules[ContentModelTask.HANDWRITING]["max"]["cer"] == 0.25
    assert rules[ContentModelTask.HANDWRITING]["min"]["word_accuracy"] == 0.70
    assert rules[ContentModelTask.LAYOUT]["min"]["f1"] == 0.85
    assert rules[ContentModelTask.TABLE]["min"]["cell_f1"] == 0.85
    assert rules[ContentModelTask.DOCUMENT_CLASSIFICATION]["min"]["accuracy"] == 0.85
