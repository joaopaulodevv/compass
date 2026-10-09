# Architecture

Status legend used throughout this document:

| Label           | Meaning                                                      |
| --------------- | ------------------------------------------------------------ |
| **Implemented** | Exists in the repository and is exercised by tests            |
| **Planned**     | Decided and scheduled on the roadmap, not built yet           |
| **Future**      | Directional. Needs an ADR before it becomes real              |

---

## 1. What exists today

Phase 1 built the backend foundation. Phase 2 added the financial domain: data arrives
from an Open Finance provider through an abstraction Compass owns, is stored
idempotently, and can be read back over HTTP.

```mermaid
flowchart LR
    client["HTTP client\n(curl, Swagger UI)"] --> api

    subgraph app["FastAPI application (apps/api) - Implemented"]
        api["API layer\n/health /ready\n/open-finance/sync\n/accounts /transactions"]
        svc["Sync service\nidempotent ingestion"]
        repo["Repositories\naccounts, transactions,\ninstitutions, users"]
        prov["Provider adapter\nMockOpenFinanceProvider"]
        api --> svc
        api --> repo
        svc --> repo
        svc --> prov
    end

    prov --> fixture[("Sandbox fixture\n6 months of history")]
    repo --> postgres[("PostgreSQL\nusers, financial_institutions,\naccounts, transactions")]
    redis[("Redis\nno consumer yet")]

    classDef idle stroke-dasharray: 4 3
    class redis idle
```

Redis is part of the local stack but **nothing in the application connects to it**. It is
provisioned so that the first real need - caching, or the background sync job that
replaces today's synchronous endpoint - does not also require an infrastructure change.
No client library is installed.

## 2. Target architecture

```mermaid
flowchart TB
    web["Next.js web frontend\n(Future)"] --> api

    api["FastAPI application API\n(Implemented: foundation + financial reads)"]

    api --> agent["LangGraph agent\n(Future)"]

    agent -->|MCP| tools["Financial MCP tools\n(Future)"]
    agent -->|retrieval| rag["Knowledge base / RAG\n(Future)"]

    tools --> services["Financial services\ndeterministic calculations\n(Planned)"]
    api --> sync["Sync service\n(Implemented)"]
    services --> repos["Repositories\n(Implemented)"]
    sync --> repos
    sync --> ofp["Open Finance provider adapter\n(mock implemented,\nreal vendor Future)"]

    repos --> postgres[("PostgreSQL\n(Implemented)")]
    rag --> vectors[("Vector store\n(Future)")]
    ofp --> openfinance["Open Finance provider\n(Future)"]

    api --> cache[("Redis\n(infrastructure only)")]

    obs["Observability:\nLangfuse (agent) + Datadog (app)\n(Future)"]
    agent -.-> obs
    api -.-> obs
```

The arrows that matter: the frontend only ever talks to the application API, and the
agent reaches data only through tools. Nothing downstream of the API is a public surface.

## 3. Layering rules

The system has one hard rule, and most of the architecture follows from it:

> Business logic lives in services. Everything else - HTTP handlers, MCP tool
> definitions, the agent - is transport.

```mermaid
flowchart LR
    subgraph transports["Transport (thin, no business rules)"]
        http["HTTP route handler"]
        mcp["MCP tool definition\n(Future)"]
    end

    http --> svc
    mcp --> svc

    svc["Service layer\npure, deterministic, typed"]
    svc --> repo["Repositories\n(database access)"]
    svc --> prov["Providers\n(Open Finance, LLM, vector store)"]
```

In the code today:

- `api/routes/open_finance.py` validates a window, calls `OpenFinanceSyncService`, maps
  the report to a response. It contains no rule about what a sync is.
- `services/open_finance_sync.py` is the only place that knows what syncing a user means.
- `repositories/` owns all SQL and contains no financial rules.
- An MCP tool for `simulate_goal` will be a schema plus a service call. If a tool body
  grows a financial rule, that rule is in the wrong place (ADR-0004).

Repositories and services exist because there is now logic and SQL to hold. Phase 1
deliberately had neither: a repository wrapping a single `SELECT 1` would have been
ceremony, not architecture.

## 4. Separation of responsibilities (the core design decision)

