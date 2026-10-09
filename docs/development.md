# Development

## Prerequisites

| Tool            | Version | Why                                        |
| --------------- | ------- | ------------------------------------------ |
| Python          | 3.13+   | Backend runtime (`.python-version` pins it) |
| [uv](https://docs.astral.sh/uv/) | 0.11+ | Dependency management and task running |
| Docker + Compose plugin | v2+ | Local PostgreSQL and Redis            |
| make            | any     | Convenience targets (optional)             |

`uv` can install Python for you: `uv python install 3.13`.

## 1. Configure the environment

```bash
cp .env.example .env
```

`.env` lives at the repository root and is git-ignored. Both Docker Compose and the API
read it. Nothing else needs editing for local development; the defaults match the
Compose services.

## 2. Run everything in Docker

```bash
docker compose up --build     # or: make up
```

This starts PostgreSQL, Redis and the API. Migrations are applied automatically on
container start (a development convenience - in a real deployment migrations are an
explicit step).

```bash
curl localhost:8000/health    # {"status":"ok","version":"0.1.0"}
curl localhost:8000/ready     # {"status":"ready","checks":{"database":"ok"}}
open http://localhost:8000/docs
```

Tear down with `docker compose down -v` (`-v` also drops the database volume).

## 3. Or run the API on your machine

Infrastructure in Docker, application on the host - the fastest edit/test loop:

```bash
docker compose up -d postgres redis
make install                               # uv sync + git hooks
make migrate                               # alembic upgrade head
make run                                   # uvicorn with --reload
```

Without `make`:

```bash
uv sync --directory apps/api --all-groups
uv run --directory apps/api alembic upgrade head
uv run --directory apps/api uvicorn compass_api.main:app --reload
```

`DATABASE_URL` in `.env.example` points at `localhost`, which is what the host-side
process needs. Compose overrides it with the `postgres` service name for the container.

## 4. API documentation

FastAPI generates it; we do not maintain a copy.

| URL              | What                        |
| ---------------- | --------------------------- |
| `/docs`          | Swagger UI                  |
| `/redoc`         | ReDoc                       |
| `/openapi.json`  | OpenAPI 3.1 schema          |

All three are disabled automatically when `APP_ENV=production`.

## 5. Tests

```bash
make test                 # full suite with coverage
make test-unit            # skip anything needing infrastructure
```

Two suites, by design:

- `apps/api/tests/unit` - no infrastructure. Settings are constructed explicitly, so
  these never depend on your local `.env`.
- `apps/api/tests/integration` - marked `integration`; they need a reachable PostgreSQL
  with migrations applied (`make migrate`). They **skip** rather than fail when no
  database is reachable, so `make test` stays useful offline.

Point the integration suite somewhere else with `TEST_DATABASE_URL`.

Coverage is reported as a diagnostic (`--cov`), with no threshold gate. A number is not
a substitute for reading what is actually covered.

## 6. Code quality

```bash
make lint        # ruff check
make format      # ruff format
make typecheck   # mypy --strict
make check       # lint + typecheck + tests (what CI runs)
make hooks       # pre-commit on all files
```

`make install` registers the git hooks. On commit: whitespace/EOF/YAML/TOML hygiene,
private-key detection, `ruff format`, `ruff check --fix`, `mypy`. On commit message:
Conventional Commits validation (see `CONTRIBUTING.md`).

The Python hooks run through `uv`, so pre-commit, CI and your shell all use the tool
versions pinned in `apps/api/uv.lock`. Invoke pre-commit from the repository root
(`make hooks`, or `uv run --project apps/api pre-commit ...`): with `--directory` the
working directory changes and pre-commit's path filters stop matching.

## 7. Database migrations

```bash
make migrate                                   # upgrade head
make migration m="add financial goals table"   # autogenerate a revision
uv run --directory apps/api alembic downgrade -1
uv run --directory apps/api alembic history
```

Two rules:

1. A new model must be imported in `apps/api/src/compass_api/db/models/__init__.py`.
   Alembic autogenerate only sees tables registered on `Base.metadata`.
2. Always read the generated revision before committing it. Autogenerate is a drafting
   tool, not an oracle - and check that `downgrade()` is correct too.

Alembic takes the connection URL from application settings (`migrations/env.py`), so
migrations and the running application can never target different databases, and no
connection string is ever committed.

## 8. Environment variables

| Variable              | Required | Default                  | Purpose                              |
| --------------------- | -------- | ------------------------ | ------------------------------------ |
| `APP_ENV`             | no       | `local`                  | `local` / `test` / `staging` / `production` |
| `LOG_LEVEL`           | no       | `INFO`                   | Root log level                        |
| `DATABASE_URL`        | **yes**  | -                        | Async PostgreSQL DSN (`postgresql+asyncpg://`) |
| `DATABASE_ECHO`       | no       | `false`                  | Log every SQL statement               |
| `REDIS_URL`           | no       | `redis://localhost:6379/0` | Reserved; no consumer yet           |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | no | `compass` | Consumed by the Compose `postgres` service |
| `OPENAI_API_KEY`      | no       | unset                    | Future agent layer                    |
| `PINECONE_API_KEY`    | no       | unset                    | Future RAG                            |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | no | unset | Future agent observability     |
| `DATADOG_API_KEY`     | no       | unset                    | Future app observability              |

`DATABASE_URL` is the only required variable: the API cannot do anything useful without
it, and a missing future credential must never stop the service from starting.

## 9. Repository layout

```
compass/
├── apps/
│   ├── api/                  # FastAPI backend (implemented)
│   │   ├── src/compass_api/
│   │   │   ├── api/          # Routers and route handlers (transport only)
│   │   │   ├── core/         # Settings, logging
│   │   │   ├── db/           # Base, session, models
│   │   │   ├── migrations/   # Alembic environment and revisions
│   │   │   └── main.py       # Application factory
│   │   └── tests/{unit,integration}
│   └── web/                  # Future Next.js app (README only)
├── docs/{architecture,development,roadmap}.md
├── docs/adr/                 # Architecture decision records
├── infra/                    # Reserved for deployment assets
├── docker-compose.yml
└── Makefile
```

## 10. Troubleshooting

**`ModuleNotFoundError: No module named 'compass_api'`** - the project is not installed
in the virtualenv: `uv sync --directory apps/api --all-groups`.

**`/ready` returns 503** - PostgreSQL is unreachable. Check `docker compose ps` and
that `DATABASE_URL` uses `localhost` from the host and `postgres` inside Compose.

**`alembic: connection refused`** - same cause; Alembic uses the same `DATABASE_URL`.

**`docker compose up` complains about a missing `.env`** - run `cp .env.example .env`.

**Integration tests all skip** - that is the designed behaviour with no database
reachable. Start one and run `make migrate`.
