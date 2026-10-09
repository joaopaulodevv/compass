# Architecture Decision Records

An ADR records a decision that is expensive to reverse, together with the context that
made it reasonable. It is written when the decision becomes concrete - not to document
intentions.

## Index

| ADR                                                              | Decision                                         | Status   |
| ---------------------------------------------------------------- | ------------------------------------------------ | -------- |
| [0001](0001-monorepo-with-independent-app-toolchains.md)         | Monorepo with independent per-app toolchains     | Accepted |
| [0002](0002-fastapi-async-backend.md)                            | FastAPI and an async-first backend               | Accepted |
| [0003](0003-postgresql-sqlalchemy-alembic.md)                    | PostgreSQL + SQLAlchemy 2.x + Alembic            | Accepted |
| [0004](0004-thin-mcp-tools-over-a-service-layer.md)              | Financial capabilities as thin MCP tools over services | Accepted |
| [0005](0005-deterministic-financial-engine.md)                   | Deterministic engine computes; the LLM explains  | Accepted |
| [0006](0006-open-finance-provider-abstraction.md)                | Open Finance data enters through a protocol Compass owns | Accepted |
| [0007](0007-money-as-signed-decimals.md)                         | Money is a signed decimal, everywhere            | Accepted |
| [0008](0008-pure-financial-engine.md)                            | The financial engine is pure Python over fetched rows | Accepted |
| [0009](0009-internal-movements-are-not-cash-flow.md)             | Internal movements are excluded from income and expenses | Accepted |
| [0010](0010-goals-store-terms-not-projections.md)                | A goal stores its terms; every projection is computed | Accepted |
| [0011](0011-mcp-tools-as-a-second-transport.md)                  | MCP is a second transport over the same services | Accepted |
| [0012](0012-agent-orchestrates-tools-never-computes.md)          | The agent orchestrates tools behind a provider interface it owns | Accepted |
| [0013](0013-local-retrieval-first-vendor-decision-deferred.md)   | Retrieval runs locally; the vector-store decision stays open | Accepted |

## Not yet decided

These are intentionally **not** ADRs. Recording them as decisions would be pretending.
They live in [../roadmap.md](../roadmap.md) until there is enough information to choose:

- Open Finance provider (Pluggy, Belvo, other) - the abstraction is decided in ADR-0006,
  the vendor is not
- Vector store (Pinecone vs `pgvector`). The retrieval machinery is built behind a
  protocol; ADR-0013 records why the vendor is still open and what would decide it
- Observability vendors (Langfuse, Datadog) and their integration points
- Whether expense categorisation stays rule-based or gains a model. The rules are in
  place and measurable; ADR-0008 and ADR-0009 depend on them staying deterministic

## Conventions

- Filename: `NNNN-short-title.md`, numbered sequentially.
- Status: `Proposed`, `Accepted`, `Superseded by ADR-NNNN`, or `Rejected`.
- ADRs are immutable once accepted. A changed decision gets a new ADR that supersedes
  the old one; the old file stays, so history remains readable.
- Use [`template.md`](template.md).
