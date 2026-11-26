# Contract GC-ICLIVE-E: the 25 label, wording and layout issues, and the small features

**Executor:** /goal (cloud session)   ·   **Created:** 2026-11-24   ·   **Part 5 of 5 (last)**
**Common rules (binding, read first):** `docs/process/goal-contract-GC-ICLIVE-common-2026-11-24.md`

**Mission.** Twenty-five issues: D-39, D-41, D-42, D-43, D-44, D-45, D-46, D-47, D-48, D-49, D-50, D-51, D-52, D-53,
D-54, D-55, D-56, D-57, D-58, D-61, D-64, D-65, D-66, D-67, D-68. Two are parked features (D-48, D-51). The owner
chose seven small features to build in this chain; six fall here (D-41, D-54, D-55, D-56, D-61, D-68; the seventh,
D-33, was in Part C). Done = the 23 non-parked issues are fixed, parked or marked as the method says, and the chain is
closed with one final report across all five parts.

## Start of the part
Read `gh pr checks` for the push of Part D once; fix a red check first. Preflight (0.2). Merge `origin/main` only if new.

## Scope
- **In scope:** the builder, positions, strategies, alerts, option chain, home and playbook screens and the server
  texts they print. **Goal type:** bug-fix loop with six small additions.
- **Screens are judged as a desktop web page** (owner rule): no phone-width work.
- **Every text a trader reads** comes from the repository's template mechanism (`backend/ofo/errors/templates.py`,
  pins in `tests/errors/template_pins.json`) or the existing wording modules; new sentences are pinned
  `pending owner read`. No broker name in feature code (a gate checks it).

## Decisions already taken (binding; ADR-320 points 5 and 6)
- **D-61:** after "Buy back the untested short" leaves a long option with no short against it, one line says so:
  "This trade now has a long <call or put> with no short against it; its result now depends on direction."
- **D-54:** deleting a playbook asks "Delete this playbook?" first; the "Test this playbook" button that does nothing
  is removed (testing on past expiries is outside V1, REQ-160), with one line saying so where the button was.
- **D-68:** the Positions header gets a "Today" total for trades opened or closed today that leaves out scenario
  strategies; "today" is the current trading day in IST; each figure follows the paused rule of REQ-109 AC-5.
- **D-41:** the Live and My Strategies cards show each trade's P&L from the same function the Positions page reads
  (a dash with "prices not live" when paused) and never stay on "Loading": after the read fails the card says so.
  "Health" is NOT built (it has no definition).
- **D-56:** Home shows the count of running strategies, the unread alert count and total P&L (same paused rule),
  each read from the function the owning page already uses.
- **D-55:** the chain's Min OI, volume and premium filters apply as typed; the Change and OI Change columns are filled
  where the feed carries the values, else the column says "not available" (REQ-083). Min OI keeps a row only if the
  side shown passes.
- **Parked, not built:** D-48, D-51: ledger rows `Feature request (parked)`.
- **D-57:** dates read "23 Nov 2026" and 24-hour IST times everywhere; one formatter.
- **D-64:** after the 15:30 close the page says "Market closed. Open legs that expire today settle at 15:45." in
  place of raw errors; no raw instrument id reaches the screen; a leg that has a price shows it (ADR-311).
- **D-66:** the Completed page shows the time the trade closed, labelled, not the last builder save.
- **D-67:** an adjustment toast never covers a page button and is not raised in the first minutes after entry for a
  rule already true at entry; the rule itself is unchanged (the plan decides it); if "first minutes" has no decided
  number in the spec, do not invent one: keep the rule firing and fix only the overlap, and write the question to
  the owner-questions file.
- **D-50** (seen once): common rules, section 3 step 2.

## Order
1. The six small features: D-54, D-61, D-68, D-41, D-56, D-55
2. Wording and labels: D-57, D-58, D-44, D-49, D-52, D-53, D-43, D-46
3. State and lists: D-42, D-65, D-66
4. Messages after the close and status contradictions: D-64, D-39
5. Layout and toasts: D-45, D-47, D-67
6. D-50

## Close of the chain (after this part's own gates)
1. Run section 6b once more on the final head.
2. Write `docs/process/GC-ICLIVE-final-report-2026-11-24.md`: one table of all 71 issues (id, plain title, status,
   what changed in one line, screen check owed), the counts per status, every decision pending the owner's read,
   every owner question, every parked item with its next step, and the screen-check list for the owner's PC ordered
   by what needs live prices, what needs a paper adjustment and what needs neither.
3. Update the pull request description (still a draft) to that table. One push.

## Definition of Done
- [ ] Each of the 23 non-parked issues has, in the ledger, one of: `Fixed, not tested`, `Parked`, `Could not
      reproduce`, `Needs owner decision`; none is left `Open` or `Fix in progress`. D-48, D-51 read
      `Feature request (parked)`.
- [ ] Each of the six small features is built to its sentence above, with a test for every state it can show
      (value, paused, read failed, nothing to show).
- [ ] Every `Fixed, not tested` issue has a failing-first test and a passed independent review.
- [ ] The ledger has 71 rows, zero rows `Open` or `Fix in progress`, and the final report's counts add up to 71.
- [ ] Every new user-facing sentence of the whole chain is listed in the final report with its pin status.
- [ ] Section 6b is green in full on the final head; one push; the pull request is still a draft and not merged.
- [ ] The final report is committed and its `DONE / PENDING / BLOCKED / PARKED / NEXT` summary names the next action:
      the screen checks on the owner's PC.
