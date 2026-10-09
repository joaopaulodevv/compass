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

## Not yet decided

These are intentionally **not** ADRs. Recording them as decisions would be pretending.
They live in [../roadmap.md](../roadmap.md) until there is enough information to choose:

- Open Finance provider (Pluggy, Belvo, other)
- Vector store (Pinecone vs `pgvector`)
- Observability vendors (Langfuse, Datadog) and their integration points
- Agent topology and conversation memory
- Expense categorisation approach (rules vs model)

## Conventions

- Filename: `NNNN-short-title.md`, numbered sequentially.
- Status: `Proposed`, `Accepted`, `Superseded by ADR-NNNN`, or `Rejected`.
- ADRs are immutable once accepted. A changed decision gets a new ADR that supersedes
  the old one; the old file stays, so history remains readable.
- Use [`template.md`](template.md).
