# Roadmap

Compass is built in small, reviewable phases. Each phase must leave the repository in a
working, tested state - no half-wired integrations waiting for a future commit.

## Phase 1 - Foundation (done)

- Monorepo structure with an obvious home for the future frontend
- FastAPI application with an application factory
- `/health` (liveness) and `/ready` (readiness, checks PostgreSQL)
- Typed, environment-driven settings; optional future credentials
- Structured JSON logging
- Async SQLAlchemy 2.x + asyncpg, minimal `users` model
- Alembic with async environment and the initial migration
- Docker Compose: API + PostgreSQL + Redis
- pytest suite (unit + integration), coverage reporting
- ruff, mypy (strict), pre-commit, Conventional Commits
- GitHub Actions: quality, tests, commit messages, Docker build
- README, architecture, development docs, ADRs 0001-0005

## Phase 2 - Financial domain and ingestion from mock data (next)

The smallest step that produces real financial data to compute on.

- `FinancialInstitution`, `Account`, `Transaction` models and migrations, all scoped by
  `user_id`
- `OpenFinanceProvider` protocol plus a mock implementation returning deterministic
  sandbox data
- An ingestion service that persists accounts and transactions idempotently
- Repositories for the above, with integration tests
- Read endpoints for accounts and transactions
- ADR: Open Finance abstraction and ingestion strategy

Deliberately still absent: provider SDKs, authentication, any calculation.

## Phase 3 - Deterministic financial engine

- Cash flow aggregation over a time window
- Expense categorisation (rule-based first; a classifier is a later question)
- Recurring expense detection
- Sustainable saving capacity
- Unit tests over fixed fixtures - these are the numbers everything else trusts

## Phase 4 - Goals and simulation

- `FinancialGoal`, `FinancialProfile` models
- Goal simulation, goal gap, path comparison, progress reforecast
- Endpoints for creating and simulating goals

## Phase 5 - MCP tool layer

- Expose Phase 3-4 services as MCP tools with explicit schemas
- Tools stay thin: schema plus a service call (see ADR-0004)
- Contract tests asserting tools and HTTP endpoints agree

## Phase 6 - Agent layer

- LangGraph conversation graph with tool calling
- Internal LLM provider interface; OpenAI as the first implementation
- Tests with mocked LLM calls - no network in the test suite
- ADR: agent topology and provider abstraction

## Phase 7 - Knowledge base and RAG

- Source curation and an ingestion pipeline with provenance metadata
  (`source`, `institution`, `product`, `category`, `retrieved_at`, `valid_from`, `url`)
- Vector store integration (Pinecone intended, not yet decided - needs an ADR)
- Freshness-aware retrieval and citations in answers
- Retrieval quality evaluation

## Phase 8 - Recommendations

- Product model and suitability constraints
- Recommendation assembly: profile + computed capacity + retrieved product knowledge
- Explanations that cite both the numbers and the sources

## Phase 9 - Authentication and isolation

- Authentication and session handling
- Enforced per-user scoping on every financial query
- Authorisation tests that prove cross-user reads are impossible

## Phase 10 - Observability and hardening

- Langfuse for agent traces, token usage, cost
- Datadog for API, database and infrastructure metrics
- Rate limiting and caching - the first concrete use for Redis
- Load and failure-mode testing

## Phase 11 - Web frontend

- Next.js application in `apps/web`
- Chat interface, financial overview, goal tracking, recommendations

## Open questions

Tracked here rather than recorded as decisions, because they are not decided:

- **Open Finance provider.** Pluggy vs Belvo vs other. Depends on sandbox quality and
  coverage of the institutions that matter.
- **Vector store.** Pinecone is the intention; a managed Postgres + `pgvector` setup
  would remove a dependency and a cost. Revisit when retrieval requirements are real.
- **Expense categorisation.** Rules are explainable and testable; a model generalises
  better. Likely rules first, measured, then revisited.
- **Background work.** Transaction ingestion will eventually want scheduling. Redis is
  already in the stack; whether that becomes a queue or an external scheduler is open.
- **Agent memory.** How much conversation state to persist, and where.
