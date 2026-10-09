"""Where vectors live.

`VectorStore` is the seam for the vendor decision. Pinecone is the current intention and
`pgvector` the obvious alternative that would add no vendor at all; neither is decided, so
neither is written (ADR-0013).

`InMemoryVectorStore` is what runs today. For a curated corpus - tens of documents, a few
hundred chunks - an exact scan is both fast enough and exactly right, with no index to
tune and no approximation to explain. It is the reference implementation any future store
is tested against.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from compass_api.domain.knowledge import KnowledgeChunk
from compass_api.knowledge.embeddings import Vector, cosine_similarity


@dataclass(frozen=True, slots=True)
class VectorRecord:
    """A chunk and its embedding, ready to store."""

    chunk: KnowledgeChunk
    embedding: Vector


@dataclass(frozen=True, slots=True)
class VectorMatch:
    """A stored chunk that matched a query."""

    chunk: KnowledgeChunk
    score: float


@runtime_checkable
class VectorStore(Protocol):
    """Stores chunk embeddings and answers nearest-neighbour queries."""

    async def upsert(self, records: Sequence[VectorRecord]) -> int:
        """Store or replace records by chunk id. Returns how many were written."""
        ...

    async def query(self, embedding: Vector, top_k: int) -> list[VectorMatch]:
        """The closest chunks, best first."""
        ...

    async def count(self) -> int:
        """How many chunks are stored."""
        ...


class InMemoryVectorStore:
    """`VectorStore` backed by a dict and an exact scan."""

    def __init__(self) -> None:
        self._records: dict[str, VectorRecord] = {}

    async def upsert(self, records: Sequence[VectorRecord]) -> int:
        for record in records:
            self._records[record.chunk.id] = record
        return len(records)

    async def query(self, embedding: Vector, top_k: int) -> list[VectorMatch]:
        if top_k <= 0:
            return []
        scored = [
            VectorMatch(chunk=record.chunk, score=cosine_similarity(embedding, record.embedding))
            for record in self._records.values()
        ]
        # Chunk id breaks ties, so equal scores come back in a stable order.
        scored.sort(key=lambda match: (-match.score, match.chunk.id))
        return scored[:top_k]

    async def count(self) -> int:
        return len(self._records)
