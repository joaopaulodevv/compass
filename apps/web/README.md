# Compass Web (not implemented)

This directory is reserved for the Compass web frontend. **Nothing is implemented yet** -
it exists so the location of the future application is unambiguous.

## Planned stack

- Next.js (App Router)
- React
- TypeScript

## Planned responsibilities

- Conversational interface to the financial assistant
- Financial overview: cash flow, categorised expenses, recurring expenses
- Goal creation, simulation and progress tracking
- Presentation of recommendations, including the reasoning and the data behind them

## Boundaries

The frontend will talk only to the FastAPI application API (`apps/api`) over HTTP.
It will never call the agent, the MCP tools, the vector store or an Open Finance
provider directly, so that authorisation, auditing and user data isolation stay in one
place on the server.

The web app will keep its own toolchain (`package.json`, its own lockfile) rather than
sharing one with the Python backend. See `docs/adr/0001-monorepo-with-independent-app-toolchains.md`.
