from __future__ import annotations

from collections import OrderedDict, defaultdict
from dataclasses import dataclass
import hashlib
import re
import threading
import time
from typing import Any, Callable, Iterable, Mapping

from .memory import LabMemory


_TOKEN_RE = re.compile(r"[a-zA-Z0-9_]{2,}")


@dataclass(frozen=True)
class RetrievedRecord:
    id: str
    kind: str
    score: float
    created_at: float
    payload: dict[str, Any]


class AcceleratedLabRetriever:
    """Hot working-set + inverted lexical/semantic retrieval for Lab records."""

    def __init__(
        self,
        memory: LabMemory,
        *,
        index_limit: int = 5000,
        hot_limit: int = 256,
        embedding_callback: Callable[[str], list[float]] | None = None,
        vector_candidate_limit: int = 32,
    ):
        self.memory = memory
        self.index_limit = max(100, min(int(index_limit), 50000))
        self.hot_limit = max(32, min(int(hot_limit), 4096))
        self.embedding_callback = embedding_callback
        self.vector_candidate_limit = max(4, min(int(vector_candidate_limit), 128))
        self._records: dict[str, dict[str, Any]] = {}
        self._tokens: dict[str, set[str]] = defaultdict(set)
        self._vectors: dict[str, tuple[float, ...]] = {}
        self._hot: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._lock = threading.RLock()
        self._last_refresh = 0.0
        self.refresh()

    @staticmethod
    def _text(value: Any) -> str:
        if isinstance(value, Mapping):
            return " ".join(
                f"{key} {AcceleratedLabRetriever._text(item)}"
                for key, item in value.items()
            )
        if isinstance(value, (list, tuple, set)):
            return " ".join(AcceleratedLabRetriever._text(item) for item in value)
        return str(value)

    @classmethod
    def _tokenize(cls, value: Any) -> set[str]:
        return set(_TOKEN_RE.findall(cls._text(value).lower()))

    def refresh(self) -> int:
        rows = self.memory.recent(limit=self.index_limit)
        records: dict[str, dict[str, Any]] = {}
        tokens: dict[str, set[str]] = defaultdict(set)
        for row in rows:
            record_id = str(row["id"])
            records[record_id] = row
            for token in self._tokenize({"kind": row["kind"], "payload": row["payload"]}):
                tokens[token].add(record_id)
        latest = max((float(row["created_at"]) for row in rows), default=time.time())
        with self._lock:
            self._records = records
            self._tokens = tokens
            self._vectors.clear()
            self._hot.clear()
            self._last_refresh = latest
        return len(records)

    def refresh_incremental(self) -> int:
        rows = self.memory.recent_since(self._last_refresh, limit=self.index_limit)
        if not rows:
            return 0
        with self._lock:
            for row in rows:
                record_id = str(row["id"])
                old = self._records.get(record_id)
                if old is not None:
                    for token in self._tokenize({"kind": old["kind"], "payload": old["payload"]}):
                        self._tokens[token].discard(record_id)
                self._records[record_id] = row
                self._vectors.pop(record_id, None)
                for token in self._tokenize({"kind": row["kind"], "payload": row["payload"]}):
                    self._tokens[token].add(record_id)
                self._last_refresh = max(self._last_refresh, float(row["created_at"]))
            if len(self._records) > self.index_limit:
                keep = sorted(
                    self._records.values(),
                    key=lambda item: float(item["created_at"]),
                    reverse=True,
                )[: self.index_limit]
                keep_ids = {str(item["id"]) for item in keep}
                self._records = {str(item["id"]): item for item in keep}
                self._tokens = defaultdict(set)
                for item in keep:
                    record_id = str(item["id"])
                    for token in self._tokenize({"kind": item["kind"], "payload": item["payload"]}):
                        self._tokens[token].add(record_id)
                self._hot = OrderedDict(
                    (record_id, row)
                    for record_id, row in self._hot.items()
                    if record_id in keep_ids
                )
        return len(rows)

    def _touch(self, record_id: str, row: dict[str, Any]) -> None:
        self._hot[record_id] = row
        self._hot.move_to_end(record_id)
        while len(self._hot) > self.hot_limit:
            self._hot.popitem(last=False)

    @staticmethod
    def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0
        dot = sum(a * b for a, b in zip(left, right))
        left_norm = sum(value * value for value in left) ** 0.5
        right_norm = sum(value * value for value in right) ** 0.5
        if left_norm <= 0 or right_norm <= 0:
            return 0.0
        return max(-1.0, min(dot / (left_norm * right_norm), 1.0))

    def _embed(self, text: str) -> tuple[float, ...] | None:
        if self.embedding_callback is None:
            return None
        try:
            values = tuple(float(value) for value in self.embedding_callback(str(text)[:16000]))
        except Exception:
            return None
        if not values or len(values) > 16384:
            return None
        return values

    def search(
        self,
        query: str,
        *,
        kind: str | None = None,
        limit: int = 20,
        use_vectors: bool = True,
    ) -> tuple[RetrievedRecord, ...]:
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return ()
        self.refresh_incremental()
        limit = max(1, min(int(limit), 200))
        with self._lock:
            latest_created = max(
                (float(row["created_at"]) for row in self._records.values()),
                default=time.time(),
            )
            candidate_ids: set[str] = set()
            for token in query_tokens:
                candidate_ids.update(self._tokens.get(token, ()))
            vector_enabled = bool(use_vectors and self.embedding_callback is not None)
            if vector_enabled and len(candidate_ids) < self.vector_candidate_limit:
                recent_ids = [
                    str(row["id"])
                    for row in sorted(
                        self._records.values(),
                        key=lambda item: float(item["created_at"]),
                        reverse=True,
                    )[: self.vector_candidate_limit]
                ]
                candidate_ids.update(recent_ids)
            candidate_rows = [
                self._records[record_id]
                for record_id in candidate_ids
                if record_id in self._records
                and (kind is None or self._records[record_id]["kind"] == kind)
            ]

        query_vector = self._embed(query) if vector_enabled else None
        scored: list[RetrievedRecord] = []
        for row in candidate_rows:
            record_id = str(row["id"])
            record_tokens = self._tokenize({"kind": row["kind"], "payload": row["payload"]})
            union = query_tokens | record_tokens
            lexical = len(query_tokens & record_tokens) / len(union) if union else 0.0
            recency = 1.0 / (
                1.0
                + max(0.0, latest_created - float(row["created_at"])) / 86400.0
            )
            vector_score = 0.0
            if query_vector is not None:
                with self._lock:
                    record_vector = self._vectors.get(record_id)
                if record_vector is None:
                    record_vector = self._embed(
                        self._text({"kind": row["kind"], "payload": row["payload"]})
                    )
                    if record_vector is not None:
                        with self._lock:
                            self._vectors[record_id] = record_vector
                if record_vector is not None:
                    vector_score = max(0.0, self._cosine(query_vector, record_vector))
            if query_vector is not None:
                score = lexical * 0.55 + vector_score * 0.35 + recency * 0.10
            else:
                score = lexical * 0.85 + recency * 0.15
            scored.append(
                RetrievedRecord(
                    id=record_id,
                    kind=str(row["kind"]),
                    score=score,
                    created_at=float(row["created_at"]),
                    payload=dict(row["payload"]),
                )
            )
            with self._lock:
                self._touch(record_id, row)
        scored.sort(key=lambda item: (-item.score, -item.created_at, item.id))
        return tuple(scored[:limit])

    def hot_stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "indexed_records": len(self._records),
                "indexed_tokens": len(self._tokens),
                "hot_records": len(self._hot),
                "hot_limit": self.hot_limit,
                "vector_reranking_available": self.embedding_callback is not None,
                "vector_cache_entries": len(self._vectors),
                "raw_text_vector_cache_persisted": False,
            }


