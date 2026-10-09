"""Searching the knowledge base.

The only endpoint that takes no user: the corpus is the same for everyone and nothing
here reads a user's data. It exists so the retrieval can be inspected directly - what the
agent is being told, and how old it is - rather than only through an answer.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from compass_api.domain.knowledge import RetrievedChunk
from compass_api.knowledge.base import (
    DEFAULT_TOP_K,
    MAX_TOP_K,
    ensure_ingested,
    get_knowledge_base,
)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


class PassageResponse(BaseModel):
    """A retrieved passage with everything needed to judge it."""

    title: str
    text: str
    score: float
    source: str
    url: str | None
    category: str | None
    retrieved_at: date
    valid_from: date | None
    age_days: int
    #: Older than the freshness policy allows. Surfaced rather than hidden: an answer
    #: built on it should say so.
    is_stale: bool

    @classmethod
    def of(cls, retrieved: RetrievedChunk) -> PassageResponse:
        provenance = retrieved.chunk.provenance
        return cls(
            title=retrieved.chunk.title,
            text=retrieved.chunk.text,
            score=retrieved.score,
            source=provenance.source,
            url=provenance.url,
            category=provenance.category,
            retrieved_at=provenance.retrieved_at,
            valid_from=provenance.valid_from,
            age_days=retrieved.age_days,
            is_stale=retrieved.is_stale,
        )


class SearchResponse(BaseModel):
    query: str
    results: list[PassageResponse]


@router.get("/search", summary="Search the curated financial knowledge")
async def search(
    q: Annotated[str, Query(min_length=2, max_length=500, description="What to look for")],
    top_k: Annotated[int, Query(ge=1, le=MAX_TOP_K)] = DEFAULT_TOP_K,
    exclude_stale: Annotated[
        bool, Query(description="Leave out passages older than the freshness policy")
    ] = False,
) -> SearchResponse:
    base = await ensure_ingested(get_knowledge_base())
    found = await base.search(q, top_k, exclude_stale=exclude_stale)
    return SearchResponse(query=q, results=[PassageResponse.of(item) for item in found])


class CorpusResponse(BaseModel):
    chunks: int = Field(description="Passages currently indexed")


@router.get("/corpus", summary="How much knowledge is indexed")
async def corpus() -> CorpusResponse:
    base = await ensure_ingested(get_knowledge_base())
    return CorpusResponse(chunks=await base.size())
