# GC-ICLIVE Part D report: the 4 speed and loading issues (25 Nov 2026)

Contract: `docs/process/goal-contract-GC-ICLIVE-D-2026-11-24.md`.
- Branch `fix/ic-live-test-1123`, draft pull request abhayla/OptionsForOptions2#722 (still a draft, not merged).
- Cloud session, owner away. No screen was opened, so the highest status is **Fixed, not tested**.
- Ledger: `docs/process/ic-live-test-2026-11-23-status.md`.
- Decisions: `spec/decisions/ADR-324.md` (PENDING OWNER READ).
- Owner questions: `docs/process/owner-questions-2026-11-24.md`, Q3 (D-40) and Q4 (D-38).

## The limit of this part

A cloud session cannot time the real app against the real database and the real broker. Every claim below is a
COUNT from a test that runs the real route, with a counting fake at the Kite HTTP transport and a local PostgreSQL 16
database, or a local timing. A claim about the real app under load is marked "not measured", with the check to run on
the owner's PC in market hours.

## Start of the part

- **Part C's checks on PR #722, read once:**
  - `frontend` was RED. Two Playwright runs of `e2e/home.spec.ts:22` expected "SENSEX, Draft" but got "Status not
    available". The test's stand-in strategy rows had no `status_word`, which D-28 (Part C) made the browser read.
    Fixed first in b85bd635.
  - `api` was still running at the start; it later finished green.
  - The other checks were green or skipped.
- **Merge from main:** none. `git log HEAD..origin/main` was empty once the shallow clone was deepened (the first count
  of 102 was a shallow-clone artefact).
- **Database:** local PostgreSQL 16 with migrations at head, and a fresh clone for each DB run (`/root/ofo-db-fresh.sh`).
  - Proof: `test_paper_duplicate_leg_d60.py` 2 passed in 2.85 s.
  - Proof: `test_paper_triggers_routes.py` 64 passed in 60.15 s.
- **Skipped (already done):** none. No Part D issue had been started.
- **Lanes:** D-36 ran in the main checkout. D-40, D-37, D-38 and the round-2 fixes ran in temporary worktrees, and their
  commits were cherry-picked onto the branch without conflicts.

## Per issue

### D-36: the adjustment check and the Review adjustment drawer take 15 to 65 s or fail

**What was wrong (counted):** the drawer's list route
(`POST /api/strategies/{id}/adjustment-approaches`):
- read the broker's available funds again for every approach;
- read each approach's basket margin one after another;
- kept its database connection checked out while it waited on the broker.

The pool has 2 connections and no overflow (`DB_POOL_SIZE=2`, `DB_MAX_OVERFLOW=0`), so a second tester's requests,
`/api/health` among them, queued behind the broker wait. The adjustment check
(`GET /api/strategies/{id}/adjustment-check`) also held its connection across its one margin read.

**Counts** (`tests_app/test_d36_adjustment_counts.py`: real routes, real OutcomeMargin and KiteMargin, counting
transport, local DB, ADJ-02 iron condor, 15 approaches, cold margin cache):

| Route | Funds calls | Basket calls | SQL statements | Connections held in the broker wait | Basket reads at once |
|---|---|---|---|---|---|
| Approaches, before | 7 | 6 | 12 | 1 | 1 |
| Approaches, after | 2 | 6 | 12 | 0 | up to 4 |
| Adjustment check, before | 2 | 1 | 20 | 1 | 1 |
| Adjustment check, after | 2 | 1 | 20 | 0 | 1 |

- One of the two remaining funds calls is the regime reader's own read, a separate reader that was left alone. The
  margin path went from 6 funds reads to 1.
- This fixture has 6 distinct baskets. The 23 Nov live trade had about 15, so the live saving is larger. That is not
  measured.

**What changed:**
- The funds are read once per request (`RequestFunds`). The holder is made per request and, in the background
  worker, per margin read. It is kept for no longer than that unit of work.
- The broker login is opened once per request.
- One time limit covers the funds and the basket of a read, the same limit as before.
- Each route hands its database connection back before every broker wait.
- The basket reads run together, at most 4 at a time, inside the Kite limiter's 10 a second and 5 s rules.
- A failed read stays its own: that approach says it could not be read, with no figure, no retry and no guess
  (ADR-016, ADR-017).
