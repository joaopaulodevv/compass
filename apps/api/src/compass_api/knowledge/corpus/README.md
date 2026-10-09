# Sandbox corpus

**This content is illustrative placeholder text written for development. It is not
quoted from, attributed to, or endorsed by any institution, and no statement in it should
be treated as current.**

Phase 7 delivers the retrieval machinery: chunking, embeddings, a vector store behind a
protocol, freshness-aware retrieval and citations. Ingesting real sources - Banco Central
do Brasil, ANBIMA, Tesouro Direto, banks' own product documentation - is a later step,
and it is deliberately not faked here: a document labelled with a real publisher's name
would be a fabricated record, and the whole point of carrying provenance is that it can
be trusted.

Every document therefore declares `source: "Compass sandbox corpus"` and no URL. When
real sources are ingested they bring their own provenance, and these files go away.

Dates are expressed as `retrieved_days_ago` and `valid_from_days_ago`, resolved against a
reference date, so the corpus stays plausibly recent without being rewritten - the same
approach the Open Finance fixture uses. One document is deliberately old, so the staleness
path is exercised by something rather than only by a unit test.
