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

Then seed a user and pull in sandbox financial data - see
[Working with financial data](#5-working-with-financial-data).

Tear down with `docker compose down -v` (`-v` also drops the database volume).

## 3. Or run the API on your machine

Infrastructure in Docker, application on the host - the fastest edit/test loop:

```bash
docker compose up -d postgres redis
make install                               # uv sync + git hooks
make migrate                               # alembic upgrade head
make seed                                  # create the local demo user
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

## 5. Working with financial data

Authentication does not exist yet, so the acting user travels in the **`X-User-Id`
header** and every financial endpoint requires it. `make seed` creates a demo user with a
fixed id, so the commands below work on any machine:

```bash
make seed
# demo user ready: 00000000-0000-4000-8000-000000000001 <demo@compass.local>

USER=00000000-0000-4000-8000-000000000001

# Ingest six months of sandbox history (no network, no credentials).
curl -X POST -H "X-User-Id: $USER" localhost:8000/open-finance/sync

# Safe to repeat: ingestion is idempotent, so nothing is duplicated.
curl -X POST -H "X-User-Id: $USER" localhost:8000/open-finance/sync

curl -H "X-User-Id: $USER" localhost:8000/accounts
curl -H "X-User-Id: $USER" 'localhost:8000/transactions?limit=5'
curl -H "X-User-Id: $USER" 'localhost:8000/transactions?since=2026-01-01&until=2026-03-31'
```

Computed views, derived on request from those transactions and never stored:

```bash
curl -H "X-User-Id: $USER" localhost:8000/insights/cashflow
curl -H "X-User-Id: $USER" localhost:8000/insights/recurring-expenses
curl -H "X-User-Id: $USER" localhost:8000/insights/saving-capacity

# Any window, both ends optional and inclusive:
curl -H "X-User-Id: $USER" \
  'localhost:8000/insights/cashflow?since=2026-01-01&until=2026-06-30'
```

A narrower window can be requested explicitly; both ends are optional and inclusive:

```bash
curl -X POST -H "X-User-Id: $USER" -H 'Content-Type: application/json' \
  -d '{"since": "2026-01-01", "until": "2026-03-31"}' \
  localhost:8000/open-finance/sync
```

Things worth knowing:

- **Amounts are JSON strings** (`"-2400.00"`), not numbers, so no client turns centavos
  into a float. They are signed: negative is money leaving the account.
- **Data is scoped by user.** Another `X-User-Id` sees an empty list, and an account id
  that is not yours returns `404` rather than `403`.
- **The provider is a local fixture.** `MockOpenFinanceProvider` reads
  `providers/open_finance/fixtures/sandbox.json`: six months of realistic history for
  three accounts at two institutions. No real provider has been chosen and no credentials
  are involved.
- Fixture dates are stored as a month offset plus a day, resolved against today, so the
  sandbox data is always recent.
- **Expenses exclude internal movements.** A credit-card bill payment and a transfer to
  the user's own savings move money they already have; the card's spending is counted
  where it happened. `internal_movements` reports the total left out, so the figures can
  be reconciled against a raw sum of the statement. This is the single assumption that
  most affects every number - see `docs/adr/0009-internal-movements-are-not-cash-flow.md`.
- **Categories come from deterministic rules**, assigned at ingestion and stored with
  `category_rule` (`keyword:groceries`, `provider:utilities`, `sign:credit`, `fallback`)
  so a surprising label can be traced. Changing the rules and re-running the sync
  re-categorises everything, because the upsert refreshes the column.
- **Saving capacity is the median monthly net over whole calendar months**, floored at
  zero. `months_considered: 0` means there is not enough history to answer - not that
  the capacity is zero.

### Goals

```bash
# "Could I?" - runs the engine and persists nothing.
curl -X POST -H "X-User-Id: $USER" -H 'Content-Type: application/json' \
  -d '{"target_amount": "20000.00", "target_date": "2028-04-15"}' \
  localhost:8000/goals/simulate

# Create one, then ask for a forecast whenever you like.
GOAL=$(curl -s -X POST -H "X-User-Id: $USER" -H 'Content-Type: application/json' \
  -d '{"name": "Viagem", "target_amount": "20000.00", "target_date": "2028-04-15",
       "monthly_contribution": "900.00"}' localhost:8000/goals | jq -r .id)

curl -H "X-User-Id: $USER" "localhost:8000/goals/$GOAL/forecast"
curl -H "X-User-Id: $USER" "localhost:8000/goals/$GOAL/forecast?annual_return_rate=0.11"

# Record progress; reaching the target marks the goal achieved.
curl -X PATCH -H "X-User-Id: $USER" -H 'Content-Type: application/json' \
  -d '{"current_amount": "4500.00"}' "localhost:8000/goals/$GOAL"

curl -X POST -H "X-User-Id: $USER" -H 'Content-Type: application/json' \
  -d '{"options": [{"label": "plano", "monthly_contribution": "900.00"},
                   {"label": "com rendimento", "monthly_contribution": "900.00",
                    "annual_return_rate": "0.11"}]}' \
  "localhost:8000/goals/$GOAL/comparison"
