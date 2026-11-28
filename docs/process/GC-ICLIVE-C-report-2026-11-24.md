# GC-ICLIVE Part C report: the 19 suggestion and alert issues (25 Nov 2026)

Contract: `docs/process/goal-contract-GC-ICLIVE-C-2026-11-24.md`. Branch `fix/ic-live-test-1123`, draft pull request
abhayla/OptionsForOptions2#722 (still a draft, not merged). Cloud session, owner away. No screen was opened, so the
highest status is **Fixed, not tested**. Ledger: `docs/process/ic-live-test-2026-11-23-status.md`. Decisions:
`spec/decisions/ADR-322.md` (owner, 25 Nov) and `spec/decisions/ADR-323.md` (PENDING OWNER READ). Owner question:
`docs/process/owner-questions-2026-11-24.md` Q2.

## Start of the part

- `origin/main` was already inside the branch, so there was no merge.
- Part B's checks on PR #722 were read once: 7 were success or skipped, `api` was still running, and none was red.
- This was a fresh cloud machine. Local PostgreSQL 16 was set up with migrations at head, and each DB run uses a fresh
  clone (`/root/dbrun.sh`, serialised by a lock).
  - Proof: `test_paper_duplicate_leg_d60.py` 2 passed in 4.22 s.
- Skipped (already done): none. No Part C issue had been started.
- Work ran in four parallel lanes in temporary worktrees. Commits were cherry-picked onto the branch. Conflicts arose
  only in `template_pins.json` and one line of `paperAlerts.js`; both sides were kept.

## Per issue

Every fixed issue got the same treatment:
- a red test from its 23 Nov case, committed alone;
- the fix at the shared reply or component;
- a fresh-context review, with a second round where it found a MAJOR, and a re-check of that round.

**D-21 (Reduce raises max loss, no reason).**
- Wrong: the Compare table showed after-values only. It had no before figures, no distance to the breakevens, and no
  reason when a number moved against the action's name.
- Now: every built approach has a "What changes" block with eight rows, before against after, each marked up, down,
  unchanged or not available. The rows read the Compare's own cells, so the block cannot differ from the table.
- A reason line appears only when max loss rises (rules: ADR-323 (9)).
- Review round 2: a single breakeven is now worded "Profit below X, no lower end" and ranks as unbounded.
- All 15 approach ids show the eight rows or their refusal: A-36, A-01, A-05, A-29, A-28, A-11, A-31, A-24, A-25,
  A-26, A-27, A-35, A-02, A-04, A-06.
  - A-04 (two expiries) says "Not available" with the engine's reason on five rows.
  - An exit's delta says "No position left after exit".
- A test greps the texts for better, worse, recommended and should, and finds none.
- Hand check ADJ-02 Reduce (A-29):
  - max loss before: 26,000 - 5,726.50 + 107.06 = 20,380.56
  - max profit after: 2,177.50 - 154.27 = 2,023.23
  - credit: (29.50 - 84.10) x 65 = -3,549.00
  - The Opus review also hand-checked A-31 and A-01.
- Strategy 164's legs are in no fixture, so the real case was not run on its own legs.
- Test: `tests_app/test_d21_what_changes.py` (see the 6b table) and `frontend/tests/adjust-what-changes.test.js`.
- Status: Fixed, not tested (three review rounds; the third allowed by the owner direction for a narrow fix fully specified by the review; final re-check PASS). Left over (MINOR, rare): a single breakeven that only touches zero keeps a finite width rank.

**D-22 and D-71 (no record of a fired stop or a settlement).**
- A fired stop stores the live index value at that moment in its reason, or says it was not available.
- A settlement stores "Paper - settled at expiry: NIFTY closed at 25,641.35".
- Alerts > History lists both, with time and prices.
- The closed trade's own rows show each reason without a click. "No legs yet" above them is unchanged.
- No migration was needed.
- Tests: `test_paper_monitor.py` 22 passed; `test_paper_settlement.py` 29 passed; `test_paper_triggers_routes.py`
  64 passed.
- Status: Fixed, not tested.

**D-23.** The Orderbook kind for a stop-out now reads Stop, and for a settlement Settled.
- Test: vitest `orderbook-kind-d23` 2 passed (red: 2 failed).
- Status: Fixed, not tested.

**D-24.** The tracking panel lists armed and fired index conditional exits, with level and state, from the server.
- The line turns "Fired" on the tick the strategy exits. This was review round 2: the panel had stopped reading the
  exits once the strategy was exited.
- Test: vitest `tracking-armed-exit-d24` 6 passed.
- Status: Fixed, not tested.

