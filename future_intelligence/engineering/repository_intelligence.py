from __future__ import annotations

import ast
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping


_TEXT_SUFFIXES = {".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".html", ".css", ".json", ".yaml", ".yml", ".md"}
_JS_IMPORT = re.compile(r"(?:from\s+|import\s*\(|require\s*\()\s*['\"]([^'\"]+)['\"]")
_ROUTE_HINT = re.compile(r"(?:route|path|href)\s*[:=]\s*['\"]([^'\"]+)['\"]", re.I)
_ROOT_SCOPES = {".", "./", "*", "**", "**/*"}


@dataclass(frozen=True)
class RepositoryNode:
    id: str
    kind: str
    path: str
    name: str
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, "kind": self.kind, "path": self.path, "name": self.name, "metadata": dict(self.metadata)}


@dataclass(frozen=True)
class RepositoryEdge:
    source: str
    target: str
    kind: str

    def to_dict(self) -> dict[str, str]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class RepositoryGraph:
    revision: str
    fingerprint: str
    nodes: tuple[RepositoryNode, ...]
    edges: tuple[RepositoryEdge, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "revision": self.revision,
            "fingerprint": self.fingerprint,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "RepositoryGraph":
        nodes = tuple(RepositoryNode(str(item["id"]), str(item["kind"]), str(item["path"]), str(item["name"]), dict(item.get("metadata") or {})) for item in data.get("nodes", ()))  # type: ignore[union-attr]
        edges = tuple(RepositoryEdge(str(item["source"]), str(item["target"]), str(item["kind"])) for item in data.get("edges", ()))  # type: ignore[union-attr]
        return cls(str(data["revision"]), str(data["fingerprint"]), nodes, edges)


class RepositoryIntelligenceBuilder:
    """Reconstructable, revision-bound local source graph; never an authority store."""

    def __init__(self, *, max_files: int = 20_000, max_file_bytes: int = 750_000, max_total_bytes: int = 50_000_000) -> None:
        self.max_files = max(1, int(max_files))
        self.max_file_bytes = max(1_000, int(max_file_bytes))
        self.max_total_bytes = max(self.max_file_bytes, int(max_total_bytes))

    @staticmethod
    def _file_id(path: str) -> str:
        return f"file:{path}"

    @staticmethod
    def _symbol_id(path: str, name: str, line: int) -> str:
        return f"symbol:{path}:{line}:{name}"

    @staticmethod
    def _normalize_prefixes(include_paths: Iterable[str]) -> tuple[str, ...]:
        raw = tuple(str(item).strip().replace("\\", "/") for item in include_paths if str(item).strip())
        if any(item in _ROOT_SCOPES for item in raw):
            return ()
        return tuple(dict.fromkeys(item.strip("/") for item in raw if item.strip("/")))

    def build(self, root: str | Path, *, revision: str, include_paths: Iterable[str] = ()) -> RepositoryGraph:
        base = Path(root).expanduser().resolve()
        if not base.is_dir():
            raise ValueError("repository intelligence root must be a directory")
        prefixes = self._normalize_prefixes(include_paths)
        nodes: list[RepositoryNode] = []
        edges: list[RepositoryEdge] = []
        file_ids: dict[str, str] = {}
        imports: list[tuple[str, str]] = []
        total = 0
        count = 0
        hasher = hashlib.sha256(str(revision).encode())
        for path in sorted(base.rglob("*")):
            if count >= self.max_files or total >= self.max_total_bytes:
                break
            if not path.is_file() or path.is_symlink() or path.suffix.lower() not in _TEXT_SUFFIXES:
                continue
            relative = path.relative_to(base).as_posix()
            if relative.startswith((".git/", ".venv/", "node_modules/", "artifacts/", "dist/", "build/")):
                continue
            if prefixes and not any(relative == prefix or relative.startswith(prefix + "/") for prefix in prefixes):
                continue
            try:
                raw = path.read_bytes()
            except OSError:
                continue
            if b"\x00" in raw or len(raw) > self.max_file_bytes or total + len(raw) > self.max_total_bytes:
                continue
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
            count += 1
            total += len(raw)
            hasher.update(relative.encode()); hasher.update(hashlib.sha256(raw).digest())
            file_id = self._file_id(relative)
            file_ids[relative] = file_id
            kind = "test" if relative.startswith("tests/") or "/test" in relative else "file"
            metadata: dict[str, object] = {"suffix": path.suffix.lower(), "bytes": len(raw)}
            routes = tuple(dict.fromkeys(_ROUTE_HINT.findall(text)))[:50]
            if routes:
                metadata["routes"] = list(routes)
            nodes.append(RepositoryNode(file_id, kind, relative, path.name, metadata))
            if path.suffix.lower() == ".py":
                try:
                    tree = ast.parse(text, filename=relative)
                except SyntaxError:
                    tree = None
                if tree is not None:
                    for item in ast.walk(tree):
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                            symbol_id = self._symbol_id(relative, item.name, int(item.lineno))
                            symbol_kind = "class" if isinstance(item, ast.ClassDef) else "function"
                            nodes.append(RepositoryNode(symbol_id, symbol_kind, relative, item.name, {"line": int(item.lineno)}))
                            edges.append(RepositoryEdge(file_id, symbol_id, "contains"))
                        elif isinstance(item, ast.Import):
                            imports.extend((relative, alias.name) for alias in item.names)
                        elif isinstance(item, ast.ImportFrom) and item.module:
                            imports.append((relative, item.module))
            elif path.suffix.lower() in {".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx"}:
                imports.extend((relative, target) for target in _JS_IMPORT.findall(text))
        for source, imported in imports:
            target = self._resolve_import(source, imported, file_ids)
            if target:
                edges.append(RepositoryEdge(file_ids[source], target, "imports"))
        unique_edges = tuple({(edge.source, edge.target, edge.kind): edge for edge in edges}.values())
        return RepositoryGraph(str(revision), hasher.hexdigest(), tuple(nodes), unique_edges)

    @staticmethod
    def _resolve_import(source: str, imported: str, file_ids: Mapping[str, str]) -> str | None:
        if imported.startswith("."):
            parent = Path(source).parent
            candidate = (parent / imported).as_posix().replace("/./", "/")
            choices = (candidate, candidate + ".js", candidate + ".mjs", candidate + ".ts", candidate + ".tsx", candidate + "/index.js")
        else:
            dotted = imported.replace(".", "/")
            choices = (dotted + ".py", dotted + "/__init__.py")
        for choice in choices:
            if choice in file_ids:
                return file_ids[choice]
        return None

    @staticmethod
    def write_cache(graph: RepositoryGraph, destination: str | Path) -> None:
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(graph.to_dict(), sort_keys=True, separators=(",", ":")), encoding="utf-8")
        temp.replace(path)
