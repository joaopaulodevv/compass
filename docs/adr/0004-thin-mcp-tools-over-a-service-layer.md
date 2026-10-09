# ADR-0004: Financial capabilities as thin MCP tools over a service layer

- **Status:** Accepted
- **Date:** 2026-10-09

## Context

The agent will need capabilities such as `get_cashflow`, `calculate_saving_capacity`,
`detect_recurring_expenses`, `simulate_goal` and `calculate_goal_gap`. These will be
exposed over MCP so the agent can call them as tools.

Two failure modes are easy to walk into:

1. Financial logic written inside tool handlers. The rules then depend on the protocol:
   they cannot be reused by an HTTP endpoint, they are awkward to unit test, and a
   protocol change becomes a rewrite of business logic.
2. A service layer that is pure indirection - a function per endpoint that forwards one
   call - which adds files and reads as architecture without being any.

MCP is also young; the transport will evolve faster than the definition of free cash flow.

## Decision

Financial capabilities live in a service layer. MCP tool definitions are thin adapters.

```
MCP tool definition (schema, validation, serialisation)
        ↓
financial service (deterministic calculation, typed domain input/output)
        ↓
repositories / providers (PostgreSQL, Open Finance adapter)
```

Rules:

- A service function takes and returns typed domain objects, never protocol envelopes. It
  does not know whether its caller is MCP, HTTP or a test.
- A tool body is a schema plus a service call plus serialisation. A financial rule
  appearing in a tool body is a defect.
- Database and provider access happens in repositories/providers, not in services'
  bodies - services receive what they need, which is what makes them testable against
  fixtures with no I/O.
- Services and repositories are introduced when there is logic or a query to hold. Phase
  1 has neither and therefore has neither layer. `SELECT 1` behind a repository would be
  the second failure mode above.

## Consequences

- The same calculation is reachable from MCP (for the agent) and from HTTP (for the
  frontend) with no duplication and no drift between the two.
- Financial logic is unit-testable over fixed fixtures - no server, no database, no LLM -
  which is the only way to trust the numbers.
- If MCP is replaced or augmented, the adapter layer is rewritten and the financial engine
  is untouched.
- Cost: one more hop for trivial capabilities, and a tool plus a service to keep in sync
  for each capability. Accepted: contract tests will assert that the tool schema and the
  service signature agree.

## Alternatives considered

- **Logic directly in MCP handlers.** Fewer files today; couples financial rules to a
  young protocol, blocks reuse over HTTP, and makes tests boot a tool server.
- **Agent calls repositories directly.** Shortest path, but the agent would then be doing
  arithmetic on raw rows - precisely what ADR-0005 forbids.
- **A separate financial microservice.** Real isolation, at the cost of network calls,
  deployment complexity and distributed debugging, for a single-maintainer project with no
  independent scaling need. A module boundary gives most of the benefit for none of the
  cost; this stays revisitable.
