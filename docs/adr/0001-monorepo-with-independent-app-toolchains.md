# ADR-0001: Monorepo with independent per-app toolchains

- **Status:** Accepted
- **Date:** 2026-10-09

## Context

Compass will eventually consist of a Python backend (API, financial services, MCP tools,
agent) and a TypeScript frontend, plus shared documentation and infrastructure
definitions. These parts change together: an endpoint and the screen that calls it, a
tool and the agent that uses it.

It is also a single-maintainer project. Coordination cost across repositories would be
paid on every change and buy nothing.

## Decision

Use a single repository with applications under `apps/`:

```
apps/api     FastAPI backend          (implemented)
apps/web     Next.js frontend         (placeholder)
docs/        documentation and ADRs
infra/       deployment assets (reserved)
```

Each application owns its own toolchain and lockfile. `apps/api` has its own
`pyproject.toml` and `uv.lock`; `apps/web` will have its own `package.json` and lockfile.
There is no shared root dependency manifest and no uv workspace.

Shared Python code, if two Python applications ever need it, will be introduced as a
`packages/` member at that point - not before.

## Consequences

- One pull request can change the API, the frontend and the documentation coherently.
- Each application is built, tested and containerised independently. CI jobs scope
  themselves with `--directory apps/api` and path filters.
- Nothing in the Python toolchain constrains the Node toolchain, which is the normal
  state of affairs in a polyglot repository.
- Cost: no cross-application dependency resolution. If shared Python code appears later,
  a workspace must be introduced then. Accepted - introducing one now would configure a
  mechanism with one member and no consumer.
- Cost: paths are slightly longer, and commands must be run with the right directory.
  Mitigated by a root `Makefile`.

## Alternatives considered

- **Separate repositories per application.** Version skew and cross-repository pull
  requests from day one, for a project with a single maintainer and no independent
  release cadence.
- **uv workspace at the repository root.** Appealing for a Python-only repository. Here
  the second application is TypeScript, so the workspace would wrap exactly one member
  and still not cover the frontend.
