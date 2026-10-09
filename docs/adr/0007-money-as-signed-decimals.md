# ADR-0007: Money is a signed decimal, everywhere

- **Status:** Accepted
- **Date:** 2026-10-09

## Context

Every number Compass eventually puts in front of a user - free cash flow, saving
capacity, the gap to a goal - is an aggregation over stored amounts. Two representation
choices made now are expensive to reverse later, because they shape the schema, the API
contract and every calculation.

Floating point cannot represent R$ 0.10. Summing six months of transactions in `float`
accumulates error that shows up as a few centavos of drift, which in a financial product
reads as a bug and undermines everything else the product says.

Direction is the second choice: either a magnitude plus a flag (`amount: 2400,
direction: "debit"`), or one signed number.

## Decision

- **`Decimal` end to end.** `NUMERIC(18, 2)` in PostgreSQL, `Decimal` in Python,
  parsed from strings in the provider fixture so no float ever appears in the path.
  `compass_api.domain.money` holds the precision constants.
- **Signed amounts.** Negative is money leaving the account, positive is money arriving.
  One column, no flag.
- **`direction` is derived, never stored** - `Direction.of(amount)` - and exposed on the
  API so clients do not each reimplement the comparison.
- **Amounts serialise as JSON strings.** A JSON number would hand every client a float to
  round badly, which defeats the point of storing a decimal.
- A credit card balance is negative when money is owed, and an account's currency is
  stored per account (BRL in practice, but the column is there).

## Consequences

- Aggregating a window is a sum, with no direction branch to get wrong - and no branch
  is the cheapest branch to test.
- Totals are exact to the centavo, and stay exact through the database, the API and the
  future financial engine.
- Clients must parse the amount string. That is a deliberate, documented contract: it
  makes the precision requirement visible at the boundary instead of silently lost.
- Cost: `Decimal` arithmetic needs care about context and rounding when percentages and
  projections arrive (interest, inflation). That belongs to the engine phase, where the
  rounding rule for each calculation will be explicit.
- Cost: a signed column makes "total spend" slightly less obvious than a magnitude
  column - it is a sum over negatives. Worth it for the single representation.

## Alternatives considered

- **Integer centavos.** Exact and fast, and the standard choice in payment systems. It
  pushes a scaling factor into every read, write, API payload and test fixture, and
  invites the one place that forgets it. `NUMERIC` gives the same exactness with the
  decimal point where a reader expects it. Revisit if performance ever demands it.
- **`float` with rounding at the edges.** Simplest to write and wrong in a way that only
  surfaces once totals are large enough to matter.
- **Magnitude plus a direction flag.** Mirrors how statements read, and makes every
  aggregation a conditional sum, with two fields that can contradict each other.
- **A money library (`py-moneyed`, `money`).** Currency-aware arithmetic for free, and a
  dependency plus a type to map through the ORM and the API for a product that is
  single-currency in practice today.
