from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
import hashlib
import json
import re
import threading
import time
from typing import Any, Callable, Iterable, Mapping

from .memory import LabMemory
from .models import new_id


_TOKEN_RE = re.compile(r"[a-zA-Z0-9_]{2,}")


@dataclass(frozen=True)
class CachePolicy:
    ttl_seconds: float = 900.0
    semantic_threshold: float = 0.92
    maximum_entries: int = 512
    persist_internal: bool = True


@dataclass(frozen=True)
class CacheEntry:
    namespace: str
    version: str
    scope: str
    sensitivity: str
    exact_key: str
    token_hashes: tuple[str, ...]
    value: Any
    expires_at: float
    prefix_key: str | None = None
    id: str = field(default_factory=lambda: new_id("cache"))

    @property
    def expired(self) -> bool:
        return time.time() >= self.expires_at


class SafeSemanticCache:
    """Owner/device-scoped exact + semantic + prefix cache.

    Raw prompts are never persisted. Semantic matching uses hashed lexical
    features and therefore does not require an external embedding authority.
    Sensitive/private entries must have an explicit non-shared scope.
    """

    SHAREABLE_SENSITIVITY = frozenset({"public", "internal"})

    def __init__(
        self,
        memory: LabMemory,
        *,
        policy: CachePolicy | None = None,
    ):
        self.memory = memory
        self.policy = policy or CachePolicy()
        self._entries: OrderedDict[str, CacheEntry] = OrderedDict()
        self._prefix: OrderedDict[str, Any] = OrderedDict()
        self._lock = threading.RLock()
        self.hits = 0
        self.misses = 0
        self.semantic_hits = 0
        self.prefix_hits = 0

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join(str(text).strip().lower().split())

    @classmethod
    def _token_hashes(cls, text: str) -> tuple[str, ...]:
        tokens = sorted(set(_TOKEN_RE.findall(cls._normalize(text))))
        return tuple(hashlib.sha256(item.encode("utf-8")).hexdigest()[:16] for item in tokens)

    @staticmethod
    def _digest(*parts: str) -> str:
        payload = "\x1f".join(parts).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @staticmethod
    def _safe_scope(scope: str, sensitivity: str) -> str:
        scope = str(scope or "").strip()
        sensitivity = str(sensitivity or "internal").strip().lower()
        if sensitivity not in {"public", "internal", "private", "sensitive", "secret"}:
            sensitivity = "sensitive"
        if sensitivity not in SafeSemanticCache.SHAREABLE_SENSITIVITY and (
            not scope or scope in {"shared", "*", "global"}
        ):
            raise PermissionError("sensitive cache entries require explicit owner/device scope")
        return scope or "shared"

    def _key(
        self,
        prompt: str,
        *,
        namespace: str,
        version: str,
        scope: str,
        sensitivity: str,
    ) -> str:
        safe_scope = self._safe_scope(scope, sensitivity)
        return self._digest(
            str(namespace),
            str(version),
            safe_scope,
            str(sensitivity).lower(),
            self._normalize(prompt),
        )

    def _trim(self) -> None:
        maximum = max(16, min(int(self.policy.maximum_entries), 10000))
        while len(self._entries) > maximum:
            self._entries.popitem(last=False)
        while len(self._prefix) > maximum:
            self._prefix.popitem(last=False)

    def put(
        self,
        prompt: str,
        value: Any,
        *,
        namespace: str = "reasoning",
        version: str = "v1",
        scope: str = "shared",
        sensitivity: str = "internal",
        ttl_seconds: float | None = None,
        prefix_key: str | None = None,
    ) -> CacheEntry:
        safe_scope = self._safe_scope(scope, sensitivity)
        ttl = max(1.0, float(ttl_seconds or self.policy.ttl_seconds))
        key = self._key(
            prompt,
            namespace=namespace,
            version=version,
            scope=safe_scope,
            sensitivity=sensitivity,
        )
        entry = CacheEntry(
            namespace=str(namespace)[:120],
            version=str(version)[:120],
            scope=safe_scope[:200],
            sensitivity=str(sensitivity).lower()[:40],
            exact_key=key,
            token_hashes=self._token_hashes(prompt),
            value=value,
            expires_at=time.time() + ttl,
            prefix_key=str(prefix_key)[:200] if prefix_key else None,
        )
        with self._lock:
            self._entries[key] = entry
            self._entries.move_to_end(key)
            self._trim()
        if (
            self.policy.persist_internal
            and entry.sensitivity in self.SHAREABLE_SENSITIVITY
        ):
            self.memory.put(
                entry.id,
                "semantic_cache_metadata",
                {
                    "id": entry.id,
                    "namespace": entry.namespace,
                    "version": entry.version,
                    "scope": entry.scope,
                    "sensitivity": entry.sensitivity,
                    "exact_key": entry.exact_key,
                    "token_hashes": list(entry.token_hashes),
                    "expires_at": entry.expires_at,
                    "raw_prompt_stored": False,
                    "value_persisted": False,
                },
            )
        return entry

    @staticmethod
    def _similarity(left: Iterable[str], right: Iterable[str]) -> float:
        a, b = set(left), set(right)
        if not a or not b:
            return 0.0
        return len(a & b) / len(a | b)

    def get(
        self,
        prompt: str,
        *,
        namespace: str = "reasoning",
        version: str = "v1",
        scope: str = "shared",
        sensitivity: str = "internal",
        allow_semantic: bool = True,
    ) -> tuple[Any | None, str]:
        safe_scope = self._safe_scope(scope, sensitivity)
        key = self._key(
            prompt,
            namespace=namespace,
            version=version,
            scope=safe_scope,
            sensitivity=sensitivity,
        )
        now = time.time()
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None and not entry.expired:
                self._entries.move_to_end(key)
                self.hits += 1
                return entry.value, "exact"
            if entry is not None:
                self._entries.pop(key, None)
            if allow_semantic:
                target_tokens = self._token_hashes(prompt)
                best: tuple[float, CacheEntry] | None = None
                for candidate in self._entries.values():
                    if candidate.expired:
                        continue
                    if (
                        candidate.namespace != str(namespace)
                        or candidate.version != str(version)
                        or candidate.scope != safe_scope
                        or candidate.sensitivity != str(sensitivity).lower()
                    ):
                        continue
                    similarity = self._similarity(target_tokens, candidate.token_hashes)
                    if similarity >= self.policy.semantic_threshold and (
                        best is None or similarity > best[0]
                    ):
                        best = (similarity, candidate)
                if best is not None:
                    self.hits += 1
                    self.semantic_hits += 1
                    return best[1].value, "semantic"
        self.misses += 1
        return None, "miss"

    def put_prefix(
        self,
        stable_context: str,
        value: Any,
        *,
        namespace: str = "model-prefix",
        version: str = "v1",
    ) -> str:
        key = self._digest(namespace, version, self._normalize(stable_context))
        with self._lock:
            self._prefix[key] = value
            self._prefix.move_to_end(key)
            self._trim()
        return key

    def get_prefix(
        self,
        stable_context: str,
        *,
        namespace: str = "model-prefix",
        version: str = "v1",
    ) -> Any | None:
        key = self._digest(namespace, version, self._normalize(stable_context))
        with self._lock:
            if key not in self._prefix:
                return None
            value = self._prefix[key]
            self._prefix.move_to_end(key)
            self.prefix_hits += 1
            return value

    def get_or_compute(
        self,
        prompt: str,
        compute: Callable[[], Any],
        **kwargs: Any,
    ) -> tuple[Any, str]:
        get_kwargs = dict(kwargs)
        value, mode = self.get(prompt, **get_kwargs)
        if mode != "miss":
            return value, mode
        value = compute()
        put_kwargs = dict(kwargs)
        put_kwargs.pop("allow_semantic", None)
        self.put(prompt, value, **put_kwargs)
        return value, "computed"

    def stats(self) -> dict[str, Any]:
        total = self.hits + self.misses
        return {
            "entries": len(self._entries),
            "prefix_entries": len(self._prefix),
            "hits": self.hits,
            "misses": self.misses,
            "semantic_hits": self.semantic_hits,
            "prefix_hits": self.prefix_hits,
            "hit_rate": self.hits / total if total else 0.0,
            "raw_prompt_persisted": False,
            "cross_owner_sensitive_cache": False,
        }
