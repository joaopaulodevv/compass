# ADR-0013: Retrieval runs locally; the vector-store decision stays open

- **Status:** Accepted
- **Date:** 2026-10-09

## Context

The assistant needs product and concept knowledge it can cite, because the alternative is
recalling it from training data - and a model cannot say when what it remembers was last
true. A confidently outdated interest rate or tax rule is worse than no answer.

Two questions had to be separated to make progress:

1. **What is the retrieval machinery?** Chunking, embeddings, a store, ranking, freshness.
2. **Which vendor runs it?** Pinecone was the stated intention. `pgvector` would add no
   vendor at all, since PostgreSQL is already here. Neither is decided, and deciding on a
   corpus of a few hundred passages would be deciding without the information that
   matters.

A third problem is specific to this phase and more important than either: the corpus
itself. Writing passages and labelling them as coming from Banco Central do Brasil or
ANBIMA would be fabricating records. The value of provenance is that it can be trusted; a
pipeline whose first act is to forge it is worse than no pipeline.

## Decision

**The machinery is built; the vendor is not chosen.** Embeddings and the vector store are
each a protocol Compass owns, with a local implementation behind it:

- `HashingEmbeddings` uses the hashing trick - tokens and bigrams hashed into 512
  dimensions with signed, sub-linear counts, L2 normalised. It is a real technique, not a
  stub: it gives genuine lexical retrieval with no model, no network and no account, and
  it is exactly reproducible, which is what makes retrieval testable. Hashing uses
  `blake2b` rather than `hash()`, which is salted per process - vectors must be identical
  across restarts or a stored index stops matching new queries.
- `InMemoryVectorStore` does an exact scan. For tens of documents that is both fast enough
  and exactly right: no index to tune, no approximation to explain, and it is the
  reference implementation any future store gets tested against.

**The corpus is honestly labelled.** Every sandbox document declares
`source: "Compass sandbox corpus"` with no URL, the directory's README says plainly that
the content is illustrative placeholder text attributed to nobody, and a test asserts that
no document claims an institution. Real sources arrive with their own provenance, and
these files go away when they do.

**Provenance travels with every passage, and freshness is reported rather than enforced.**
A retrieved chunk carries its source, retrieval date, validity date, age in days and a
staleness flag. Old passages are **flagged, not dropped**: silently omitting the only
passage on a topic leaves the user believing nothing was found, while an answer built on
something two years old should say so. Callers that want the strict behaviour pass
`exclude_stale`.

**Dates in the corpus are relative** (`retrieved_days_ago`), resolved against a reference
date - the same approach the Open Finance fixture uses, so the sandbox stays plausibly
recent without being rewritten, and one document is deliberately old so the staleness path
is exercised by something real.

**Knowledge is a tool, not a context dump.** `search_financial_knowledge` is an MCP tool
the model chooses to call, so what grounds an answer is visible in the stored tool calls.
It takes no `user_id`: the corpus is the same for everyone, and asking for an identity
would only invite one. The agent's toolbox therefore injects the identity *only* into tools
whose schema declares it.

## Consequences

- The assistant can ground a claim in a document and name its source, and the citation is
  checkable after the fact through the stored tool calls.
- The whole pipeline is tested with no network, no account and no API key, including the
  part that decides what the model is told.
- Swapping in a managed store is one adapter per protocol plus a configuration branch; the
  chunking, the freshness policy and the tool do not change.
- **Cost, and the significant one: no semantic matching.** A hashing embedder matches
  words, so "guardar dinheiro" will not retrieve a passage that only says "poupança". A
  model-based embedder behind the same protocol is the upgrade, and it is the reason the
  protocol exists.
- Cost: an in-memory store is rebuilt on every process start and shared by nothing. Fine
  for a curated corpus with local embeddings, useless for a large one or for embeddings
  that cost money per call.
- Cost: the corpus is placeholder content, so the assistant's knowledge answers are
  structurally right and substantively provisional. That is stated in the corpus README,
  in the development docs and in the provenance the user sees - not papered over.
- Freshness is a single `max_age_days`. A year is generous for a principle and far too long
  for a rate; the age travels with the answer precisely because one threshold cannot serve
  both.

## Alternatives considered

- **Integrate Pinecone now.** It is the stated intention, and it would mean an account, a
  key, a network dependency in the tests, and a vendor chosen before the corpus exists to
  justify it. The protocol keeps the door open at no cost.
- **Use `pgvector` in the existing PostgreSQL.** Attractive - no vendor, one less system,
  and real ANN when the corpus grows - and it would still need an embedding model to be
  worth the migration. Likely the first thing to try when the local embedder becomes the
  limit.
- **Call OpenAI embeddings now.** Better retrieval immediately, at the cost of a network
  call in the ingestion path, an API key to run the tests meaningfully, and a cost per
  query - for a corpus that is placeholder text.
- **Skip retrieval and put the knowledge in the system prompt.** Simpler and it does not
  scale past a page, cannot carry provenance per claim, and makes every answer pay for
  every topic.
- **Ingest real sources now.** The actual goal, and it needs source selection, licensing
  and a re-ingestion schedule - which is a phase, not a step. Faking it in the meantime was
  the one option ruled out on principle.
