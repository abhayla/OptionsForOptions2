# Owner questions, 2026-10-25 (builder sequence chunk 2, session 06fe7549 - asked while the owner was away)

Q1 is from chunk 2 (session 06fe7549); Q2-Q6 are from chunk 3 session A (session a43256ae, 2026-10-25 night, owner
asleep). Each question is parked here per run-discipline B2; nothing waits on it tonight. Answer any time; the answer goes into
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

## Q2 - Strategy name length: 40 characters (our approved rule) or 20 (Sensibull)? (row 29, REQ-134 AC-1, record RD-108)

Business call: the name limit is what every user sees and types when saving a strategy; it is a product rule, and the
approved requirement differs from the reference product we copy by default (ADR-152).

Spec basis:
- REQ-134 AC-1: "Saving a strategy that has never been saved asks for a name, prefilled \"New Strategy\", 1 to 40
  characters after trimming spaces".
- ADR-152: Sensibull is the default where the spec is silent; here the spec is not silent.
- Reference register RD-108 (open, SPEC CHANGE): Sensibull caps the name at 20 characters (study 2026-10-21).

Real case: "NIFTY Oct iron condor wide" is 26 characters - allowed under 40, refused under 20.

Options:
1. (Recommended) Keep 40, close RD-108 as DIFFERENT-BY-DECISION. Why: it is the approved rule, longer names carry the
   expiry and shape a user needs to find a strategy later, and nothing in the product depends on 20.
2. Change to 20 like Sensibull (SPEC CHANGE of REQ-134 AC-1; migration 0025's CHECK and the API refusal change with it).

What happens meanwhile: row 29 builds 40 (the approved text); RD-108 stays open.

## Q3 - Counting process items in chunk 3 (ADR-181 allows two)

Business call: ADR-181's cap is your rule about how much process work a chunk may carry; only you can say how it counts.

Spec basis:
- ADR-181: "for builder sequence chunk 3 the cap is TWO items, and they are named: (1) one local gate command ... (2) one
  dispatch command".

Real case: PR #539 fixed three false failures of the gate on this PC (a pytest plugin installed only here, Windows
`platform` calls refused by the egress guard, and a format check that failed on 93 old unformatted files). Without it no
row could pass the gate here.

Options:
1. (Recommended) Count #539 as part of item 1 (a defect fix of the gate, not a new tool). Why: it adds no new tool or
   check; it makes the approved gate work as approved.
2. Count it as a third item (record a miss on tracker row 7 for chunk 3).

What happens meanwhile: the handover counts it as part of item 1 and says so.

## Q4 - Does a rename appear in the strategy's history, and what does Restore do with it? (rows 28 and 29; REQ-070 AC-2/AC-3, REQ-134 AC-3)

Business call: what the history shows and what Restore brings back is what a user sees and relies on; two approved
texts touch it.

Spec basis:
- REQ-070 AC-2: "A meaningful change is: adding/removing a leg, changing strikes, changing quantities, changing expiry,
  or materially changing risk or payoff; small UI interactions create no history".
- REQ-134 AC-3: "Renaming changes only the name; it adds a history entry (\"Renamed from X to Y\") and never changes legs,
  prices, tracking state or version."
- REQ-070 AC-3: "The user can restore an earlier configuration; the current one is preserved first".

How I read them (and built, pending your answer): they do not contradict. AC-2 says what MUST be saved and what must
not (small UI interactions); a rename is neither - it is a deliberate, confirmed action that REQ-134 AC-3 adds as its own
entry. The rename entry is shown in the history but is not a configuration to restore (it holds the same legs), so the
Restore button is not offered on it.

Real case: "NIFTY Oct condor" renamed to "Condor wider" at 10:40 IST -> history shows "Renamed from NIFTY Oct condor to
Condor wider"; Restore is offered on the leg changes above and below it, not on that line.

Options:
1. (Recommended) As built: rename entries are shown, never restorable; REQ-070 AC-2 gains one line naming them.
2. No rename entry in the history (SPEC CHANGE of REQ-134 AC-3).
3. Rename entries are restorable (restoring brings back the old name too).

## Q5 - After a strategy is executed, can an earlier configuration still be restored? (row 28; REQ-070 AC-3/AC-5, REQ-038 AC-2, ADR-019)

Business call: whether a user can rewrite a strategy whose orders were sent is a product and audit rule.

Spec basis:
- REQ-070 AC-3: "The user can restore an earlier configuration; the current one is preserved first".
- REQ-070 AC-5: "The history remains after execution and is reachable from the Strategy screen, not shown on it by
  default".
- ADR-019 / REQ-038 AC-2 (the store refuses to change an executed strategy's definition; no silent strategy rewrite).

How I read them (and built, pending your answer): after execution the history is reachable (AC-5) but Restore is not
offered; the store's existing refusal stays.

Options:
1. (Recommended) As built: view-only history after execution. Why: an executed strategy's legs must match the orders
   Zerodha holds; restoring would make the screen disagree with the broker.
2. Restore after execution creates a NEW draft copy (Save As) from the old configuration, leaving the executed one as is.

## Q6 - Can a strategy that is being tracked but never sent a basket be deleted? (row 28; REQ-070 AC-6, ADR-118)

Business call: deleting something the user asked to monitor is a product rule.

Spec basis:
- REQ-070 AC-6: "Only a strategy that never sent a basket can be deleted: the user confirms, Undo is offered, the draft is
  hidden from every list and kept on the server with its history for audit".
- The spec says nothing about tracking in the delete rule (searched: REQ-070, ADR-118, REQ-109 tracking).

How I read it (and built, pending your answer): AC-6's only condition is "never sent a basket", so it can be deleted;
deleting also stops its tracking, and Undo brings both back.

Options:
1. (Recommended) As built.
2. A tracked strategy cannot be deleted until tracking is stopped (the Delete button explains why).
