# Contract GC-ICLIVE-C: the 19 suggestion and alert issues

**Executor:** /goal (cloud session)   ·   **Created:** 2026-11-24   ·   **Part 3 of 5**
**Common rules (binding, read first):** `docs/process/goal-contract-GC-ICLIVE-common-2026-11-24.md`

**Mission.** Nineteen issues where a suggestion or an alert is wrong, missing or late: D-21, D-22, D-23, D-24, D-25,
D-26, D-27, D-28, D-29, D-30, D-31, D-32, D-33, D-34, D-35, D-62, D-69, D-70, D-71. Three are parked features and are
not built (D-34, D-35, D-62). Done = the other sixteen are fixed, parked or marked as the method says.

## Start of the part
Read `gh pr checks` for the push of Part B once; fix a red check first. Preflight (0.2). Merge `origin/main` only if new.

## Scope
- **In scope:** `backend/ofo/adjustment/`, the adjustment routes and readers, alerts and their history, the paper
  monitor's alert text, the tracking panel, the adjustment drawer and Compare screen, the opportunities list.
  **Goal type:** bug-fix loop.

## Decisions already taken (binding)
- **D-21** (ADR-320 point 3): an adjustment approach is never judged, flagged or hidden on max loss or max profit
  alone. Every approach shows a "What changes" block, before against after, no verdict, no word such as better or
  worse: profit range (both breakevens and the width in points), distance from the index to each breakeven,
  probability of profit, max profit, max loss, the credit or debit of the adjustment, margin, net delta, each marked
  up or down; plus one plain reason line where a number moves against the action's name (Reduce on strategy 164:
  "removes credit from the put side, so the call spread becomes the largest loss"). First list which of these the
  Compare table already shows; build only what is missing; every figure comes from the engine. Any "Largest / Lowest"
  leader label stays a fact about one row and is never worded as a recommendation.
- **D-25**: ADR-238 already decides it: Take profit is refused when the whole trade is not in profit and is never
  shown beside a loss; the basis is before charges with the after-charges result beside it (ADR-294). The 23 Nov case
  (strategy 162 offered Take profit at a loss) is a defect against it.
- **D-33** (ADR-320 point 5): a paper trade stays allowed when funds are short; the line reads
  "Not enough funds. Paper trade: this practice order is still allowed; a real order of this size would be refused."
- **D-22, D-71**: a fired stop and an expiry settlement each leave a record a trader can find: time, what happened,
  the index value at that moment, the prices; shown in Alerts History and on the closed trade's own page (settled legs
  say "Paper - settled at expiry", REQ-109 AC-7). No new screen: use the existing history and the closed-trade page.
- **D-23**: stop-out rows in the Orderbook carry their real kind (stop), not "Add".
- **D-24**: an armed conditional exit is shown on the builder's tracking panel with its level and state.
- **D-32**: the drawer's "Watch an index level" says in its own label that it only alerts and does not exit.
- **D-28**: one state word per strategy across every route (Draft / Running / Completed; owner decision of 13 Nov).
- **Parked, not built:** D-34, D-35, D-62: ledger rows `Feature request (parked)`.
- **Seen once:** D-69, D-70: common rules, section 3 step 2.

## Order
1. D-25, D-23, D-28 (small, spec-settled)
2. D-22, D-71, D-27 (records and history)
3. D-24, D-32, D-26 (what the panel shows; D-26: an idea that lapsed says so and when, and a live idea keeps its
   Review button)
4. D-29, D-30, D-31 (alert list times, counts on one unit, one labelled trigger value)
5. D-21 (the "What changes" block: the largest item; do it after the Part B numbers it reads)
6. D-33
7. D-69, D-70

## Definition of Done
- [ ] Each of the 16 non-parked issues has, in the ledger, one of: `Fixed, not tested`, `Parked`, `Could not
      reproduce`, `Needs owner decision`; none is left `Open` or `Fix in progress`. D-34, D-35, D-62 read
      `Feature request (parked)`.
- [ ] Every `Fixed, not tested` issue has a failing-first test from its real 23 Nov case and a passed independent review.
- [ ] D-21: the "What changes" block shows all eight measures for every approach the engine can produce (the report
      lists each approach id and confirms the eight lines), with no verdict word anywhere in its texts (a test greps
      the rendered texts for "better", "worse", "recommended", "should").
- [ ] Every new user-facing sentence is pinned and marked `pending owner read`, and listed in the report.
- [ ] Section 6b is green in full; one push; the pull request is still a draft; the report (section 10) is committed.

## Next
`/goal docs/process/goal-contract-GC-ICLIVE-D-2026-11-24.md`
