"""The knowledge pipeline: chunking, embeddings, store and retrieval.

All of it runs locally with no network and no vendor account, which is the point - the
retrieval that grounds the assistant's claims has to be testable.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from compass_api.domain.knowledge import KnowledgeDocument, Provenance
from compass_api.knowledge.base import DEFAULT_MAX_AGE_DAYS, KnowledgeBase
from compass_api.knowledge.chunking import chunk_document
from compass_api.knowledge.corpus_loader import SANDBOX_SOURCE, load_corpus
from compass_api.knowledge.embeddings import (
    EmbeddingProvider,
    HashingEmbeddings,
    cosine_similarity,
    tokenize,
)
from compass_api.knowledge.store import InMemoryVectorStore, VectorRecord, VectorStore

TODAY = date(2026, 6, 15)


def document(
    text: str, *, identifier: str = "doc", title: str = "Title", days_ago: int = 10
) -> KnowledgeDocument:
    return KnowledgeDocument(
        id=identifier,
        title=title,
        text=text,
        provenance=Provenance(
            source="test",
            retrieved_at=TODAY - timedelta(days=days_ago),
            category="liquidity",
        ),
    )


# --- chunking ------------------------------------------------------------------------


def test_short_documents_stay_in_one_piece() -> None:
    chunks = chunk_document(document("Um paragrafo curto."))

    assert len(chunks) == 1
    assert chunks[0].id == "doc#000"
    assert chunks[0].document_id == "doc"


def test_paragraphs_are_grouped_up_to_the_limit() -> None:
    text = "\n\n".join(["a" * 400, "b" * 400, "c" * 400])

    chunks = chunk_document(document(text), max_chars=900)

    assert len(chunks) == 2
    assert all(len(chunk.text) <= 900 for chunk in chunks)


def test_a_paragraph_longer_than_the_limit_splits_on_sentences() -> None:
    """Never mid-word: a passage cut inside a number is worse than one cut late."""
    text = " ".join(f"Frase numero {index} com algum conteudo." for index in range(60))

    chunks = chunk_document(document(text), max_chars=300)

    assert len(chunks) > 1
    assert all(len(chunk.text) <= 300 for chunk in chunks)
    assert all(chunk.text.endswith(".") for chunk in chunks)


def test_chunk_ids_derive_from_the_document_so_reingestion_replaces() -> None:
    first = chunk_document(document("\n\n".join(["x" * 500, "y" * 500])))
    again = chunk_document(document("\n\n".join(["x" * 500, "y" * 500])))

    assert [chunk.id for chunk in first] == [chunk.id for chunk in again]


def test_chunks_inherit_the_document_provenance() -> None:
    chunks = chunk_document(document("texto", days_ago=40))

    assert chunks[0].provenance.retrieved_at == TODAY - timedelta(days=40)
    assert chunks[0].provenance.category == "liquidity"


def test_blank_documents_produce_nothing() -> None:
    assert chunk_document(document("   \n\n  ")) == []


# --- embeddings ----------------------------------------------------------------------


def test_the_embedder_satisfies_the_protocol() -> None:
    assert isinstance(HashingEmbeddings(), EmbeddingProvider)


def test_tokenizing_strips_accents_and_stop_words() -> None:
    assert tokenize("A liquidez de uma reserva") == ["liquidez", "reserva"]


async def test_embeddings_are_normalised_and_fixed_width() -> None:
    embedder = HashingEmbeddings(dimensions=64)

    vectors = await embedder.embed(["liquidez diaria", "reserva de emergencia"])

    assert all(len(vector) == 64 for vector in vectors)
    assert all(abs(cosine_similarity(vector, vector) - 1.0) < 1e-9 for vector in vectors)


async def test_embeddings_are_stable_across_instances() -> None:
    """Hashing must not be salted per process, or a stored index stops matching."""
    first = await HashingEmbeddings().embed(["reserva de emergencia"])
    second = await HashingEmbeddings().embed(["reserva de emergencia"])

    assert first == second


def test_similar_text_scores_higher_than_unrelated_text() -> None:
    embedder = HashingEmbeddings()
    query = embedder.embed_one("reserva de emergencia")

    close = cosine_similarity(query, embedder.embed_one("a reserva de emergencia serve para"))
    far = cosine_similarity(query, embedder.embed_one("tipos de risco de mercado"))

    assert close > far


def test_an_empty_text_embeds_without_dividing_by_zero() -> None:
    assert (
        cosine_similarity(HashingEmbeddings().embed_one(""), HashingEmbeddings().embed_one(""))
        == 0.0
    )


def test_similarity_never_goes_negative() -> None:
    """Negative similarity is not a useful distinction for ranking."""
    embedder = HashingEmbeddings(dimensions=8)

    scores = [
        cosine_similarity(embedder.embed_one(left), embedder.embed_one(right))
        for left, right in [("liquidez", "risco"), ("meta", "cartao"), ("aporte", "divida")]
    ]

    assert all(score >= 0.0 for score in scores)


# --- store ---------------------------------------------------------------------------


async def test_the_store_satisfies_the_protocol() -> None:
    assert isinstance(InMemoryVectorStore(), VectorStore)


async def test_upserting_the_same_chunk_replaces_it() -> None:
    store = InMemoryVectorStore()
    embedder = HashingEmbeddings()
    chunk = chunk_document(document("texto"))[0]

    await store.upsert([VectorRecord(chunk=chunk, embedding=embedder.embed_one("a"))])
    await store.upsert([VectorRecord(chunk=chunk, embedding=embedder.embed_one("b"))])

    assert await store.count() == 1


async def test_querying_an_empty_store_returns_nothing() -> None:
    assert await InMemoryVectorStore().query(HashingEmbeddings().embed_one("x"), 5) == []


async def test_query_respects_top_k() -> None:
    store = InMemoryVectorStore()
    embedder = HashingEmbeddings()
    for index in range(5):
        chunk = chunk_document(document(f"texto {index}", identifier=f"doc-{index}"))[0]
        await store.upsert(
            [VectorRecord(chunk=chunk, embedding=embedder.embed_one(f"texto {index}"))]
        )

    assert len(await store.query(embedder.embed_one("texto"), 3)) == 3
    assert await store.query(embedder.embed_one("texto"), 0) == []


# --- the corpus and retrieval --------------------------------------------------------


def test_the_committed_corpus_loads_with_honest_provenance() -> None:
    """The sandbox corpus must not claim to come from an institution it does not."""
    documents = load_corpus(reference_date=TODAY)

    assert len(documents) >= 5
    assert {doc.provenance.source for doc in documents} == {SANDBOX_SOURCE}
    assert all(doc.provenance.url is None for doc in documents)
    assert all(doc.provenance.category for doc in documents)
    assert all(doc.provenance.retrieved_at <= TODAY for doc in documents)


def test_corpus_dates_are_relative_so_the_sandbox_stays_recent() -> None:
    earlier = load_corpus(reference_date=TODAY)
    later = load_corpus(reference_date=TODAY + timedelta(days=365))

    assert [doc.id for doc in earlier] == [doc.id for doc in later]
    assert min(doc.provenance.retrieved_at for doc in later) > min(
        doc.provenance.retrieved_at for doc in earlier
    )


def test_an_unknown_corpus_directory_yields_nothing(tmp_path: Path) -> None:
    assert load_corpus(corpus_dir=tmp_path) == []


async def test_ingesting_and_searching_the_corpus() -> None:
    base = KnowledgeBase()
    report = await base.ingest(load_corpus(reference_date=TODAY))

    assert report.documents >= 5
    assert report.chunks >= report.documents
    assert await base.size() == report.chunks

    found = await base.search("reserva de emergencia", as_of=TODAY)
    assert found
    assert "emergency-fund" in found[0].chunk.document_id
    assert found[0].score > 0


async def test_reingesting_does_not_duplicate() -> None:
    base = KnowledgeBase()
    documents = load_corpus(reference_date=TODAY)

    await base.ingest(documents)
    size = await base.size()
    await base.ingest(documents)

    assert await base.size() == size


async def test_results_are_ordered_by_score() -> None:
    base = KnowledgeBase()
    await base.ingest(load_corpus(reference_date=TODAY))

    found = await base.search("liquidez e retorno", top_k=5, as_of=TODAY)

    scores = [item.score for item in found]
    assert scores == sorted(scores, reverse=True)


async def test_old_passages_are_flagged_rather_than_dropped() -> None:
    """An answer built on something years old should say so - not pretend it is current,
    and not pretend nothing was found."""
    base = KnowledgeBase()
    await base.ingest(
        [
            document("liquidez diaria e resgate", identifier="fresh", days_ago=10),
            document("liquidez diaria e resgate", identifier="old", days_ago=900),
        ]
    )

    found = await base.search("liquidez diaria", top_k=5, as_of=TODAY)

    by_id = {item.chunk.document_id: item for item in found}
    assert by_id["fresh"].is_stale is False
    assert by_id["old"].is_stale is True
    assert by_id["old"].age_days == 900


async def test_stale_passages_can_be_excluded_when_asked() -> None:
    base = KnowledgeBase()
    await base.ingest([document("liquidez diaria", identifier="old", days_ago=900)])

    assert await base.search("liquidez diaria", as_of=TODAY)
    assert await base.search("liquidez diaria", as_of=TODAY, exclude_stale=True) == []


async def test_the_freshness_policy_is_configurable() -> None:
    documents = [document("liquidez diaria", days_ago=100)]

    lenient = KnowledgeBase(max_age_days=DEFAULT_MAX_AGE_DAYS)
    strict = KnowledgeBase(max_age_days=30)
    await lenient.ingest(documents)
    await strict.ingest(documents)

    assert (await lenient.search("liquidez", as_of=TODAY))[0].is_stale is False
    assert (await strict.search("liquidez", as_of=TODAY))[0].is_stale is True


@pytest.mark.parametrize("query", ["", "   "])
async def test_an_empty_query_returns_nothing(query: str) -> None:
    base = KnowledgeBase()
    await base.ingest(load_corpus(reference_date=TODAY))

    assert await base.search(query, as_of=TODAY) == []


async def test_a_query_sharing_nothing_with_the_corpus_returns_nothing() -> None:
    """Noise must come back empty rather than as a weak answer presented confidently."""
    base = KnowledgeBase()
    await base.ingest(load_corpus(reference_date=TODAY))

    assert await base.search("xyzzy qwertyuiop zzzz", as_of=TODAY) == []
