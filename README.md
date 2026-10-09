# Compass

An AI-powered personal financial assistant: it reads your financial history, works out
what you can actually afford, and explains the answer.

> **Project status: Phase 1 of 11 complete.** The backend foundation is built and tested.
> The agent, the financial engine, the Open Finance integration, the knowledge base and
> the frontend are **not implemented yet**. This README distinguishes throughout between
> what exists and what is planned - see the [roadmap](docs/roadmap.md).

---

## The problem

Most personal finance tools stop at a dashboard. They show you where the money went and
leave the actual question unanswered:

> *"I want R$20,000 for a trip in 18 months. Can I do it, and what should I do with the
> money in the meantime?"*

Answering that needs three different things, and generic chatbots conflate them:

1. **Your data** - what you actually earn and spend, not a budgeting template.
2. **Correct arithmetic** - sustainable saving capacity, goal feasibility, the gap. An
   LLM asked to do this produces confident, irreproducible, sometimes wrong numbers.
3. **Current product knowledge** - what a product's conditions are *today*, with a
   source, not what a model remembers about rates from its training data.

## The approach

Compass separates those three concerns and keeps them separate:

| Concern                 | Owner                                                  |
| ----------------------- | ------------------------------------------------------ |
| Financial data          | Open Finance adapter + PostgreSQL                      |
| Financial calculations  | Deterministic, unit-tested services exposed as MCP tools |
| Product knowledge       | RAG over curated sources, with provenance and dates    |
| Orchestration and wording | LLM agent (LangGraph)                                |

**The LLM never computes a number that matters.** It decides which tools to call and
explains the result. The engine calculates; retrieval supplies knowledge. That decision is
recorded in [ADR-0005](docs/adr/0005-deterministic-financial-engine.md) and it shapes
everything else.

## High-level architecture

```mermaid
flowchart TB
    web["Next.js frontend\n(Future)"] --> api
    api["FastAPI application API\n(foundation implemented)"]
    api --> agent["LangGraph agent\n(Future)"]
    agent -->|MCP| tools["Financial tools\n(Future)"]
    agent -->|retrieval| rag["Knowledge base\n(Future)"]
    tools --> services["Financial services\ndeterministic\n(Future)"]
    services --> repos["Repositories\n(Planned)"]
    services --> ofp["Open Finance adapter\n(Future)"]
    repos --> pg[("PostgreSQL\n(Implemented)")]
    rag --> vec[("Vector store\n(Future)")]
    ofp --> of["Open Finance provider\n(Future)"]
    api --> redis[("Redis\ninfrastructure only")]
```

Full detail, including the layering rules and the request flow for a goal simulation:
[docs/architecture.md](docs/architecture.md).

## Current status

**Implemented**

- FastAPI application with an application factory and lifespan-managed resources
- `GET /health` (liveness, no dependencies) and `GET /ready` (readiness, checks PostgreSQL)
- Generated OpenAPI docs at `/docs`, `/redoc`, `/openapi.json`, disabled in production
- Typed, environment-driven configuration; future credentials optional by design
- Structured single-line JSON logging
- Async SQLAlchemy 2.x + asyncpg, with a minimal `users` model
- Alembic with an async environment and the initial migration
- Docker Compose stack: API + PostgreSQL + Redis
- Test suite (26 tests, unit + integration), coverage reporting
- ruff, mypy strict, pre-commit, Conventional Commits, GitHub Actions
- Architecture documentation and five ADRs

