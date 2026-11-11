# Goal contract GC-ICSAFE: close iron condor, write the finish line, fix the four first-user failures (2026-11-10)

**Status:** APPROVED by the owner on 2026-11-10 (scope answered with the question tool at 13:5x IST: "Steps 1, 2 and 3
together"; direction approved 13:07 IST).
**Executor:** `/goal` in a fresh session of this project, started on a trading day before 09:00 IST (first choice
Wed 11 Nov 2026).
**Standing direction step:** 1, 2 and 3 of `docs/process/standing-direction.md` (review page
https://claude.ai/artifact/H4LhEbLVt372vUork193pc). Cards D-01, D-02, D-03, plus clean-up D-09 and D-11.
**This file** is untracked in the main checkout. Task 2 MOVES it into the run's worktree (copy, then delete the
main-checkout copy) and commits it with the run.
**Written against:** main `5a8f5683`, 2026-11-10 13:59 IST.

**Mission, in plain words:** finish what is open on iron condor and stop adding to it; write the list of what
Zerodha must see; and repair four things a first user would hit: the loss alarm that never rings when no screen is
open, no warning when the background watcher dies, the calendar that ends on 31 Dec 2026, and the daily contract list
that needs a hand-push. Also land the faster test database and leave the desk clean.

**Core:** the background worker process can use the day's stored Kite login and, with it, read the account's margin
without a screen open. (The margin reader already exists; the login is what is missing.)
**Proof (task 12, before any stage E code):** in the worker process, the day's stored session loads and one margin
read through the existing reader returns a value and its time; print "margin read OK at <time>, age <s> s" only. Never write the figure to a
file, a commit, an issue or the status page (public repo). If the read fails or no session exists -> HALT stage E
item #627, report with the output, continue the other stages.

## §0 Run rules

1. **Idempotent start.** First action: read this file, `docs/process/standing-direction.md`, the newest
   `docs/process/session-handover-*.md`, `git log --oneline -40` on main and the status rows `c01..c57`. A row whose
   done line already holds on main is marked done with that evidence and skipped. Never redo finished work.
2. **Paper only (ADR-281).** No real order, no Kite order page, no click inside any Kite order panel. Nothing is
   adopted from Kite. Margin and funds figures from Kite never go into any file.
3. **Iron condor freeze (standing direction rule 2).** This run adds no adjustment approach, trigger, wording round,
   guide content or iron-condor decision row. It fixes named defects only. A defect outside a task's done line
   becomes a `deferred` issue (`gh_issue.py app ... --stage`), with its evidence.
4. **Name the step.** Every brief and commit subject starts `GC-ICSAFE c<nn>`. Work that fits no row is not started.
5. **Status page:** https://claude.ai/artifact/LcMTSr5xx8LvAYVniotkxK, db collection `tasks`, rows `kind: "task"`,
   ids `c01..c57`, ordered 201..257 (created in the planning session on 2026-11-10; the older `t*`, `f*`, `g*` rows were
   removed that day, backup in `D:\Abhay\scratch\status-page-backup-2026-11-10`). One ArtifactData `update` at a task's START and one at its FINISH (state, time
   from `Get-Date` in the same step, actual minutes, evidence line). Pin `if_version`. Never a mid-task write. Write a
   row only when its state changes: never on a timer, never to add progress notes.
6. **Workers.** Builders are Sonnet (`model: sonnet`). Opus only for the Tier A reviewers of
   tasks 41, 46 and 47, each with a `Why Opus:` line. Every brief
   carries `Budget:`, `Core:` / `Proof:`, `Class:`, `Report: evidence-table`, the `.claude/kit/builder-brief.md`
   standing items, a `Reuse:` line from a grep done before the brief, and every answer state (stated, absent, not
   found, failed, empty, ambiguous) with what each does. Merge the builder's reported sha after a diff read, never a
   branch by name. DB-heavy test runs are the orchestrator's one sequential pass, not each builder's.
