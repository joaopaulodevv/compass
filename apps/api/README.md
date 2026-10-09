# Compass API

FastAPI application API for Compass. See the repository root `README.md` for the
product overview and `docs/development.md` for how to run this service.

Quick reference:

```bash
uv sync --all-groups          # install dependencies
uv run alembic upgrade head   # apply migrations
uv run uvicorn compass_api.main:app --reload
uv run pytest
```

Interactive API documentation is served at `/docs` (Swagger UI) and `/redoc`.
