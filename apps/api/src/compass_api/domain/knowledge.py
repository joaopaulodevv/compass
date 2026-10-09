"""Knowledge the assistant may cite.

Financial product information goes stale: a rate, a tax rule or a minimum changes, and a
confidently outdated figure is worse than no answer. So provenance is not metadata here -
it is part of the value. Every chunk carries where it came from, when it was retrieved and
from when it applies, and retrieval reports how old it is.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class Provenance:
    """Where a piece of knowledge came from, and when."""

    #: The publisher, as a reader would name it.
    source: str
    #: When Compass read it. Freshness is measured from here.
    retrieved_at: date
    url: str | None = None
    #: From when the content applies, if it says.
    valid_from: date | None = None
    institution: str | None = None
    product: str | None = None
    #: What it is about: liquidity, risk, emergency_fund, fixed_income, planning...
    category: str | None = None

    def age_days(self, as_of: date) -> int:
        return max((as_of - self.retrieved_at).days, 0)


@dataclass(frozen=True, slots=True)
class KnowledgeDocument:
    """A source document, before chunking."""

    id: str
    title: str
    text: str
    provenance: Provenance


@dataclass(frozen=True, slots=True)
class KnowledgeChunk:
    """A passage small enough to retrieve and cite."""

    id: str
    document_id: str
    title: str
    text: str
    provenance: Provenance


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    """A chunk that matched, with everything needed to judge it."""

    chunk: KnowledgeChunk
    #: Cosine similarity, 0-1. Higher is closer.
    score: float
    age_days: int
    #: True when the chunk is older than the policy allows - surfaced, not hidden, so an
    #: answer can say that its source may be out of date.
    is_stale: bool