**Planned next** - financial domain models, a mock Open Finance provider, and transaction
ingestion. See [Phase 2](docs/roadmap.md#phase-2---financial-domain-and-ingestion-from-mock-data-next).

**Not implemented** - Open Finance integration, financial calculations, MCP tools,
LangGraph agent, LLM calls, vector store, RAG ingestion, Langfuse, Datadog,
authentication, recommendations, frontend.

Redis runs in the local stack but **nothing consumes it yet**; it is infrastructure
prepared for caching, background jobs and rate limiting. No client library is installed,
because inventing a use case to justify a dependency is worse than an idle container.

## Technology stack

| Layer            | Choice                                      | Status                  |
| ---------------- | ------------------------------------------- | ----------------------- |
| Backend          | Python 3.13, FastAPI, Pydantic v2           | Implemented             |
| Database         | PostgreSQL 16, SQLAlchemy 2.x (async), Alembic | Implemented          |
| Packaging        | uv, `pyproject.toml`                        | Implemented             |
| Cache / queue    | Redis                                       | Infrastructure only     |
| Quality          | ruff, mypy (strict), pytest, pre-commit     | Implemented             |
| CI               | GitHub Actions                              | Implemented             |
| Local infra      | Docker Compose                              | Implemented             |
| Agent            | LangGraph, provider-agnostic LLM interface (OpenAI first) | Future    |
| Tooling protocol | MCP                                         | Future                  |
| Financial data   | Open Finance provider behind an owned protocol | Future               |
| Knowledge base   | RAG, Pinecone intended (undecided)          | Future                  |
| Observability    | Langfuse (agent), Datadog (application)     | Future                  |
| Frontend         | Next.js, React, TypeScript                  | Future                  |

## Local development

Requires Docker with the Compose plugin, and [uv](https://docs.astral.sh/uv/) for
host-side work.

```bash
git clone <repository-url> && cd compass
cp .env.example .env
docker compose up --build
```

Then:

```bash
curl localhost:8000/health   # {"status":"ok","version":"0.1.0"}
curl localhost:8000/ready    # {"status":"ready","checks":{"database":"ok"}}
```

API documentation: <http://localhost:8000/docs> (Swagger UI) and
<http://localhost:8000/redoc>.

Running the API on the host against Dockerised infrastructure - the faster loop:

```bash
docker compose up -d postgres redis
make install        # dependencies + git hooks
make migrate        # alembic upgrade head
make run            # uvicorn --reload
```

`make help` lists every target. Full instructions, including environment variables and
troubleshooting: [docs/development.md](docs/development.md).

No secrets are committed. `.env` is git-ignored; `.env.example` documents every variable,
including the ones for capabilities that do not exist yet.

## Testing

```bash
make test        # full suite with coverage
make test-unit   # no infrastructure required
make check       # lint + types + tests (what CI runs)
```

Unit tests construct settings explicitly and need no infrastructure. Integration tests
are marked `integration` and need a reachable PostgreSQL with migrations applied; they
skip rather than fail without one.

Coverage is a diagnostic, not a target - there is no threshold gate.

## Repository structure

```
compass/
├── apps/
│   ├── api/                      # FastAPI backend (implemented)
│   │   ├── src/compass_api/
│   │   │   ├── api/              # Routers and handlers (transport only)
│   │   │   ├── core/             # Settings, structured logging
│   │   │   ├── db/               # Declarative base, session, models
│   │   │   ├── migrations/       # Alembic environment and revisions
│   │   │   └── main.py           # Application factory
│   │   ├── tests/{unit,integration}
│   │   ├── Dockerfile
│   │   ├── alembic.ini
│   │   └── pyproject.toml / uv.lock
│   └── web/                      # Future Next.js app (README only)
├── docs/
│   ├── architecture.md
│   ├── development.md
│   ├── roadmap.md
│   └── adr/                      # Architecture decision records
├── infra/                        # Reserved for deployment assets
├── .github/workflows/ci.yml
├── docker-compose.yml
├── .env.example
├── Makefile
└── CONTRIBUTING.md
```

## Architecture decisions

| ADR | Decision |
| --- | -------- |
| [0001](docs/adr/0001-monorepo-with-independent-app-toolchains.md) | Monorepo with independent per-app toolchains |
| [0002](docs/adr/0002-fastapi-async-backend.md) | FastAPI and an async-first backend |
| [0003](docs/adr/0003-postgresql-sqlalchemy-alembic.md) | PostgreSQL + SQLAlchemy 2.x + Alembic |
| [0004](docs/adr/0004-thin-mcp-tools-over-a-service-layer.md) | Financial capabilities as thin MCP tools over services |
| [0005](docs/adr/0005-deterministic-financial-engine.md) | The deterministic engine computes, the LLM explains |

Vendor choices that are not yet decided - Open Finance provider, vector store,
observability integration - are tracked as open questions in the
[roadmap](docs/roadmap.md#open-questions) rather than written up as decisions.

## Roadmap

Eleven phases, from the foundation to the frontend:
[docs/roadmap.md](docs/roadmap.md). Each phase leaves the repository working and tested.

## Contributing

Conventional Commits, enforced locally and in CI. See [CONTRIBUTING.md](CONTRIBUTING.md).