- The drawer has a Retry button. A second click while a read is in flight is ignored, and only the newest reply shows.

**How it is known to work:**
- `test_d36_adjustment_counts.py` 6 passed, including:
  - full reply unchanged: both routes' JSON replies equal the goldens taken before the fix;
  - a failed basket stays its own;
  - a failed funds read leaves every approach not available, with one funds call;
  - one overall time limit;
  - the worker does not reuse a failed read.
- `test_adjustment_approaches_route.py` 108 passed, `test_outcome_margin.py` 62 passed, `test_adjustment_check.py`
  11 passed, `test_background_worker.py` 24 passed, `test_background_cycle.py` 78 passed,
  `test_background_stored_login.py` 20 passed (helper runs, each file alone).
- vitest `adjustment-opportunities` 23 passed.

**The low-risk part (finished paper strategies), counted:**
- `GET /paper/strategies` runs 6 SQL statements whatever the number of strategies, makes no broker call, and spends
  about 0.3 ms of arithmetic per finished book (6 finished books: about 2 ms).
- Skipping that work would save about 2 ms and put the totals at risk, so nothing was skipped. The counting test is
  kept: `test_paper_totals.py::test_d36_the_list_does_fixed_database_work_and_finished_books_cost_only_cheap_arithmetic`.

**Review:**
- Round 1 (Opus) found one CRITICAL: the background worker made the funds holder once at start, so the first funds
  figure, or the first failure, would serve every later check. It also found four MINORs: the time limit had
  doubled, there was no failed-funds test, Retry had no in-flight guard, and the login was opened per read.
- Round 2 fixed all five. The re-check closed all five.
- The re-check then found N1. The worker's 300 s margin refresh is answered from OutcomeMargin's plan cache (ADR-099,
  kept until the plan changes), so the worker can use the morning's funds figure all day.
  - N1 predates Part D and is outside D-36's done list. It is filed as deferred issue #723, with both texts (ADR-099
    and the worker's `MARGIN_REFRESH_S` / `MARGIN_STALE_S` design).
  - The worker docstring that claimed otherwise was corrected (ccd492a4).
- N2 (MINOR, not fixed): the funds read has its own wait inside the shared time limit. So a funds read that takes
  nearly the whole limit fails the first basket in a request while later ones get a full limit.

**Not measured:** the drawer's and the check's real time with one and with two testers, and `/api/health` meanwhile.
Check on the PC in market hours:
1. Open Review adjustment on a live condor.
2. Read the approaches route's log line (`engine_s`, `total_s`).
3. Time `/api/health` while a second tester opens the drawer.

**Status:** Fixed, not tested.

### D-37: the what-if shows nothing for a target level or date (seen once)

**What was wrong (reproduced from the code, one attempt):**
- After a level was picked, a reply with no target figures (prices not live) marked the target block stale.
- The block kept the previous one, which carried no reason.
- So Target and Date showed "-" with nothing beside them.

**What changed:**
- The outcome reply carries `target_not_live_text` ("not shown while prices are not live", pending owner read) only
  when prices are not live: not connected, entry prices, or computed with no live spot.
- The page keeps it only from the latest reply and clears it after a failed request.
- The readouts show it beside the dash.
- A failed request or a refused target never shows it.

**How it is known to work:**
- `test_outcome_target.py` + `test_outcome_target_badge.py` 32 passed (round 1).
- Round 2's touched files: 100 passed and 42 passed. The one OpenAPI failure then was generated-file drift, fixed in
  bf70ece9.
- vitest target files: 106 passed across five files.

**Review:** round 1 found one MAJOR: the sentence showed on any stale block, network failures included. Round 2 fixed
it. The re-check passed, with one LOW: on a computed reply with no spot, the sentence can sit beside dimmed last-good
figures, next to their stale line.

**Screen check owed:** Builder what-if with prices not live: pick a level, then drag the date.

**Status:** Fixed, not tested.

### D-38: other pages load slowly or time out

