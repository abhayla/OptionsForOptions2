# Lane J results (26-27 Nov 2026): the join of the screens line and the alerts-and-plans line

Branch `integration/nb-1126`, cut from `origin/fix/screen-findings-1126` (7bf64eb). Pushed only there; no PR.
Standing-direction step: step 4 (the journey for iron condor), owner-directed batch of 26 Nov (ADR-330; freeze lifted
for these items by the owner on 26 Nov, see RESULTS-lane-p.md). Highest status claimed for anything here:
**Fixed, not tested** (the owner tests on his PC in market hours, 27 Nov 09:15 IST).

Spec basis: ADR-330 (1) to (27) and its one-module instruction; ADR-002; ADR-003; ADR-008; ADR-016 to ADR-019.

## Status for the coordinator (this session cannot send messages: the session-message service refuses it as untrusted)

**Full app (DB) suite on the final code head 1eb5097, run as CI runs it (GITHUB_ACTIONS=true, per-file database
clones, -m "not full_chain"): `7638 passed, 5 skipped, 23 deselected, 1 xfailed in 2917.28s` (0 failed). Skips:
trial ENDED x3 (ADR-039), EXECUTE_REPLAY_URL unset, no INDEX row in the test catalogue.**

1. Final head for 27 Nov: the head of this commit (docs only on top of 1eb5097). Merged: Lane R a2b44dd, Lane U
   12e04b9 (Change expiry), Lane D 491df12, all of Lane P, Step 2 wiring, Step 3 checks, P7, P8, S-11, the
   Not-applicable line, ADR-330 (31) with 0057.
2. Migrations the PC applies: 0054, 0055, 0056, 0057, each with its old-code-safe proof and its read-only check in
   section (a); 0057 first on the scratch copy ofo_rehearsal_1127. #753 (0058) is built on side branch feat/0058-plan-acceptance-1127 per ADR-330 (45), waiting for the coordinator to join it to the test branch (not on this branch yet).
3. No push to integration/nb-1126 after 07:30 IST until you say.
4. Blocking: nothing. Waiting for the owner (none blocks the test): LJ-2 and the "pending owner read" wordings.

## (a) PC set-up (do these first, in this order; about 30 minutes, start 08:15 IST)

Corrected 26 Nov night from the PC rehearsal (PR #722 comment 7196817335, "Rehearsal for the 27 Nov test": 0054 to 0056
applied on a restored copy of `ofo_dev` in 2 min 44 s, row counts equal, grants unchanged). Facts it found: the
database is on the VPS (127.0.0.1:5432 on the PC is an SSH tunnel), the PC has no `pg_dump`, and
`scripts/orchestrator/db_run.py` always targets `ofo_test`, so it is NOT used below.

