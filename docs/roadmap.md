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

## Phase 5 - MCP tool layer (done)

- Nine tools over the existing services: `get_accounts`, `get_transactions`,
  `get_cashflow`, `detect_recurring_expenses`, `calculate_saving_capacity`, `list_goals`,
  `simulate_goal`, `calculate_goal_gap`, `compare_goal_paths`
- Registration is mechanical - schemas from type hints, descriptions from docstrings - so
  nothing about a tool is written twice
- Contract tests asserting every tool returns what the HTTP route returns, on real data
- Runs standalone over stdio: `python -m compass_api.mcp_server`
- ADR-0011

## Phase 6 - Agent layer (done)

- LangGraph conversation graph: the model thinks, tools run, results go back, bounded by
  a tool budget that ends in words rather than silence
- An LLM interface Compass owns (`agent/llm/base.py`) with an OpenAI adapter and a
  scripted provider for tests - the suite makes no network call and needs no API key
- The agent calls the MCP server, so its capabilities are exactly the MCP tools
- `user_id` stripped from every schema the model sees and injected server-side: a model
  cannot pass an argument it was never offered
- Conversations and messages persisted, with the tool calls that produced each answer
- `POST /conversations`, `GET /conversations`,
  `POST /conversations/{id}/messages`, `GET /conversations/{id}/messages`
- Without `OPENAI_API_KEY` the conversational endpoints answer 503 and everything else
  keeps working
- ADR-0012

## Phase 7 - Knowledge base and RAG (done)

- The retrieval machinery end to end: corpus loading, paragraph-aligned chunking,
  embeddings, a vector store, ranking and freshness-aware retrieval
- Embeddings and the vector store are each a protocol Compass owns, with a local
  implementation behind it - a hashing embedder and an exact-scan store, so the whole
  pipeline runs with no network and no vendor account
- Provenance on every passage (`source`, `category`, `retrieved_at`, `valid_from`,
  `age_days`); old passages are flagged, not silently dropped
- `search_financial_knowledge` as an MCP tool the agent chooses to call, so what grounds
  an answer is visible in the stored tool calls
- `GET /knowledge/search`, `GET /knowledge/corpus`
- The sandbox corpus is labelled as illustrative placeholder text attributed to nobody;
  faking a publisher's name would forge the very provenance the phase exists to carry
- ADR-0013 records why the vector-store vendor is still open

**Still open, and stated plainly:** the corpus is placeholder content and the embedder is
lexical, not semantic. Ingesting real sources (Banco Central do Brasil, ANBIMA, Tesouro
Direto, banks' own documentation) and moving to a model-based embedder are the next steps,
and both land behind the protocols already in place.

## Phase 8 - Recommendations (next)

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
