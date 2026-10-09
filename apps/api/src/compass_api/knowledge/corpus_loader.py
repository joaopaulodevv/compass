"""Reading the committed corpus.

Dates are stored as "days ago" and resolved against a reference date, so the sandbox stays
plausibly recent without being rewritten - the same approach the Open Finance fixture
uses, for the same reason.

The content is illustrative placeholder text, not a citation from any institution. See
`corpus/README.md`: faking a publisher's name would be a fabricated record, and provenance
only has value if it can be trusted.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from compass_api.domain.knowledge import KnowledgeDocument, Provenance

CORPUS_DIR = Path(__file__).parent / "corpus"

SANDBOX_SOURCE = "Compass sandbox corpus"


class _Document(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=1)
    retrieved_days_ago: int = Field(ge=0)
    valid_from_days_ago: int | None = Field(default=None, ge=0)
    institution: str | None = None
    product: str | None = None


class _Corpus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    documents: tuple[_Document, ...]


def load_corpus(
    reference_date: date | None = None, corpus_dir: Path | None = None
) -> list[KnowledgeDocument]:
    """Every document in the corpus directory, with dates resolved."""
    today = reference_date or date.today()
    directory = corpus_dir or CORPUS_DIR

    documents: list[KnowledgeDocument] = []
    for path in sorted(directory.glob("*.json")):
        corpus = _Corpus.model_validate(json.loads(path.read_text(encoding="utf-8")))
        documents.extend(_to_document(entry, today) for entry in corpus.documents)
    return documents


def _to_document(entry: _Document, today: date) -> KnowledgeDocument:
    return KnowledgeDocument(
        id=entry.id,
        title=entry.title,
        text=entry.text,
        provenance=Provenance(
            source=SANDBOX_SOURCE,
            retrieved_at=today - timedelta(days=entry.retrieved_days_ago),
            url=None,
            valid_from=(
                today - timedelta(days=entry.valid_from_days_ago)
                if entry.valid_from_days_ago is not None
                else None
            ),
            institution=entry.institution,
            product=entry.product,
            category=entry.category,
        ),
    )
