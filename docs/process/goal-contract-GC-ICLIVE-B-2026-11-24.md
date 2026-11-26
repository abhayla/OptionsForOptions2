# Contract GC-ICLIVE-B: the 16 money-number issues

**Executor:** /goal (cloud session)   ·   **Created:** 2026-11-24   ·   **Part 2 of 5**
**Common rules (binding, read first):** `docs/process/goal-contract-GC-ICLIVE-common-2026-11-24.md`

**Mission.** Sixteen issues where a money number is wrong or sits on a different basis on different screens:
D-06, D-07, D-08, D-09, D-10, D-11, D-12, D-13, D-14, D-15, D-16, D-17, D-18, D-19, D-20, D-63. The arithmetic under the
app matched hand checks on 23 Nov; the faults are in which number a screen reads and how it is labelled. Done = each
is fixed at the place the number is produced, or parked or marked as the method says, with a test built from the real
case in the issue list.

## Start of the part
Read `gh pr checks` for the push of Part A once; a red check is fixed first (common rules, section 5). Run the
preflight (0.2). Merge `origin/main` only if it has new commits (0.1).

## Scope
- **In scope:** `backend/ofo/engine/`, `backend/ofo/charges/`, `backend/ofo/tracking/`, the paper and strategy routes
  that serve these numbers, the builder, positions and cards components that print them. **Goal type:** bug-fix loop.
- **Rule for the whole part:** ONE engine owns every P&L and payoff number (ADR-008). Where two screens disagree, find
  the two code paths, make both read the one engine function, and label the basis. Never fix a number in a component.
- Changes to engine or scenario maths follow the checklist in the `options-math-review` skill of this repository.

## Decisions already taken (binding)
- **D-12** (ADR-320 point 1): on expiry day the theta figure is replaced by "Decay left today: Rs X", the time value
  still in the position until the close. Other days unchanged. Units are labelled.
- **D-14** (ADR-320 point 2): on expiry day only, max profit and profit left are shown twice, labelled "If held to
  expiry" (no exit charges) and "If exited now" (paid plus the estimated cost to close; ADR-263, ADR-306). Real case:
  strategy 157 read +290.49 all day and settled at +387.01. The "Charges" line states which charges it shows.
- **D-13**: ADR-306 already decides it: profit left and loss left are after all charges. Make every place that says
  "before charges" or serves a gross `profit_left` agree with it, and correct the wording of REQ-109 AC-9 where it
  still quotes the superseded ADR-301 text. The handover notes D-13 was never confirmed on a screen: reproduce first.
- **D-08**: on expiry day the estimated-now figures and the what-if use the real time left to the close, not a day; at
  zero time left the value is intrinsic. If the spec has a rule for the last minutes, cite it; else decide by the
  nearest decision and record it (common rules, section 4).
- **D-15**: the plan's prices and the paper fill prices are different facts: the builder summary of a paper trade
  shows the fill prices and says so; the plan stays visible as the plan. No re-quote is hidden.
- **D-16, D-17, D-11**: one basis per number, labelled on every screen that shows it (breakevens: say whether charges
  and booked P&L are in; time value: the same prices as the credit beside it; the "Add Booked" switch changes the
  tiles as well as the chart).

## Order (dependencies first)
1. D-13, D-14 (the charges basis: several later items read it)
2. D-06, D-07, D-11, D-16 (one number, several screens)
3. D-10, D-63 (closed legs and two-expiry trades)
4. D-08, D-12 (expiry day)
5. D-15, D-17, D-18 (prices shown)
6. D-09 (paper fills far from the quote on the dialog: find whether the dialog shows a stale quote or the fill uses
   another price; the fill rule itself is REQ-109 AC-4; a display fix states the age of the quote)
7. D-19 (last price outside its own bid and ask: a feed timing fact; if it cannot be reproduced from recorded
   values, label the last price with its time and mark `Could not reproduce` for the rest)
8. D-20 (seen once: put-call parity gap; common rules, section 3 step 2)

## Definition of Done
- [ ] Each of the 16 issues has, in the ledger, one of: `Fixed, not tested` with its test and result line; `Parked`
      with what is left; `Could not reproduce` with what was tried; `Needs owner decision` with the question written.
      None is left `Open` or `Fix in progress`.
- [ ] Every `Fixed, not tested` issue has a failing-first test built from the real 23 Nov case, a passed independent
      review, and a hand-arithmetic check of the corrected number recorded in the report.
- [ ] For every number that appeared on more than one screen (D-06, D-07, D-11, D-16, D-18), the report names the ONE
      function all those screens now read.
- [ ] Section 6b is green in full; one push; the pull request is still a draft; the report (section 10) is committed.

## Next
`/goal docs/process/goal-contract-GC-ICLIVE-C-2026-11-24.md`
