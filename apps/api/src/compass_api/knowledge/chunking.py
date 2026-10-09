"""Splitting a document into passages worth retrieving.

Paragraph boundaries are the split points: they are where a document's author already
decided one idea ends. Paragraphs are grouped until a size limit, and a paragraph longer
than the limit on its own is split on sentences rather than mid-word.

No overlap between chunks. Overlap exists to stop an answer being cut in half, and with
paragraph-aligned chunks that mostly does not happen - while overlap would make the same
sentence retrievable twice and crowd out a second source.
"""

from __future__ import annotations

import re

from compass_api.domain.knowledge import KnowledgeChunk, KnowledgeDocument

#: Big enough for a complete idea with its qualifications, small enough that a retrieved
#: passage is mostly about what was asked.
MAX_CHUNK_CHARS = 900

_PARAGRAPH = re.compile(r"\n\s*\n")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def chunk_document(
    document: KnowledgeDocument, max_chars: int = MAX_CHUNK_CHARS
) -> list[KnowledgeChunk]:
    """Split a document into chunks, ids derived from the document's.

    Deriving the id means re-ingesting the same corpus overwrites rather than duplicates:
    the same idempotency property the transaction ingestion has.
    """
    passages = _passages(document.text, max_chars)
    return [
        KnowledgeChunk(
            id=f"{document.id}#{index:03d}",
            document_id=document.id,
            title=document.title,
            text=passage,
            provenance=document.provenance,
        )
        for index, passage in enumerate(passages)
    ]


def _passages(text: str, max_chars: int) -> list[str]:
    paragraphs = [block.strip() for block in _PARAGRAPH.split(text) if block.strip()]

    passages: list[str] = []
    current = ""
    for paragraph in paragraphs:
        for piece in _split_oversized(paragraph, max_chars):
            if not current:
                current = piece
            elif len(current) + len(piece) + 2 <= max_chars:
                current = f"{current}\n\n{piece}"
            else:
                passages.append(current)
                current = piece
    if current:
        passages.append(current)
    return passages


def _split_oversized(paragraph: str, max_chars: int) -> list[str]:
    """Break a paragraph that is too long on sentence boundaries."""
    if len(paragraph) <= max_chars:
        return [paragraph]

    pieces: list[str] = []
    current = ""
    for sentence in _SENTENCE.split(paragraph):
        if not current:
            current = sentence
        elif len(current) + len(sentence) + 1 <= max_chars:
            current = f"{current} {sentence}"
        else:
            pieces.append(current)
            current = sentence
    if current:
        pieces.append(current)
    return pieces
