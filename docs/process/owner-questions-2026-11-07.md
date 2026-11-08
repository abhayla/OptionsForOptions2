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

## Q2. Approve fix plan v4 (code-verified), and which speed-up?

Plan: D:\Abhay\scratch\ic-uitest\FIX-PLAN-v4-2026-11-07.md - every issue (~65) in 4 parallel lanes, one screen test at
the end, ~42 h builder time, ~16 h elapsed. Implementation = code + unit tests of changed code + test of what changed +
on-screen check; no PRs, no CI. Business call: lifts the development hold and sets the round's scope.

Options:
- **A. Approve v4 with 5 builders (recommended):** lane B split in two; ~12 h elapsed; nothing dropped.
- B. Approve v4, issue 68 (roll to a later expiry as a new strategy) in a later round: ~12 h elapsed with 4 builders.
- C. Approve v4 as is: ~16 h elapsed.
- D. Change it again.

Until answered: nothing is built (development on hold).

Q2 answer (owner 7 Nov ~01:1x): NOT approved. "Save the plan in detail. I will come back to this plan again. We will
revisit and get it reviewed again through reviewers." Saved in docs/process/fix-plan-2026-11-07/.

## Q3 (fix batch 1, night of 7 Nov). Read the new user-facing wording batch 1 adds (pinned "pending owner read")

Business call: these are texts users read on screen (decision-support wording, ADR-003); only the owner approves wording.

Spec basis: ADR-266 (stale leg marked at mid; loss above max loss = "not checked"), ADR-268 (T-01 at/beyond the short),
ADR-271 (paper orders block delete), ADR-272 (stale prices: banner, no leaders, Prepare disabled). Each text was written
to its ADR; none changes a decision.

What: about 10 new templates in `tests/errors/template_pins.json` marked "pending owner read" (builder 2: 7 stale-price
texts; builder 3: STRATEGY_VALIDATION_515 inconsistent prices, STRATEGY_VALIDATION_504 "Can't delete: paper orders were
placed for this strategy."; builder 1: "spot is beyond the sold 23,500 CE by 100 points"). The screen check
screenshots (handover) show them in place.

Recommended: **A. Keep them as written and read them in the screen-check screenshots** (they follow the ADR wording and
the existing tone; a later wording pass can change any of them in minutes). B. Hold batch 1 until you have read them.

Until answered: built with the texts as written (safe default: not shipped anywhere, feature branch only).

Q3 answer (owner 7 Nov ~09:2x IST, question tool): "Approve all (Recommended)". The 9 batch-1 texts are marked "owner read 2026-11-07" in tests/errors/template_pins.json (pin test 63 passed). The builder-1 T-01 "beyond the sold" text is on the parked branch (#664), not approved here.

## Q4 (13:3x). How to close batch 1 with 5 goal-hook items open?
Owner answer (question tool): "Stop now". Batch 1 accepted as it is; repair tool fix, ADR-268 "delta taken as 1" wording, a full impact run on the final tip, and the stale-price / T-01-at-the-short on-screen checks stay open in #664. The owner clears the goal and decides the push.
