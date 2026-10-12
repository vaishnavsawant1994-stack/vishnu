from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from .models import SourceReference, VishnuBlock, VishnuDocument
from .semantic import LocalSemanticGraph, extract_entities


class Stage16PolicyError(ValueError):
    pass


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def _stable_id(prefix: str, *parts: Any) -> str:
    payload = "\0".join(_canonical(part) if isinstance(part, (dict, list, tuple)) else str(part) for part in parts)
    return f"{prefix}_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:24]}"


def _tokens(text: str) -> set[str]:
    return {token.casefold() for token in re.findall(r"[\w@.+#/%-]{2,}", str(text or ""), flags=re.UNICODE)}


DOCUMENT_TYPES = (
    "application",
    "bank_statement",
    "certificate",
    "contract",
    "email",
    "form",
    "invoice",
    "letter",
    "manual",
    "policy",
    "presentation",
    "purchase_order",
    "receipt",
    "report",
    "research_paper",
    "resume",
    "statement",
    "unknown",
)

_DOCUMENT_TYPE_CUES: dict[str, tuple[str, ...]] = {
    "invoice": ("invoice", "invoice no", "amount due", "bill to", "subtotal", "tax", "total"),
    "receipt": ("receipt", "payment received", "cash", "change", "merchant"),
    "purchase_order": ("purchase order", "po number", "ship to", "vendor", "ordered by"),
    "contract": ("agreement", "contract", "party", "parties", "effective date", "terms", "hereby", "shall"),
    "resume": ("curriculum vitae", "resume", "experience", "education", "skills", "employment"),
    "research_paper": ("abstract", "introduction", "methodology", "methods", "results", "references", "doi"),
    "bank_statement": ("account statement", "opening balance", "closing balance", "debit", "credit", "transaction"),
    "policy": ("policy", "purpose", "scope", "effective", "procedure", "compliance"),
    "manual": ("manual", "instructions", "warning", "installation", "troubleshooting", "chapter"),
    "report": ("executive summary", "findings", "recommendations", "appendix", "report"),
    "certificate": ("certificate", "certify", "awarded", "issued", "valid until"),
    "form": ("form", "please complete", "signature", "checkbox", "date of birth"),
    "application": ("application", "applicant", "apply", "declaration", "eligibility"),
    "letter": ("dear", "sincerely", "regards", "subject:"),
    "statement": ("statement", "balance", "period ending"),
    "presentation": ("agenda", "slide", "questions", "thank you"),
    "email": ("from:", "to:", "cc:", "subject:"),
}

_FIELD_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("invoice_number", re.compile(r"\b(?:invoice\s*(?:no\.?|number|#))\s*[:#-]?\s*([A-Z0-9][A-Z0-9._/-]{1,40})", re.I)),
    ("purchase_order_number", re.compile(r"\b(?:purchase\s*order|po)\s*(?:no\.?|number|#)?\s*[:#-]?\s*([A-Z0-9][A-Z0-9._/-]{1,40})", re.I)),
    ("account_number", re.compile(r"\baccount\s*(?:no\.?|number|#)\s*[:#-]?\s*([A-Z0-9*][A-Z0-9*._/-]{2,40})", re.I)),
    ("reference_number", re.compile(r"\b(?:reference|ref)\s*(?:no\.?|number|#)?\s*[:#-]?\s*([A-Z0-9][A-Z0-9._/-]{1,40})", re.I)),
    ("email", re.compile(r"\b([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})\b", re.I)),
    ("phone", re.compile(r"(?<!\w)(\+?[0-9][0-9 ()-]{6,}[0-9])\b")),
    ("date", re.compile(r"\b((?:(?:19|20)\d{2}[-/.][01]?\d[-/.][0-3]?\d)|(?:[0-3]?\d[-/.][01]?\d[-/.](?:19|20)?\d{2}))\b")),
    ("amount", re.compile(r"(?<!\w)([$€£₹]\s?[0-9][0-9,]*(?:\.\d{1,2})?)\b")),
)

