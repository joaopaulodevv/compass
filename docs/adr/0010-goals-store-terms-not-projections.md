# ADR-0010: A goal stores its terms; every projection is computed

- **Status:** Accepted
- **Date:** 2026-10-09

## Context

A goal is "R$ 20,000 for a trip in 18 months". Everything a user actually wants to know
about it is derived: how long it takes at what they can save, what the deadline demands,
whether they are ahead or behind, how the options compare.

Those answers change whenever anything they depend on changes - a new month of
transactions shifts the measured saving capacity, a contribution recorded moves the
balance, and time passing moves the line the user is measured against. A projection
stored at creation is wrong by the next day and has no way to say so.

There is also a question with no honest answer yet: what return to assume. Compass does
not know what any product pays - the knowledge base that would tell it is a later phase -
and a default rate picked here would propagate into every projection as an unsourced
number presented as a measurement.

## Decision

**Only terms are stored**: name, target amount, optional target date, what was already
set aside, what the user plans to contribute, status. Everything else is computed on
request by the pure engine (ADR-0008), so a stale forecast cannot be served.

Four rules follow from wanting the numbers to be defensible rather than merely plausible:

- **The return rate is always the caller's assumption.** It is a request parameter with a
  default of zero - saving without growth - and it is echoed back in the response.
  Compass never invents it. When the knowledge base can supply a sourced, dated rate for
  a real product, it will arrive as that parameter, with its provenance.
- **An annual rate converts to a monthly one properly**: `(1 + annual) ** (1/12) - 1`,
  not `annual / 12`. Dividing by twelve overstates monthly growth and quietly flatters
  every projection.
- **A requirement rounds up; a measurement rounds to nearest.** `required_monthly` is
  rounded up to the centavo, because a contribution rounded to nearest lands short of the
  target - and a required amount that does not meet the requirement is worse than
  useless.
- **Reaching the target is judged on the balance rounded to the centavo.** Money is only
  meaningful to the centavo, and without this R$ 10,000 at an effective 10% a year would
  "fail" to reach R$ 11,000 in twelve months by a fraction of a cent of decimal residue.

Projections step one month at a time rather than using a closed-form annuity formula. The
loop *is* the definition - contribute, then earn a return on the balance - so it can be
read, checked against a spreadsheet, and extended later (a contribution that changes, a
withdrawal) without re-deriving algebra. `required_monthly` solves the same definition
algebraically, and a test asserts the two never disagree.

**Where the contribution came from is part of the answer.** A forecast uses, in order:
the figure the caller asked for, the goal's own plan, or the saving capacity measured
from the user's history - and reports which. "You could save R$ 3,784 a month" means
something different when it is measured from six months of the user's own transactions
than when they typed it in.

## Consequences

- A forecast is always current: it reflects today's balance, today's date and today's
  measured capacity.
- The goal endpoints compose with the Phase 3 engine rather than duplicating it - the
  fallback contribution *is* the saving capacity from ADR-0009.
- A user can ask "could I?" before committing: `POST /goals/simulate` runs the same
  engine with nothing persisted.
- Cost: every read recomputes. The work is a few hundred decimal operations over one
  goal, which is nothing; if a dashboard ever needs many goals at once, caching belongs
  in front of the service, not in the schema.
- Cost: no history of past projections, so "what did we tell the user in March?" cannot
  be answered. If that becomes a requirement it is an append-only log of forecasts, not a
  column on the goal.
- A rate the user picks can be unrealistic. The API caps it at 100% a year, which rejects
  the absurd without pretending to validate the plausible.

## Alternatives considered

- **Store the projection alongside the goal** (months to target, projected completion).
  Cheap reads, and every row is stale the moment anything moves. It also invites the
  question of when to refresh, which has no good answer.
- **Default to a "typical" return rate**, such as the current Selic or savings-account
  yield. More useful-looking output, built on a number Compass cannot source or date -
  precisely the failure mode ADR-0005 exists to prevent.
- **Closed-form annuity formulas only.** Compact and fast, and harder to read, harder to
  check by hand, and it would have to be re-derived for the first variable-contribution
  feature.
- **A separate contributions table**, with the balance derived from it. More faithful to
  reality and the right design once contributions are tracked individually; today
  `current_amount` plus `PATCH` is the smaller thing that works, and the table can
  replace it without changing any projection.
