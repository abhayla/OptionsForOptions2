# Owner questions, 2026-10-25 (builder sequence chunk 2, session 06fe7549 - asked while the owner was away)

Each question is parked here per run-discipline B2; nothing waits on it tonight. Answer any time; the answer goes into
the spec as a decision row the same turn.

## Q1 - Does a typed price set the "planned" premium that the price tolerance is measured from? (row 21, REQ-077 AC-8)

Business call: what a user's typed planning price is allowed to do to a real order is a product rule about money, not a
technical choice; two of your approved rules point different ways once tolerance protection is switched on.

Spec basis:
- REQ-077 AC-8: "A typed price is a planning number only: the order's limit price on Execute still comes from market
  depth and the user's tolerance (ADR-080, ADR-095) ... The basket never uses a typed price as its limit."
- ADR-095 decision: "each leg gets the share of it that its planned value (planned premium x quantity) has of the sum of
  all legs' planned values. The leg's rupee share is turned into a per-unit price allowance (share / quantity) and its
  LIMIT is then rounded to the tick toward the user".
- Code today (verified 2026-10-24 by an independent check): the Execute plan takes each limit from the worst market-depth
  level needed to fill (ADR-080 (3)); a typed price cannot move it. `backend/ofo/engine/price_protection.py` (ADR-095,
  NOT yet wired into Execute) sets a protected limit to "planned + allowance" (BUY) / "planned - allowance" (SELL).

The clash (real case): a NIFTY 23000 CE whose market is 79.40; the user typed 81.30 as their planning price. Once
tolerance protection is wired, ADR-095 read literally makes the BUY limit 81.30 + allowance, i.e. the typed price sets
the order limit - which AC-8 forbids. Nothing is affected today (protection is not wired); the question decides how it
is wired.

Options:
1. (Recommended) The tolerance and its allowance are always measured from the MARKET price at Execute time (the depth
   price / LTP captured then), never from a typed or saved planning price. Why: it keeps AC-8 exactly ("planning number
   only") and a stale or wrong typed number can never widen or move a real order; ADR-095's split by planned value can
   use the same market prices.
2. The tolerance is measured from the saved planned price (typed or captured), so a user who typed 81.30 gets a limit
   around 81.30. Changes AC-8 (SPEC CHANGE: "The basket never uses a typed price as its limit" would be rewritten).
3. Measure from the captured price only; a typed price is ignored for protection (falls back to the market).

What happens meanwhile: nothing - row 21 builds AC-8 as written (the limit comes from depth only), and the wiring of
price protection waits for this answer.