1. **Back up `ofo_dev` FIRST, on the VPS over SSH** (as in the rehearsal): `pg_dump -Fc -d ofo_dev -f
   <backup folder>/ofo_dev-2026-11-27-before-0054.dump` run on the VPS as the database owner, then copy the file to
   `C:\Users\itsab\ofo-backups\`. Check it: `pg_restore --list <file>` lists TABLE DATA entries (the rehearsal's dump
   had 47) and the file size is about the rehearsal's (1,795,550 bytes on 26 Nov). Do not go on if either check fails.
   The VPS disk is about 90% full (12 GB free): enough for one dump of about 2 MB.
2. In the checkout the app serves from (NOT a `wt-new.ps1` worktree: `npm ci` there would empty the running app's
   linked `node_modules`): stop the API, the worker supervisor and the frontend; `git fetch origin`;
   `git checkout integration/nb-1126` at the head named in section (c) "Push log" (last row).
3. `pip install -r requirements-app.txt`; `cd frontend && npm ci && npm run build && cd ..` (the build reads
   `docs/api/openapi.json` beside `frontend/`, so run it in the full checkout).
4. **0057 was NOT in the 26 Nov rehearsal** (it ran 0054 to 0056 only). First run this same command with `ofo_dev`
   replaced by `ofo_rehearsal_1127` (the scratch copy left in place by the rehearsal, already at 0056): it must apply
   only 0057 and end at `0057_history_delete_entries (head)`; then run the 0057 check of the list below on that copy.
   Only then migrate the live database:
   **Migrate `ofo_dev`** with the owner-role URL built in memory for this one command (same user and password as the
   rehearsal, read from GLOBAL.env; nothing written to a file), from the checkout root:
   `python -c "import os,subprocess,sys,urllib.parse; sys.path.insert(0,'scripts/orchestrator'); import db_run as d; g=d.read_env(d.GLOBAL_ENV); u='postgresql+asyncpg://'+g['WINDOWS_VPS_PG_ADMIN_USER']+':'+urllib.parse.quote(g['WINDOWS_VPS_PG_ADMIN_PASSWORD'],safe='')+'@127.0.0.1:5432/ofo_dev'; e=dict(os.environ,ALEMBIC_DATABASE_URL=u); [subprocess.run([sys.executable,'-m','alembic','-c','backend/ofo_app/alembic.ini']+a,env=e,check=True) for a in (['current'],['upgrade','head'],['current'])]"`
   Proved here on a scratch database named `ofo_dev` (26 Nov night): it printed `current`, migrated, and printed
   `0057_history_delete_entries (head)`. On the PC it prints `0053_close_finished_strategies` first, runs the migrations listed below in order, and prints the last one
   with `(head)`. A stop with an error: do not start the app; restore from the dump of step 1 and send the error.
5. **After-checks (read-only SQL on `ofo_dev`, run with `psql -d ofo_dev` on the VPS over SSH, as step 1; each line was run
   on a test database migrated by this command, 26 Nov):**
   - `SELECT public.ofo_assert_app_role_allowlist('ofo_app', 'post');` returns without an error (the app role's
     grants and every pinned function body are as the branch expects).
   - Row counts of `adjustment_suggestions`, `strategy_adjustment_plans`, `adjustment_playbooks` and `strategy_history`
     equal the counts taken just before step 4 (no migration below changes or deletes a row, except 0056 filling
     `slug` on the standard playbooks).
   - The per-migration checks in the list below.
6. Start the API, the background worker supervisor (`python scripts/orchestrator/supervise_worker.py`) and the
   frontend. In the browser: (a) Positions > Adjustment opportunities still lists the old records; (b) Alerts > Active
   opens and its row count equals the bell number; (c) a live price ticks on Positions.

Migrations on this branch (the PC is at 0053), each with its old-code safety and what the PC checks after it:

- **0054_actionable_alert_answers**: NULL columns `kind`, `answer`, `answered_at`, `no_longer_true_since`,
  `escalated_at` on `adjustment_suggestions`; old rows keep NULL and read as adjustment rules. One-way: never run
  `alembic downgrade` (it refuses once new alerts exist).
  Old code: the PC's code before this branch (7bf64eb) against a database the branch migrated to 0055 passed
  test_background_worker, test_adjustment_opportunities, test_background_cycle, test_held_tracking,
  test_playbook_store (193 passed, 0 failed; Lane J, 26 Nov).
  PC check: `SELECT count(*) FROM adjustment_suggestions WHERE kind IS NOT NULL;` returns 0 right after the migration.
- **0055_plan_stop_base**: `stop_base JSONB NULL` on `strategy_adjustment_plans`. Old code: as 0054 (same run).
  PC check: `SELECT count(*) FROM strategy_adjustment_plans WHERE stop_base IS NOT NULL;` returns 0 right after.
- **0056_several_standard_playbooks**: drops the one-standard-playbook-per-type unique index; adds `slug` (each
  standard playbook gets `<type>-default`, unique per type); ADR-330 (9). Old code (7bf64eb) against a database at
  0056: test_background_worker 24, test_adjustment_opportunities 34, test_background_cycle 78, test_held_tracking 6,
  test_playbook_routes 18, test_system_playbook_versions 23, test_adjustment_plan 10, test_paper_monitor 23,
  test_paper_triggers_routes 65, test_exit_door 34 passed; test_playbook_store 50 passed and 1 failed by design (it
  expects the database to refuse a second standard playbook, which 0056 allows on purpose).
  PC check: `SELECT count(*) FROM adjustment_playbooks WHERE is_system AND slug IS NULL;` returns 0 (the rehearsal: all
  12 got `<type>-default`).
- **0057_history_delete_entries** (ADR-330 (31)): the strategy-history item validator accepts two new kinds,
  `deleted` and `undeleted`; no table, column, grant or row change. Migrate BEFORE starting the new code (at 0056 a
  new-code Delete or Undo is refused by the database and rolls back). Old code (3d7aaf7, before 0057) against a
  database at 0057 holding a `deleted` entry: test_strategy_store 98, test_strategy_bulk_delete 11,
  test_strategy_delete_app 31, test_strategy_name_app 28 passed; its history screen shows such an entry as "this change
  could not be shown". Tier A review (Opus): SHIP (all 44 old history rows of every kind still valid after the
  upgrade; grants unchanged; downgrade refuses while a delete entry exists).
  PC check: `SELECT count(*) FROM strategy_history WHERE NOT public.ofo_strategy_change_items_valid(change_summary);`
  returns 0.

These old-code tests build their own throwaway databases (they are run here, on test databases, not on the PC); the
PC runs only the read-only checks above.

**#753 / migration 0058 (round 3): order and rollback.** Owner rule (ADR-330 (45)): only the first save, accepting a
playbook (also the same one again) and Reset to playbook stamp a new acceptance; a plan-sheet edit never stamps.
Deploy order: run `alembic upgrade head` (0058 included) FIRST, then restart the API on the new code. Rollback rule:
a code rollback must ALSO run `alembic downgrade 0057_history_delete_entries`, because old code never sends the
acceptance signal and on a 0058 database its accepts (POST, Reset) would not stamp (a plan the user re-accepts would
stay "saved before ADR-247"; its edits no longer restamp). New code on a 0057 database still works (0041's function
stamps on every body change). PC read-only check after 0058 (changes nothing): `SELECT position('ofo.plan_acceptance'
in pg_get_functiondef('public.strategy_adjustment_plans_guard()'::regprocedure)) > 0;` returns `t` (and `f` after the
downgrade); `alembic current` names `0058_plan_stamp_only_on_switch`.

## (b) Screen-check list (owner, paper only, market hours 09:15-15:30 IST; Ctrl+F5 once after the rebuild)

Each row starts with "[needs live prices: yes/no]". Step 2 (the wiring: fired stops through the one alert module
with the max-loss line, Exit on an alert through the one exit door, the leg-stop risk line, the Plan watch box) has
been on origin since push 2 (7d81d0a, 26 Nov evening); rows L1 to L8 test it.

Live-price checks first (rows L1 to L9 need ticking prices), then the rest. Each row: the clicks, then the exact text
expected. Write PASS / FAIL and what you saw beside each.

Set-up for the live rows: one paper iron condor WITH a plan (Positions > Paper > Add to Paper from the builder; then the
plan sheet: Set plan, a Stop (Rs) a little above the current loss so it can be crossed, Save), and one paper iron condor
WITHOUT a plan.

L1. [needs live prices: yes] Plan watch on the builder (ADR-330 (13)). Open the planned trade in the builder (My Strategies > its row > Open in
    Builder). Expected: beside the live P&L a box titled "Plan watch", one row per trigger (profit target, loss stop,
    2x credit, each adjustment rule; each armed Stops-panel exit under "Armed in the Stops panel"), each row showing
    fires at, now, distance as "₹X (Y%)", and a state. The "now" and distance figures change with the prices.
L2. [needs live prices: yes] Plan watch on Positions. Positions > Paper: the planned trade's row shows the same box in its compact form, with the
    same figures as L1 at the same moment. The trade WITHOUT a plan reads "No plan: nothing is watched for this
    strategy" and still lists its armed Stops-panel exits, if any. A fully closed trade shows no box.
L3. [needs live prices: no] Max-loss line before a leg stop is saved (ADR-330 (6)). Positions > Paper > the planned trade > Stops. Pick the
    short CALL leg, type a stop price above its price. Within about half a second a line appears under the box:
    "If this stop fires, max loss becomes Rs X (now Rs Y)." (or "If this stop fires, there is no fixed maximum loss
    (now Rs Y)." when the leg's wing would be left alone). Change the price: the line goes away and comes back for the
    new price. Clear the box: no line. Save is clickable in every case.
L4. [needs live prices: yes] Save that leg stop at a price the market will reach soon. When it fires: a pop-up appears for about 6 seconds,
    titled with the trade's name, number and expiry, as in "Short Iron Condor (#172, 1 Dec)", whose text ends with the
    same "If this stop fires, max loss becomes Rs X (now Rs Y)." line as L3. The bell number does NOT go up.
    Alerts > History shows the same message once. The leg is exited on the Paper Orderbook (one exit order).
L5. [needs live prices: yes] Actionable alert stays until answered (ADR-330 (3), (4)). Wait for (or arrange) the plan's loss stop on the planned
    trade to be crossed. Expected: a short pop-up, and the bell number goes up by 1. Alerts > Active: as many rows as
    the bell; the row shows "Fired at HH:MM", its title with "(#<number>, <d Mon>)", and two buttons "Exit the
    position" and "Continue with the position". Opening the page does not lower the bell.
L6. [needs live prices: yes] If the loss comes back inside the stop: the row stays and adds "no longer true since HH:MM"; when it crosses again
    that line goes away. If the loss gets worse, a second pop-up "Worse than when it fired: ...".
L7. [needs live prices: yes] Press "Continue with the position": the row leaves Active, the bell drops by 1, Alerts > History shows the answer
    and its time. Nothing is exited (Paper Orderbook unchanged).
L8. [needs live prices: yes] Exit from an alert (ADR-330 (3), (12)). On another alert press "Exit the position". Expected: the answer is stored
    and the SAME exit confirmation as on Positions opens on the Alerts page for that trade. Press Cancel: nothing is
    exited (Orderbook unchanged). Raise another alert, press "Exit the position", then Confirm: one exit per open leg
    appears on the Paper Orderbook, and the trade reads closed on Positions.
L9. [needs live prices: yes] Time exit on any day (ADR-330 (7)). Plan sheet: "Time exit" with a date box (blank = expiry day). Set today and a
    time 5 minutes ahead; Save. At that time an alert appears as in L5; nothing exits.

Without live prices (any time):

N1. [needs live prices: yes] Stop fixed at entry (ADR-330 (1)). On an iron condor with a plan, note the plan's stop line (e.g. "15.4 % of max
    loss (Rs 400.40)" and "2x credit Rs 7,800"). Close the call side (two exits). Reopen the plan: the same rupees.
N2. [needs live prices: no] Rupee levels with the preview sentence (ADR-330 (5)). Plan sheet: type 400 in "Stop (Rs)" on a 1-lot iron condor:
    the percent box fills from the server and the line under it reads "a loss of Rs 400.00 (<p> % of max loss), 2x the
    credit received ... whichever comes first"; after Save the saved plan shows the same sentence.
N3. [needs live prices: no] Own-plan rule (ADR-330 (11)). The trade without a plan: plan card reads "No plan: nothing is watched for this
    strategy"; no adjustment suggestions or target/stop alerts for it; its Stops-panel exits still fire.
N4. [needs live prices: no] Paper total line (ADR-330 (15)). Positions > Paper with at least one closed paper trade: under the total
    "Includes 1 closed strategy." (or "Includes N closed strategies."). If a trade has no live price, the left-out line
    "1 strategy left out: its price is not live." is shown too, and the total adds up to the rows it shows.
N5. [needs live prices: yes] Whole-trade close closes its alert. Exit a whole paper trade that has an unanswered alert: Alerts > History shows
    "Closed by system: the trade closed at HH:MM"; the bell drops by 1.
N6. [needs live prices: no] Top menu (P12): on My Strategies click "Strategies" in the top menu: its menu opens; click again: closes.
N7. [needs live prices: no] Stop above the max loss (ADR-330 (25), Lane P LP-4). Plan sheet of a 1-lot iron condor with max loss Rs 2,600: type
    3000 in "Stop (Rs)": one line under the box reads "This stop (Rs 3,000) is above the trade's max loss (Rs 2,600),
    so it cannot be reached." Save still works. Type 400 again: the line goes.
N8. [needs live prices: yes] Side closed (ADR-330 (2), (33), Lane P P7, server side only): on a paper iron condor with a plan exit both call legs.
    Within one worker cycle Alerts > Active gains one row naming the closed side and the bell goes up by 1. Its two
    page answers (add legs / confirm the new shape) are not built yet (Lane P Wave 2, Lane J next).
N9. [needs live prices: yes] Real P&L total (Lane S): Positions with no real position in a strategy: "Real P&L" shows a dash and "No real
    positions are open in your strategies."; "Paper P&L" shows its own figure beside it, not added. With one real
    position: the total shows the row's figure with "Zerodha, as at HH:MM:SS IST" and equals Kite's P&L for that
    contract at the same minute. Filter All / Real / Paper: the two totals stay separate.
N10. [needs live prices: yes] Side closed, the answers (ADR-330 (2)(b), (33)). After N8, Alerts > Active, the side-closed row: press "Add the
    legs again": the answer is stored and the builder of that trade opens. On another side-closed row press "Confirm
    the new shape": the confirmation shows the row's own sentence "The call side of this trade is closed. Add the legs
    again, or confirm the new shape: this strategy will change from its entry shape to Bull Put Spread." (the shape as
    the server names it); Cancel: nothing
    is stored and the row stays asking; Confirm: the row leaves Active, the bell drops by 1.
    Plan watch after a side closed (ADR-330 (2)(a)): a plan rule that needs the closed side reads "Not applicable: the
    call side is closed" with dashes for now and distance; the other side's rules keep working. Note: the stock iron
    condor plan has no side-scoped rule (only T-05 is, and it is off), so this line shows only on a plan with T-05 on.
N11. [needs live prices: no] Reset to playbook (ADR-330 (9), (32)). A plan saved from a playbook: switch one condition off, type a Rs 400 stop
    and a 15:15 time exit, Save. Open the plan sheet > Edit > "Reset to playbook": one confirmation says the typed
    levels stay; Confirm: the condition is on again, the Rs 400 stop and 15:15 stay, the changed / switched-off markers
    show. A plan whose playbook was deleted: the reset is refused with the server's sentence.
N12. [needs live prices: no] Deleted / Restored in the history (ADR-330 (31)). My Strategies: delete one draft, then Undo. Open its history:
    two entries "Deleted" and "Restored", each with its time, and no Restore button on either. Bulk: tick 3 rows,
    Delete selected, Undo: each of the 3 histories has one "Deleted" and one "Restored".
N13. [needs live prices: no] Customise triggers keeps the plan (S-11). Plan sheet: type 400 in "Stop (Rs)" and a time exit (today, 15:15),
    then press "Customise triggers": the customise page opens. Come back to the builder: the plan sheet opens again by
    itself with 400 and 15:15 still typed; Save saves them. Another strategy's sheet shows nothing held.
N14. [needs live prices: yes] Change expiry (ADR-330 (42), Lane U D-48). Builder of a paper trade: pick another
    expiry in a leg's expiry box (or "all legs"): the leg moves to that expiry. KNOWN LEFTOVER (Lane U, not fixed
    tonight): a leg stop set on that leg in the Stops panel does NOT follow the moved leg; check the Stops panel after
    the move and write down what it shows.
Re-checks after the merge (quick):
R1. [needs live prices: yes] Exit from Positions: Positions > Paper > a trade > Exit: the confirmation, Cancel exits nothing, Confirm exits.
R2. [needs live prices: no] Positions: the real and paper lists load; the Stops link of a Live Strategies card opens Positions at that trade's
    Stops panel (ADR-330 (21)).
R3. [needs live prices: yes] Builder: open a saved paper trade; the payoff, Greeks and live P&L show; Add Selected from the chain adds legs; the
    leave question reads "Leave the builder? The N pending changes will be lost." (ADR-330 (22)).
R4. [needs live prices: yes] Alert titles and lists carry the number and the NEAREST open-leg expiry, as in "Short Iron Condor" (#172, 1 Dec)
    (ADR-330 (19)); a trade with no open leg shows "(#172)" only. Two paper trades with the same name show two numbers.

## (c) What is merged, what is left out

| Head | Commit | Status |
|---|---|---|
| fix/screen-findings-1126 (Lane R, base) | 7bf64eb | base |
| fix/ic-live-test-1123 (ADR-330 answers, docs) | 2ed05a7 | merged |
| feat/nb-plan-alerts-1126 (Lane P first push) | 7bca124 | merged |
| fix/ic-live-test-1123 (ADR-330 (28) to (33)) | 3d66541 | merged (push 2) |
| fix/screen-findings-1126 (Lane R, newer) | ce5316e (includes 8384516) | merged (push 2) |
| Lane J Step 2 (W2-A, W2-B, W2-C) | lanej/w2a 6a1474b, lanej/w2b c2452b1, lanej/w2c 364cbae | merged (push 2) |
| Lane J Step 3 (P9 checks) | lanej/s3 2490974 | merged (push 2) |

| fix/ic-live-test-1123 | e40a5ad | merged (push 3) |
| fix/screen-findings-1126 (Lane R, newest) | ecb3655 | merged (push 3) |
| feat/nb-plan-alerts-1126 (Lane P second push: 0056, P7, P8, LP-4, alert titles) | a59f7a9 | merged (push 3) |
| fix/suite-findings-1126 (Lane U, includes test/screen-suite-1126) | b81970b | merged (push 3) |
| feat/nb-real-pnl-1126 (Lane S, Real P&L total) | d344d82 | merged (push 3) |

Screen inventory (Lane U's guard `frontend/tests/screen-inventory-guard.test.js`): the merged code had 7 controls with
no row and 3 stale rows; rows updated (SHARED-21 paper-not-live-ack, BUILD-05, BUILD-52, BUILD-55/57/60 plan rupee and
time fields, ALERT-01 now the alert answer buttons; "Compare approaches" is gone). The IDs are positional, so later
rows were renumbered; e2e test titles that quote old BUILD numbers are now stale text (no test reads them).
Push 3 merge notes: alert titles were built on both lines; ONE function now (`backend/ofo_app/alert_title.py`, Lane
P's rule: the nearest open-leg expiry; a failed read leaves that row "(#id)"), W2-A's duplicate templates removed.
StrategyBuilderPage: Lane R's props and Lane U's undo-text both kept; PaperStrategies: W2-B's exit-closed watch and
Lane U's closeByPage both kept. Template pins merged by key.
Push 4: Lane P's Wave 2 page steps P7 (side-closed answers) and P8 (Reset to playbook) and ADR-330 (31) with
migration 0057 (Lane J builders; 0057 Tier A review SHIP). Not built: the P7 "Not applicable: the <side> side is
closed" rule line (needs a new plan-watch / adjustment-check field and a new sentence).

Full app (DB) suite, run as CI runs it (GITHUB_ACTIONS=true, per-file database clones) on 8ba68be: 7468 passed,
1 failed, 6 skipped (environment: trial ended, replay URL, catalogue index row, owner migration URL). The failure
(tests_app/test_d38_page_counts.py golden) was Lane P's and passes on push 3. Playwright CI job: 269 passed; the
positions ADR-138 (2) cases fail the same way on the screens line 7bf64eb (pre-existing); health.spec failed only on
the merged tree (fixed in push 4); strategy-live AC-4 and navigation menu cases are flaky (pass on reruns, also fail on
the parents). Not run: execute-screen e2e (needs a database named exactly ofo_test).

## Step 2 and Step 3: what was built (status: Fixed, not tested)

| Item | Spec | What it does | Proof |
|---|---|---|---|
| W2-A fired stop through the one alert module | ADR-330 (3)(b), (6), (19)(b); one-module instruction | `paper_monitor._fire` raises `actionable_alerts.inform('stop_fired', ...)` in the exit's own transaction (no more `paper_alerts` write); the message carries "If this stop fires, max loss becomes Rs X (now Rs Y)." priced at the recorded fill (see LJ-1); a failing line never stops the exit or the record; the pop-up reads `GET /alerts/answered?after=<id>` once per new row, never on first load, never on the bell; alert titles "Name (#id, d Mon)" from one function `alert_title.py` | guard `test_actionable_alert_one_module` red with the old exemption removed, green after; mutation (add_alert back) red; `test_stop_fired_message` 14, `test_paper_monitor` 23, `test_actionable_alerts` 35, `test_alert_routes` 4, `header-stop-fired-popup` 4 |
| W2-B Alerts Exit through the one exit door | ADR-330 (3), (12) | "Exit the position" stores the answer then opens the same exit confirmation as Positions on the Alerts page; Cancel exits nothing; a failed answer opens nothing | `alerts-exit-door-w2b` 6 failed on the old code, 21 pass with `alerts-actionable` |
| W2-B leg-stop risk line before Save | ADR-330 (6) | the Stops panel reads `leg-stop-risk` 400 ms after typing; prints the server's line only on "yes"; out-of-order or stale answers dropped; Save never blocked | `paper-stops-leg-risk-w2b` 7 failed on the old code, 10 pass |
| W2-C Plan watch box | ADR-330 (11), (13) | one reader `lib/planWatch.js`, one component `PlanWatch.vue`, on the builder beside the live P&L and on each open Positions paper row; a failed read shows no old figure; paused rows a dash and the reason | `plan-watch-*` 23 pass |
| Paper total line | ADR-330 (15) | already printed on the screens line (Lane Q2): "Includes N closed strategies." | (existing tests) |
| Step 3 stand-alone checks | ADR-330 (12) | `ofo/checks/` index_level, leg_price, pnl_amount, pnl_percent, time_of_day answer Met / NotMet / NotComputable; `stops.crossed` and the playbook percent rule call them; guard `tests/test_checks_no_side_effects.py` | `test_paper_monitor` 23 unmodified; checks 38; mutation (equality made NotMet) 4 failed |

Tier A reviews (independent, Opus): Step 2 round 1 FIX (MAJOR: the alert's max-loss line priced at the stop level
understated a gapped fill, stop 140.70 filled 180.00: Rs 12,005.50 shown, Rs 14,560.00 true) -> fixed, gap test red on
the old pricing and green now; seven MINORs listed below. Step 3: SHIP, three MINORs listed below.

### Merge 1: fix/ic-live-test-1123

| File | Conflict | Resolution |
|---|---|---|
| docs/process/coverage-stages.yaml | both added issue rows | union: the base's rows kept (ADR-327 to ADR-329), #742 and #743 added |
| docs/process/coverage-register.md | generated | regenerated (`coverage.py . --write --no-gh`; `--check` OK) |

### Merge 2: feat/nb-plan-alerts-1126

20 files were changed on both lines since they parted (e01f747); 17 merged without a text conflict. Three conflicts:

| File | Conflict | Resolution |
|---|---|---|
| backend/ofo_app/paper_settlement.py | both added a module constant (`_MIDDAY`, `_ZERO`) | both kept |
| tests/orchestrator/test_select_app_tests.py | both added app-test selection pins | both sides' pins kept |
| tests_app/test_order_closure_all_routes.py | both added route edges and the count line | both edge sets kept (level_watch, monitoring_pause, alerts, plan_watch); `PINNED_EDGE_COUNT` = 37 at the fork + 4 + 4 = 45 |

Generated files after the merge: spec digest, coverage register, `docs/api/openapi.json`
(`generate_openapi.py` output byte-identical), `tests_app/reply_inventory.py` (`--check` exit 0, notes unchanged): all
current, none hand-edited.

### Breaks the merge caused (each line passed its own gates; the merged tree did not)

| Gate | What failed | Fix |
|---|---|---|
| ruff ratchet | PLR2004 559 -> 560: each line added one magic number and removed another | `tests_app/test_paper_totals_closed.py` names its expected count |
| G2 `tests/test_paper_orders_one_door.py` (one exit door) | Lane P's `paper_leg_stop_risk` flipped BUY/SELL itself (`routes/paper.py:1523`) | the close's side and quantity come from `open_legs_to_close`, the door's own rule; `test_leg_stop_risk` passes |
| G4 `tests/test_alert_writers_one_caller.py` (one caller per alert writer) | still pinned `open_suggestion` / `record_held` to `background.py`; Lane P moved both into `actionable_alerts.py` | G4's homes follow the move (the plan: "guard G4 replaced (Phase 8)"); Lane P's one-module guard keeps every other caller out |
| ADR-008 second layer `frontend/tests/strategy-table.test.js` | W2-A's pop-up reader used `Math.max` / `.reduce` (for an id) in `lib/paperAlerts.js` | a plain loop |
| `tests_app/test_error_boundary_scan.py` | `str()` inside the leg-stop-risk route's return (a dict key) | the open quantity read before the return |
| `tests/test_bundle_secret_scan.py` | W2-C's prop `refreshToken` in the built bundle reads as a credential name | renamed `readTick` |

## Push log

| Push | Head | Contents | Gate |
|---|---|---|---|
| 1 | 7231916 | Step 1 (the two merges and the three breaks above) | `prepush.py --full` TOTAL PASS 2023.6 s (domain, app, vitest, lint, coverage, alembic guard) |

| 2 | 7d81d0a | ic docs 3d66541, Lane R ce5316e, Step 2, Step 3, the review fix | `prepush.py --full` TOTAL PASS 2137 s |
| 3 | 3d7aaf7 | ic docs e40a5ad, Lane R ecb3655, Lane P a59f7a9 (0056), Lane U b81970b, Lane S d344d82 | `prepush.py --full` TOTAL PASS 2460 s |
| 4+5 | 9f769b5 | P7 page answers, P8 Reset button, ADR-330 (31) with 0057, health e2e fix, side-closed templates; Not-applicable plan line, S-11 hold, Lane R 71ed990, Lane U 63091d7 | `prepush.py --full` TOTAL PASS 2195 s |
| 6 | ae01cc6 | section (a) corrected from the PC rehearsal; owner question LJ-2 | `prepush.py --full` TOTAL PASS 2067 s |
| 7 | (see push 8 row) | Lane U d9de498, Lane D 91cc43b, three full-suite test fixes, #753 parked | `prepush.py --full` |
| 8 | (in push 9) | Lane U final 12e04b9 (Change expiry, ADR-330 (42)), Lane R a2b44dd (banner ADR-330 (36), (38) hover, N-30, D-15 label, (39) index age rule, D-27 PC step; its checks are in RESULTS-lane-r.md) | - |
| 9 | 1eb5097 | the rehearsal-corrected section (a), Lane D final 491df12 (with Lane U 12e04b9 and Lane R a2b44dd from push 8) | `prepush.py --full` TOTAL PASS 2025 s; full DB suite 7638 passed, 0 failed |
| 10 | (this push, FINAL for 27 Nov) | docs only: this status and the DB result line | see the commit's gate |

Coordinator message for push 1 could not be sent: the session-message service refused this session (untrusted
device); recorded here instead.

## To file as deferred issues (the coordinator files them; Lane J files none)

| Title | Evidence | Spec basis | Done when |
|---|---|---|---|
| A fired stop never executes while the monitor clock is ahead of the database clock | Tier A review: 0054's insert guard `shown_at > clock_timestamp()` (`alembic/versions/0054_actionable_alert_answers.py:92`) refuses the stop_fired row; with `Market(at=2026-11-27 04:30 UTC)` the fire rolled back every tick: fires 0, failures 1, stops 0. The old paper_alerts write had no such check. | ADR-330 (3)(b); ADR-016 (submitted is not executed) | a fire whose record time is ahead of the DB clock still exits once and records once (test with a skewed clock) |
| The fired-stop line is judged on the book read before the strategy lock | `paper_monitor.py:218-220,245`: a lot added between the look and the lock is exited by the door but the line is for the smaller quantity | ADR-330 (6); ADR-008 | the line is computed from the book the door returned (`done.book` before the exit) |
| Old and new fired stops sit in two History lists | `routes/paper.py:2006-2016`, `paperAlerts.js:100` still say /paper/alerts/records holds every fired stop; new ones land only in /alerts/answered; each shows once but not in one time order | ADR-330 (3)(b) | History lists every fired stop in one time order; the comments say where each lives |
| An alert title is computed when read, not kept from when it fired | `alert_title.py:43-52`: a rolled-then-closed trade shows "(#172)" although it fired as "(#172, 8 Dec)"; a strategy without a paper book never gets an expiry | ADR-330 (19)(b) | the title is stored with the row at fire time (or the docstring stops promising it) |
| A plan POST on an EXISTING plan stamps and replaces its body | `SaveDraftBar.vue:481` opens the sheet with edit=false; `routes/adjustment_plan.py` POST path (`_write` edit False) accepts and replaces the body whatever exists | ADR-330 (45) | the sheet opened from the save bar for a strategy that already has a plan sends PUT (edit=true) |
| Header poll reads the whole history until the first stop fires | `paperAlerts.js:23-36`, `routes/alerts.py:197-198`: stopSeen 0 means every poll reads all of History plus one book load per strategy | none: speed only | the first read asks for the newest id only |
| Exit from two alerts of one strategy can offer the same legs twice | `AlertsPage.vue:57-58`: busy is released before the door opens; a second alert's Exit during the first POST offers the same legs; a second Confirm posts a second exit (needs two Confirms) | ADR-330 (3), (12); ADR-019 | the Alerts page holds one open exit per strategy until the first answers |
| A list refresh closes the Alerts page's exit dialog without a word | `PaperStrategies.vue:387,390` in exitOnlyFor mode | ADR-330 (3) | a cancelled dialog says why |
| test_settings_reader_guard pins a source line number | `tests/test_settings_reader_guard.py:109`; W2-A padded `paper_monitor.py` with a comment to keep read_snapshot at line 68 (fails closed: removing the comment turns the guard red) | none (test hygiene) | the guard finds the function by name, not by line |
| A playbook comparison word other than le/ge reads "checked, not met" | Step 3 review: `playbook_eval.py:512` `_exact` turns NotComputable into fired=False; the save check (`playbook_store.py:497-515`) never validates cmp; shipped playbooks are clean | ADR-330 (12); ADR-003 | an unknown cmp is refused on save, or shown "not checked" |
| The checks guard restricts only calls of crossed | `tests/test_checks_no_side_effects.py:74-78`: a direct leg_price/index_level call in ofo_app (skipping the live-price check of stops.py:58), `import crossed as _c`, a `lambda conn:` pass | ADR-330 (12) | each of the three samples turns the guard red |
| The P7 plan rule line "Not applicable: the <side> side is closed" is not shown | `side_scope.rule_notes` is wired into no route and the sentence is not in the catalogue (Lane J P7 builder) | ADR-330 (2)(a) | the plan watch and the plan sheet print that line for each rule of the closed side |
| The inbox heading of a side_closed row reads "Adjustment opportunity detected" | Lane P open finding (routes/adjustment_opportunities.py group label) | ADR-330 (2)(b), (3) | the inbox names the side that closed |

## Full app (DB) suite on the head (Lane G's gap: the gate does not run tests_app with a database)

Run as CI's "Run app tests" step (GITHUB_ACTIONS=true, per-file database clones, -m "not full_chain"):
- 9f769b5 (push 4+5): `3 failed, 7579 passed, 5 skipped, 23 deselected in 2970.93s`. The three, each failing alone too:
  `tests_app/test_d38_page_counts.py::test_plan_counts_and_reply` (Lane J P8 9e04198c added the reset labels without
  regenerating golden_d38/plan.json), `tests_app/test_paper_totals.py::test_d36_the_list_does_fixed_database_work_and_finished_books_cost_only_cheap_arithmetic`
  (Lane U 7397330f added shown_date to the paper list: 2 fixed statements, budget 6 -> 8 with the reason beside it,
  still independent of the number of strategies), `tests_app/test_strategy_followups.py::test_the_api_answers_not_found_to_a_put_on_another_users_strategy_and_stores_nothing`
  (Lane U 9972cae7, ADR-330 (37): GET of a missing strategy answers STRATEGY_VALIDATION_523; the test now expects that
  for GET and USER_INPUT_003 for PUT). All three: test expectations behind a deliberate change, no code change; fixed
  in this push (b150d5e). Skips (5): trial ENDED (ADR-039), EXECUTE_REPLAY_URL unset, no INDEX row in the test
  catalogue, and two environment-only.
- 1eb5097 (final code head): `7638 passed, 5 skipped, 23 deselected, 1 xfailed in 2917.28s`, 0 failed.

Merge notes, push 7: Lane U d9de498 (displayFormat.js: Lane J's istHm kept; Lane U's removal of localDay kept; REQ-070:
Lane J's ADR-330 (31) criterion stays AC-8, Lane U's toast criterion becomes AC-9); Lane D 91cc43b (#739 fixed twice:
Lane U shows the server's count of days left, Lane D an India-day count in the browser; REQ-135 AC-2 says the server
computes it, so Lane U's stays and Lane D's localDay and its tests are dropped; template pins merged by key). Full
vitest on the push-7 tree: 280 files, 3152 tests passed.

## #753 (0058): built on feat/0058-plan-acceptance-1127, not yet joined to this branch (0058 is applied only when the coordinator joins it)

Built on side branch `lanej/753` (head 8b00ed77, not pushed), two rounds, both Tier A reviews (Opus) FIX:
- Round 1 (stamp only on a playbook switch): Reset to playbook and accepting the same playbook stopped being a new
  acceptance (a strategy-82-shaped plan kept only the % of max loss stop after Reset); a sheet edit that points an old
  plan with no playbook at the active one still stamped.
- Round 2 (stamp only on an explicit acceptance, a transaction-local signal from accept/Reset): Reset stamps, but a
  playbook switch made from the plan sheet is a PUT and no longer stamps (the page sends POST only for a new plan), so
  that switch would also leave fewer stops; plus a pre-existing defect: a sheet edit of an old plan with no playbook
  replaces its whole body (routes/adjustment_plan.py:792), losing its own stops.
What is left: the owner's answer to LJ-2 (what counts as a new acceptance), then a signal that the page's switch and
Reset send and an edit does not (the route cannot tell a switch from an edit today: PUT carries both), the round-2
review's minors (an error inside the accept path is hidden by the finally at playbook_store.py:746; the source-scan
test is a weak pin), and the deploy order rule (a code rollback must also downgrade 0058).
Today's behaviour on the branch is unchanged from 0041 (every body edit restamps accepted_at): #753 stays open.

Round 3 (owner decided LJ-2 option 1; branch feat/0058-plan-acceptance-1127): the plan sheet sends `accept: true` on
PUT only when the user picked a playbook in its selector or pressed "Use playbook as is"; POST and Reset always
accept; a level edit never carries it. An edit of an old plan with no playbook now keeps the plan's own body (its own
margin stop "4" and T-16), so R1/R2-MAJOR-2 is fixed in the same route (`_body_to_save`), not deferred. Known leftover:
"Use playbook as is" from the sheet on a plan that already follows that playbook now copies the playbook's body (as
POST does) instead of keeping the plan's customisations; this is what "as is" says. No deferred issue is needed.
| A plan sheet opened while another tab switched the plan's playbook gets "playbook_id is not valid. Correct that value" on Save | 0058 final review (Opus, 27 Nov): routes/adjustment_plan.py PUT refuses a different stored playbook without accept (nothing written); the words read as a typing error | ADR-330 (45); ADR-003 | the refusal says the plan changed elsewhere and offers to reload |
| PreferencesTab cannot edit a plan with no playbook | 0058 final review: it sends playbook_id null and gets 422, nothing written; unchanged since 206a9f06 | ADR-330 (45); ADR-250 | an edit from PreferencesTab of a no-playbook plan saves, keeps its own stops, and stamps nothing |

## Lines waiting for a person's approval (none written by Lane J)

- Catalogue wordings pinned "pending owner read": `stop_fired_note`, `stop_fired_note_with_line`, `alert_title_unnamed`
  (W2-A); `alert_side_closed_text` (now also names the shape that remains), `plan_sheet_reset`, `plan_sheet_reset_confirm` and
  the `labels:plan_sheet` pin (P7/P8); `change_deleted` "Deleted", `change_undeleted` "Restored" (ADR-330 (31)).
- REQ-070 AC-8 text (ADR-330 (31)); the 0057 downgrade refusal rule.
- Owner question LJ-1: answered (ADR-330 (41), the recorded fill, as built).
- Owner question LJ-2 (#753): open; 0058 parked.