```

Worth knowing:

- **Nothing about a goal is precomputed.** The forecast is derived every time, so it
  always reflects today's balance, today's date and today's measured capacity.
- **A forecast says where its contribution came from** (`requested`, `goal_plan` or
  `measured_capacity`). Without a plan of their own, the user is told what their own
  history supports.
- **The return rate is yours, not Compass's.** It defaults to zero - saving without
  growth - and Compass will not guess one until the knowledge base can supply a sourced,
  dated figure.

## 6. The MCP tool server

The financial capabilities are also exposed as MCP tools, for an agent or any MCP client:

```bash
uv run --directory apps/api python -m compass_api.mcp_server   # stdio transport
```

Nine tools, each taking the acting user as an explicit `user_id` argument - the same
stand-in for authentication the HTTP layer takes as a header. They are thin adapters over
the same services the API uses, and `tests/integration/test_mcp_contract.py` asserts the
two answer identically on real data.

Adding a tool is adding a function to `FINANCIAL_TOOLS` in
`apps/api/src/compass_api/mcp_server/tools.py`: the schema comes from the type hints and
the description from the docstring.

## 7. Talking to the assistant

The conversational endpoints need an LLM. Without `OPENAI_API_KEY` they answer `503` and
everything else keeps working - that is deliberate, not a failure.

```bash
export OPENAI_API_KEY=sk-...      # or put it in .env
# optional: OPENAI_MODEL=gpt-4o-mini is the default

CONV=$(curl -s -X POST -H "X-User-Id: $USER" -H 'Content-Type: application/json' \
  -d '{}' localhost:8000/conversations | jq -r .id)

curl -X POST -H "X-User-Id: $USER" -H 'Content-Type: application/json' \
  -d '{"content": "quanto consigo guardar por mes?"}' \
  "localhost:8000/conversations/$CONV/messages"

curl -H "X-User-Id: $USER" "localhost:8000/conversations/$CONV/messages"
```

The assistant's reply carries `tool_calls`: which tools produced its numbers. Every
figure it states should be traceable there - if one is not, the model computed it and that
is a bug in the prompt or the tools, not a rounding difference.

The agent calls the MCP tools, and `user_id` is injected server-side: the model never sees
that argument, so it cannot be redirected at another user's data.

**The test suite never calls a model.** `ScriptedLLM` replays queued responses, which is
what makes the agent's behaviour - tools offered, results fed back, budget respected -
testable at all.

## 8. Tests

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

The financial engine's tests need no infrastructure at all: the calculations are pure
functions, so each case is a hand-written list of movements and a value worked out by
hand. That is deliberate - these are the numbers everything else trusts, and a test that
needs a database is a test nobody writes for the awkward cases.

Integration tests create their own user and delete it afterwards, which cascades to that
user's accounts and transactions - so tests cannot see each other's data, and the cascade
itself gets exercised. The sandbox provider is pinned to a fixed reference date, so every
assertion about dates and windows is deterministic.

Point the integration suite somewhere else with `TEST_DATABASE_URL`.

Coverage is reported as a diagnostic (`--cov`), with no threshold gate. A number is not a
substitute for reading what is actually covered. Note one artefact: a few lines that run
immediately after an `await` inside the test client's worker thread are not traced, so
they show as uncovered even though the tests exercise them.

## 9. Code quality

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

## 10. Database migrations

```bash
make migrate                                   # upgrade head
make migration m="add financial goals table"   # autogenerate a revision
make drift                                     # fail if models and migrations disagree
uv run --directory apps/api alembic downgrade -1
uv run --directory apps/api alembic history
```

`make drift` (`alembic check`) is also a CI step: it fails the build if a model changed
without a migration.

Two rules:

1. A new model must be imported in `apps/api/src/compass_api/db/models/__init__.py`.
   Alembic autogenerate only sees tables registered on `Base.metadata`.
2. Always read the generated revision before committing it. Autogenerate is a drafting
   tool, not an oracle - and check that `downgrade()` is correct too. The Phase 2
   revision is a concrete example: autogenerate emitted the enum's CHECK constraint
   twice and the duplicate had to be removed by hand.

Alembic takes the connection URL from application settings (`migrations/env.py`), so
migrations and the running application can never target different databases, and no
connection string is ever committed.

## 11. Environment variables

| Variable              | Required | Default                  | Purpose                              |
| --------------------- | -------- | ------------------------ | ------------------------------------ |
| `APP_ENV`             | no       | `local`                  | `local` / `test` / `staging` / `production` |
| `LOG_LEVEL`           | no       | `INFO`                   | Root log level                        |
| `DATABASE_URL`        | **yes**  | -                        | Async PostgreSQL DSN (`postgresql+asyncpg://`) |
| `DATABASE_ECHO`       | no       | `false`                  | Log every SQL statement               |
| `REDIS_URL`           | no       | `redis://localhost:6379/0` | Reserved; no consumer yet           |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | no | `compass` | Consumed by the Compose `postgres` service |
| `OPENAI_API_KEY`      | no       | unset                    | The assistant. Absent, its endpoints answer 503 |
| `OPENAI_MODEL`        | no       | `gpt-4o-mini`            | Which model the assistant uses        |
| `PINECONE_API_KEY`    | no       | unset                    | Future RAG                            |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | no | unset | Future agent observability     |
| `DATADOG_API_KEY`     | no       | unset                    | Future app observability              |

