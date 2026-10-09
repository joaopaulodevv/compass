# Compass API

FastAPI application API for Compass. See the repository root `README.md` for the
product overview and `docs/development.md` for how to run this service.

Quick reference:

```bash
uv sync --all-groups             # install dependencies
uv run alembic upgrade head      # apply migrations
uv run python -m compass_api.seed  # create the local demo user
uv run uvicorn compass_api.main:app --reload
uv run pytest
```

Interactive API documentation is served at `/docs` (Swagger UI) and `/redoc`.

Layout:

| Package         | Holds                                                        |
| --------------- | ------------------------------------------------------------ |
| `api/`          | Routers, handlers and dependencies. Transport only           |
| `core/`         | Settings and structured logging                              |
| `domain/`       | Money rules and provider-neutral snapshots                   |
| `providers/`    | Open Finance adapters, including the sandbox fixture         |
| `repositories/` | All SQL                                                      |
| `services/`     | Business rules: ingestion, categorisation, and the pure engine |
| `migrations/`   | Alembic environment and revisions                            |

Financial endpoints require an `X-User-Id` header while authentication does not exist.
See `docs/development.md` in the repository root.
