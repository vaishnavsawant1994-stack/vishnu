from knowledge.governance import KnowledgeAuthority
from knowledge.universal_store import UniversalKnowledgeStore

# Keep compatibility for older imports (`from knowledge.store import KnowledgeStore`)
# while making the Universal Content Intelligence store authoritative at runtime.
from knowledge import store as _store_module
_store_module.KnowledgeStore = UniversalKnowledgeStore
KnowledgeStore = UniversalKnowledgeStore

__all__ = ["KnowledgeStore", "KnowledgeAuthority", "UniversalKnowledgeStore"]