class ContextCompressor:
    """Deterministic evidence-preserving context selection and deduplication."""

    def __init__(self, *, max_chars: int = 16000, max_chunks: int = 32):
        self.max_chars = max(1000, min(int(max_chars), 200000))
        self.max_chunks = max(1, min(int(max_chunks), 256))

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return set(_TOKEN_RE.findall(str(text).lower()))

    def compress(
        self,
        query: str,
        chunks: Iterable[Mapping[str, Any] | str],
    ) -> dict[str, Any]:
        query_tokens = self._tokens(query)
        seen: set[str] = set()
        ranked: list[tuple[float, str, str]] = []
        input_count = 0
        for index, chunk in enumerate(chunks):
            input_count += 1
            if isinstance(chunk, Mapping):
                chunk_id = str(chunk.get("id") or f"chunk-{index}")
                text = str(chunk.get("text") or chunk.get("content") or chunk)
                priority = float(chunk.get("priority", 0.0) or 0.0)
            else:
                chunk_id = f"chunk-{index}"
                text = str(chunk)
                priority = 0.0
            normalized = " ".join(text.split())
            digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
            if not normalized or digest in seen:
                continue
            seen.add(digest)
            tokens = self._tokens(normalized)
            overlap = len(query_tokens & tokens) / max(1, len(query_tokens))
            score = overlap * 0.8 + max(0.0, min(priority, 1.0)) * 0.2
            ranked.append((score, chunk_id, normalized))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        selected: list[str] = []
        provenance: list[str] = []
        used = 0
        for _, chunk_id, text in ranked[: self.max_chunks]:
            remaining = self.max_chars - used
            if remaining <= 0:
                break
            excerpt = text[:remaining]
            if not excerpt:
                continue
            selected.append(excerpt)
            provenance.append(chunk_id)
            used += len(excerpt)
        return {
            "text": "\n\n".join(selected),
            "provenance": provenance,
            "input_chunks": input_count,
            "selected_chunks": len(selected),
            "deduplicated_chunks": max(0, input_count - len(ranked)),
            "characters": used,
            "truncated": len(ranked) > len(selected) or used >= self.max_chars,
        }