7. **Tests.** Targeted per file. DB tests one file at a time, one list at a time:
   `python scripts/orchestrator/db_run_fresh.py . python -m pytest -c pytest-app.ini tests_app/<file>.py`
   (the database host also serves production; never run a suite there ad hoc). Long output to a log outside the
   repo; read the tail. No browser e2e suite, no mutation run except the Tier A review's own.
8. **Browser.** Claude in Chrome, the owner's visible Chrome window, app pages only, desktop width. Start servers
   with the commands in `docs/process/session-handover-2026-11-08-gc-ictrack.md` (Redis 5 on 6380, API 8765 in bus
   mode, vite 5173 from the main checkout). Long processes and every gate run under Desktop Commander
   `start_process` (the idle low-memory stop killed a gate on 2026-11-10). Stop only PIDs this run started; never
   select a process by its command line.
9. **Stuck work.** At most 2 rounds per item, then a `parked` issue with evidence and `PARKED (#N)` in the row. Second
   red of one failure class: an independent reviewer (fresh context) before a third try. Owner away or night: write
   to `docs/process/owner-questions-2026-11-11.md` with a recommendation; never the question tool at night.
10. **Done claims.** Every done row names the command or screenshot and its result line. "It ran" is a check: name the
    value that moved. A worker's report is a claim: re-run its gate or read its artifact before marking the row.
11. **Teaching rule** (`~/.claude/rules/teach-the-owner.md`): owner-facing text in the handover and the
    owner-questions file is in plain words, what the user sees first.

