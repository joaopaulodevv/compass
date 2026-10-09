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

## Phase 2 - Financial domain and ingestion from sandbox data (done)

- `FinancialInstitution`, `Account` and `Transaction` models and migration, all scoped by
  `user_id`
- `OpenFinanceProvider` protocol plus `MockOpenFinanceProvider` over a committed fixture:
  six months of realistic history, no network, no credentials
- Provider-neutral snapshots (`domain/open_finance.py`) as the only shapes crossing the
  provider boundary
- Idempotent ingestion keyed on the provider's own identifiers, so overlapping syncs
  update rather than duplicate
- Repositories owning all SQL; money as signed `NUMERIC(18, 2)`
- `POST /open-finance/sync`, `GET /accounts`, `GET /accounts/{id}`, `GET /transactions`
  with filtering and pagination
- `X-User-Id` as the temporary isolation key, required and validated on every financial
  endpoint
- `make seed` for a local demo user; `alembic check` in CI against model/migration drift
- ADR-0006 (provider abstraction and idempotent ingestion), ADR-0007 (signed decimals)

Deliberately still absent: provider SDKs, authentication, any calculation.

## Phase 3 - Deterministic financial engine (done)

- Rule-based categorisation (`services/categorization.py`), matching whole token
  sequences rather than substrings, stored on the transaction with the rule that produced
  it so any label is traceable
- Cash flow over a window: income, expenses, net, a monthly series that marks partial
  months, and a category breakdown with shares
- Internal movements (credit-card bill payments, transfers between the user's own
  accounts) excluded from income and expenses, and reported separately so the exclusion
  is visible - ADR-0009
- Recurring-expense detection with an explicit definition: at least three occurrences, a
  21-38 day average cadence, amounts within 25% of their median
- Sustainable saving capacity: median monthly net over whole calendar months, floored at
  zero
- `GET /insights/cashflow`, `/insights/recurring-expenses`, `/insights/saving-capacity`
- The engine is pure: no I/O, so every number is tested against hand-worked values with
  no database in the loop - ADR-0008

## Phase 4 - Goals and simulation (done)

- `FinancialGoal`: only the terms are stored - target, optional date, what is already set
  aside, the planned contribution, status. Every projection is computed on request, so a
  stale forecast cannot be served (ADR-0010)
- Goal simulation, required contribution, gap against the target date, path comparison
  and progress against the straight line to the deadline - all in a pure engine
- A forecast falls back from an explicit contribution, to the goal's own plan, to the
  saving capacity measured in Phase 3 - and reports which it used
- `POST /goals/simulate` answers "could I?" with nothing persisted
- Expected returns are always the caller's assumption, converted from an effective annual
  rate properly rather than divided by twelve
- `POST /goals`, `GET /goals`, `GET /goals/{id}`, `PATCH /goals/{id}`,
  `GET /goals/{id}/forecast`, `POST /goals/{id}/comparison`

`FinancialProfile` was **not** created. A table of self-declared attributes with no
consumer would be premature: what the agent will actually need - saving capacity,
recurring commitments, cash-flow shape - is already computed from real data. It belongs
with the suitability rules in Phase 8, where something finally reads it.

## Phase 5 - MCP tool layer (next)

- Expose the Phase 3-4 services as MCP tools with explicit schemas: `get_cashflow`,
  `detect_recurring_expenses`, `calculate_saving_capacity`, `simulate_goal`,
  `calculate_goal_gap`, `compare_goal_paths`
- Tools stay thin: schema plus a call into the same pure function the HTTP route uses
  (ADR-0004), so there is nothing to keep in sync beyond the schema
- Contract tests asserting the tool schemas and the service signatures agree

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
