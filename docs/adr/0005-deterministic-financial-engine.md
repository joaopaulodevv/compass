# ADR-0005: The deterministic engine computes, the LLM explains

- **Status:** Accepted
- **Date:** 2026-10-09

## Context

Compass answers questions like *"can I afford R$20,000 in 18 months?"*. Answering
involves arithmetic over the user's transaction history, and an explanation the user can
act on.

An LLM is good at the second part and unreliable at the first. It can produce a plausible
monthly saving figure that is simply wrong, and it will produce a different one next time.
Wrong numbers in financial guidance are not a cosmetic defect: they change what someone
does with their money. Non-deterministic numbers are also untestable and unauditable.

## Decision

Responsibilities are separated and the separation is enforced in code structure:

| Concern                | Owner                               |
| ---------------------- | ----------------------------------- |
| User financial data    | Repositories / Open Finance adapter |
| Financial calculations | Deterministic services, exposed as MCP tools |
| Product knowledge      | RAG over curated, dated sources     |
| Orchestration, wording | LLM agent                           |

Specifically:

- **The LLM never produces a number that matters.** Balances, cash flow, saving capacity,
  goal feasibility, gaps and projections come from deterministic code. The agent chooses
  which tools to call, with what arguments, in what order, and turns their output into an
  explanation.
- **Calculations are pure and deterministic.** Same inputs, same outputs, unit-tested
  against fixtures. No LLM call inside a calculation.
- **Product claims are retrieved, not recalled.** Statements about rates, liquidity or
  conditions come from retrieved documents with `source`, `url`, `retrieved_at` and
  `valid_from` metadata, and are cited. Model recall of a product's terms is not an
  acceptable source.
- **Suitability stays rule-based.** Constraints on what may be recommended are code, not
  prompt instructions. A prompt is not an enforcement mechanism.

## Consequences

- Every number in an answer traces to a tool call, and every product claim to a document.
  That is what makes the output auditable and the system testable.
- The financial engine can be tested exhaustively with no LLM in the loop; the agent can
  be tested with mocked LLM calls and no network.
- A model upgrade or provider switch cannot change the arithmetic.
- Cost: more moving parts than letting the model reason over raw data, and each capability
  needs an explicit tool. This is the point - an opaque pipeline would be smaller and
  untrustworthy.
- Cost: the agent can still misframe correct numbers or call the wrong tool. Mitigation is
  evaluation of agent behaviour and tracing (Langfuse, later phase), not loosening the
  boundary.

## Alternatives considered

- **Let the LLM compute from retrieved rows.** Far less code, and unacceptable: wrong,
  irreproducible numbers presented with confidence.
- **Code interpreter / generated-code execution.** Flexible, but then the calculation is
  generated per request, so it cannot be reviewed or regression-tested, and it adds a
  sandboxing problem.
- **Fully rule-based system, no LLM.** Trustworthy and rigid. The explanation and
  conversational framing are much of the product's value, and that is what LLMs are
  genuinely good at.
