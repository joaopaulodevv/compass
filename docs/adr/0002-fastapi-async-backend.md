# ADR-0002: FastAPI and an async-first backend

- **Status:** Accepted
- **Date:** 2026-10-09

## Context

The backend's work is almost entirely waiting: PostgreSQL queries, Open Finance HTTP
calls, LLM calls (slow, often streamed), and vector-store lookups. Its public contract
needs to be discoverable by a frontend developer and, later, by an agent.

It must also validate untrusted input strictly - this is financial data - and the project
already uses Pydantic models as the natural way to express financial payloads.

## Decision

Use FastAPI, with an async-first posture:

- Routes are `async def`; database access uses SQLAlchemy's asyncio extension with
  `asyncpg`.
- The application is built by a `create_app(settings)` factory rather than a module-level
  singleton, so settings are injectable and tests do not touch the real environment.
- Startup and shutdown live in a lifespan context manager, which owns process-wide
  resources (currently: disposing the database engine).
- OpenAPI/Swagger comes from the framework and is never maintained by hand. It is
  disabled automatically when `APP_ENV=production`.

Async is the default **because** the workload is I/O-bound. Where a future piece of work
is CPU-bound (a heavy simulation, say), it will be run in a thread or process pool rather
than being made async for consistency's sake.

## Consequences

- One concurrency model end to end: an agent waiting on an LLM does not occupy a thread.
- Request and response schemas are typed and validated at the boundary, and the generated
  OpenAPI schema is always accurate.
- Dependency injection gives tests a seam: `app.dependency_overrides` replaces the
  database session, which is how the readiness endpoint is tested without a database.
- Cost: async code is less forgiving. A blocking call inside a coroutine stalls the event
  loop, and that class of bug is easy to introduce. `flake8-async` lint rules are enabled
  to catch the common cases.
- Cost: the async ecosystem has fewer mature libraries than the sync one in places.

## Alternatives considered

- **Django + DRF.** Admin, ORM and auth out of the box, but a heavier structure than this
  project needs and a weaker async story for a workload dominated by LLM latency.
- **Flask.** Familiar and small, but no first-class typed validation or generated OpenAPI,
  both of which are load-bearing here.
- **Litestar.** Comparable technically. FastAPI wins on ecosystem familiarity, which
  matters for a project meant to be read by others.
