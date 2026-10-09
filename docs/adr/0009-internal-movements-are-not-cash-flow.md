# ADR-0009: Internal movements are excluded from income and expenses

- **Status:** Accepted
- **Date:** 2026-10-09

## Context

A statement is not a list of income and expenses. It contains movements that only shuffle
money the user already has, and the sandbox history shows both kinds in the same month:

| Movement                      | Account      | Amount      |
| ----------------------------- | ------------ | ----------- |
| `PAGAMENTO CARTAO NUBANK`     | checking     | -1,684.30   |
| `SUPERMERCADO PAO DE ACUCAR`  | credit card  | -742.18     |
| `POSTO IPIRANGA`              | credit card  | -298.70     |
| ...                           | credit card  | ...         |
| `APLICACAO POUPANCA`          | checking     | -800.00     |
| `DEPOSITO POUPANCA`           | savings      | +800.00     |

Summing every negative amount counts the card's spending twice: once as the purchases,
once again as the bill that settles them. It also counts a transfer to the user's own
savings as if the money had been spent, and the matching credit as if it were income.

On the sandbox data that error is roughly R$ 19,600 over six months - against R$ 24,600
of real expenses. Not a rounding issue: it would make every derived figure, including the
saving capacity the product exists to tell the user, wrong by more than half.

## Decision

Movements carry a category, and two categories mark them as **internal**:
`CREDIT_CARD_PAYMENT` and `INTERNAL_TRANSFER`. Internal movements are excluded from
income, from expenses and from the category breakdown. The spending is counted where it
happened - on the card.

Three supporting rules follow from the same concern for not misleading:

- **The exclusion is reported, not silent.** `CashflowSummary.internal_movements` carries
  the total that was left out, and `movements_excluded` the count. A reader can see that
  money moved and why it is not in the totals.
- **Income is decided by sign, not by a category whitelist.** Any non-internal credit is
  money arriving. A refund or a reversal that no rule recognises would otherwise vanish
  from the totals instead of being counted.
- **The provider's `transfer` label is not trusted.** A Pix to a third party is an
  expense; moving money to one's own savings is not; providers call both `transfer`.
  Compass's own keyword rules decide, and an unrecognised Pix stays an expense
  categorised `OTHER` - which overstates nothing.

Saving capacity then takes the **median of monthly net cash flow over whole calendar
months only**, floored at zero. The median because a bonus month must not become a
monthly promise; whole months because a partial one looks artificially cheap; floored
because a negative median means there is no capacity to save, not a negative amount to
set aside.

## Consequences

- Cash flow, the category breakdown and saving capacity describe what the user actually
  earns and spends.
- The correctness of every figure now depends on the categorisation of a handful of
  decisive descriptions. That is why categorisation is rule-based, deterministic, stored
  with the rule that produced it, and tested case by case - and why an LLM is nowhere
  near it (ADR-0005).
- A card payment that is genuinely money leaving the user's finances - paying someone
  else's card - would be misclassified as internal. Accepted: the opposite default is
  wrong far more often.
- Cost: the totals no longer match a naive sum of the statement, so the API reports the
  excluded total to make the difference explainable.
- Money moved to savings stays inside the capacity figure, because net cash flow has the
  transfer removed from both sides. That is where it belongs: saving is what the figure
  is about.

## Alternatives considered

- **Cash accounts only** (ignore credit-card accounts entirely, treat the bill as the
  expense). Simple, and it loses the category of every card purchase - which is most of
  the user's discretionary spending and the part worth advising on. It also lags: the
  bill arrives a month after the spending.
- **Count everything and warn the user.** Honest about the method and useless as advice.
- **Pair transfers by matching amounts and dates across accounts.** More precise in
  principle - it would catch an internal transfer no keyword recognises - and it invents
  pairings when two unrelated movements happen to match. Worth revisiting when the data
  includes transfers the rules miss.
