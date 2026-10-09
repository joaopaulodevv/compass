"""The knowledge base: curated sources, retrieved with their provenance.

The pipeline is deliberately small and swappable:

    corpus -> chunking -> embeddings -> vector store -> retrieval (freshness-aware)

Embeddings and the vector store are protocols Compass owns, with local implementations
that need no network and no vendor account. That keeps the whole thing testable today and
leaves the vendor decision where it belongs - open, and behind one seam each
(ADR-0013).
"""

from compass_api.knowledge.base import KnowledgeBase, get_knowledge_base

__all__ = ["KnowledgeBase", "get_knowledge_base"]
