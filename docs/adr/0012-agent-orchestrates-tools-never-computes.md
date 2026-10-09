# ADR-0012: The agent orchestrates tools behind a provider interface it owns

- **Status:** Accepted
- **Date:** 2026-10-09

## Context

ADR-0005 decided that the LLM orchestrates and explains while the engine calculates.
Phase 6 is where that stops being a principle and becomes code, which forces four
questions it did not have to answer in the abstract:

1. What does Compass depend on - a vendor SDK, or something it owns?
2. How does a model that is good at being persuaded get stopped from reading another
   user's data?
3. What happens when a model loops, says nothing, or asks for a tool that fails?
4. What is kept afterwards, so an answer can be checked?

The data in play makes these sharper than usual. A transaction description is attacker-
controlled text that the model will read, so "the prompt tells it not to" is not a
security boundary.

## Decision

**`agent/llm/base.py` is the interface Compass depends on**: send a conversation, offer
tools, get back text or tool calls, know what it cost. Four concepts, no streaming
helpers, no assistants API, no embeddings. `agent/llm/openai.py` is the only file that
knows OpenAI exists; `agent/llm/scripted.py` replays a script for tests. The provider is
chosen in one dependency function, and a missing key answers `503` on the conversational
endpoints while the rest of the API keeps working.

**The agent calls the MCP server, not its own copy of the tools.** What the model can do
is exactly what any MCP client could do, with the same schemas.

**Isolation is structural, not prompted.** `user_id` is stripped from every schema the
model sees and injected server-side on every call. A model cannot pass an argument it was
never offered, so neither a crafted question nor text planted in a transaction
description can redirect a tool at someone else's data. A test asserts that a tool call
carrying another user's id still reads the caller's.

**Every failure mode ends in a sentence to the user.** A tool that fails returns its
error as text the model can react to rather than raising through the turn. The tool loop
is bounded, and when the budget runs out the model is asked once more *with no tools
offered*, which forces words instead of silence or an endless chain. A model that replies
with nothing still produces an answer.

**The answer records what produced it.** An assistant message stores the tool calls made
and the model that made it. ADR-0005 promises every number traces back to a tool call;
this column is where that promise can be checked after the fact.

**The system prompt is a named constant with its own tests.** It is part of the product's
behaviour: it forbids arithmetic rather than asking for care, forbids inventing a return
rate, and requires saying what is missing instead of filling a gap. The tools enforce; the
prompt must at least not undermine them.

**History is replayed as plain turns; tool results are not.** A figure fetched last week,
replayed as if current, would be worse than fetching it again. The system prompt is
rebuilt each turn rather than stored, so improving it improves every future answer instead
of leaving old threads frozen.

## Consequences

- Switching provider is one adapter and one branch. Running a cheaper model for a cheap
  turn is the same change.
- The whole suite runs with no network and no API key, and tests assert what the agent
  *does* - tools offered, results fed back, budget respected - rather than what a model
  happened to say.
- Token usage is carried from the first version, so adding Langfuse later is wiring, not
  an interface change.
- Cost: the interface will not fit every provider perfectly. Anthropic's and OpenAI's tool
  formats differ in detail, and some of that difference will land in the adapters. That is
  the point of having adapters.
- Cost: re-fetching data every turn costs tool calls that a cached result would not. The
  alternative is stale numbers presented as current, which is not a trade worth making
  here.
- Cost: the bounded loop can cut off a genuinely complex question. Six rounds covers the
  worked example in the product brief with room to spare, and the limit is a constructor
  argument.
- The OpenAI adapter's network call is not covered by tests, by design. Its translation
  functions are, because that is where the bugs live.

## Alternatives considered

- **Depend on LangChain's chat models directly.** Immediate multi-provider support, and
  the application's core would depend on a fast-moving abstraction owned by someone else.
  LangGraph is used for the graph; the model interface stays ours.
- **Let the model pass `user_id`.** Simpler, and it makes data isolation depend on a
  model's judgement under adversarial input. Not a trade to make with financial data.
- **Give the agent the HTTP API instead of MCP tools.** No second transport, and the model
  would infer its options from OpenAPI rather than from definitions written for it - and
  the agent would become an HTTP client of its own process.
- **Store the full message history including tool results and replay it.** Cheaper turns
  and a faithful transcript, at the cost of answering today's question with last week's
  numbers.
- **Stream the answer.** Better perceived latency, and a different endpoint contract. The
  loop underneath would not change, so it can be added when there is a frontend to consume
  it.
