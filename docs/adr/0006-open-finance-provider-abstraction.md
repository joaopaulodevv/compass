# ADR-0006: Open Finance data enters through a protocol Compass owns

- **Status:** Accepted
- **Date:** 2026-10-09

## Context

Compass needs real financial history, which means an Open Finance aggregator. No provider
has been chosen - Pluggy and Belvo are both plausible, and the choice depends on sandbox
quality and on coverage of the institutions that matter, neither of which is known yet.

Meanwhile every later phase needs data to compute on. Waiting for the provider decision
would block the financial engine, the agent and the frontend behind a procurement
question.

Two further forces shape this:

- Provider payloads are vendor-shaped, inconsistent and large. Letting them reach the
  database or the calculations would spread one vendor's schema through the system.
- Syncs overlap. A scheduled job re-reads the last few weeks every run, and a user can
  trigger one at will. A duplicated salary credit would inflate every cash-flow figure
  derived from it, silently and permanently.

## Decision

**Ingestion depends on a protocol Compass defines**, never on a vendor SDK:

```
provider adapter  ->  domain snapshots  ->  sync service  ->  repositories  ->  PostgreSQL
```

- `compass_api.providers.open_finance.base.OpenFinanceProvider` is a `typing.Protocol`
  with `get_institutions`, `get_accounts` and `get_transactions`. Structural typing means
  an adapter - or a test double - satisfies it without importing an abstract base of ours.
- The only shapes crossing that boundary are the frozen, strictly validated snapshots in
  `compass_api.domain.open_finance`. A vendor field that is not in a snapshot does not
  enter the system.
- `MockOpenFinanceProvider` reads a committed fixture: six months of realistic history,
  no network, no credentials. It is the development and test implementation, and it is
  the reference for what a real adapter must produce.
- Dates in the fixture are a month offset plus a day, resolved against a reference date.
  The data stays recent without being rewritten, and a test that pins the reference date
  gets identical results every run.
- Ingestion is **idempotent**, keyed on the provider's own identifiers:
  `(user_id, provider, external_id)` for accounts and
  `(account_id, provider, external_id)` for transactions, both enforced by unique
  constraints and written with `INSERT ... ON CONFLICT DO UPDATE`.
- `provider` is stored on every row, so data from several providers can coexist and one
  provider's records can be re-synced or retired without touching the others.
- The sync service is the only place that knows what "syncing a user" means. It receives
  a provider; it does not choose one. `compass_api.api.deps.get_open_finance_provider` is
  the single place that selects the implementation.

## Consequences

- The provider decision is deferred without blocking anything. Choosing one means writing
  one adapter and changing one dependency function.
- Every later phase can be built and tested against deterministic data, with no network
  and no credentials in the test suite.
- Re-running a sync is safe, which is what makes an eventual scheduled job or a
  user-triggered refresh possible at all.
- Cost: an extra translation layer, and snapshots to extend whenever a new field is
  genuinely needed. That friction is the point - it is what stops vendor shapes leaking.
- Cost: the mock can drift from real provider behaviour (pagination, partial windows,
  revised transactions, currency edge cases). The first real adapter will expose this;
  the snapshots are where any correction lands.
- Writing with `ON CONFLICT DO UPDATE` means a provider that revises a transaction
  overwrites the stored row. That is intended today. If an audit trail of revisions is
  ever needed it becomes a new ADR, not a tweak.

## Alternatives considered

- **Pick a provider now and use its SDK directly.** Fastest to a real integration, and
  it would put one vendor's schema in the database and in the calculations. Reversing
  that later means a migration plus a rewrite.
- **Store raw provider payloads and normalise on read.** Keeps everything the provider
  sent, at the cost of every reader knowing every vendor's shape. Worth revisiting if an
  audit trail is required, but it is the wrong default.
- **Delete and re-insert each sync window.** Trivially correct against duplicates, and it
  discards row identity, `created_at`, and anything Compass later attaches to a
  transaction - its own category, for instance.
- **Hash the transaction fields as the idempotency key.** Works without a provider id,
  but two identical coffees on the same day would collide, and any corrected field would
  create a new row instead of updating one.