_RELATION_PATTERNS: tuple[tuple[str, re.Pattern[str], str, str], ...] = (
    ("works_for", re.compile(r"\b([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){1,2})\s+(?:works|worked)\s+(?:at|for)\s+([A-Z][A-Za-z0-9&.'-]+(?:\s+[A-Z][A-Za-z0-9&.'-]+){0,5})\b"), "person", "organization"),
    ("signed_by", re.compile(r"\b(?:signed|approved)\s+by\s+([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){1,2})\b", re.I), "document", "person"),
    ("payable_to", re.compile(r"\b(?:payable\s+to|pay\s+to)\s+([A-Z][A-Za-z0-9&.'-]+(?:\s+[A-Z][A-Za-z0-9&.'-]+){0,5})\b", re.I), "document", "organization"),
)

_CLAIM_CUES = re.compile(r"\b(shall|must|will|is|are|was|were|has|have|agrees?|requires?|states?|reports?|total(?:s|ed)?|due|effective)\b", re.I)
_REFERENCE_RE = re.compile(r"\b(?:section|clause|article|figure|table|appendix|exhibit|footnote)\s+([A-Z0-9][A-Z0-9._-]*)\b", re.I)
_URL_RE = re.compile(r"\bhttps?://[^\s<>\"]+", re.I)
_DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.I)


@dataclass(frozen=True)
class EvidenceAnchor:
    anchor_id: str
    document_id: str
    document_sha256: str
    block_index: int
    page: int | None
    bbox: tuple[float, float, float, float] | None
    text: str
    text_start: int
    text_end: int
    confidence: float
    source: dict[str, Any]
    model_id: str

    def public(self) -> dict[str, Any]:
        value = asdict(self)
        value["bbox"] = list(self.bbox) if self.bbox else None
        return value


@dataclass
class DocumentGraph:
    document_id: str
    document_sha256: str
    filename: str
    document_type: str
    document_type_confidence: float
    nodes: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    sections: list[dict[str, Any]] = field(default_factory=list)
    fields: list[dict[str, Any]] = field(default_factory=list)
    entities: list[dict[str, Any]] = field(default_factory=list)
    relations: list[dict[str, Any]] = field(default_factory=list)
    claims: list[dict[str, Any]] = field(default_factory=list)
    references: list[dict[str, Any]] = field(default_factory=list)
    tables: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    model_versions: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def public(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "stage": 16,
            "document_id": self.document_id,
            "document_sha256": self.document_sha256,
            "filename": self.filename,
            "document_type": self.document_type,
            "document_type_confidence": self.document_type_confidence,
            "nodes": self.nodes,
            "edges": self.edges,
            "sections": self.sections,
            "fields": self.fields,
            "entities": self.entities,
            "relations": self.relations,
            "claims": self.claims,
            "references": self.references,
            "tables": self.tables,
            "evidence": self.evidence,
            "model_versions": self.model_versions,
            "warnings": self.warnings,
            "grounded_only": True,
            "contains_hidden_chain_of_thought": False,
            "foundation_model": False,
        }


class Stage16DocumentTypeClassifier:
    def classify(self, text: str, *, filename: str = "") -> dict[str, Any]:
        normalized = _norm(f"{filename}\n{text}")
        scores: dict[str, float] = {}
        for label, cues in _DOCUMENT_TYPE_CUES.items():
            hits = sum(1 for cue in cues if cue in normalized)
            if hits:
                scores[label] = hits / max(2.0, float(len(cues)))
        if not scores:
            return {"label": "unknown", "confidence": 0.0, "accepted": False, "alternatives": []}
        ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        best_label, best_score = ordered[0]
        confidence = min(0.99, 0.40 + best_score)
        accepted = confidence >= 0.55
        return {
            "label": best_label if accepted else "unknown",
            "raw_label": best_label,
            "confidence": confidence,
            "accepted": accepted,
            "alternatives": [{"label": label, "confidence": min(0.99, 0.40 + score)} for label, score in ordered[:3]],
        }


