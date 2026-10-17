# Owner questions parked by GC-2a (2026-10-16 night run, owner away)

Run discipline B2: the run did not stop for these; each has a recommendation. Answer with the question tool in the
next owner-present session; the answer becomes a decision row the same turn.

## OQ-10: the breakeven columns show about -Rs 215 under a "breakeven" label (issue 269 D5, remainder)

- **What happens now (real case):** the 1-lot NIFTY iron condor of 2026-10-15 (SELL 23150 CE 53.30, BUY 23350 CE
  17.30, SELL 22750 PE 65.15, BUY 22550 PE 34.00). Since W-075 the expiry values include the round trip of Rs 214.96
  (ADR-082 (2)), but the breakeven levels are still the zero points of the payoff BEFORE charges (the ADR-008
  formulas are locked). So the two columns labelled as breakevens show a TOTAL of about -Rs 215, not 0.
- **Spec basis:** REQ-034 AC-5 ("the exact live level and the 0-P&L (breakeven) levels are inserted as extra
  columns"); ADR-082 decision (2) (expiry scenario values include the round-trip charges); ADR-072 (the loss regions
  are computed from the payoff, "consistent with ADR-071's 'before charges and taxes'"); ADR-008 (formulas locked).
  The spec does not say whether a breakeven is before or after charges once ADR-082 put charges into the values.
  OQ-4 (a) (2026-10-16) settled the max-loss sentence only; the breakeven columns were named in its context, not in
  its options.
- **Options:**
  - **(a) Recommended: move the breakeven columns to the true 0-P&L level after charges** (for this condor each
    breakeven moves inward by 214.96 / 65 = 3.31 points: credit 67.15, so 22,682.85 becomes about 22,686.16 and
    23,217.15 becomes about 23,213.84 (computed 2026-10-16 from the leg prices above). Why: AC-5 says the column is the 0-P&L level, and the table's P&L now includes charges; a "breakeven"
    that shows a loss is the kind of contradiction a beginner reads as a bug. Cost: the engine's formulas stay
    locked; the shift is a separate, labelled step on top (one function, exact Decimal), plus the "Where do I start
    losing?" sentence must use the same levels (ADR-072) - about one Tier A item.
  - (b) Keep the levels and relabel the columns "Breakeven (before charges)". Cheap (a label), but the table keeps
    showing a loss at a column called breakeven.
  - (c) Leave as is. Not recommended: the screen contradicts itself.
- **Business call:** it changes what every user sees on the outcome screen (the breakeven levels and labels).

## OQ-11 (W-104): the Execute screen's labels and layout

- **Built (recommended):** on a saved strategy, "Execute Strategy" opens `/strategy/<id>/execute`. The screen waits
  for live prices for every leg, then offers "Prepare entry orders" and "Prepare exit orders" (the Execute API gives
  no held flag, so both are offered and the route refuses the wrong one with its catalogue message). The reply is shown
  as an orders table (Side, Quantity, Contract, Order type, Price, Tag) and a cost list: "Net premium (minus = paid)",
  "Charges" (or the server's note), "Funds available (Zerodha)", "Margin required (Zerodha)", "Figures read at". The
  platform's own planning margin is NOT shown here (only Zerodha's figure). The Kite button reads "Open Kite to place
  these orders" and disappears after one click (a second post would duplicate the basket).
- **Spec basis:** REQ-056 AC-1 ("one 'Execute Strategy' action"); REQ-073 AC-1; ADR-097 ("the owner gives a final
  yes on the exact contract, side, quantity, limit price and cost"); REQ-055 AC-3 (a platform estimate is labelled
  "planning estimate"). The spec does not fix the button words or the table columns.
- **Business call:** wording and layout users see on the order path.

## OQ-12 (W-104): "Check with Zerodha" shows plan state and contract units, not a row per order

- **What happens now:** the return route's reply (`ReturnOut`) carries each plan's state, a per-contract comparison
  (Zerodha units vs platform units, mismatch code), the mismatch count and orders tagged outside any stored plan. It
  has no list of the strategy's own orders with Zerodha's status, so the screen shows plan 1 "filled", the contracts
  table and "Mismatches: 0" - not "order X: COMPLETE".
- **Recommended:** add a per-order list (tag, order id, Zerodha status, filled quantity) to the return reply in a
  backend item, then show it on this screen. Cost: one Tier A backend item plus a screen change.
- **Spec basis:** REQ-073 AC-3 ("reads the actual order states and positions from Zerodha and reconciles them").
- **Business call:** what the owner sees after placing real orders.

## OQ-13 (W-104): a strategy saved without a planned entry cannot reach "live" on the Execute screen

- **Built (recommended, fail closed):** the live socket follows a strategy only with each leg's planned entry; a
  pre-ADR-075 draft has none, so the screen shows the catalogue not-live message (`gate_data_unhealthy`) and never
  calls Execute. Recommended: keep this, and later point the user to reprice the draft in the builder first.
- **Spec basis:** ADR-075 (planned entry captured with the leg); REQ-056 AC-1. The spec says nothing on executing a
  draft with no planned entry (searched: planned_entry, reprice, Execute).
- **Business call:** whether such drafts may be executed at all.
