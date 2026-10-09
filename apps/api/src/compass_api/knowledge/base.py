"""The knowledge base: ingest once, retrieve with provenance.

Retrieval reports age and staleness rather than quietly dropping old passages. An answer
built on something from two years ago should say so; an answer that silently omits the
only passage on a topic leaves the user believing nothing was found.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from functools import lru_cache

from compass_api.domain.knowledge import KnowledgeDocument, RetrievedChunk
from compass_api.knowledge.chunking import chunk_document
from compass_api.knowledge.corpus_loader import load_corpus
from compass_api.knowledge.embeddings import EmbeddingProvider, HashingEmbeddings
from compass_api.knowledge.store import InMemoryVectorStore, VectorRecord, VectorStore

logger = logging.getLogger(__name__)

#: Beyond this, a passage is reported as possibly out of date. A year is generous for
#: principles and far too long for a rate - which is exactly why the age travels with the
#: answer instead of being decided here.
DEFAULT_MAX_AGE_DAYS = 365

#: Below this similarity a match is noise rather than a weak answer.
MIN_SCORE = 0.05

DEFAULT_TOP_K = 4
MAX_TOP_K = 10


@dataclass(frozen=True, slots=True)
class IngestionReport:
    documents: int
    chunks: int


class KnowledgeBase:
    """Curated passages, embedded and searchable."""

    def __init__(
        self,
        embeddings: EmbeddingProvider | None = None,
        store: VectorStore | None = None,
        max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    ) -> None:
        self._embeddings = embeddings or HashingEmbeddings()
        self._store = store or InMemoryVectorStore()
        self._max_age_days = max_age_days

    async def ingest(self, documents: Sequence[KnowledgeDocument]) -> IngestionReport:
        """Chunk, embed and store. Re-ingesting the same documents replaces them."""
        chunks = [chunk for document in documents for chunk in chunk_document(document)]
        if not chunks:
            return IngestionReport(documents=0, chunks=0)

        vectors = await self._embeddings.embed(
            [_embedding_text(chunk.title, chunk.text) for chunk in chunks]
        )
        await self._store.upsert(
            [
                VectorRecord(chunk=chunk, embedding=vector)
                for chunk, vector in zip(chunks, vectors, strict=True)
            ]
        )
        logger.info(
            "knowledge ingested",
            extra={"documents": len(documents), "chunks": len(chunks)},
        )
        return IngestionReport(documents=len(documents), chunks=len(chunks))

    async def search(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        *,
        as_of: date | None = None,
        exclude_stale: bool = False,
    ) -> list[RetrievedChunk]:
        """Passages matching the query, best first, each with its age."""
        if not query.strip():
            return []

        today = as_of or date.today()
        embedding = (await self._embeddings.embed([query]))[0]
        matches = await self._store.query(embedding, min(top_k, MAX_TOP_K))

        retrieved = []
        for match in matches:
            if match.score < MIN_SCORE:
                continue
            age = match.chunk.provenance.age_days(today)
            stale = age > self._max_age_days
            if stale and exclude_stale:
                continue
            retrieved.append(
                RetrievedChunk(
                    chunk=match.chunk, score=round(match.score, 4), age_days=age, is_stale=stale
                )
            )
        return retrieved

    async def size(self) -> int:
        return await self._store.count()


def _embedding_text(title: str, text: str) -> str:
    """The title is part of what a passage is about, so it is embedded with it."""
    return f"{title}\n\n{text}"


@lru_cache
def get_knowledge_base() -> KnowledgeBase:
    """The process-wide knowledge base, built and ingested on first use.

    Lazy rather than at startup: the API is useful without it, and a process that never
    answers a knowledge question should not pay for one. With the local embedder this
    costs no network call at all.
    """
    return KnowledgeBase()


async def ensure_ingested(base: KnowledgeBase) -> KnowledgeBase:
    """Ingest the committed corpus if the base is empty."""
    if await base.size() == 0:
        await base.ingest(load_corpus())
    return base