12. **Engineering standards for every task** (the builder's brief quotes these; the reviewer checks them; row 45 is the
    orchestrator's own read against them):
    - **Reuse before writing.** Grep first. A brief names the existing function its fix calls (section 2 and row 6).
      Writing a second version of something that exists is a defect, even when it works.
    - **Fix the cause, in the one place every case passes through.** Never a second code path beside the first
      (ADR-275), never a detector where a structural fix is possible.
    - **Smallest change that fully works.** No new dependency, no new table, no new helper layer, no option nobody
      asked for. If a new table or dependency seems needed, the brief says why the existing ones do not fit.
    - **Failing test first, on the real function,** then the fix; one real-data proof before merge.
    - **Fail closed, say why.** Every answer state is handled (stated, absent, not found, failed, empty, ambiguous);
      "not checked" always carries its reason; never a guess, never a silent last-good value.
    - **Money is exact decimal** (ADR-008); every money number comes from the engine; user text comes from the
      templates and passes the wording checks; secrets and account figures are never logged or written to a file.
    - **Leave it clean.** No dead code, no commented-out code, no debug prints, no TODO without an issue number; names
      and layout follow the neighbouring code; a comment only for a "why" the code cannot show; ruff and the complexity
      baseline stay green.
    - **No time on small things.** Cosmetic clean-ups, renames and "while I am here" changes are not done; a real
      defect outside the row becomes a `deferred` issue in one line.

## §1 Decisions already made (do not pause on these)

- **ONE pull request, at the end** (owner, 2026-11-10: "only once everything is done, only then create a PR and run
  CI"). Code and docs together, one `prepush.py` gate, one CI run (rows 53, 54). PRs #688 and #690 already exist and
  are only merged. Trade-off accepted: nothing of this run reaches main until the end, so every task is committed
  on the branch, reviews run by area on the diff, and the live proof (row 40) runs before the PR.
- **#685 scope.** Fix items 3, 4 and 5 (real defects a user sees). Items 1, 6, 7 are test-data only and item 2
  (a separate Completed tab) is a new screen: all four stay in #685, untouched.
- **#627 scope (corrected in the plan review).** The margin read, its rate limit and its answer states are already
  built; T-13 is already built. The one gap is that the worker process has no Kite session. Fix: the worker loads
  the day's stored session through the same code the API process uses, and picks it up when the login arrives
  after the worker started. Also in scope: the heartbeat-alert half of item 3. NOT in scope: the restart service
  (belongs with hosting, D-05) and items 4, 5, 6. Update the issue body, which is out of date.
- **Live day 2 runs from the run's work folder,** before the merge, so the real-data proof comes before the PR.
- **Heartbeat.** The worker writes a heartbeat each cycle (reuse the existing store; no new table unless grep proves
  none fits). The API process checks its age each minute; older than 180 s in market hours -> one alert through the
  shared Notifier gateway (`POST /notify`, project block and keys per `D:\Abhay\GLOBAL.md` section 2 and
  `D:\Abhay\GLOBAL.env`; never copy either into the repo), `dedupeKey` per day per state, and one "recovered" alert.
  Outside market hours and on holidays: silent. If the gateway is unreachable from this PC: the alert code is built
  and unit-proven, the row is PARTIAL, and the reach-ability goes to the owner-questions file.
- **#686 behaviour (departs from the issue text, on purpose).** The issue proposed refusing live start-up from
  1 Dec without the next year's list. That would stop the app in December on days the calendar does cover, before NSE
  has published. Instead: (a) from 30 days before the last listed date a daily warning (log line, header banner, one
  Notifier alert per day); (b) a date after the last listed date reads "calendar has no dates for <year>", a state
  distinct from "market closed", shown on screen; rule checks stay withheld (fail closed) with that reason. Record
  this in the issue. The 2027 list itself cannot be loaded now (NSE publishes in December): owner/maintainer step,
  written into the owner-questions file with the source used for the 2026 file.
- **#680 design.** Read the ADR-058 body first. The guard must tell a strike-range trim (every expiry still present,
  strikes contiguous, row count and file end sane) from a cut-off file (expiries missing, or the file ends mid-row,
  or a whole segment gone). A trim is accepted and logged with counts; a cut-off file is refused as today. If that
  departs from ADR-058's words, write the amendment as a decision row under the owner's data-issues delegation,
  labelled SPEC CHANGE with the quoted text.
- **#682 design.** Structural, not a detector: one database connection per request, handed down to nested readers
  (`settings_store.database_now`, `paper_book.load_owned` and every other reader the class grep finds). Proof at
  pool size 1.
- **#688** merges only after a fresh Tier A review (it creates and grants on databases on the host that serves
  production). The earlier session told the owner it would not merge before he had seen it: write one line in the
  owner-questions file when the review passes, then merge on green. Technical call, told as information.
- **g37** (same-day condor, live) can only run on Tue 17 Nov 2026, an expiry day. If this session is not running
  then, the row stays "not yet run live" and this contract closes PARTIAL naming it.
- **g25** (owner reads 23 new texts) is the owner's. Non-blocking; pins stay "pending owner read".
- **Not touched:** the privacy clean-up question Q1 in `owner-questions-2026-11-09.md` (owner's choice, a history
  rewrite); no force-push of any kind in this run.

## §2 Read first / reuse (verified 2026-11-10 on main 5a8f5683)