**D-25 (Take profit at a loss): Needs owner decision.**
- The built change is kept. The offer now names the result before charges (the profit test) and after charges.
- The independent Opus review found no path that offers or accepts Take profit at a loss before charges.
- It also confirmed a clash between two owner texts:
  - ADR-238 (6): "never shown Take profit beside a loss".
  - ADR-294 (4) and the contract: the test is before charges, with the after-charges result shown beside it.
- Strategy 162 at -223 after charges is offered under ADR-294 (4) and forbidden under ADR-238 (6).
- Question Q2 recommends refusing on an after-charges loss too.
- Test: `test_take_profit_basis_d25.py` 5 passed.

**D-26.**
- A lapsed idea says when it lapsed. The time comes from the close's own timeline entry, not a later append; that
  was review round 2.
- A live idea keeps Review while an open record exists.
- Tests: `test_opportunity_lapse_time_d26.py` 5 passed; vitest `rules-line-d26` 3 passed.
- Status: Fixed, not tested.

**D-27: Parked.**
- No cause was found. The engine and the route give rows for two-adjustment shapes, and the review agrees.
- Built anyway: the section says it is reading, re-reads on every opening, and says when no step is recorded.
- Next step: on the PC, read `GET /api/strategies/155/adjustment-history`.

**D-28.**
- One server function gives Draft, Running or Completed on every strategy and paper reply. Running means at least one
  open leg.
- Every screen shows the server's word. Review round 2 removed the browser's own derivation, and an exited book now
  reads Completed.
- Deferred: a real basket that never filled still reads Running (`_HAS_ORDER_SQL`). Real-order code is frozen
  (ADR-281).
- Tests: `test_strategy_tracking.py` 17 passed; vitest 36 passed.
- Status: Fixed, not tested.

**D-29.**
- The alert list, the unread count, mark-read and the adjustment inbox now read this process's own strategies only.
  The inbox was review round 2.
- Old scenario PATH alerts no longer fill the bell.
- Open records on Active show a time.
- Tests: `test_paper_triggers_routes.py` 64 passed; `test_playbook_store.py` 50 passed.
- Status: Fixed, not tested.

**D-30.**
- The counters now say they count conditions, with the conditions and the rows side by side.
- Records on expired contracts lapse as "The contracts have expired", with the time. The expiry day stays live.
- One failed lapse is contained and retried (round 2).
- C10 (still Open after its exit): the retry of a failed lapse write is proven, but the 23 Nov cause is unknown. The
  worker log of 14:31 to 14:33 would settle it.
- Tests: `test_expired_record_lapse_d30.py` 5 passed; `test_background_worker.py` 24 passed;
  `test_background_cycle.py` 78 passed.
- Status: Fixed, not tested.

**D-31.**
- While a record is open, the panel and the drawer show the record's fired value, with the poll value labelled "Now"
  and its time.
- Drawer lines name their rule.
- The minor round removed a duplicate wording line and broke an old test (`adjustment-opportunities.test.js`, 3 lines
  against 4). That was caught on the merged branch and fixed with the old test unchanged.
- Test: `test_trigger_value_one_source_d31.py` 2 passed.
- Status: Fixed, not tested.

**D-32.** The heading reads "Watch an index level: it only alerts and does not exit". This is the only copy of the
label, on the Compare page. Status: Fixed, not tested.

**D-33.** The short-funds line reads the ADR-320 (5) sentence. The paper order stays allowed: the server has no funds
check on paper. Status: Fixed, not tested.

**D-69 and D-70: Could not reproduce.** Each had one attempt from the code, with real QuoteBook reads.
- D-69: a silent index token keeps its last value and its own time, because feed health is judged on the whole feed
  (F-32).
- D-70: frames the vendor sends after the close are applied.
- There is no feed log for 23 Nov, and nothing was built.
- Possible owner questions: a per-quote age limit for the index; freezing option prices at 15:30.

**D-34, D-35, D-62.** Feature request (parked), as the owner decided on 24 Nov.

## Owner decisions of 25 Nov (ADR-322, relayed by the orchestrating session)

Verified in that session's transcript: question-tool answers 1 to 5.
1. D-04 and D-60: the extra rounds stand. The ledger notes it.
2. D-17: time value at live prices, labelled "at live prices, as of HH:MM:SS".
   - Built in review round 2: the label takes the oldest of the spot and leg times, and a closed market reads "at the
     last close prices".
   - Tests: `test_outcome_time_value_basis_d17.py` 6 passed; vitest 2 passed.
   - Q1 is marked answered.
   - Status: Fixed, not tested.
3. REQ-109 AC-5 is per leg. The text is changed with a SPEC CHANGE note. The code was already per leg.
4. ADR-321: the 9 points are owner-approved, and 16 Part B pins are cleared.
5. Spot-clock gate: the plan route's entry and its unused `judge_spot` read were removed in one commit.
   `test_spot_clock_scan.py` 19 passed.

## New user-facing sentences (pending owner read)

