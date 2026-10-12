from __future__ import annotations

import hashlib
import re
from typing import Any

from .semantic import extract_entities
from .stage17_runtime import Stage17ProductionContentRuntime as _Stage17BaseRuntime


def _tokens(value: str) -> set[str]:
    return {token.casefold() for token in re.findall(r"[\w@.+#/%-]{2,}", str(value or ""), flags=re.UNICODE)}


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def _link_id(kind: str, value: str, documents: list[str]) -> str:
    payload = "\0".join([kind, value, *documents])
    return "link_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


_EVIDENCE_FIELDS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("invoice_number", re.compile(r"\b(?:invoice\s*(?:no\.?|number|#))\s*[:#-]?\s*([A-Z0-9][A-Z0-9._/-]{1,40})", re.I)),
    ("purchase_order_number", re.compile(r"\b(?:purchase\s*order|po)\s*(?:no\.?|number|#)?\s*[:#-]?\s*([A-Z0-9][A-Z0-9._/-]{1,40})", re.I)),
    ("account_number", re.compile(r"\baccount\s*(?:no\.?|number|#)\s*[:#-]?\s*([A-Z0-9*][A-Z0-9*._/-]{2,40})", re.I)),
    ("reference_number", re.compile(r"\b(?:reference|ref)\s*(?:no\.?|number|#)?\s*[:#-]?\s*([A-Z0-9][A-Z0-9._/-]{1,40})", re.I)),
)
_ORGANIZATION = re.compile(
    r"\b([A-Z][\w&.'-]*(?:\s+[A-Z][\w&.'-]*){0,5}\s+(?:Inc\.?|LLC|Ltd\.?|Limited|Corp\.?|Corporation|Company|Co\.?|GmbH|AG|PLC|LLP|Technologies|Systems|Group))\b"
)