- Open work to collect: `fix/toast-no-native-dialog` 853dffe2 (#689); `fix/gc-icguide-day2` 724fbe7e (10 Nov
  handover, owner-questions notes, PATH-63 January chain); `tooling/db-template` f8729df7 (PR #688);
  `docs/standing-direction` 6d17bab3 (not pushed at writing time: its gate was still running).
- Uncommitted in the main checkout, written by the GC-ICGUIDE session: `docs/process/coverage-stages.yaml` (+1 line,
  #689), `docs/process/owner-questions-2026-11-09.md` (+27 lines), `views/status-page.json`; untracked
  `.claude/g2.log` (77 bytes, a stray error log).
- Worker: `backend/ofo_app/background.py` (line 94 lists what is not built); T-16 "not checked" reason
  `adjust_trigger_missing_margin`; evaluator `backend/ofo/adjustment/playbook_eval.py`.
- Calendar: `backend/ofo/market_calendar.json` (21 dates, all 2026; remaining holidays 24 Nov and 25 Dec).
  Trading days for this run: Wed 11, Thu 12, Fri 13, Mon 16, Tue 17 Nov. Check the file again on the day.
- Instrument refresh: `ofo_app.catalogue_refresh`, `apply_update(force=True)`, ADR-058.
- Issues to read in full before their task: #685, #689, #627 (and its 2026-11-04 comment), #686, #680, #682, #688.
- Findings to read before designing: `knowledge/findings/market-calendar-runs-out-at-year-end.json`,
  `db-role-connection-limit-below-pool-size` and the other `db-rol*` files, `local-ci-mirror-runs-a-subset`.
- Zerodha's ask for the checklist: finding F-31 in `spec/findings.md`; milestone ADR-060.

- **Verified reuse map (2026-11-10, main 5a8f5683). Build on these; do not rebuild them:**
  - Loss alarm (#627): the margin read ALREADY EXISTS in the worker: `backend/ofo_app/background.py` `MarginCache`,
    `screen_margin_reader`, `refresh_margins`, `_margin_loop`, with rate limit and answer states (module docstring
    step 3). The gap is at ~line 1870: "this process holds no Kite session of its own yet
    (`live_market.current_session` answers None here)". The stored login is in `backend/ofo_app/broker_token_store.py`
    (`store_session`). The fix shares the session; it writes no margin code. T-13 (day open) is also already built.
  - Alert left open (#685 item 3): lapse code exists: `playbook_store.lapse` / `lapse_all`,
    `background._lapse_open_of`, `_lapse_exited`, `_lapse_not_monitored`.
  - Calendar (#686): one module, `backend/ofo/market_calendar.py` (`market_status`, `_day_status`, `is_market_open`);
    8 readers call it. Change it there once.
  - Daily contract list (#680): the guard is `backend/ofo/instruments/catalogue.py` (`check_max_delist_percent`,
    the refusal near lines 192-218), fed by the admin setting `data.max_delist_percent`.
  - Screens that hang (#682): nested readers `settings_store.database_now` (:78), `catalogue_picker.database_now`
    (:40), `paper_book.load_owned` (:66).
  - Notifier: NO client exists in this repo (`catalogue_load.py:10` and `background.py:94` both say "not built").
    Row 25 writes ONE small client; the heartbeat and the calendar warning both use it.

## §3 Tasks (each <= 15 min; status row id = c + number)


### Stage A. Set up

| # | Task (plain words) | For the session | Min | Done line |
|---|---|---|---|---|
| 1 | Read the plan and skip anything already finished | Idempotent start (run rule 1); confirm status rows c01..c57, o01..o08, n01..n09 exist | 10 | list of rows already true on main, in the run log |
| 2 | Open a separate work folder for this run | `wt-new.ps1` (name `OptionsForOptions2-gc-icsafe`, branch `build/gc-icsafe`, TTL 48h); move this contract in | 5 | `git log` on the branch shows the contract commit; main-checkout copy gone |
| 3 | Merge the standing direction file (its merge request is already open) | PR #690: merge on green with `merge.py`; no new PR | 10 | file on main, or the PR's check state |
| 4 | Collect the two finished fixes that were never pushed | Read each diff, then merge 853dffe2 (#689) and 724fbe7e (10 Nov notes, January test data) by sha | 15 | both shas are ancestors of the branch |
| 5 | Save the loose edits lying on the main copy | Bring the 3 uncommitted main-checkout files onto the branch as a patch; confirm byte-identical; only then restore them in main; read then remove `.claude/g2.log` | 10 | `git status` on main is clean; the three changes are on the branch |
| 6 | Before any coding: for each fix, name the existing code it must use | Reuse map, one line per fix, starting from section 2's verified list; grep before adding to it. A fix with no reuse line gets a one-line reason | 15 | reuse map in the run log; every build brief quotes its line |

### Stage B. Live market day 1

| # | Task (plain words) | For the session | Min | Done line |
|---|---|---|---|---|
| 7 | Check today is a trading day | `market_calendar.json`. Not one: move rows c07-c12 and c40 to the next trading day and work the other stages | 5 | the date and the file's answer |
| 8 | Check the owner's broker login for today is in place | `broker_sessions` row for today and `/user/profile` answers. Absent at 09:20: owner-questions note, continue other stages, re-check each hour | 5 | session time, or the note |
| 9 | Start the app on live prices | Live stack from the main checkout (run rule 8) | 15 | PIDs recorded; feed state connected |
| 10 | Live check: weekly and this-month iron condors, built, watched and adjusted once on practice money | Was GC-ICGUIDE row g35. Through the screens | 15 | screenshots + one value per step |
| 11 | Live check: next-month and two-months-out iron condors, same | Was GC-ICGUIDE row g36 | 15 | screenshots + one value per step |
| 12 | CORE PROOF: the background watcher can use today's broker login and read margin | In the worker process: load the day's stored session (`broker_token_store`) and make one margin read through the existing `screen_margin_reader`. Print time and age only, never the figure. A throwaway script is fine | 15 | 'worker session OK, margin read OK at <time>', or HALT rows c22-c24, c40, c46 |

### Stage C. Iron condor faults, then freeze

| # | Task (plain words) | For the session | Min | Done line |
|---|---|---|---|---|
| 13 | Alert left open after the user already acted: find the cause, write the failing check | #685 item 3. RCA + failing test first. Class: every open record whose legs no longer match the tracked position | 15 | test is red for the stated reason |
| 14 | Alert left open after the user already acted: fix by reusing the existing 'lapse' code | #685 item 3: call the existing `playbook_store.lapse` / `_lapse_open_of`; no second lapse path. Prove on PATH-60 | 15 | test green; count of such records before and after |
| 15 | Alert shows a different limit from the settings panel: one source for the number | #685 item 4. RCA why record 215 used 0.3500 when the panel read 0.3000; failing test first; both read the same function | 15 | panel and record show the same number on PATH-61 |
| 16 | Three wrong labels on alerts and the compare screen | #685 item 5: T-09 'below' vs inclusive compare, unit and decimals, Compare 'max profit' label. Texts through the existing templates; run `tests/strategy/test_templates.py`, name guard, `tests_app/test_reply_inventory.py`, ruff ratchet | 15 | checks pass; before/after text listed |
| 17 | Re-check two practice-data screens that were left partly done | GC-ICGUIDE rows 26 and 27, test data, visible Chrome | 15 | screenshots + values |
| 18 | Re-check the 'roll into January' picture | GC-ICGUIDE row 29 on PATH-63 | 15 | screenshot + the Compare line |
| 19 | Confirm the new-alert message no longer freezes the page | #689 on screen: in-page toast, page keeps updating, no native dialog | 10 | screenshot taken while the toast is up |

### Stage D. The finish line

| # | Task (plain words) | For the session | Min | Done line |
|---|---|---|---|---|
| 20 | Draft the list of what Zerodha must see before a demo | `docs/process/demo-ready-checklist.md`: one row per F-31 item (9) plus each screen ADR-060 names; columns: what Zerodha must see, state today (measured or 'unmeasured'), proof needed, who does it | 15 | all 9 items + screens listed; no state is a guess |
| 21 | Ask the owner to approve the list | Owner-questions entry in plain words, with a recommendation | 5 | entry written |

### Stage E. First-user failures

| # | Task (plain words) | For the session | Min | Done line |
|---|---|---|---|---|
| 22 | Loss alarm: find exactly why the watcher has no broker login | #627. RCA: `live_market.current_session()` answers None in the worker process (`background.py` ~line 1870). Read how the API process gets its session and what `broker_token_store` holds | 15 | one-sentence cause + the function the fix will call, in the issue |
| 23 | Loss alarm: the watcher uses the day's stored login, also when the login arrives after it started | #627 fix: worker loads the stored session through the same code the API uses; no new margin code, no new token store. Token never logged | 15 | builder sha; failing-then-green test |
| 24 | Loss alarm: checks for 'no login today', 'login expired' and 'login arrives late' | #627 tests: each state reads 'not checked' with its reason (the existing `missing_margin` path), never a guess | 15 | 3 tests pass; domain + one DB file at a time |
| 25 | CORE for warnings: send one real test warning to the owner's phone | Smallest client for the shared Notifier (`POST /notify`, zero new dependency), one message marked TEST. Proves the road before anything is built on it | 15 | HTTP status line; or PARTIAL + owner-questions note and rows c27, c28 alerts stay unit-proven |
| 26 | Watcher heartbeat: the watcher records that it is alive | Worker writes a heartbeat each cycle in an existing store (new table only if the reuse map proves none fits); API process checks its age each minute | 15 | test: age over 180 s in market hours is 'stale' |
| 27 | Watcher heartbeat: warn the owner when it stops, and when it recovers | Uses the c25 client. One alert per day per state; silent outside market hours and on holidays (REQ-115 AC-6) | 15 | tests: stale -> one alert, repeat -> none, recover -> one |
| 28 | Calendar: warn from 30 days before its last date | #686, in `ofo/market_calendar.py` (the one module every reader calls): daily log line, header banner, one Notifier alert per day via the c25 client | 15 | test: 2026-12-02 warns; 2026-11-11 does not |
| 29 | Calendar: say 'no dates for 2027' instead of 'market closed' | #686: new state from `market_status`; rule checks stay withheld with that reason; screen text through the wording checks | 15 | test: 2027-01-04 reads the new state |
| 30 | Calendar: note for the owner to load the 2027 holiday list in December | #686: owner-questions entry naming the source; comment on the issue recording the changed design | 5 | entry + issue comment |
| 31 | Daily contract list: find why a complete list was refused | #680: read ADR-058 body and `ofo/instruments/catalogue.py` (`check_max_delist_percent`, ~line 192-218); RCA; design note in the issue | 15 | note posted |
| 32 | Daily contract list: write the failing check with the real refused list | #680: failing test first with REAL fixtures: the list refused on 2026-11-09 (or today's download) and a hand-truncated copy | 15 | test red on today's code |
| 33 | Daily contract list: accept a trimmed list, still refuse a cut-off file | #680: change the one guard; SPEC CHANGE row for ADR-058 if its words change | 15 | real list accepted with counts; truncated copy refused |
| 34 | Daily contract list: today's refresh runs with no hand-push | #680 live: the day's refresh without `force` on ofo_dev | 10 | refresh log line with added / delisted counts |
| 35 | Screens that hang: list every screen request that takes two database connections | #682 RCA: the two named routes plus the class grep (`settings_store.database_now`, `catalogue_picker.database_now`, `paper_book.load_owned` callers) | 15 | list in the issue |
| 36 | Screens that hang: write the check that fails today | #682: one test that calls `POST /paper/strategies/{id}/orders` and `GET /api/strategies/{id}/adjustment-check` at pool size 1. This single test is both the proof and the guard against it coming back | 15 | red on today's code (timeout named) |
| 37 | Screens that hang: fix the two known ones | #682: the request's own connection is handed down to the nested readers; no new pool, no new helper layer | 15 | builder sha |
| 38 | Screens that hang: fix the rest of the list | #682: remaining readers from the c35 list, same pattern | 15 | builder sha; list fully ticked |
| 39 | Screens that hang: run the checks | #682: the c36 test green; touched DB files one at a time | 15 | both routes answer under 5 s at pool 1; pass counts per file |
| 40 | Live market day 2: the loss alarm is checked on every open strategy with no screen open | Run the stack from the run's work folder (before the merge, so the proof comes first). Worker log between two named times | 15 | count of checked T-16 lines > 0 and count of `adjust_trigger_missing_margin` = 0 |

### Stage F. Clean-up

| # | Task (plain words) | For the session | Min | Done line |
|---|---|---|---|---|
| 41 | Faster test database: strict independent review | #688 Tier A: fresh Opus (`Why Opus:` creates and grants on the production database host) | 15 | verdict |
| 42 | Faster test database: fix, tell the owner, merge (its merge request is already open) | #688: fixes if any; one owner-questions line; merge on green; no new PR | 15 | merge sha, or findings parked |
| 43 | Old unfinished branches: keep, or remove if already on main | `git cherry main <branch>` for `build/gc-ictrack*`, `docs/adr-275-one-code-path`. Fully on main: delete the local branch. Else list for the owner, delete nothing | 15 | table: branch, commits not on main, action |
| 44 | Remove leftover work folders safely | `wt-sweep.ps1`; `wt-rm.ps1` for merged and clean ones; count installed packages in the main checkout before and after | 10 | counts equal |

### Stage G. Review, one merge, close

| # | Task (plain words) | For the session | Min | Done line |
|---|---|---|---|---|
| 45 | Senior-developer read of the whole change against the standards list | Orchestrator reads the full diff against run rule 12 (reuse, smallest change, no dead code, no float money, fail closed, tests first). Anything off is fixed before review | 15 | one line per standard: holds / fixed |
| 46 | Strict independent review: the watcher's broker login | Tier A: fresh Opus, adversarial (`Why Opus:` Tier A, handles a login secret and guards money). Mutation-tests each guard | 15 | verdict |
| 47 | Strict independent review: the warnings to the owner | Tier A: fresh Opus, heartbeat + Notifier client + calendar warning | 15 | verdict |
| 48 | Independent review: iron condor fixes and the daily contract list | Tier B: fresh Sonnet, diff only: #685 items, #689, #680 | 15 | verdict |
| 49 | Independent review: screens that hang | Tier B: fresh Sonnet, diff only: #682 | 15 | verdict |
| 50 | Fix what the reviews found, part 1 | Contingency. Second red of one class: an independent reviewer before a third try | 15 | re-run passes, or 'nothing to fix' |
| 51 | Fix what the reviews found, part 2 | Contingency | 15 | re-run passes, or 'nothing to fix' |
| 52 | Write the hand-over note and bring the branch up to date | Handover in plain words (DONE / PENDING / BLOCKED / PARKED / NEXT); merge main into the branch; ruff after the merge | 15 | handover committed; branch contains main |
| 53 | Run the full pre-push check once | `python scripts/orchestrator/prepush.py` under Desktop Commander; write the final report draft while it runs | 15 | TOTAL PASS + marker for HEAD |
| 54 | ONE merge request for everything; merge when the automatic checks are green. Iron condor is now frozen | The only new PR of this run: code + docs together, Spec-deviation block, ONE CI run, `merge.py <pr> --reviewed-sha <sha>` | 15 | merge sha on main |
| 55 | Independent check that every finished task really met its 'done when' line | Verifier over the done lines of every task that changed behaviour (c13-c19, c22-c40) | 15 | one evidence block per row |
| 56 | Tue 17 Nov only: same-day iron condor on live prices | Was GC-ICGUIDE row g37. Session not running that day: 'not yet run live', contract PARTIAL | 15 | screenshots + values, or the PARTIAL line |
| 57 | Final report and close the work folder | Final report (section 7); `wt-rm.ps1`; last status rows | 10 | report sent; `git status` on main clean |

While the gate or CI is in flight, work the next row; never wait idle. Commit after every task on the run's branch (subject `GC-ICSAFE c<nn>: ...`); push nothing until row 53 passes.

**Size (15-minute tasks, hidden steps included):** 57 rows, 770 planned minutes (~12.8 h), or ~16.7 h with the 30% overrun measured on earlier contracts. One gate run and one CI run (about 1 h) are on top. Two market days are needed (c07-c12 on day 1, c40 on day 2), plus 17 Nov for c56.

Status rows also hold what is NOT in this contract, so the page shows the whole road: `o01..o08` (the owner's own actions) and `n01..n09` (later work with no contract yet). This run updates an `o` row only when the owner has done it, and never changes an `n` row.

## §4 Verification gates

- Per row: its done line, with the command and result line (evidence before claims).
- For the one PR: `prepush.py` TOTAL PASS with a marker for the pushed HEAD, then CI green. Local `ci_local.py` alone is
  not the gate (finding `local-ci-mirror-runs-a-subset`).
- Tier A review: tasks 46, 47 (worker login + alerts) and 41 (#688). Tier B: tasks 48, 49. Tier C: docs.
- Every defect fix carries RCA, Class (as a data filter, size before and after), failing test first, class-level
  fix, one real-data proof, and a detection change or `No detection change: <reason>`.
- Screens proven by hand entry through the real forms, never by loading a fixture.

## §5 Failure budget and hard stops

- 2 rounds per item, then park (§0.9). A halted core proof (task 12) halts only #627 (rows c22-c24, c40, c46).
- HARD STOPS, never worked past: any real order; any click in a Kite order panel; a force-push or history rewrite;
  deleting an unmerged branch or a dirty worktree; a production deploy; any run of a test suite on the database host
  outside `db_run_fresh.py`; writing an account figure to a file; a new iron-condor feature.
- Under about 3 GB free memory: stop any process this run started that is not needed, by PID, before starting a gate.

## §6 Done

All of these hold:
- every row c01..c57 is `done` with evidence, or `parked` with an issue (that keeps the contract PARTIAL);
- the ONE pull request of this run is merged to main, and the two that were already open (#688, #690) are merged or parked;
- the live checks carried over from GC-ICGUIDE are done (c10, c11); c56 is done or carries "not yet run live (17 Nov)";
- the worker log of one live day shows T-16 checked on every open paper strategy (c40);
- #680's real list is accepted and a truncated copy refused; #682 answers at pool size 1; #686 warns and names the
  missing year; the heartbeat alert is proven or PARTIAL with the reason;
- `docs/process/demo-ready-checklist.md` exists with every F-31 item and the approval question is filed;
- `git status` on main is clean and no worktree of this run remains.

Not in this contract: real orders (ADR-281, standing direction step 4); hosting and a second login (step 4); the
short strangle test (D-04); the issue triage (D-07); the status-record clean-up (D-08); fewer decision rows (D-10);
structural debts (D-12); #684, #683, #644; #627 items 2, 4, 5, 6 and the restart service; a Completed tab; SENSEX;
the 2027 holiday list itself; the privacy clean-up Q1.

## §7 Final report

DONE / PENDING / BLOCKED / PARKED / NEXT, in plain words first, then:
- the status page link, the PR and its merge sha;
- per first-user failure: what a user saw before, what a user sees now, and the proof line;
- the live-day results with one example value each (no account figures);
- what the owner must do: read the 23 texts (g25), approve the checklist, load the 2027 list in December, answer Q1;
- every deviation from this contract;
- NEXT = standing direction step 4 and the side test (D-04), each needing its own contract.

## §8 Authorization trail

| When (IST) | Decision | By |
|---|---|---|
| 2026-11-10 13:07 | Standing direction approved; holds until changed in explicit words | owner, chat |
| 2026-11-10 13:5x | This contract covers steps 1, 2 and 3 together | owner, question tool |
| 2026-11-10 14:2x | Plan review: one PR at the end, reuse-first, standards block; #627 re-scoped to the missing worker login (the margin reader already exists) | owner asked for the review; reviewer decided |
| 2026-11-10 | #685 scope, #627 scope, margin-read states, heartbeat design, #686 behaviour, #680 and #682 design, PR split, #688 review tier, g37 handling | reviewer, as technical calls; told to the owner as information |