Backend sentences are pinned in `tests/errors/template_pins.json`. Front-end sentences are pinned by their tests and
a code comment, the convention of Parts A and B.

- D-25:
  - "Whole trade closed at the planned prices: {before} before charges (the figure the profit test used), {after}
    after charges."
  - The variant for when the charges could not be priced.
- D-30:
  - "Counters count conditions, not rows. Conditions: {conditions}. Rows: {rows}. One row can hold several
    conditions."
  - "The contracts have expired".
- D-22 and D-71:
  - "{what}; {underlying} was at {level} at that moment"
  - "{what}; the index value at that moment was not available"
  - "Paper - settled at expiry: {underlying} closed at {level}"
  - "{what}; settled {prices}. A paper settlement only: no order was sent to Zerodha."
  - "No stops or expiry settlements yet."
- D-24:
  - "Conditional exit: all legs exit if the index goes above/below {level}. Armed." (or "Fired.")
  - "Could not read the conditional exits. Nothing was changed."
- D-32: "Watch an index level: it only alerts and does not exit".
- D-33: "Not enough funds. Paper trade: this practice order is still allowed; a real order of this size would be
  refused." (the owner's words)
- D-17:
  - "at live prices, time not given"
  - "at the last close prices, as of {time}"
  - "at the last close prices"
  - "at live prices, as of {time}" is owner read (ADR-322).
- D-21:
  - 29 `adjust_wc_*` texts (title, row labels, direction words, cell and reason lines).
  - "Profit below {level}, no lower end" and "Profit above {level}, no upper end".
- D-27:
  - "Reading the adjustment history..."
  - "No entry or adjustment is recorded for this strategy yet."

## Gates of 6b

| Gate | Command | Result line |
|---|---|---|
| Generated files | reply_inventory, OpenAPI (+ outcome.openapi.json), spec digest, coverage map | commits 9feaf299, 2a02d512 (reply inventory +57 lines, none removed); reviewer notes 6a9ff821 |
| Reply inventory | `python scripts/reply_inventory.py --check` | rc=0 (on 8155b7f9) |
| OpenAPI drift | `tests_app/test_openapi_drift.py`; `generate_openapi.py` vs committed | 1 passed; identical |
| Coverage map | `coverage.py . --check` | OK: every discovered id has a valid stage (on 8155b7f9) |
| Front end, whole | `npx vitest run` | Test Files 202 passed (202); Tests 2472 passed (2472) (on 2a02d512; no front-end change after) |
| DB files touched, one pass | `/root/dbrun.sh <16 files>` | 130 failed, 418 passed: every failure "Catalogue update refused: would drop 750 of 750 live NIFTY contracts (ADR-058)" (cross-file interference, known before this part); each failing file alone: paper_monitor 22, paper_settlement 29, paper_triggers_routes 64, playbook_store 50, strategy_tracking 17 passed |
| DB files touched, one at a time | `/root/dbrun.sh <file>` x16 | all green (response door 214 passed after 7787b7ac) |
| ci_local | `python tools/ci_local.py` (DB clone) | TOTAL: 16 passed, 0 failed, 5 skipped (on 8155b7f9) |
| prepush | `python scripts/orchestrator/prepush.py` | run 2 found 10 stale app tests (fixed in 3bc4e0a6, 8155b7f9, f7e135fd, c0a196b0, 5744a66f; review PASS); final result on the report commit: in the progress log and the PR #722 comment |

Why the 10 stale tests were missed: each lane ran only the test files it touched, never the full app suite; prepush runs the full suite and found them. Sibling class checked: repo_scan 483 passed after the fixes.

## Not tested and screen checks owed

Every row of the ledger names its screen check. None of the work was opened in a browser. Each check waits for the
owner's PC in market hours.

## DONE / PENDING / BLOCKED / PARKED / NEXT

- **DONE:** D-21, D-22, D-23, D-24, D-26, D-28, D-29, D-30, D-31, D-32, D-33, D-71 Fixed, not tested; D-17 Fixed,
  not tested (owner decision ADR-322); ADR-322 points 1-5 recorded and built.
- **PENDING (owner):** D-25 Needs owner decision (Q2); ADR-323 points 1-9 pending owner read; every new sentence above.
- **BLOCKED:** none.
- **PARKED:** D-27 (next: read the route reply for strategy 155 on the PC). Could not reproduce: D-69, D-70.
  Feature request (parked): D-34, D-35, D-62. Deferred: a real basket never filled reads Running (D-28,
  `_HAS_ORDER_SQL`, real orders frozen); D-21 single touching breakeven rank; D-17 route-level older-spot test.
- **NEXT:** the orchestrating session starts Part D: `docs/process/goal-contract-GC-ICLIVE-D-2026-11-24.md`. Part D
  reads the checks of this push once at its start.