class Stage17ProductionContentRuntime(_Stage17BaseRuntime):
    """Production-hardened Stage 17 runtime.

    The durable Stage 17 store remains the processing authority. Grounded
    retrieval composes Stage 16 graphs with the already-populated scope-isolated
    LocalSemanticGraph so cross-document links never depend on a lossy public
    graph projection or on re-running a model at query time.
    """

    version = "vishnu-production-content-runtime/17.3"

    @staticmethod
    def _structured_field_answer(graph, question: str) -> dict[str, Any] | None:
        question_tokens = _tokens(question)
        if not question_tokens:
            return None
        evidence = {str(item.get("anchor_id")): item for item in graph.evidence if item.get("anchor_id")}
        candidates: list[tuple[float, str, list[dict[str, Any]], str]] = []
        for field in graph.fields:
            name = str(field.get("name") or "")
            name_tokens = _tokens(name.replace("_", " "))
            if not name_tokens or not name_tokens.issubset(question_tokens):
                continue
            citations = [evidence[anchor_id] for anchor_id in field.get("evidence_anchor_ids", []) if anchor_id in evidence]
            if not citations:
                continue
            confidence = max(0.0, min(0.99, float(field.get("confidence") or 0.0)))
            candidates.append((confidence, str(field.get("value") or ""), citations, name))

        # Legacy Knowledge chunks can predate Stage 16 field projection. Recover
        # only exact deterministic identifiers from persisted evidence text; the
        # evidence anchor itself remains the citation authority.
        for field_name, pattern in _EVIDENCE_FIELDS:
            name_tokens = _tokens(field_name.replace("_", " "))
            if not name_tokens.issubset(question_tokens):
                continue
            for anchor in graph.evidence:
                match = pattern.search(str(anchor.get("text") or ""))
                if match:
                    candidates.append((0.98, str(match.group(1)).strip(), [anchor], field_name))

        if not candidates:
            return None
        candidates.sort(key=lambda item: (-item[0], item[3], item[1]))
        confidence, answer, citations, field_name = candidates[0]
        return {
            "answered": True,
            "answer": answer,
            "confidence": confidence,
            "source_kind": "field",
            "field_name": field_name,
            "citations": citations,
            "grounded": True,
        }

    def answer(self, question: str, *, scope_type: str, scope_id: str, document_id: str | None = None) -> dict[str, Any]:
        st, si = self._scope(scope_type, scope_id)
        answers: list[dict[str, Any]] = []
        for graph in self._candidate_graphs(scope_type=st, scope_id=si, document_id=document_id):
            result = self._structured_field_answer(graph, question)
            if result is None:
                result = self.understanding.answer(graph, question)
            if result.get("answered") and result.get("grounded") and result.get("citations"):
                answers.append({**result, "document_id": graph.document_id, "document_type": graph.document_type})
        if not answers:
            return {
                "stage": 17,
                "answered": False,
                "grounded": False,
                "answer": None,
                "reason": "unsupported_by_available_evidence",
                "citations": [],
                "scope_type": st,
                "scope_id": si,
                "document_id": document_id,
            }
        answers.sort(key=lambda item: (-float(item.get("confidence") or 0.0), str(item["document_id"])))
        best = answers[0]
        return {"stage": 17, "scope_type": st, "scope_id": si, **best, "candidate_documents": len(answers)}

    def _semantic_graph_links(self, *, scope_type: str, scope_id: str, limit: int) -> list[dict[str, Any]]:
        """Project the canonical LocalSemanticGraph links into Stage 17 shape."""
        out: list[dict[str, Any]] = []
        for item in self.semantic_graph.cross_document_links(scope_type=scope_type, scope_id=scope_id, limit=limit):
            by_document: dict[str, list[dict[str, Any]]] = {}
            for mention in item.get("mentions", []):
                document_id = str(mention.get("document_id") or "").strip()
                if not document_id:
                    continue
                by_document.setdefault(document_id, []).append(
                    {
                        "position": mention.get("position"),
                        "excerpt": mention.get("excerpt"),
                        "confidence": mention.get("confidence"),
                        "citation": mention.get("citation"),
                    }
                )
            documents = sorted(by_document)
            if len(documents) <= 1:
                continue
            kind = str(item.get("kind") or "entity")
            canonical = str(item.get("canonical") or "").strip()
            value = _normalized(canonical)
            out.append(
                {
                    "link_id": _link_id(kind, value, documents),
                    "kind": kind,
                    "canonical": canonical,
                    "normalized_value": value,
                    "document_ids": documents,
                    "members": [
                        {"document_id": document_id, "mentions": by_document[document_id]}
                        for document_id in documents
                    ],
                    "derived_from": "semantic_graph",
                    "grounded": True,
                }
            )
        return out

    def links(self, *, scope_type: str, scope_id: str, limit: int = 100) -> list[dict[str, Any]]:
        st, si = self._scope(scope_type, scope_id)
        graphs = self._candidate_graphs(scope_type=st, scope_id=si, limit=limit)
        links = list(self.understanding.link_documents(graphs))
        existing = {(str(item.get("kind")), str(item.get("normalized_value"))) for item in links}

        # The LocalSemanticGraph is indexed from the canonical raw VishnuDocument
        # during Stage 17 processing and therefore retains exact entity mentions
        # even when a Stage 16 public graph projection omits text needed for a
        # query-time reconstruction. Reuse that authority before any fallback.
        for link in self._semantic_graph_links(scope_type=st, scope_id=si, limit=limit):
            key = (str(link.get("kind")), str(link.get("normalized_value")))
            if key not in existing:
                links.append(link)
                existing.add(key)

        # Defensive compatibility fallback for old Stage 17 graph records that
        # may contain evidence text but predate the semantic-graph projection.
        evidence_entities: dict[tuple[str, str], dict[str, list[str]]] = {}
        for graph in graphs:
            for anchor in graph.evidence:
                anchor_id = str(anchor.get("anchor_id") or "")
                text = str(anchor.get("text") or "")
                entities = list(extract_entities(text))
                seen = {(str(item["kind"]), str(item["normalized"])) for item in entities}
                for match in _ORGANIZATION.finditer(text):
                    canonical = str(match.group(1)).strip()
                    normalized = _normalized(canonical)
                    if ("organization", normalized) not in seen:
                        entities.append({"kind": "organization", "normalized": normalized, "canonical": canonical})
                        seen.add(("organization", normalized))
                for entity in entities:
                    key = (str(entity["kind"]), str(entity["normalized"]))
                    by_document = evidence_entities.setdefault(key, {})
                    by_document.setdefault(graph.document_id, [])
                    if anchor_id and anchor_id not in by_document[graph.document_id]:
                        by_document[graph.document_id].append(anchor_id)

        for (kind, value), by_document in sorted(evidence_entities.items()):
            documents = sorted(by_document)
            if len(documents) <= 1 or (kind, value) in existing:
                continue
            links.append(
                {
                    "link_id": _link_id(kind, value, documents),
                    "kind": kind,
                    "normalized_value": value,
                    "document_ids": documents,
                    "members": [
                        {"document_id": document_id, "evidence_anchor_ids": by_document[document_id]}
                        for document_id in documents
                    ],
                    "derived_from": "persisted_evidence",
                    "grounded": True,
                }
            )
            existing.add((kind, value))

        links.sort(key=lambda item: (str(item.get("kind")), str(item.get("normalized_value")), tuple(item.get("document_ids") or [])))
        return links[: max(1, min(int(limit), 500))]