class Stage16DeepDocumentUnderstanding:
    """Grounded Stage 16 semantic runtime over Vishnu's canonical document blocks."""

    version = "vishnu-document-understanding/16.1"

    def __init__(self, *, classifier: Any | None = None, model_id: str = "vishnu-stage16-grounded-semantic-runtime-v1"):
        self.classifier = classifier or Stage16DocumentTypeClassifier()
        self.model_id = str(model_id)

    @staticmethod
    def _anchor(document: VishnuDocument, block: VishnuBlock, block_index: int, *, text_start: int = 0, text_end: int | None = None, model_id: str) -> EvidenceAnchor:
        text = str(block.text or "")
        end = len(text) if text_end is None else max(text_start, min(len(text), int(text_end)))
        bbox = None
        if block.source.bbox and len(block.source.bbox) == 4:
            bbox = tuple(float(value) for value in block.source.bbox)
        source = block.source.compact()
        anchor_id = _stable_id("ev", document.sha256, block_index, text_start, end, source)
        return EvidenceAnchor(
            anchor_id=anchor_id,
            document_id=document.document_id,
            document_sha256=document.sha256,
            block_index=block_index,
            page=block.source.page,
            bbox=bbox,
            text=text[text_start:end],
            text_start=text_start,
            text_end=end,
            confidence=max(0.0, min(1.0, float(block.confidence if block.confidence is not None else 1.0))),
            source=source,
            model_id=model_id,
        )

    @staticmethod
    def _node(kind: str, value: str, anchor_id: str, *, confidence: float = 1.0, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        normalized = _norm(value)
        return {
            "node_id": _stable_id("node", kind, normalized),
            "kind": kind,
            "value": str(value).strip(),
            "normalized": normalized,
            "confidence": max(0.0, min(1.0, float(confidence))),
            "evidence_anchor_ids": [anchor_id],
            "metadata": dict(metadata or {}),
        }

    @staticmethod
    def _infer_table_semantics(block: VishnuBlock, anchor_id: str) -> dict[str, Any] | None:
        if block.kind != "table" and not (isinstance(block.data, dict) and (block.data.get("kind") == "table" or block.data.get("cells"))):
            return None
        data = dict(block.data or {}) if isinstance(block.data, dict) else {}
        cells = [dict(cell) for cell in data.get("cells") or [] if isinstance(cell, dict)]
        columns: dict[int, dict[str, Any]] = {}
        rows: dict[int, list[dict[str, Any]]] = {}
        for cell in cells:
            row = int(cell.get("row") or 0)
            column = int(cell.get("column") or 0)
            rows.setdefault(row, []).append(cell)
            text = str(cell.get("text") or cell.get("value") or "").strip()
            cell_type = str(cell.get("cell_type") or "body")
            entry = columns.setdefault(column, {"column": column, "headers": [], "value_types": set()})
            if row == 0 or "header" in cell_type:
                if text:
                    entry["headers"].append(text)
            if text:
                if re.fullmatch(r"[$€£₹]?\s?[0-9][0-9,]*(?:\.\d+)?", text):
                    entry["value_types"].add("number")
                elif re.search(r"(?:19|20)\d{2}[-/.][01]?\d[-/.][0-3]?\d", text):
                    entry["value_types"].add("date")
                else:
                    entry["value_types"].add("text")
        normalized_columns = []
        for column in sorted(columns):
            item = columns[column]
            normalized_columns.append({"column": column, "headers": item["headers"], "value_types": sorted(item["value_types"])})
        return {
            "table_id": _stable_id("table", anchor_id),
            "evidence_anchor_ids": [anchor_id],
            "rows": len(rows),
            "columns": normalized_columns,
            "cells": cells,
            "semantic": True,
            "header_hierarchy": [item["headers"] for item in normalized_columns if item["headers"]],
        }

    def understand(self, document: VishnuDocument) -> DocumentGraph:
        if not isinstance(document, VishnuDocument):
            raise TypeError("Stage 16 requires VishnuDocument input")
        type_prediction = self.classifier.classify(document.full_text, filename=document.filename)
        graph = DocumentGraph(
            document_id=document.document_id,
            document_sha256=document.sha256,
            filename=document.filename,
            document_type=str(type_prediction.get("label") or "unknown"),
            document_type_confidence=float(type_prediction.get("confidence") or 0.0),
            model_versions={
                "stage16": self.version,
                "parser": document.parser_version,
                "layout": document.layout_version,
                "ocr": str(document.ocr_version or ""),
            },
        )
        document_node = self._node("document", document.filename or document.document_id, "", confidence=1.0, metadata={"document_id": document.document_id})
        document_node["node_id"] = _stable_id("node", "document", document.sha256)
        document_node["evidence_anchor_ids"] = []
        graph.nodes.append(document_node)

        entity_map: dict[tuple[str, str], dict[str, Any]] = {}
        current_section: dict[str, Any] | None = None
        page_seen: set[int] = set()

        for index, block in enumerate(document.blocks):
            text = str(block.text or "").strip()
            anchor = self._anchor(document, block, index, model_id=self.model_id)
            graph.evidence.append(anchor.public())
            anchor_id = anchor.anchor_id
            if anchor.page is not None:
                page_seen.add(int(anchor.page))

            block_node = self._node(
                f"block:{block.kind}", text or block.kind, anchor_id,
                confidence=anchor.confidence,
                metadata={"block_index": index, "source": anchor.source},
            )
            graph.nodes.append(block_node)
            graph.edges.append({
                "edge_id": _stable_id("edge", document_node["node_id"], "contains", block_node["node_id"], index),
                "subject_id": document_node["node_id"],
                "predicate": "contains",
                "object_id": block_node["node_id"],
                "confidence": anchor.confidence,
                "evidence_anchor_ids": [anchor_id],
            })

            if block.kind in {"title", "heading", "section", "subheading"} and text:
                level = 0 if block.kind == "title" else 1 if block.kind in {"heading", "section"} else 2
                section = {
                    "section_id": _stable_id("section", document.sha256, index, text),
                    "title": text,
                    "level": level,
                    "page": anchor.page,
                    "evidence_anchor_ids": [anchor_id],
                }
                if current_section and level > int(current_section.get("level") or 0):
                    section["parent_section_id"] = current_section["section_id"]
                graph.sections.append(section)
                current_section = section
            elif current_section:
                block_node["metadata"]["section_id"] = current_section["section_id"]

            if text:
                for entity in extract_entities(text):
                    key = (str(entity["kind"]), str(entity["normalized"]))
                    item = entity_map.get(key)
                    if item is None:
                        item = {
                            "entity_id": str(entity["entity_id"]),
                            "kind": str(entity["kind"]),
                            "canonical": str(entity["canonical"]),
                            "normalized": str(entity["normalized"]),
                            "confidence": anchor.confidence,
                            "evidence_anchor_ids": [anchor_id],
                        }
                        entity_map[key] = item
                    elif anchor_id not in item["evidence_anchor_ids"]:
                        item["evidence_anchor_ids"].append(anchor_id)
                        item["confidence"] = max(float(item["confidence"]), anchor.confidence)

                for field_name, pattern in _FIELD_PATTERNS:
                    for match in pattern.finditer(text):
                        value = str(match.group(1)).strip()
                        field = {
                            "field_id": _stable_id("field", document.sha256, field_name, _norm(value)),
                            "name": field_name,
                            "value": value,
                            "normalized_value": _norm(value),
                            "confidence": anchor.confidence,
                            "page": anchor.page,
                            "evidence_anchor_ids": [anchor_id],
                        }
                        if field not in graph.fields:
                            graph.fields.append(field)

                if block.kind in {"key_value", "form_field"} and isinstance(block.data, dict):
                    key = str(block.data.get("key") or block.data.get("name") or "field").strip()
                    value = block.data.get("value")
                    if value not in (None, ""):
                        graph.fields.append({
                            "field_id": _stable_id("field", document.sha256, key, _norm(value)),
                            "name": key,
                            "value": str(value),
                            "normalized_value": _norm(value),
                            "confidence": anchor.confidence,
                            "page": anchor.page,
                            "evidence_anchor_ids": [anchor_id],
                        })

                for predicate, pattern, subject_kind, object_kind in _RELATION_PATTERNS:
                    for match in pattern.finditer(text):
                        if subject_kind == "document":
                            subject_id = document_node["node_id"]
                        else:
                            subject_value = match.group(1)
                            subject_id = _stable_id("entity", subject_kind, _norm(subject_value))
                        if subject_kind == "document":
                            object_value = match.group(1)
                        else:
                            object_value = match.group(2)
                        object_id = _stable_id("entity", object_kind, _norm(object_value))
                        graph.relations.append({
                            "relation_id": _stable_id("relation", subject_id, predicate, object_id, anchor_id),
                            "subject_id": subject_id,
                            "predicate": predicate,
                            "object_id": object_id,
                            "object_value": object_value,
                            "confidence": min(0.95, anchor.confidence),
                            "evidence_anchor_ids": [anchor_id],
                        })

                sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", text) if part.strip()]
                for sentence in sentences:
                    if len(sentence) >= 8 and _CLAIM_CUES.search(sentence):
                        lower = sentence.casefold()
                        claim_type = "obligation" if re.search(r"\b(shall|must|required?)\b", lower) else "financial" if re.search(r"[$€£₹]|\b(total|amount|price|cost|due)\b", lower) else "factual"
                        graph.claims.append({
                            "claim_id": _stable_id("claim", document.sha256, sentence),
                            "claim_type": claim_type,
                            "text": sentence,
                            "confidence": min(0.95, anchor.confidence),
                            "page": anchor.page,
                            "evidence_anchor_ids": [anchor_id],
                        })

                for match in _REFERENCE_RE.finditer(text):
                    graph.references.append({
                        "reference_id": _stable_id("reference", document.sha256, match.group(0), anchor_id),
                        "kind": match.group(0).split()[0].casefold(),
                        "target": match.group(1),
                        "text": match.group(0),
                        "confidence": anchor.confidence,
                        "evidence_anchor_ids": [anchor_id],
                    })
                for pattern, kind in ((_URL_RE, "url"), (_DOI_RE, "doi")):
                    for match in pattern.finditer(text):
                        graph.references.append({
                            "reference_id": _stable_id("reference", document.sha256, match.group(0), anchor_id),
                            "kind": kind,
                            "target": match.group(0).rstrip(".,;)"),
                            "text": match.group(0).rstrip(".,;)"),
                            "confidence": anchor.confidence,
                            "evidence_anchor_ids": [anchor_id],
                        })

            table = self._infer_table_semantics(block, anchor_id)
            if table:
                graph.tables.append(table)

        graph.entities = sorted(entity_map.values(), key=lambda item: (item["kind"], item["normalized"]))
        for entity in graph.entities:
            graph.nodes.append({
                "node_id": entity["entity_id"],
                "kind": f"entity:{entity['kind']}",
                "value": entity["canonical"],
                "normalized": entity["normalized"],
                "confidence": entity["confidence"],
                "evidence_anchor_ids": entity["evidence_anchor_ids"],
                "metadata": {},
            })
        if len(page_seen) > 1:
            graph.model_versions["cross_page_context"] = "vishnu-cross-page/16.1"
        if graph.document_type == "unknown":
            graph.warnings.append("document_type_low_confidence")
        return graph

    def index_into_semantic_graph(self, document: VishnuDocument, store: LocalSemanticGraph, *, scope_type: str, scope_id: str) -> dict[str, Any]:
        graph = self.understand(document)
        base = store.index_document(document, scope_type=scope_type, scope_id=scope_id)
        return {"semantic_index": base, "document_graph": graph.public()}

    @staticmethod
    def _evidence_by_id(graph: DocumentGraph) -> dict[str, dict[str, Any]]:
        return {str(item["anchor_id"]): item for item in graph.evidence}

    def answer(self, graph: DocumentGraph, question: str, *, min_score: float = 0.22) -> dict[str, Any]:
        query_tokens = _tokens(question)
        if not query_tokens:
            raise Stage16PolicyError("grounded document question cannot be empty")
        evidence = self._evidence_by_id(graph)
        candidates: list[tuple[float, str, list[str], str]] = []
        for field in graph.fields:
            haystack = f"{field['name']} {field['value']}"
            overlap = len(query_tokens & _tokens(haystack)) / max(1, len(query_tokens))
            if overlap:
                candidates.append((overlap + 0.25, str(field["value"]), list(field["evidence_anchor_ids"]), "field"))
        for claim in graph.claims:
            overlap = len(query_tokens & _tokens(claim["text"])) / max(1, len(query_tokens))
            if overlap:
                candidates.append((overlap, str(claim["text"]), list(claim["evidence_anchor_ids"]), "claim"))
        for entity in graph.entities:
            overlap = len(query_tokens & _tokens(f"{entity['kind']} {entity['canonical']}")) / max(1, len(query_tokens))
            if overlap:
                candidates.append((overlap, str(entity["canonical"]), list(entity["evidence_anchor_ids"]), "entity"))
        for anchor in graph.evidence:
            overlap = len(query_tokens & _tokens(anchor.get("text") or "")) / max(1, len(query_tokens))
            if overlap:
                candidates.append((overlap * 0.9, str(anchor.get("text") or ""), [str(anchor["anchor_id"])], "evidence"))
        if not candidates:
            return {"answered": False, "answer": None, "confidence": 0.0, "reason": "unsupported_by_document", "citations": []}
        candidates.sort(key=lambda item: (-item[0], item[3], item[1]))
        score, answer, anchor_ids, source_kind = candidates[0]
        if score < float(min_score):
            return {"answered": False, "answer": None, "confidence": max(0.0, min(1.0, score)), "reason": "insufficient_grounding", "citations": []}
        citations = [evidence[anchor_id] for anchor_id in anchor_ids if anchor_id in evidence]
        if not citations:
            return {"answered": False, "answer": None, "confidence": 0.0, "reason": "missing_evidence_anchor", "citations": []}
        return {
            "answered": True,
            "answer": answer,
            "confidence": max(0.0, min(0.99, score)),
            "source_kind": source_kind,
            "citations": citations,
            "grounded": True,
        }

    @staticmethod
    def compare(left: DocumentGraph, right: DocumentGraph) -> dict[str, Any]:
        def keyed(items: Iterable[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
            return {str(item[key]): item for item in items}
        left_fields = {(str(item["name"]).casefold(), str(item["normalized_value"])): item for item in left.fields}
        right_fields = {(str(item["name"]).casefold(), str(item["normalized_value"])): item for item in right.fields}
        left_claims = keyed(left.claims, "claim_id")
        right_claims = keyed(right.claims, "claim_id")
        left_entities = {(item["kind"], item["normalized"]): item for item in left.entities}
        right_entities = {(item["kind"], item["normalized"]): item for item in right.entities}
        changes: list[dict[str, Any]] = []
        left_by_name: dict[str, set[str]] = {}
        right_by_name: dict[str, set[str]] = {}
        for name, value in left_fields:
            left_by_name.setdefault(name, set()).add(value)
        for name, value in right_fields:
            right_by_name.setdefault(name, set()).add(value)
        for name in sorted(set(left_by_name) | set(right_by_name)):
            if left_by_name.get(name, set()) != right_by_name.get(name, set()):
                changes.append({"kind": "field_change", "field": name, "before": sorted(left_by_name.get(name, set())), "after": sorted(right_by_name.get(name, set()))})
        for key in sorted(set(left_entities) - set(right_entities)):
            changes.append({"kind": "entity_removed", "entity": left_entities[key]})
        for key in sorted(set(right_entities) - set(left_entities)):
            changes.append({"kind": "entity_added", "entity": right_entities[key]})
        for claim_id in sorted(set(left_claims) - set(right_claims)):
            changes.append({"kind": "claim_removed", "claim": left_claims[claim_id]})
        for claim_id in sorted(set(right_claims) - set(left_claims)):
            changes.append({"kind": "claim_added", "claim": right_claims[claim_id]})
        return {
            "left_document_id": left.document_id,
            "right_document_id": right.document_id,
            "same_document_type": left.document_type == right.document_type,
            "changes": changes,
            "semantic_change_count": len(changes),
            "grounded": True,
        }

    @staticmethod
    def link_documents(graphs: Iterable[DocumentGraph]) -> list[dict[str, Any]]:
        rows = list(graphs)
        index: dict[tuple[str, str], list[tuple[str, str]]] = {}
        for graph in rows:
            for entity in graph.entities:
                index.setdefault((str(entity["kind"]), str(entity["normalized"])), []).append((graph.document_id, entity["entity_id"]))
            for field in graph.fields:
                if str(field["name"]) in {"invoice_number", "purchase_order_number", "account_number", "reference_number"}:
                    index.setdefault((str(field["name"]), str(field["normalized_value"])), []).append((graph.document_id, field["field_id"]))
        links = []
        for (kind, value), refs in sorted(index.items()):
            documents = sorted({document_id for document_id, _ in refs})
            if len(documents) > 1:
                links.append({
                    "link_id": _stable_id("link", kind, value, documents),
                    "kind": kind,
                    "normalized_value": value,
                    "document_ids": documents,
                    "members": [{"document_id": document_id, "node_id": node_id} for document_id, node_id in refs],
                })
        return links


class Stage16DeepDocumentUnderstandingProvider:
    """Thin provider for the canonical VishnuDocument ingestion surface."""

    name = "vishnu-stage16-deep-document-understanding-v1"
    version = "vishnu-document-understanding/16.1"
    external = False

    def __init__(self, runtime: Stage16DeepDocumentUnderstanding | None = None):
        self.runtime = runtime or Stage16DeepDocumentUnderstanding()

    def analyze(self, document: VishnuDocument) -> dict[str, Any]:
        return self.runtime.understand(document).public()

    def answer(self, document: VishnuDocument, question: str) -> dict[str, Any]:
        graph = self.runtime.understand(document)
        return self.runtime.answer(graph, question)
