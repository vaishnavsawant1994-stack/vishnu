from __future__ import annotations

import hashlib
import io
import json
import re
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Iterable

import numpy as np
from PIL import Image, ImageOps

from .models import ContentKind, VishnuBlock, VishnuDocument
from .stage17_grounded_runtime import Stage17ProductionContentRuntime


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _stable_id(prefix: str, *parts: Any) -> str:
    payload = "\0".join(_canonical(value) if isinstance(value, (dict, list, tuple)) else str(value) for value in parts)
    return f"{prefix}_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:24]}"


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def _tokens(value: Any) -> set[str]:
    return {token.casefold() for token in re.findall(r"[\w@.+#/%-]{2,}", str(value or ""), flags=re.UNICODE)}


def _runs(mask: np.ndarray, *, min_length: int = 1) -> list[tuple[int, int]]:
    values = np.asarray(mask, dtype=bool).reshape(-1)
    output: list[tuple[int, int]] = []
    start: int | None = None
    for index, enabled in enumerate(values):
        if enabled and start is None:
            start = index
        elif not enabled and start is not None:
            if index - start >= min_length:
                output.append((start, index))
            start = None
    if start is not None and len(values) - start >= min_length:
        output.append((start, len(values)))
    return output


class Stage18PolicyError(ValueError):
    pass


@dataclass(frozen=True)
class VisualEvidenceAnchor:
    anchor_id: str
    document_id: str
    document_sha256: str
    page: int
    bbox: tuple[float, float, float, float]
    kind: str
    text: str
    confidence: float
    source: dict[str, Any]
    model_id: str

    def public(self) -> dict[str, Any]:
        value = asdict(self)
        value["bbox"] = list(self.bbox)
        return value


@dataclass
class MultimodalDocumentGraph:
    document_id: str
    document_sha256: str
    filename: str
    charts: list[dict[str, Any]] = field(default_factory=list)
    diagrams: list[dict[str, Any]] = field(default_factory=list)
    equations: list[dict[str, Any]] = field(default_factory=list)
    figures: list[dict[str, Any]] = field(default_factory=list)
    ui_elements: list[dict[str, Any]] = field(default_factory=list)
    visual_claims: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    page_summaries: list[dict[str, Any]] = field(default_factory=list)
    model_versions: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    real_world_corpus_qualified: bool = False
    real_world_evidence_sha256: str | None = None

    def public(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "stage": 18,
            "document_id": self.document_id,
            "document_sha256": self.document_sha256,
            "filename": self.filename,
            "charts": self.charts,
            "diagrams": self.diagrams,
            "equations": self.equations,
            "figures": self.figures,
            "ui_elements": self.ui_elements,
            "visual_claims": self.visual_claims,
            "evidence": self.evidence,
            "page_summaries": self.page_summaries,
            "model_versions": self.model_versions,
            "warnings": self.warnings,
            "grounded_only": True,
            "contains_hidden_chain_of_thought": False,
            "foundation_model": False,
            "real_world_corpus_qualified": self.real_world_corpus_qualified,
            "real_world_evidence_sha256": self.real_world_evidence_sha256,
        }