**What was found (counted):**
- The 10 s is the browser's own limit for every call (`frontend/src/services/api.js:47-49`, 10000 ms). It was not
  raised.
- Counts are from `tests_app/test_d38_page_counts.py` (real routes, counting transport, local DB) and vitest
  `create-strategy-d38`.

| Page | Before | After |
|---|---|---|
| Plan dialog (`GET adjustment-plan`, no plan) | connection held in the market wait: 1; a failed market read asked 2 times | 0; asked once |
| Plan dialog | SQL 12, funds 1, market reads 1 | unchanged |
| Settings (`GET /api/settings`) | SQL 5 (the database clock read twice) | SQL 4 |
| Create Strategy step 4 (3 cards, 7 legs) | planned-entry requests 3 | 1 (all cards' contracts, in chunks of 20 = the route limit) |
| Create Strategy step 4 | outcome requests 3, already sent together | unchanged |

**What changed:**
- Every reply number is unchanged: both routes' full replies equal goldens taken before the fix.
- A read that hits the time limit now says it took too long and keeps what was picked or typed.
- A failed playbook pick, for any reason, keeps the sheet and the typed fields and shows the could-not-load line
  inline.
- Both choices are written as ADR-324 point 4, PENDING OWNER READ, with owner question Q4. The new sentences are in
  `frontend/src/lib/sharedStateText.js`, marked pending owner read.

**How it is known to work:**
- `test_d38_page_counts.py` 5 passed. `test_adjustment_plan` 10, `test_settings_route` 25,
  `test_adjustment_plan_customise` 9 and `test_adjustment_plan_settings` 2 passed (helper, each alone).
- vitest `create-strategy-d38` + `d38-timeouts-pages` 6 passed.
- Two stale tests found by the full runs were updated without weakening:
  - `test_d04_one_door.py`: the type read now takes no reader at all, and a signature check proves it (34317f92).
  - `plan-fields-independent.test.js`: a failed pick shows the could-not-load line inline and keeps the fields
    (2cd353c7).

**Review:** no CRITICAL or MAJOR. Three MINORs are left:
- a naive-datetime guard in the settings IST day (the driver returns an aware time today);
- a failed chunk on step 4 gives a page-level line, not one per card (as before);
- a failed pick has no Retry button; the trader can pick again.

**Not measured:**
- The settings page's 10 s is not explained by local counts: 5 cheap statements and no broker call. The likely cause
  is waiting for one of the 2 pool connections behind requests that held theirs across a broker wait; D-36 and this
  fix release those connections. Not measured.
- Check on the PC in market hours: time the plan dialog on a paper add, Create Strategy step 4, and
  `/settings/app-settings` while a second tester uses the drawer.

**Status:** Fixed, not tested.

### D-40: header totals blank and cards fail because of expired scenario strategies

**What was wrong:**
- Every paper strategy was summed into the header.
- One strategy with an open leg on an expired contract (old "Scenario PATH-nn" trades) made Total, Unbooked and Decay
  blank for all of them, while Booked and Charges still summed everything.
- The two PATH cards' "server error" was not a 500. The route answered 200 with a plain reason. The browser's
  `readPaperBook` failed because the catalogue lists no contract for a past expiry.

**What changed:**
- A strategy with an open leg on an expired contract is left out of every header figure: Total, Booked, Unbooked,
  Decay, Charges and the after-charges figures. Expired means the contract is retired, or its expiry is before today,
  on the IST date.
  - This holds whatever the broker connection (round 2).
  - The header says how many were left out: "1 strategy left out: its contract has expired." / "N strategies left
    out: their contracts have expired.", pending owner read.
  - Total = Booked + Unbooked holds.
- Each strategy reply carries `expired_open`.
- The Live card shows the server's expiry sentence only when `expired_open` is true. A genuinely unreadable book still
  shows its error.
- Old scenario strategies are not deleted.
- Decision: ADR-324 points 1 to 3, PENDING OWNER READ, owner question Q3.

**How it is known to work:**
- `test_paper_totals.py` 19 passed (alone).
  - It includes the hand check: booked 2,236.00 = 731.25 - (-1,504.75).
  - It also covers the not-connected-plus-expired case, one expired leg among live ones, and expired plus stale.
- `test_paper_routes.py` 48 passed, `test_paper_list_figures.py` 14 passed.
- vitest paper and live files passed: 87 in round 1, plus the round-2 files.

**Review:** round 1 found two MAJORs:
- expiry was detected only on a paused book;
- `readPaperBook` hid a real unreadable-book error.

Round 2 fixed both, and the re-check passed. One LOW is left: `_book_day` prefers a stored snapshot's day over the
answer's day, so a stale snapshot can make "today" an older day. The fix would be the later of the two.

**Screen check owed:** the Positions paper page header with PATH-60/61 present, and the Live cards.

**Status:** Fixed, not tested.

## Also found this part

**Local one-pass DB runs show cross-file interference** ("Catalogue update refused: would drop 750 of 750 live NIFTY
contracts", ADR-058).
- This is known from Part C. It is the same on the base commit b85bd635:
  `tests_app -m repo_scan` gives 6 failed in `test_strategy_shape_matrix`, the same 6 on the branch head, and that
  file passes alone.
- CI's `api` job ran green on Part C's push.
- Every touched DB file passes alone.

## Decisions taken pending the owner's read

ADR-324:
- (1) to (3), D-40: header figures over the strategies that can be priced; expired ones left out with a count line;
  the Live card shows the expiry sentence.
- (4), D-38: timeout wording; a failed pick keeps the typed fields.

New sentences pending owner read:
- `target_not_live` (catalogue, D-37);
- the two left-out sentences (catalogue, D-40);
- the D-38 timeout texts in `sharedStateText.js`.

## Owner questions written

- Q3 (D-40): which figures the header adds up when some strategies are on expired contracts.
- Q4 (D-38): the timeout words, and keeping the typed fields on a failed pick.

## Follow-ups filed

#723 (deferred): the worker's margin refresh is answered from the plan cache, so T-16 can use the morning's funds figure.

## Gates of section 6b

| Gate | Command | Result |
|---|---|---|
| Generated files | one commit bf70ece9 (reply inventory, `openapi.json`, `outcome.openapi.json`, digest, coverage stage S6.7 for ADR-324) | committed |
| Reply inventory | `python scripts/reply_inventory.py --check` | exit 0 |
| OpenAPI drift | `pytest -c pytest-app.ini tests_app/test_openapi_drift.py` | 1 passed |
| Coverage map | `python scripts/orchestrator/coverage.py . --check` | OK: every discovered id has a valid stage (the open-issues compare skipped: `gh` not signed in here) |
| Front end, whole | `npx vitest run` | Test Files 205 passed (205); Tests 2492 passed (2492) |
| DB files touched, one pass | 7 files under `/root/ofo-db-fresh.sh` | 19 failed, 116 passed. All 19 are in `test_paper_totals.py`, with the ADR-058 cross-file interference above. Alone: `test_paper_totals.py` 19 passed; the other 6 files together 116 passed. |
| App suite without DB | `pytest -c pytest-app.ini -m "not full_chain"` (as prepush) | 5382 passed, 5 failed. 4 were generated-file drift, fixed by bf70ece9; 1 was a stale D-04 test, fixed in 34317f92. |
| ci_local | `python tools/ci_local.py` | TOTAL: 16 passed, 0 failed, 5 skipped |
| prepush | `python scripts/orchestrator/prepush.py` | result on the report commit: in the progress log and the PR #722 comment |

Why the two stale tests were missed: each lane ran its own touched files. The full no-DB run and the whole vitest run
found them before prepush, as the Part B and C lesson asked. Sibling class: whole vitest and the no-DB app suite are
both green after the fixes.

## DONE / PENDING / BLOCKED / PARKED / NEXT

- **DONE:** D-36, D-37, D-38 and D-40 are Fixed, not tested. Part C's red frontend check is fixed.
- **PENDING:**
  - screen checks on the owner's PC in market hours (listed per issue);
  - the owner's read of ADR-324, Q3 and Q4;
  - #723.
- **BLOCKED:** none.
- **PARKED:** none.
- **NEXT:** Part E, started by the orchestrating session:
  `/goal docs/process/goal-contract-GC-ICLIVE-E-2026-11-24.md`
