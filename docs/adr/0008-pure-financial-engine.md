# ADR-0008: The financial engine is pure Python over fetched rows

- **Status:** Accepted
- **Date:** 2026-10-09

## Context

Every figure Compass will put in front of a user - cash flow, saving capacity, the gap to
a goal - comes out of the same engine. ADR-0005 committed to those numbers being
deterministic and auditable, because the LLM is never allowed to compute them.

There were two places to put the arithmetic: in SQL, aggregated by PostgreSQL, or in
Python over rows fetched from it.

SQL is the obvious choice for aggregation at scale, and it is the wrong default here.
Testing `GROUP BY date_trunc('month', ...)` needs a database, which makes the tests that
guard the most important numbers in the product slow, environment-dependent, and awkward
to write for edge cases - a partial month, a window with no data, three charges of ten
centavos.

## Decision

Calculations are **pure functions over a list of movements**:

```
repository -> Sequence[Movement] -> engine function -> result dataclass
```

- `compass_api.domain.analysis.Movement` is the engine's only input type. It is
  deliberately **not** the ORM `Transaction`: a calculation must not be able to depend on
  persistence, lazy loading, or the shape of a provider payload.
- `services/cashflow.py`, `services/recurring.py` and `services/saving_capacity.py`
  contain no I/O at all. They import no session, no repository and no settings.
- `services/insights.py` is the only place that joins the two: it reads movements through
  the repository and hands them to the engine. Routes call it and orchestrate nothing.
- Results are frozen dataclasses, so a figure cannot be mutated after the fact.
- Every derived figure is rounded to centavos, half away from zero
  (`domain.money.quantize_money`). Sums of stored amounts are already exact; this matters
  for a mean or a median of an even number of values.

## Consequences

- The tests that guard the numbers need no database, no server and no fixtures on disk.
  Each case is a hand-written list of movements and an expected value worked out by hand -
  which is the only way to be confident the arithmetic is right rather than merely stable.
- An edge case is cheap to add, so the edge cases are actually covered: partial months,
  empty windows, inverted windows, exactness to the centavo.
- The same functions will back the future MCP tools with no changes, because they already
  know nothing about transport (ADR-0004).
- Cost: the whole window is loaded into memory. For six months of one user's transactions
  that is a few hundred rows and irrelevant. It would stop being irrelevant at years of
  history or a batch job over many users.
- Cost: aggregation logic that PostgreSQL would do well is hand-written.

The revisit threshold is explicit: if a window ever needs more rows than fit comfortably
in memory, or a report has to run across users, the aggregation moves into SQL behind the
same repository method - and the pure functions stay as the reference implementation the
SQL is tested against.

## Alternatives considered

- **Aggregate in SQL.** Faster and scales further, at the cost of making the product's
  most important tests require a database. Deferred, not rejected: the repository
  boundary is where it would land.
- **Pure functions over ORM `Transaction` objects.** One less type to map. It would let a
  calculation reach a relationship and trigger a lazy load, which under asyncio fails as
  a greenlet error far from the cause, and it would couple the engine to the schema.
- **A pandas/polars pipeline.** Expressive for this shape of work, and a heavy dependency
  plus a second mental model for a few hundred rows. Reconsider if the analysis grows
  into genuine data processing.