class Stage18VisualAnalyzer:
    """Bounded local visual-structure analyzer composed with Stages 15-17.

    The analyzer intentionally does not pretend to be a foundation vision model.
    It extracts deterministic visual primitives from image/PDF pages and combines
    them with already-grounded OCR/layout text. Owner-activated learned Stage 18
    classifiers may enrich labels, but the evidence geometry remains local and
    inspectable.
    """

    version = "vishnu-multimodal-visual-reasoning/18.1"
    model_id = "vishnu-stage18-grounded-visual-runtime-v1"
    MAX_PAGES = 12
    MAX_DIMENSION = 1024

    _EQUATION_RE = re.compile(
        r"(?:[A-Za-z0-9_]+\s*=\s*[^\n]{1,160}|[∑∫√≈≠≤≥±×÷∞∂∇]|(?:sin|cos|tan|log|exp)\s*\([^\n]{1,100}\))",
        re.I,
    )
    _ERROR_RE = re.compile(r"\b(error|failed|failure|warning|exception|invalid|unavailable|denied)\b", re.I)
    _UI_ACTIONS = {
        "save", "cancel", "submit", "continue", "next", "back", "login", "sign in",
        "sign up", "delete", "edit", "create", "add", "upload", "download", "send",
        "search", "close", "confirm", "approve", "retry", "refresh", "done",
    }

    def __init__(self, *, learned_model: Any | None = None):
        self.learned_model = learned_model

    @classmethod
    def _bounded_image(cls, image: Image.Image) -> Image.Image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        if max(image.size) > cls.MAX_DIMENSION:
            scale = cls.MAX_DIMENSION / max(image.size)
            image = image.resize(
                (max(1, int(image.width * scale)), max(1, int(image.height * scale))),
                Image.Resampling.LANCZOS,
            )
        return image

    @classmethod
    def decode_pages(
        cls,
        raw_content: bytes | None,
        *,
        filename: str,
        detected_mime: str,
        content_kind: ContentKind,
    ) -> list[Image.Image]:
        if not raw_content:
            return []
        if content_kind is ContentKind.IMAGE or str(detected_mime).startswith("image/"):
            try:
                with Image.open(io.BytesIO(raw_content)) as source:
                    source.load()
                    return [cls._bounded_image(source.copy())]
            except Exception as exc:
                raise Stage18PolicyError("Stage 18 image payload is unreadable") from exc
        if content_kind is ContentKind.PDF or str(detected_mime) == "application/pdf" or str(filename).lower().endswith(".pdf"):
            try:
                import fitz  # PyMuPDF

                pages: list[Image.Image] = []
                with fitz.open(stream=raw_content, filetype="pdf") as pdf:
                    for page_index in range(min(len(pdf), cls.MAX_PAGES)):
                        pix = pdf[page_index].get_pixmap(matrix=fitz.Matrix(1.4, 1.4), alpha=False)
                        image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                        pages.append(cls._bounded_image(image))
                return pages
            except Exception as exc:
                raise Stage18PolicyError("Stage 18 PDF visual rendering failed") from exc
        return []

    @staticmethod
    def _page_blocks(document: VishnuDocument, page: int) -> list[VishnuBlock]:
        output: list[VishnuBlock] = []
        for block in document.blocks:
            source_page = block.source.page
            if source_page is None:
                if page == 1 and document.content_kind is ContentKind.IMAGE:
                    output.append(block)
            elif int(source_page) == int(page):
                output.append(block)
        return output

    @classmethod
    def _page_text(cls, document: VishnuDocument, page: int) -> str:
        return "\n".join(block.text for block in cls._page_blocks(document, page) if block.text).strip()

    @staticmethod
    def _visual_arrays(image: Image.Image) -> tuple[np.ndarray, np.ndarray]:
        gray = np.asarray(ImageOps.grayscale(image), dtype=np.float64) / 255.0
        ink = gray < 0.78
        return gray, ink

    @staticmethod
    def _line_geometry(ink: np.ndarray) -> dict[str, Any]:
        row_density = np.mean(ink, axis=1)
        col_density = np.mean(ink, axis=0)
        horizontal = _runs(row_density >= 0.58, min_length=1)
        vertical = _runs(col_density >= 0.58, min_length=1)
        return {
            "horizontal": horizontal[:80],
            "vertical": vertical[:80],
            "row_density": row_density,
            "col_density": col_density,
        }

    @staticmethod
    def _bar_candidates(ink: np.ndarray) -> list[dict[str, Any]]:
        height, width = ink.shape
        # Ignore outer page margins and find solid-ish vertical runs whose ink
        # occupies a meaningful part of the page height.
        col_density = np.mean(ink, axis=0)
        runs = _runs(col_density >= 0.10, min_length=max(2, width // 100))
        bars: list[dict[str, Any]] = []
        for left, right in runs:
            if right - left > width * 0.22:
                continue
            region = ink[:, left:right]
            occupied_rows = np.where(np.mean(region, axis=1) >= 0.45)[0]
            if len(occupied_rows) < max(4, height // 18):
                continue
            top, bottom = int(occupied_rows.min()), int(occupied_rows.max()) + 1
            if bottom - top < height * 0.08:
                continue
            bars.append(
                {
                    "bbox": [left, top, right, bottom],
                    "width": right - left,
                    "height": bottom - top,
                    "bottom": bottom,
                }
            )
        if len(bars) < 3:
            return []
        bottoms = [bar["bottom"] for bar in bars]
        baseline = float(np.median(bottoms))
        aligned = [bar for bar in bars if abs(bar["bottom"] - baseline) <= max(4, height * 0.06)]
        if len(aligned) < 3:
            return []
        aligned.sort(key=lambda item: item["bbox"][0])
        maximum = max(1, max(item["height"] for item in aligned))
        for index, item in enumerate(aligned):
            item["index"] = index
            item["relative_value"] = float(item["height"] / maximum)
        return aligned[:40]

    @staticmethod
    def _box_candidates(lines: dict[str, Any], image: Image.Image) -> list[dict[str, Any]]:
        horizontal = [int((start + end) / 2) for start, end in lines["horizontal"]]
        vertical = [int((start + end) / 2) for start, end in lines["vertical"]]
        boxes: list[dict[str, Any]] = []
        for yi, top in enumerate(horizontal):
            for bottom in horizontal[yi + 1 : yi + 8]:
                if bottom - top < max(12, image.height // 40):
                    continue
                for xi, left in enumerate(vertical):
                    for right in vertical[xi + 1 : xi + 8]:
                        if right - left < max(20, image.width // 40):
                            continue
                        if (right - left) * (bottom - top) > image.width * image.height * 0.35:
                            continue
                        boxes.append({"bbox": [left, top, right, bottom]})
                        if len(boxes) >= 80:
                            return boxes
        return boxes

    def _learned_label(self, subtask: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        if self.learned_model is None:
            return None
        try:
            result = self.learned_model.predict(subtask, payload, reject_below=0.0)
        except Exception:
            return None
        return dict(result) if isinstance(result, dict) else None

    def _anchor(
        self,
        document: VishnuDocument,
        *,
        page: int,
        bbox: Iterable[float],
        kind: str,
        text: str = "",
        confidence: float = 1.0,
        source: dict[str, Any] | None = None,
    ) -> VisualEvidenceAnchor:
        coords = tuple(float(value) for value in bbox)
        if len(coords) != 4:
            raise Stage18PolicyError("Stage 18 evidence bbox requires four coordinates")
        anchor_id = _stable_id("vev", document.sha256, page, coords, kind, text)
        return VisualEvidenceAnchor(
            anchor_id=anchor_id,
            document_id=document.document_id,
            document_sha256=document.sha256,
            page=int(page),
            bbox=coords,
            kind=str(kind),
            text=str(text),
            confidence=max(0.0, min(1.0, float(confidence))),
            source=dict(source or {}),
            model_id=self.model_id,
        )

    def _equations(self, document: VishnuDocument, page: int, image: Image.Image) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for block in self._page_blocks(document, page):
            text = str(block.text or "")
            matches = list(self._EQUATION_RE.finditer(text))
            if block.kind == "equation" and text.strip() and not matches:
                matches = [re.match(r".*", text, re.S)] if text else []
            for match in matches:
                if match is None:
                    continue
                value = str(match.group(0) or "").strip()
                bbox = block.source.bbox or [0.0, 0.0, float(image.width), float(image.height)]
                anchor = self._anchor(
                    document,
                    page=page,
                    bbox=bbox,
                    kind="equation",
                    text=value,
                    confidence=block.confidence if block.confidence is not None else 0.92,
                    source=block.source.compact(),
                )
                output.append(
                    {
                        "equation_id": _stable_id("eq", anchor.anchor_id, value),
                        "text": value,
                        "variables": sorted(set(re.findall(r"\b[A-Za-z][A-Za-z0-9_]*\b", value)))[:40],
                        "operators": sorted(set(ch for ch in value if ch in "=+-*/^∑∫√≈≠≤≥±×÷∞∂∇")),
                        "page": page,
                        "bbox": list(anchor.bbox),
                        "confidence": anchor.confidence,
                        "evidence_anchor_ids": [anchor.anchor_id],
                        "evidence": anchor.public(),
                    }
                )
        return output

    def analyze(
        self,
        document: VishnuDocument,
        *,
        raw_content: bytes | None = None,
        real_world_qualification: dict[str, Any] | None = None,
    ) -> MultimodalDocumentGraph:
        if not isinstance(document, VishnuDocument):
            raise TypeError("Stage 18 requires VishnuDocument input")
        report = dict(real_world_qualification or {})
        qualified = bool(
            report.get("qualified") is True
            and report.get("real_world_corpus_qualified") is True
            and report.get("synthetic_evidence_can_qualify") is False
            and str(report.get("evidence_sha256") or "").strip()
        )
        graph = MultimodalDocumentGraph(
            document_id=document.document_id,
            document_sha256=document.sha256,
            filename=document.filename,
            model_versions={
                "stage18": self.version,
                "parser": document.parser_version,
                "layout": document.layout_version,
                "ocr": str(document.ocr_version or ""),
            },
            real_world_corpus_qualified=qualified,
            real_world_evidence_sha256=str(report.get("evidence_sha256")) if qualified else None,
        )
        pages = self.decode_pages(
            raw_content,
            filename=document.filename,
            detected_mime=document.detected_mime,
            content_kind=document.content_kind,
        )
        if not pages:
            # Non-visual documents remain valid Stage 18 records; no visual claim
            # is manufactured from text-only input.
            graph.warnings.append("no_renderable_visual_pages")
            return graph

        for page_index, image in enumerate(pages, start=1):
            gray, ink = self._visual_arrays(image)
            lines = self._line_geometry(ink)
            bars = self._bar_candidates(ink)
            boxes = self._box_candidates(lines, image)
            page_text = self._page_text(document, page_index)
            page_tokens = _tokens(page_text)
            page_summary = {
                "page": page_index,
                "width": image.width,
                "height": image.height,
                "ink_density": float(np.mean(ink)),
                "horizontal_rules": len(lines["horizontal"]),
                "vertical_rules": len(lines["vertical"]),
                "boxes": len(boxes),
                "bars": len(bars),
            }
            graph.page_summaries.append(page_summary)

            if len(bars) >= 3:
                chart_bbox = [
                    min(item["bbox"][0] for item in bars),
                    min(item["bbox"][1] for item in bars),
                    max(item["bbox"][2] for item in bars),
                    max(item["bbox"][3] for item in bars),
                ]
                anchor = self._anchor(
                    document,
                    page=page_index,
                    bbox=chart_bbox,
                    kind="chart",
                    text=page_text[:1000],
                    confidence=0.88,
                    source={"detector": "bar_geometry"},
                )
                values = [float(item["relative_value"]) for item in bars]
                chart = {
                    "chart_id": _stable_id("chart", anchor.anchor_id),
                    "chart_type": "bar_chart",
                    "page": page_index,
                    "bbox": chart_bbox,
                    "series": [{"series_id": "series_0", "bars": bars, "unit": None}],
                    "max_index": int(np.argmax(values)),
                    "min_index": int(np.argmin(values)),
                    "trend": "mixed" if len(set(round(value, 2) for value in values)) > 1 else "flat",
                    "confidence": 0.88,
                    "evidence_anchor_ids": [anchor.anchor_id],
                }
                learned = self._learned_label(
                    "stage18_chart_type",
                    {"text": page_text, "visual_features": page_summary, "candidate": "bar_chart"},
                )
                if learned and learned.get("accepted") is not False:
                    chart["learned_label"] = learned.get("label")
                    chart["learned_confidence"] = learned.get("confidence")
                graph.charts.append(chart)
                graph.evidence.append(anchor.public())
                graph.visual_claims.extend(
                    [
                        {
                            "claim_id": _stable_id("vclaim", chart["chart_id"], "maximum"),
                            "kind": "chart_maximum",
                            "value": chart["max_index"],
                            "confidence": 0.88,
                            "evidence_anchor_ids": [anchor.anchor_id],
                        },
                        {
                            "claim_id": _stable_id("vclaim", chart["chart_id"], "minimum"),
                            "kind": "chart_minimum",
                            "value": chart["min_index"],
                            "confidence": 0.88,
                            "evidence_anchor_ids": [anchor.anchor_id],
                        },
                    ]
                )
            elif len(lines["horizontal"]) >= 1 and len(lines["vertical"]) >= 1 and ({"chart", "graph", "trend", "series"} & page_tokens):
                anchor = self._anchor(
                    document,
                    page=page_index,
                    bbox=[0, 0, image.width, image.height],
                    kind="chart",
                    text=page_text[:1000],
                    confidence=0.62,
                    source={"detector": "axes_and_text"},
                )
                graph.charts.append(
                    {
                        "chart_id": _stable_id("chart", anchor.anchor_id),
                        "chart_type": "line_or_scatter_chart",
                        "page": page_index,
                        "bbox": [0, 0, image.width, image.height],
                        "series": [],
                        "confidence": 0.62,
                        "evidence_anchor_ids": [anchor.anchor_id],
                    }
                )
                graph.evidence.append(anchor.public())

            if len(boxes) >= 3 and (len(lines["horizontal"]) + len(lines["vertical"]) >= 4):
                anchor = self._anchor(
                    document,
                    page=page_index,
                    bbox=[0, 0, image.width, image.height],
                    kind="diagram",
                    text=page_text[:1000],
                    confidence=min(0.95, 0.55 + len(boxes) * 0.03),
                    source={"detector": "boxes_and_connectors"},
                )
                diagram = {
                    "diagram_id": _stable_id("diagram", anchor.anchor_id),
                    "diagram_type": "flow_or_architecture_diagram",
                    "page": page_index,
                    "bbox": [0, 0, image.width, image.height],
                    "nodes": [
                        {"node_id": f"n{index}", "bbox": item["bbox"], "label": None}
                        for index, item in enumerate(boxes[:24])
                    ],
                    "edges": [],
                    "confidence": anchor.confidence,
                    "evidence_anchor_ids": [anchor.anchor_id],
                }
                learned = self._learned_label(
                    "stage18_diagram_type",
                    {"text": page_text, "visual_features": page_summary, "candidate": diagram["diagram_type"]},
                )
                if learned and learned.get("accepted") is not False:
                    diagram["learned_label"] = learned.get("label")
                    diagram["learned_confidence"] = learned.get("confidence")
                graph.diagrams.append(diagram)
                graph.evidence.append(anchor.public())

            equations = self._equations(document, page_index, image)
            for equation in equations:
                graph.equations.append({key: value for key, value in equation.items() if key != "evidence"})
                graph.evidence.append(equation["evidence"])

            figure_blocks = [block for block in self._page_blocks(document, page_index) if block.kind in {"figure", "image", "chart"}]
            for block_index, block in enumerate(figure_blocks):
                bbox = block.source.bbox or [0, 0, image.width, image.height]
                anchor = self._anchor(
                    document,
                    page=page_index,
                    bbox=bbox,
                    kind="figure",
                    text=block.text,
                    confidence=block.confidence if block.confidence is not None else 0.80,
                    source=block.source.compact(),
                )
                graph.figures.append(
                    {
                        "figure_id": _stable_id("figure", anchor.anchor_id, block_index),
                        "page": page_index,
                        "bbox": list(anchor.bbox),
                        "caption": block.text.strip() or None,
                        "confidence": anchor.confidence,
                        "evidence_anchor_ids": [anchor.anchor_id],
                    }
                )
                graph.evidence.append(anchor.public())

            ui_matches: list[tuple[str, VishnuBlock]] = []
            for block in self._page_blocks(document, page_index):
                normalized = _norm(block.text)
                if not normalized:
                    continue
                for action in self._UI_ACTIONS:
                    if normalized == action or normalized.startswith(action + " ") or normalized.endswith(" " + action):
                        ui_matches.append((action, block))
                        break
                if self._ERROR_RE.search(normalized):
                    ui_matches.append(("error_message", block))
            screenshot_like = "screenshot" in _norm(document.metadata) or document.metadata.get("capture_kind") == "screenshot"
            if ui_matches or (screenshot_like and len(boxes) >= 2):
                for index, (role, block) in enumerate(ui_matches[:80]):
                    bbox = block.source.bbox or [0, 0, image.width, image.height]
                    anchor = self._anchor(
                        document,
                        page=page_index,
                        bbox=bbox,
                        kind="ui_element",
                        text=block.text,
                        confidence=block.confidence if block.confidence is not None else 0.84,
                        source=block.source.compact(),
                    )
                    element_type = "error" if role == "error_message" else "button"
                    graph.ui_elements.append(
                        {
                            "ui_element_id": _stable_id("ui", anchor.anchor_id, index),
                            "element_type": element_type,
                            "action": None if role == "error_message" else role,
                            "text": block.text.strip(),
                            "page": page_index,
                            "bbox": list(anchor.bbox),
                            "confidence": anchor.confidence,
                            "evidence_anchor_ids": [anchor.anchor_id],
                        }
                    )
                    graph.evidence.append(anchor.public())

        graph.evidence = list({str(item["anchor_id"]): item for item in graph.evidence}.values())
        return graph

    @staticmethod
    def answer(graph: MultimodalDocumentGraph, question: str) -> dict[str, Any]:
        query = _norm(question)
        tokens = _tokens(query)
        evidence = {str(item.get("anchor_id")): item for item in graph.evidence}

        def citations(ids: Iterable[str]) -> list[dict[str, Any]]:
            return [evidence[item] for item in ids if item in evidence]

        if graph.charts and ({"chart", "graph", "highest", "largest", "maximum", "lowest", "smallest", "minimum", "trend"} & tokens):
            chart = graph.charts[0]
            bars = list((chart.get("series") or [{}])[0].get("bars") or []) if chart.get("series") else []
            if bars and ({"highest", "largest", "maximum"} & tokens):
                index = int(chart.get("max_index") or 0)
                bar = bars[index]
                answer = f"Bar {index + 1} is the highest detected bar with relative value {float(bar.get('relative_value') or 0.0):.3f}."
            elif bars and ({"lowest", "smallest", "minimum"} & tokens):
                index = int(chart.get("min_index") or 0)
                bar = bars[index]
                answer = f"Bar {index + 1} is the lowest detected bar with relative value {float(bar.get('relative_value') or 0.0):.3f}."
            else:
                answer = f"Detected a {chart.get('chart_type')} with {len(bars)} measurable bars." if bars else f"Detected a {chart.get('chart_type')}."
            refs = citations(chart.get("evidence_anchor_ids") or [])
            return {"answered": bool(refs), "grounded": bool(refs), "answer": answer if refs else None, "confidence": chart.get("confidence", 0.0), "citations": refs, "source_kind": "chart"}

        if graph.diagrams and ({"diagram", "architecture", "flow", "nodes", "boxes"} & tokens):
            diagram = graph.diagrams[0]
            refs = citations(diagram.get("evidence_anchor_ids") or [])
            answer = f"Detected {len(diagram.get('nodes') or [])} diagram nodes in a {diagram.get('diagram_type')}."
            return {"answered": bool(refs), "grounded": bool(refs), "answer": answer if refs else None, "confidence": diagram.get("confidence", 0.0), "citations": refs, "source_kind": "diagram"}

        if graph.equations and ({"equation", "formula", "variable", "variables", "math"} & tokens):
            equation = graph.equations[0]
            refs = citations(equation.get("evidence_anchor_ids") or [])
            answer = f"Equation: {equation.get('text')}. Variables: {', '.join(equation.get('variables') or []) or 'none detected'}."
            return {"answered": bool(refs), "grounded": bool(refs), "answer": answer if refs else None, "confidence": equation.get("confidence", 0.0), "citations": refs, "source_kind": "equation"}

        if graph.ui_elements and ({"button", "click", "next", "error", "warning", "screen", "ui"} & tokens):
            candidates = graph.ui_elements
            if "error" in tokens or "warning" in tokens:
                candidates = [item for item in candidates if item.get("element_type") == "error"] or candidates
            elif "next" in tokens:
                candidates = [item for item in candidates if item.get("action") == "next"] or candidates
            item = candidates[0]
            refs = citations(item.get("evidence_anchor_ids") or [])
            if item.get("element_type") == "error":
                answer = f"The screen contains this error or warning: {item.get('text')}."
            else:
                answer = f"Detected {item.get('element_type')} '{item.get('text')}' at bounding box {item.get('bbox')}."
            return {"answered": bool(refs), "grounded": bool(refs), "answer": answer if refs else None, "confidence": item.get("confidence", 0.0), "citations": refs, "source_kind": "ui"}

        return {
            "answered": False,
            "grounded": False,
            "answer": None,
            "confidence": 0.0,
            "citations": [],
            "reason": "unsupported_by_visual_evidence",
        }


class Stage18ProductionMultimodalRuntime(Stage17ProductionContentRuntime):
    """Scope-isolated production Stage 18 runtime over completed Stage 17 state."""

    version = "vishnu-production-multimodal-runtime/18.1"
    schema_version = 1

    def __init__(
        self,
        db_path: str | Path,
        *,
        understanding=None,
        visual_analyzer: Stage18VisualAnalyzer | None = None,
    ):
        super().__init__(db_path, understanding=understanding)
        self.visual_analyzer = visual_analyzer or Stage18VisualAnalyzer()
        self.stage18_lock = RLock()
        self._init_stage18()

    def _init_stage18(self) -> None:
        with self._con() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS stage18_multimodal_intelligence(
                    document_id TEXT NOT NULL,
                    scope_type TEXT NOT NULL,
                    scope_id TEXT NOT NULL,
                    object_sha256 TEXT NOT NULL,
                    state TEXT NOT NULL,
                    runtime_version TEXT NOT NULL,
                    version_fingerprint TEXT NOT NULL,
                    graph_sha256 TEXT,
                    graph_json TEXT,
                    real_world_corpus_qualified INTEGER NOT NULL DEFAULT 0,
                    real_world_evidence_sha256 TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    error_code TEXT,
                    error_message TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    PRIMARY KEY(document_id,scope_type,scope_id)
                );
                CREATE INDEX IF NOT EXISTS idx_stage18_scope
                    ON stage18_multimodal_intelligence(scope_type,scope_id,state,updated_at);
                """
            )

    def version_manifest(self, document: VishnuDocument) -> dict[str, Any]:
        return {
            **super().version_manifest(document),
            "stage18_runtime": self.version,
            "stage18_visual_analyzer": self.visual_analyzer.version,
        }

    def stage18_version_fingerprint(self, document: VishnuDocument) -> str:
        return hashlib.sha256(_canonical(self.version_manifest(document)).encode("utf-8")).hexdigest()

    def stage18_status(self, *, document_id: str, scope_type: str, scope_id: str) -> dict[str, Any] | None:
        st, si = self._scope(scope_type, scope_id)
        with self._con() as con:
            row = con.execute(
                "SELECT * FROM stage18_multimodal_intelligence WHERE document_id=? AND scope_type=? AND scope_id=?",
                (str(document_id), st, si),
            ).fetchone()
        if not row:
            return None
        item = dict(row)
        item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
        item.pop("graph_json", None)
        item["real_world_corpus_qualified"] = bool(item["real_world_corpus_qualified"])
        return item

    def multimodal_graph(self, *, document_id: str, scope_type: str, scope_id: str) -> MultimodalDocumentGraph | None:
        st, si = self._scope(scope_type, scope_id)
        with self._con() as con:
            row = con.execute(
                "SELECT graph_json,state FROM stage18_multimodal_intelligence WHERE document_id=? AND scope_type=? AND scope_id=?",
                (str(document_id), st, si),
            ).fetchone()
        if not row or row["state"] != "completed" or not row["graph_json"]:
            return None
        payload = json.loads(row["graph_json"])
        allowed = {
            "document_id", "document_sha256", "filename", "charts", "diagrams", "equations",
            "figures", "ui_elements", "visual_claims", "evidence", "page_summaries",
            "model_versions", "warnings", "real_world_corpus_qualified", "real_world_evidence_sha256",
        }
        return MultimodalDocumentGraph(**{key: payload[key] for key in allowed if key in payload})

    def needs_reprocessing(self, document: VishnuDocument, *, scope_type: str, scope_id: str, extraction_version: int = 1) -> bool:
        if super().needs_reprocessing(document, scope_type=scope_type, scope_id=scope_id, extraction_version=extraction_version):
            return True
        status = self.stage18_status(document_id=document.document_id, scope_type=scope_type, scope_id=scope_id)
        if not status or status.get("state") != "completed":
            return True
        return status.get("version_fingerprint") != self.stage18_version_fingerprint(document)

    def process(
        self,
        document: VishnuDocument,
        *,
        scope_type: str,
        scope_id: str,
        object_sha256: str | None = None,
        extraction_version: int = 1,
        metadata: dict | None = None,
        raw_content: bytes | None = None,
        real_world_qualification: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        base = super().process(
            document,
            scope_type=scope_type,
            scope_id=scope_id,
            object_sha256=object_sha256,
            extraction_version=extraction_version,
            metadata=metadata,
        )
        if base.get("state") != "completed":
            raise RuntimeError("Stage 18 requires completed Stage 17 intelligence")
        st, si = self._scope(scope_type, scope_id)
        object_sha = str(object_sha256 or document.sha256).strip().lower()
        fingerprint = self.stage18_version_fingerprint(document)
        current = self.stage18_status(document_id=document.document_id, scope_type=st, scope_id=si)
        if current and current.get("state") == "completed" and current.get("object_sha256") == object_sha and current.get("version_fingerprint") == fingerprint:
            return {**current, "stage17": base}

        stamp = _now()
        with self.stage18_lock, self._con() as con:
            con.execute(
                """INSERT INTO stage18_multimodal_intelligence(
                    document_id,scope_type,scope_id,object_sha256,state,runtime_version,version_fingerprint,
                    created_at,updated_at,metadata_json)
                    VALUES(?,?,?,?, 'running', ?,?,?,?,?)
                    ON CONFLICT(document_id,scope_type,scope_id) DO UPDATE SET
                    object_sha256=excluded.object_sha256,state='running',runtime_version=excluded.runtime_version,
                    version_fingerprint=excluded.version_fingerprint,updated_at=excluded.updated_at,completed_at=NULL,
                    error_code=NULL,error_message=NULL,metadata_json=excluded.metadata_json""",
                (document.document_id, st, si, object_sha, self.version, fingerprint, stamp, stamp, _canonical(metadata or {})),
            )
        try:
            graph = self.visual_analyzer.analyze(
                document,
                raw_content=raw_content,
                real_world_qualification=real_world_qualification,
            )
            payload = graph.public()
            graph_sha = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
            completed = _now()
            with self._con() as con:
                con.execute(
                    """UPDATE stage18_multimodal_intelligence SET state='completed',graph_sha256=?,graph_json=?,
                       real_world_corpus_qualified=?,real_world_evidence_sha256=?,updated_at=?,completed_at=?
                       WHERE document_id=? AND scope_type=? AND scope_id=?""",
                    (
                        graph_sha,
                        _canonical(payload),
                        int(graph.real_world_corpus_qualified),
                        graph.real_world_evidence_sha256,
                        completed,
                        completed,
                        document.document_id,
                        st,
                        si,
                    ),
                )
            status = self.stage18_status(document_id=document.document_id, scope_type=st, scope_id=si) or {}
            return {**status, "stage17": base}
        except Exception as exc:
            with self._con() as con:
                con.execute(
                    "UPDATE stage18_multimodal_intelligence SET state='failed',updated_at=?,error_code=?,error_message=? WHERE document_id=? AND scope_type=? AND scope_id=?",
                    (_now(), type(exc).__name__, str(exc)[:2000], document.document_id, st, si),
                )
            raise

    def answer_visual(self, question: str, *, scope_type: str, scope_id: str, document_id: str | None = None) -> dict[str, Any]:
        st, si = self._scope(scope_type, scope_id)
        sql = "SELECT document_id,graph_json FROM stage18_multimodal_intelligence WHERE scope_type=? AND scope_id=? AND state='completed' AND graph_json IS NOT NULL"
        args: list[Any] = [st, si]
        if document_id is not None:
            sql += " AND document_id=?"
            args.append(str(document_id))
        sql += " ORDER BY updated_at DESC LIMIT 100"
        with self._con() as con:
            rows = con.execute(sql, args).fetchall()
        answers: list[dict[str, Any]] = []
        for row in rows:
            payload = json.loads(row["graph_json"])
            allowed = {
                "document_id", "document_sha256", "filename", "charts", "diagrams", "equations",
                "figures", "ui_elements", "visual_claims", "evidence", "page_summaries",
                "model_versions", "warnings", "real_world_corpus_qualified", "real_world_evidence_sha256",
            }
            graph = MultimodalDocumentGraph(**{key: payload[key] for key in allowed if key in payload})
            result = self.visual_analyzer.answer(graph, question)
            if result.get("answered") and result.get("grounded") and result.get("citations"):
                answers.append({**result, "document_id": str(row["document_id"])})
        if not answers:
            return {
                "stage": 18,
                "answered": False,
                "grounded": False,
                "answer": None,
                "reason": "unsupported_by_visual_evidence",
                "citations": [],
                "scope_type": st,
                "scope_id": si,
                "document_id": document_id,
            }
        answers.sort(key=lambda item: (-float(item.get("confidence") or 0.0), item["document_id"]))
        return {"stage": 18, "scope_type": st, "scope_id": si, **answers[0], "candidate_documents": len(answers)}

    def compare_visual(self, *, first_document_id: str, second_document_id: str, scope_type: str, scope_id: str) -> dict[str, Any]:
        first = self.multimodal_graph(document_id=first_document_id, scope_type=scope_type, scope_id=scope_id)
        second = self.multimodal_graph(document_id=second_document_id, scope_type=scope_type, scope_id=scope_id)
        if first is None or second is None:
            raise KeyError("Both documents must have completed Stage 18 intelligence")
        return {
            "stage": 18,
            "first_document_id": first_document_id,
            "second_document_id": second_document_id,
            "chart_count_delta": len(second.charts) - len(first.charts),
            "diagram_count_delta": len(second.diagrams) - len(first.diagrams),
            "equation_count_delta": len(second.equations) - len(first.equations),
            "ui_element_count_delta": len(second.ui_elements) - len(first.ui_elements),
            "grounded": True,
            "foundation_model": False,
        }
