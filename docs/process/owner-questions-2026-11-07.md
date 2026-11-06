# Owner questions, 2026-11-07 (written at night; nothing is blocked by them)

## Q1. Issue 80: one combined order or two when an adjustment trades the same contract twice on the same side?

Business call: it changes which real orders are sent and what they cost.

Case (6-7 Nov test run, PATH-40, paper): an A-01 roll bought 23150 PE twice in one basket, once to close the old short
and once to open the new long. The end position is the same either way.

Spec basis: ADR-007 Q43 / REQ-030 AC-11 ("same contract with opposite actions = two separate legs; no auto-netting")
covers opposite actions in the builder, not two same-side orders in one adjustment basket.

Options:
- **A. One combined order (recommended).** Same contract, same side, same basket: one order for the total quantity
  (e.g. BUY 4 lots of 23150 PE); the history still lists the close and the open as separate lines. Saves Rs 20 brokerage
  per case and a second fill.
- B. Keep two orders, in the spirit of Q43 "no netting". Costs Rs 20 more and a second fill each time.

Until answered: nothing changes (development is on hold).