Financial advice fails in two distinct ways: wrong numbers, and wrong explanations. The
architecture keeps them apart so they can be tested and trusted separately. See
[ADR-0005](adr/0005-deterministic-financial-engine.md).

| Concern                   | Owner                        | Property required            |
| ------------------------- | ---------------------------- | ---------------------------- |
| User financial data       | Repositories / provider adapter | Auditable, isolated per user |
| Financial calculations    | Financial services (via MCP tools) | Deterministic, unit-tested |
| Product knowledge         | RAG over curated sources     | Sourced, dated, traceable    |
| Orchestration and wording | LLM agent                    | Helpful, grounded            |

**The LLM never computes a number that matters.** It decides which tools to call, in what
order, and explains the result in plain language.

Worked example - *"I want R$20,000 for a trip in 18 months"*:

```mermaid
sequenceDiagram
    actor User
    participant API as FastAPI
    participant Agent as LangGraph agent
    participant Tools as Financial MCP tools
    participant KB as Knowledge base
    User->>API: question
    API->>Agent: conversation turn
    Agent->>Tools: get_financial_profile(user_id)
    Agent->>Tools: get_cashflow(user_id, window)
    Agent->>Tools: calculate_saving_capacity(...)
    Agent->>Tools: simulate_goal(target=20000, months=18)
    Agent->>Tools: calculate_goal_gap(...)
    Agent->>KB: retrieve(liquidity, short-term fixed income)
    Agent-->>API: explanation grounded in tool output + sources
    API-->>User: answer
```

Every number in the answer traces back to a tool call; every product statement traces
back to a retrieved document.

## 5. Data model

Implemented: `users`, `financial_institutions`, `accounts`, `transactions`.

```mermaid
erDiagram
    User ||--o{ Account : owns
    User ||--o{ Transaction : owns
    FinancialInstitution ||--o{ Account : issues
    Account ||--o{ Transaction : records

    User {
        uuid id PK
        string email UK
        string display_name
    }
    FinancialInstitution {
        uuid id PK
        string provider
        string external_id
        string name
    }
    Account {
        uuid id PK
        uuid user_id FK
        uuid institution_id FK
        string provider
        string external_id
        string type
        numeric current_balance
        timestamptz synced_at
    }
    Transaction {
        uuid id PK
        uuid user_id FK
        uuid account_id FK
        string provider
        string external_id
        date booked_at
        numeric amount
        string description
        string provider_category
    }
```

Design points worth knowing:

- **`(user_id, provider, external_id)` on accounts and `(account_id, provider,
  external_id)` on transactions are unique.** They are the idempotency keys that make
  re-syncing an overlapping window safe (ADR-0006).
- **`user_id` is denormalised onto `transactions`.** It keeps the isolation filter on the
  same row as the data and spares every cash-flow query a join. The cost is one redundant
  column that ingestion must set correctly, which a test covers.
- **Amounts are `NUMERIC(18, 2)` and signed** - negative is an outflow. `direction` is
  derived, never stored (ADR-0007).
- **`account.type` is a VARCHAR with a CHECK constraint**, not a native PostgreSQL enum:
  adding a value later is an ordinary migration rather than an `ALTER TYPE` that cannot
  run inside a transaction.
- **`provider_category` keeps the provider's own label.** Compass's categorisation is a
  later phase and will get its own column, so the raw value stays auditable.

Planned next, when the calculations that use them exist:

```mermaid
erDiagram
    User ||--o{ FinancialGoal : sets
    User ||--|| FinancialProfile : has
    User ||--o{ Recommendation : receives
    Product ||--o{ Recommendation : referenced_by
```

**Data isolation.** Authentication does not exist yet, but every financial table carries
`user_id`, every repository method takes it, and every query filters on it. An account id
that belongs to someone else reads as `404`, not `403` - existence is itself information.
When authentication arrives it supplies the same value from a verified token; nothing
downstream changes.

## 6. External integrations

### Open Finance (mock implemented, vendor undecided)

No provider has been chosen. Candidates include Pluggy and Belvo. The application depends
on a protocol it owns - `OpenFinanceProvider` - and on the frozen snapshots in
`compass_api.domain.open_finance`. A vendor field that is not in a snapshot does not
enter the system. See [ADR-0006](adr/0006-open-finance-provider-abstraction.md).

