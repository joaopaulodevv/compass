# ADR-0011: MCP is a second transport over the same services

- **Status:** Accepted
- **Date:** 2026-10-09

## Context

The agent needs to reach the financial engine. ADR-0004 fixed the shape of that - tools
stay thin over services - but left two things open once a real SDK was involved: how a
tool gets a database session and the acting user, and how to stop the MCP answers and the
HTTP answers drifting apart as the engine changes.

Drift is the real risk. Two transports over the same domain usually grow their own small
conveniences - a rounding here, a default window there - until the API and the agent
disagree about the user's money, and nothing fails to reveal it.

## Decision

**`compass_api/mcp_server/` is an adapter, not a layer.** Each tool parses arguments,
opens a session, calls a service, and serialises the result. There is no financial rule in
the package, and a test asserts the tools and the HTTP routes agree on real data.

- **Registration is mechanical.** `FINANCIAL_TOOLS` is a tuple of functions; the server
  loops over it. The schema comes from the type hints and the description from the
  docstring, so nothing about a tool is written twice and a tool cannot describe itself
  incorrectly.
- **Serialisation is generic.** One `to_jsonable` converter walks dataclasses, decimals,
  dates, UUIDs and enums. Adding a field to a result type cannot silently drop it from
  the agent's view. Amounts cross as strings, exactly as over HTTP.
- **`user_id` is an explicit argument on every tool.** Authentication does not exist yet;
  the caller supplies the same isolation key the HTTP layer takes as a header. A unit
  test asserts every tool requires it, because that argument is the only thing standing
  between one user's data and another's.
- **A tool that cannot answer raises `ToolError`.** Its message reaches the model, while
  any other exception is hidden behind a generic failure. "Goal not found" must not come
  back as a plausible-looking zero.
- **The session factory is overridable through a `ContextVar`.** FastAPI has
  `dependency_overrides`; an MCP tool's signature *is* its public schema, so a session
  cannot be passed as an argument. The contract tests need the tools to use a factory
  created in the test's own event loop, because the HTTP application owns a different
  engine inside the test client's loop.
- **The server instructs the model not to do arithmetic.** The instruction that the tools
  are exact and the model's own arithmetic is not belongs where a model will read it.

The package is named `mcp_server` rather than `mcp` so it cannot shadow the SDK it
imports.

## Consequences

- The agent reaches the same numbers the API serves, and the contract tests fail loudly if
  that stops being true.
- Adding a capability is adding a function to one tuple: no registration boilerplate, no
  schema to maintain by hand.
- The MCP server runs standalone over stdio (`python -m compass_api.mcp_server`), so it
  can be attached to any MCP client, not only to Compass's own agent.
- Cost: the SDK is now a runtime dependency of the API package, and its API changed
  between major versions (`FastMCP` became `MCPServer` in 2.x). The adapter is the only
  place that would have to change again.
- Cost: a `ContextVar` for the session factory is a seam that exists mainly for tests.
  The alternative was threading a factory through every signature, which would put test
  plumbing into the published schema.
- Tools trust `user_id` completely. That is the same trust the HTTP header carries today,
  and the same thing authentication will replace.

## Alternatives considered

- **Reuse the FastAPI response models for serialisation.** Guarantees identical output by
  construction, and makes the agent's contract depend on a transport module - the import
  direction ADR-0004 exists to prevent. The contract tests buy the same guarantee without
  the coupling.
- **Put the MCP server in a separate application.** Cleaner process boundary, at the cost
  of duplicating configuration, database wiring and deployment for a server that is a thin
  adapter over the same code. Worth revisiting if the tools ever need to scale separately.
- **Expose the HTTP API to the agent instead of MCP tools.** No new dependency, and it
  would make the agent an HTTP client of its own process, with schemas the model has to
  infer from OpenAPI rather than tool definitions written for it.
- **Hand-written JSON schemas per tool.** Total control, and two descriptions of every
  tool to keep in sync.
