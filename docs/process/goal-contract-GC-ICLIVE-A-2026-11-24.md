# Contract GC-ICLIVE-A: finish the seven critical issues properly

**Executor:** /goal (cloud session)   ·   **Created:** 2026-11-24   ·   **Part 1 of 5**
**Common rules (binding, read first):** `docs/process/goal-contract-GC-ICLIVE-common-2026-11-24.md`

**Mission.** The seven critical issues of the 23 Nov live test (D-01, D-02, D-03, D-04, D-05, D-59, D-60) are built on
branch `fix/ic-live-test-1123` and pass their own tests, but four pieces were never independently reviewed, one issue
is partial, one front-end test fails in the full run, and several small review findings were left. This part closes
all of that, so that each of the seven carries only what a screen check would add. Done = every box below ticked,
one push, the ledger and tracker rows exact.

## Scope
- **In scope:** the code and tests of those seven issues; the status ledger; the files section 5 of the common rules
  names as generated. **Goal type:** bug-fix loop.
- **Out of scope:** any other issue; any new screen; real-order code paths (frozen) except reading them.

## Stages (in this order)

### A1. Prove the database route
Common rules, section 2. **Acceptance:** the two test result lines and a passing `prepush.py` on the unchanged head
are in the progress log. On failure: HALT as section 2 step 5 says.

### A2. Create the status ledger
Create `docs/process/ic-live-test-2026-11-23-status.md` with one row for each of D-01 to D-71 (common rules,
section 7), filled from `session-handover-2026-11-24.md` and the issue list: the seven as `Fixed, not tested` with
their owed screen check (D-60 as `Fix in progress`: the strike stepper is open), D-34, D-35, D-48, D-51, D-62 as
`Feature request (parked)`, every other row `Open`. **Acceptance:** 71 rows, committed.

### A3. The failing front-end test
`frontend/tests/option-chain.test.js`, "row 33: a strike range change sends one new request with that strike count
(server cap 15)": failed once in the whole-suite run (expected `strikes_each_side` 5, got 15), passes alone.
Run the whole suite on the branch and on `origin/main`. If it fails on main too, or only under load, it is a test
that depends on order or timing: fix the test's isolation (shared state, timers, a mock leaking between files), never
its expectation. If the branch causes it, fix the cause. **Acceptance:** `npx vitest run` whole suite green three
times in a row, the cause written in the progress log in one sentence.

### A4. Independent review of the four unreviewed pieces, and their fixes
One fresh-context reviewer per piece, read-only, diff only, findings only, with the class and required behaviour taken
from the named decision:
1. D-05 last fix, commit `ef733f08` (an Exit confirm box left open through an unreadable refresh): class = every path
   to a paper exit from the paper list while prices are paused (REQ-109 AC-5).
2. D-04 server change `2915daf6` and fallback `6972d3d7`: class = every paper basket at or over the plan maximum
   (ADR-318 points 1 to 5); and rules from the entry shape with the fallback (ADR-318 point 4).
3. D-60 round 2, commits `1a81d59e` and `e1b210d8` and the gate move `aa6ea9fb`: class = every way a leg is added or
   moved in the builder, and Add to Paper with a kept duplicate (ADR-319).
4. The three gate commits `8b3b21d7`, `aa6ea9fb`, `ef1b1093`: behaviour unchanged, the approved "Not saved: the live
   price is already at or beyond this level, ..." line still reads exactly as ADR-317 gives it.
CRITICAL and MAJOR findings are fixed by the method (common rules, section 3). **Acceptance:** four review files under
`docs/process/` appended to `ic-live-test-2026-11-23-reviews.md`, every CRITICAL and MAJOR finding closed or the issue
parked with the finding quoted.

### A5. D-60: the strike stepper asks
A strike step that lands a leg on a contract another leg already holds with the same action must ask "<contract> is
already in this strategy." with "Increase quantity", "Keep separate", "Cancel", through the one shared check
`frontend/src/lib/legDoor.js` `admitLegs` (the reply is applied in `sendEdit`, `StrategyBuilderPage.vue` near line
750; Cancel keeps the legs as they were). Tests: step onto a held contract asks; onto a free contract does not; the
three answers do what the picker's answers do. Also add a component test that the builder prints the refusal sentence
when Add to Paper is refused for a kept duplicate. Option Chain "Add Selected" is NOT changed (it replaces the leg
list; changing that is an owner question already written in the handover). **Acceptance:** tests red then green,
review passed, ledger row D-60 `Fixed, not tested`.

### A6. The small review findings (one commit each, tests first)
1. D-03: when the paper confirm list cannot read the armed exits it shows "Could not check your armed exits." instead
   of nothing (`PaperConfirmDialog.vue` `askArmedExits`); add the missing test that another user's strategy is refused
   by `GET /paper/strategies/{id}/armed-exits`.
2. D-02: the stop-out alert lists the legs in the recorded (buys first) order (`backend/ofo_app/paper_monitor.py`
   near line 231); the docstring of `buys_first` in `paper_store.py` says plainly that a paper ENTRY is recorded as
   sent and may show a sale before its hedge.
3. D-05: the red "Not saved" line clears when the next refresh succeeds; "Enter at least one level" is not shown
   beside a "Saved:" line.
**Acceptance:** each item committed with its test.

### A7. Close the part
Common rules, section 6b, then one push, the pull request comment, the report of section 10.

## Definition of Done
- [ ] The database route is proven (A1) and its result lines are in the progress log.
- [ ] The ledger exists with exactly 71 rows and every row's status is one of the allowed values.
- [ ] The whole front-end suite is green three times in a row and the cause of the earlier failure is stated.
- [ ] All four reviews are written; zero CRITICAL or MAJOR finding is open on an issue marked `Fixed, not tested`.
- [ ] The strike stepper asks on every step onto a held contract with the same action (tests prove each of the three answers).
- [ ] Every one of the three A6 items is committed with its test.
- [ ] Each of D-01, D-02, D-03, D-04, D-05, D-59, D-60 has a ledger row and (if reachable) a tracker row saying what a screen check still owes, and nothing else is open on it.
- [ ] Section 6b is green in full and its result lines are in the report; one push made; the pull request is still a draft.
- [ ] The final report (common rules, section 10) is committed, with the DONE / PENDING / BLOCKED / PARKED / NEXT summary.

## Next
`/goal docs/process/goal-contract-GC-ICLIVE-B-2026-11-24.md`