```python
@runtime_checkable
class OpenFinanceProvider(Protocol):
    @property
    def name(self) -> str: ...
    async def get_institutions(self, user_id: UUID) -> Sequence[InstitutionSnapshot]: ...
    async def get_accounts(self, user_id: UUID) -> Sequence[AccountSnapshot]: ...
    async def get_transactions(
        self, user_id: UUID, since: date, until: date
    ) -> Sequence[TransactionSnapshot]: ...
```

`MockOpenFinanceProvider` implements it over a committed fixture: six months of realistic
history for three accounts at two institutions, no network, no credentials. Fixture dates
are a month offset plus a day resolved against a reference date, so the data stays recent
without being rewritten and a test that pins the date gets identical results.

Choosing a real provider means writing one adapter and changing
`compass_api.api.deps.get_open_finance_provider`. Sandbox and production credentials will
live in separate environments; real financial credentials are never committed.

### LLM provider (Future)

The first implementation will target OpenAI. The agent will depend on a narrow internal
interface (chat completion, tool calling, embeddings) so that switching provider or
running a cheaper model for a subtask is a configuration change, not a rewrite.
`OPENAI_API_KEY` is already declared in settings as optional.

### Knowledge base / RAG (Future)

Pinecone is the current intention, not a decision - it has no ADR yet. The non-negotiable
part is **provenance and freshness**: financial product conditions go stale, and a
confidently outdated interest rate is worse than no answer.

Planned sources: Banco Central do Brasil, ANBIMA, Tesouro Direto, official bank product
documentation, financial education material.

Planned chunk metadata:

```
source | institution | product | category | retrieved_at | valid_from | url
```

Retrieval will filter and rank on freshness, and answers will cite the source and the
date, so a reader can tell whether a figure is current.

## 7. Observability (Future)

Two concerns, two tools, one rule: business logic must not import a vendor SDK.

- **Langfuse** - agent traces, prompts, tool calls, token usage, latency, cost.
- **Datadog** - API latency, error rates, logs, database and infrastructure metrics.

Preparation already in place: structured single-line JSON logs via
`compass_api.core.logging`, which any collector can ingest, and optional vendor keys in
settings that do not block startup when absent. The sync service already logs counts and
identifiers only - never amounts, descriptions or merchants.

## 8. HTTP surface

| Endpoint                   | Purpose                                  | Requires `X-User-Id` |
| -------------------------- | ---------------------------------------- | -------------------- |
| `GET /health`              | Liveness. Touches no dependency          | No                   |
| `GET /ready`               | Readiness. Checks PostgreSQL             | No                   |
| `POST /open-finance/sync`  | Ingest accounts and transactions         | Yes                  |
| `GET /accounts`            | List the user's accounts                 | Yes                  |
| `GET /accounts/{id}`       | One account, scoped to its owner         | Yes                  |
| `GET /transactions`        | Paginated, filterable by account and window | Yes               |

Keeping liveness and readiness separate means a database blip withholds traffic without
causing an orchestrator to restart otherwise healthy processes. Probes require no user: an
orchestrator has no identity to present.

`X-User-Id` is a temporary stand-in for authentication. It is trusted, which is why
authentication comes before any deployment on the roadmap. The value it carries is already
the isolation key used by every query, so replacing its source with a verified token
changes nothing downstream.

`POST /open-finance/sync` is synchronous because the sandbox provider answers instantly.
Against a real provider it becomes a queued job returning `202` and a job id - the first
concrete use for the Redis already in the stack.

## 9. Security principles

Applied so far:

- No secrets in the repository; `.env` is git-ignored and `.env.example` is the contract.
- All configuration comes from the environment and is validated at startup.
- Credentials are typed as `SecretStr`, so they do not appear in logs, reprs or
  tracebacks (covered by a test). A blank value reads as absent, never as configured.
- Every financial query is scoped by `user_id`; another user's row reads as `404`.
- The sync service logs counts and identifiers, never financial data.
- Connection errors are logged without echoing connection strings to clients.
- Interactive API docs are automatically disabled when `APP_ENV=production`.
- The container runs as a non-root user.
- No real financial credentials exist: the only provider is a local fixture.

Committed to for later phases:

- Authentication, after which `user_id` comes from a verified token.
- Authorisation tests proving cross-user reads are impossible.
- Strict separation between sandbox and production Open Finance integrations.