`DATABASE_URL` is the only required variable: the API cannot do anything useful without
it, and a missing future credential must never stop the service from starting.

## 12. Repository layout

```
compass/
├── apps/
│   ├── api/                  # FastAPI backend (implemented)
│   │   ├── src/compass_api/
│   │   │   ├── api/          # Routers, handlers, dependencies (transport only)
│   │   │   ├── core/         # Settings, logging
│   │   │   ├── db/           # Base, session, models
│   │   │   ├── domain/       # Money rules, provider-neutral snapshots
│   │   │   ├── providers/    # Open Finance adapters (+ sandbox fixture)
│   │   │   ├── repositories/ # All SQL lives here
│   │   │   ├── agent/       # LLM interface, graph, prompt, toolbox
│   │   │   ├── mcp_server/   # MCP adapter over the same services
│   │   │   ├── services/     # Business rules (ingestion today)
│   │   │   ├── migrations/   # Alembic environment and revisions
│   │   │   ├── seed.py       # Local demo user
│   │   │   └── main.py       # Application factory
│   │   └── tests/{unit,integration}
│   └── web/                  # Future Next.js app (README only)
├── docs/{architecture,development,roadmap}.md
├── docs/adr/                 # Architecture decision records
├── infra/                    # Reserved for deployment assets
├── docker-compose.yml
└── Makefile
```

## 13. Troubleshooting

**`ModuleNotFoundError: No module named 'compass_api'`** - the project is not installed
in the virtualenv: `uv sync --directory apps/api --all-groups`.

**`/ready` returns 503** - PostgreSQL is unreachable. Check `docker compose ps` and
that `DATABASE_URL` uses `localhost` from the host and `postgres` inside Compose.

**`alembic: connection refused`** - same cause; Alembic uses the same `DATABASE_URL`.

**`docker compose up` complains about a missing `.env`** - run `cp .env.example .env`.

**Integration tests all skip** - that is the designed behaviour with no database
reachable. Start one and run `make migrate`.

**`422` from a financial endpoint** - the `X-User-Id` header is missing or is not a UUID.
It is rejected before any query runs.

**`404` from `POST /open-finance/sync`** - that user does not exist. Run `make seed`, or
use the id of a user you created.

**`/accounts` returns an empty list** - nothing has been ingested for that user yet. Run
the sync call first, and check you are sending the same `X-User-Id`.

**`/insights/saving-capacity` reports `months_considered: 0`** - the window contains no
*whole* calendar month. Widen it; partial months are excluded on purpose.

**A transaction has an unexpected category** - read its `category_rule` on
`GET /transactions`. It names the rule that fired, so the fix is either a rule in
`services/categorization.py` or nothing at all.

**`503` from a `/conversations` endpoint** - `OPENAI_API_KEY` is not set. The financial
API does not need it; only the assistant does.

**A goal forecast says `monthly_contribution: "0.00"`** - the measured capacity is zero
because there is no ingested history, or no whole month in it. Run the sync, or pass
`?monthly_contribution=`.

**The demo user has no data after running the tests** - the integration suite deletes the
demo user on purpose, to cover the seed's insert path deterministically, and that
cascades to its accounts and transactions. Run `make seed` and the sync again.
