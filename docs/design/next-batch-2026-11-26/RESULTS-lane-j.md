# Lane J results (26-27 Nov 2026): the join of the screens line and the alerts-and-plans line

Branch `integration/nb-1126`, cut from `origin/fix/screen-findings-1126` (7bf64eb). Pushed only there; no PR.
Standing-direction step: step 4 (the journey for iron condor), owner-directed batch of 26 Nov (ADR-330; freeze lifted
for these items by the owner on 26 Nov, see RESULTS-lane-p.md). Highest status claimed for anything here:
**Fixed, not tested** (the owner tests on his PC in market hours, 27 Nov 09:15 IST).

Spec basis: ADR-330 (1) to (27) and its one-module instruction; ADR-002; ADR-003; ADR-008; ADR-016 to ADR-019.

## SAFE TO CLOSE (Lane J, 27 Nov about 18:40 IST)

**STATUS: SAFE TO CLOSE. Head: the head of `hotfix/loss-stop-1127` on origin (this commit; code as reviewed at 0dcfc33e, ADR-330 (47) included, gate passed on 596c6562). The PC: restart the API and the worker supervisor; no frontend rebuild; no migration. What is left goes to Lane J2 (list below).**

**Stream S1, for round 1 (coordinator about 17:15 IST): what the PC can run.**
- (b) Proving it with the market closed, without building a second tool: Lane Q2's branch `test/live-day-gaps-1127`
  adds tests only (`tests/adjustment/test_plan_stop_to_alert_chain.py`, five guard kinds), not a replay command. The
  repo's own dev/test path is scenario mode, which drives the API and the SEPARATE worker process: set `APP_ENV=development`
  and `OFO_SCENARIO=PATH-<nn>` for both processes (`backend/ofo_app/scenario_mode.py`), seed the trade with
  `python scripts/orchestrator/dev_run.py <checkout> python scripts/seed_scenario.py PATH-<nn>` (ofo_dev only; it
  refuses any other database), save a plan with a Stop (Rs) on "Scenario PATH-<nn>", then move the market frame by frame
  with `POST /api/scenario/frame` (the worker reads the shared frame index before every cycle, `background.py:957`).
  A frame past the stop must give one alert row within a minute (or at entry + 5 minutes when the stop was already
  crossed at entry). Not proven end to end here: I did not run this chain with a plan stop on a path scenario; whether
  a PATH fixture reaches a given rupee level must be read from its frames (`tests/fixtures/adjust_paths/`). If none
  does, that is the one small item for Lane J2 (a path frame past a typed stop), not a new tool.
- (c) Market-closed PC steps (round 1, about 01:00): pull the joined build; restart the API and the worker
  supervisor (no frontend rebuild for this branch, no migration); run the scenario steps above for: a rupee stop, a %
  stop (T-06), a profit target (T-07 and rupee), the time exit, a stop already crossed when the plan is saved; for each,
  the read-only check `SELECT rule_id, shown_at AT TIME ZONE 'Asia/Kolkata' FROM public.adjustment_suggestions g JOIN
  public.strategies s ON s.id = g.strategy_id WHERE s.name = 'Scenario PATH-<nn>' ORDER BY shown_at;` and the worker log
  line `background: strategy <id> check skipped: <reason>` if no row appears.
- Monday steps (market open): T1-05 (rupee and %), T1-06 (a stop already crossed when the plan is accepted: alert at
  entry + 5 minutes), T1-07, T1-08, a profit target and the time exit on a fresh trade, a stop crossed before 09:30 on a
  weekly trade, and a trade with 4+ alerts that day; each with the SQL above on the real strategy name.
- Not on this branch, for Lane J2 (S1 items in your 17:15 list that are not built here): the visible "not being
  watched" state for a trade the worker cannot price (the worker now logs the reason; the screen state and the one
  alert need a spec row), closing the last leg closes its alerts (T1-09), the monitor clock ahead of the database
  clock, the three review MINORs above, and the Plan watch spot step after a cut (needs Lane U's `index_spot_of`).

**ADR-330 (47) built (owner 16:25 IST; commits ceaa1e2f to 0dcfc33e; fixed, not tested).** Every plan exit (loss stop %
and rupee, 2x-credit stop, profit target % and rupee, time exit T-10b, and any plan rule naming one of their triggers)
alerts on the first check past its level or time: no candle-close wait, no quiet-time hold, no daily cap, no pause
skip; one set `stop_lines.PLAN_EXIT_RULES` / `plan_exit_rule_ids(body)` read by the gate, the cap and the restart count.
Adjustment rules keep candle, quiet time and cap. The 5-minute period after entry (`alert_gate.entry_period_end`,
entry + the pop-up quiet period): an exit already past its level at entry, never read clear, raises nothing until entry
+ 5 minutes, then raises once if still past; never swallowed (a restart inside the period re-delays it; a level read
clear after entry and crossed again alerts at once). #207 shape: accepted 13:13:33, crossed from 13:14: one alert at
13:18:44. This changes the 13:03-15:27 pushes, which raised a stop at the first check inside the 5 minutes. Tests:
`tests/adjustment/test_plan_exits_adr330.py` (41 of 64 failed before the build), domain 1250 passed; existing tests
that used T-07 as the example capped or candle-close rule now use T-14. ADR row: the coordinator writes ADR-330 (47).
Tier A review (Opus): SHIP (an exit crossed at entry was delayed and then raised in every run, never swallowed, also with
the worker paused when the period ends; T-07, rupee profit and T-10b open once per crossing, no flood; restart count and
live gate read one set; 6 of 6 mutants killed). To file as deferred issues (MINOR): the "seen clear" mark lives only in
memory, so after a restart or a plan change a crossed-clear-crossed exit is delayed again up to 5 minutes after entry
(`alert_gate.py` `_Rule.clear_seen`; the stored `adjustment_rule_state` could seed it); a restored open exit record gives
no escalation until the period ends; a user rule mixing an adjustment trigger with T-07 (any_of) lets the adjustment
trigger skip the candle, quiet time and cap (no system playbook has such a rule).

**ADR-330 (58) (paper and real, one path): no paper-only path found** in the worker's alert path:
`background.py:1930-1990` `owner_lister` lists every strategy of the owner (open paper legs, or real Zerodha trades and
adopted holdings, ADR-276); its only filter `listable(scenario_id, mode)` separates scenario strategies from real ones,
not paper from real; `adjustment_readers.py:155-175` builds the tracked book for real books too; `alert_gate.py` and
`actionable_alerts.py` have no paper reference. Data gaps, not exemptions: a real-book trade has no adjustment count
and no paid charges ("not checked", ADR-276 (4)), so T-18 and charge-based rules are not checked for it.

**Push times:** `origin/hotfix/loss-stop-1127` moved 13:03 (57d9ff49) -> about 13:35 (e231a5c5) -> about 15:28 IST
(303460ba, the stop-gaps fix) -> this push. If your copy shows 13:03, `git fetch origin`.

**Your 14:53 message (raw Plan watch answers), read against the code:**
- #207 (stop line FIRED in Plan watch, no alert row): the Plan watch route evaluates afresh, while the worker evaluates
  with the stored rule memory. A stored `held_at_entry = t, seen_clear = f` row made the worker's evaluation answer
  "already true" every minute (`playbook_eval.py:1203`), so the gate got no reading. The route has no such memory, so it
  says FIRED. This head ignores that memory for loss stops (dabcc8ce), and a test replays #207's restart
  (`test_207_restart_at_13_33_30_opens_the_stop_at_the_first_live_check`).
- #209 (all 16 lines NOT_COMPUTABLE, "spot not available", USER_INPUT_151) is the Plan watch ROUTE's answer, from the
  API process. The likely cause there is the route's 4 s price budget: a cut market read is answered as the
  not-connected market, so the spot is not available (`routes/plan_watch.py` `_budgeted`; the API log's 54 "market read
  over 4.0 s" lines). That is the API, not the worker. The worker reads its spot from the feed's ticks only
  (`background.py:323-341`, `feed_spot`); it never calls the REST quote, Lane U's door or the route budget (the
  merged-tree diff along its path is empty). So #209's route answer does not show that the worker could not read the
  spot. The worker's new skip line (`background: strategy 209 check skipped: prices_<state>`) will show it if it could
  not. If the PC sees that line for #209, the cause is in the worker's feed read, and I will hand it to Lane U.
- Still open, not on this branch: a plan with a stop whose check cannot compute raises no "your stop is not being
  checked" alert (as ADR-330 (44) does for paper exits). It needs a spec row and a build: for the next lane.

**Your 15:09 message (Lane U's spot RCA): what is on this branch and what is left.**
- (b) part 1, a strategy the worker cannot price is no longer silently paused: done on this branch. The worker logs
  `background: strategy <id> check skipped: <reason>` (reasons include `prices_STALE`, `prices_LEG_MISSING`,
  `not_ticked`, `no_gate_read`) once each time a strategy's skip reason changes (dabcc8ce, 3d16435e).
- (b) part 2, the one "your stop is not being checked" alert for a plan with a stop that cannot be priced (the
  ADR-330 (44) pattern): NOT built. It needs a spec row (the alert kind and its wording through the one alert module) and
  must sit on top of Lane U's worker REST read (eac36352). It is for the next lane.
- (a) the Plan watch budget must wrap only the market read and still resolve the spot after a cut, through Lane U's
  `index_spot_of` (its own about 2 s deadline): NOT built. It depends on `laneu/spot-either`, which is not on origin yet,
  so it goes on a branch cut from that branch once it is pushed (`routes/plan_watch.py` `_budgeted`, about 20 lines, plus
  the route test). It is for the next lane. Until then a cut market read answers the whole box as not computable.
- (c) #207 (the check says FIRED, no row): the cause in the code is the worker's stored at-entry memory
  (`held_at_entry = t, seen_clear = f`, `playbook_eval.py:1203`), which the route's fresh check does not have. Fixed on
  this branch (dabcc8ce: stored memory is ignored for loss stops), with the restart test. If the PC still sees no row
  for #207 after this pull, the new skip line names the reason.
- The stop-gaps fix (dabcc8ce, reviewed 14:00): on this branch since this push. The 14:50 push was delayed because the
  gate failed on a test placed in `tests/` that imports the app (moved to `tests_app/`, 2bc0947f), then on a test stub of
  `gate_readings.readings` without the new required `stops` argument (fixed in this commit).

**Head: the head of `hotfix/loss-stop-1127` on origin** (this commit). Code: 206a9f0 + the daily-cap exemption
(c040e73e) + the rupee stop fast path (468561e4) + the stop-gaps class fix (dabcc8ce, 415e98f4, 3d16435e). Fixed, not
tested. **The PC: pull; restart the worker supervisor and the API; no frontend rebuild; no migration.** Re-run T1-05
(rupee and %), T1-06 (#207 shape: a stop already crossed when the plan is accepted), T1-07, T1-08, and a stop crossed
before 09:30 on a weekly trade.

**#207, third cause (your 13:58 message): fixed, with the class.** A plan's loss stop (T-06, T-16, the 2x-credit stop,
the rupee stop, and any rule whose triggers include T-06 or T-16, whatever its id) is now never held by: the quiet time
after the open; a price pause inside a candle (it skipped the stop fast path for the rest of that candle,
`alert_gate.py:396`, leaving no row and no log); or the at-entry rule memory (`adjustment_rule_state.held_at_entry`: a
stored row made the stop answer "already true" on every check after every restart, `playbook_eval.py:1203`; stored rows
are now ignored for stops). The time exit T-10b was already never held at entry. A worker restart no longer swallows a
live crossing (test `test_207_restart_at_13_33_30_opens_the_stop_at_the_first_live_check`: opens at 13:33:44). The worker
logs `background: strategy <id> check skipped: <reason>` when a strategy's skip reason changes. A stop is never judged on
a stale price (the gate gets readings only after a fresh read). Decision: ADR-267 amendment 3 (your 13:38 ruling).
Tests: 1197 domain tests passed; the new tests fail on e231a5c5 (25 of 29); Tier A review (Opus): the gate change is
correct, 6 of 7 mutants killed; its one MAJOR (skip-log volume: one INFO line per second) fixed in round 2 (3d16435e).
Not proven from the code: which of the three held #207 on the PC (no code path found that writes `held_at_entry = t`
for the rupee stop, so the paused candle is the likelier one); the new skip-log line will show it.

**Left for a fresh lane tonight:**
- 0058 plan acceptance: `feat/0058-plan-acceptance-1127` f963ab6 (pushed, final review SHIP, not merged).
- The 08:30 instrument list: `lanej/builder-open-0827` 4812a3f (pushed; two review MAJORs open: the 08:35 window
  hard-coded, a failed run waits an hour; do not pull today).
- The Plan watch box (Lane R now) and route speed (after Lane U's door); Lane J's unpushed box fix 64ce1a50 on
  `lanej/pw-first-1127`.
- `routes/playbooks.py` test_playbook holds a connection across market reads (listed 10:16).
- To file as deferred issues: a mixed any_of rule with T-06/T-16 and an adjustment trigger has one record, so once it is
  open or dismissed on its adjustment member a later stop crossing inside it raises nothing (review finding,
  pre-existing); the worker's stops wiring has no worker-level test (review); no test pins the exact Rs 50.00 line in the
  rupee fast-path file; the rupee profit target, T-07 and T-10b still wait for the candle close (owner question: does
  REQ-170 AC-5's "conditional exit" include them?); exempt T-07 when the plan's Target is saved (owner question).
- Two reviewer scratch folders in this session's scratchpad (`mut`, `chk`) that a safety hook would not let me delete;
  the owner's to clear.

**Today's work by model (27 Nov, Lane J; owner rule 14:14: the task picks the model).** Departures marked.

| Task | Model that did it |
|---|---|
| Main session: split, route, verify, report, RESULTS text, git commits/pushes | Opus (this session) |
| Plan watch slowness, first build (6dc76aa5, later dropped for Lane U) | Sonnet |
| Plan watch page + route budget build, round 1 and round 2 | Sonnet |
| Plan watch Tier A reviews (two) | Opus (Tier A) |
| Repo scans / openapi checks helper | Sonnet (stopped early) |
| adjustment-history connection release build | Sonnet |
| Plan watch box first-read RCA + fix (64ce1a50) | Opus: DEPARTURE (building; routed as "hard debugging"; should have been Sonnet) |
| Plan watch route profiling (stopped, out of scope) | Opus: DEPARTURE (same) |
| #200 loss stop RCA + daily-cap fix | Opus: DEPARTURE (building/RCA; should have been Sonnet) |
| #200 cap fix Tier A review | Opus (Tier A) |
| #202 rupee stop fast path RCA + fix | Opus: DEPARTURE (same) |
| #202 fix Tier A review | Opus (Tier A) |
| Merged-tree alert path check (#207) | Opus: DEPARTURE (investigation; should have been Sonnet) |
| Stop gaps class fix + #207 restart tests | Opus: DEPARTURE (same) |
| Stop gaps Tier A review | Opus (Tier A) |
| Pre-push gates (prepush.py --full), eight runs | Opus main session ran them as background commands: DEPARTURE (gate runs go to a Sonnet helper) |

## Hotfix status for the coordinator: `hotfix/loss-stop-1127` (27 Nov, T1-05 FAIL: the Rs 100 loss stop of A-D #200 raised no alert)

**Latest (13:55 IST), your 13:33/13:42 questions on A-G #207: answer so far; the fix for the remaining gaps is being built on
this branch (ETA about 15:00 with review and gate).**
- Did today's pulls stop the worker's alerts? **No.** On the PC's merged tree (206a9f0 + plan-watch-1127 1b576947 +
  index-quote-1127 b8297a96 + api-blocking-1127 8fe19979 + plan-watch-load-1127 ffb63f66 + maxloss-line-1127 9d758f0d)
  the diff along the worker's alert path is empty (`git diff 206a9f06..merged` over ofo/adjustment, ofo/alerts,
  background.py, actionable_alerts.py, adjustment_check.py, settings_in_force.py, adjustment_readers.py, db_gate.py,
  playbook_store.py, spot_source.py: nothing). The worker never calls run_check, the REST index quote, Lane U's door,
  the plan-watch budget or Lane R's connection release; its only market input is the feed's ticks (background.py:426).
  Alert and worker tests on the merged tree: 1126 domain passed; 145 worker DB tests passed (140 on 206a9f0; +5 new).
- #207's stop is the rupee stop, not T-06: `loss_stop_rupees` "80" switches the T-06 lines off
  (settings_in_force.py:443-444), and before 57d9ff49 the rupee stop waited for the candle close (cause 2 above); on a
  steady Rs 199 loss on fresh, unpaused checks the old code would still have opened it at the 13:15 close (test
  `tests/adjustment/test_stop_207_minute_cycle.py`, merged tree). So a further hold applies to #207. Two can swallow a
  stop silently, and both are being fixed now:
  (a) **a price pause in a candle blocks the stop fast path**: `alert_gate.py:396` returns before the fast path at :405,
      and the pause drops the running candle; a probe pausing every 2 minutes gave no rupee alert at all; a pause is not
      logged per check (background.py:1327, :1371), only counted in the minute line's `reads`;
  (b) **the at-entry hold**: a rule already true when the plan is accepted (`AlreadyTrue`, playbook_eval.py:1203) gives
      no reading until it has been seen clear; #207's loss was past the stop from about 13:14, 30 s after the 13:13:33
      accept, so its stop may never fire (probe: no alert for 17 minutes).
  The daily cap does not apply to #207 (zero rows; the cap counts per strategy). Quiet time and the mixed-rule gap do not
  apply to #207 either (being fixed in the same class fix).
- Please run on the PC (read-only) to tell (a) from (b) for #207:
  `SELECT r.adjustment_no, r.rule_id, r.held_at_entry, r.seen_clear FROM public.adjustment_rule_state r JOIN public.strategies s ON s.id = r.strategy_id WHERE s.name ILIKE '%#207%' ORDER BY 1, 2;`
  (`held_at_entry = t, seen_clear = f` on `plan.rupee_loss` = (b)), and the worker's `background: minute` lines from
  13:10 to 13:30: the `reads` counts (STALE, LEG_MISSING, DISCONNECTED, NOT_TICKED = pauses, (a)) and the `outcomes`
  counts (`already_true` = (b)).

**Latest (12:50 IST, the coordinator's 12:22 case A-E #202, Stop Rs 50, 0 alert rows): second cause found and fixed
(468561e4, a32d8101); fixed, not tested.** RCA: `stop_lines.py:114` `is_stop_rule` covered only T-06, T-16 and the
2x-credit stop, so at `alert_gate.py:405` the plan's rupee loss stop (`plan.rupee_loss`, the plan's one loss stop when a
rupee level is typed, ADR-330 (5)(a)) skipped the stop fast path: it waited for the alert style's candle close and had to
be past its line on the last check of that candle (breaks REQ-170 AC-5, "risk exits are not delayed"). A-A2's Rs 1 stop
raised its row exactly at the 10:00 close. Test with #202's exact plan and prices (`tests/adjustment/test_rupee_stop_immediate.py`,
15 tests): before the fix the alert opened only at the candle close (12:15:00 weekly), and with the loss dipping under
Rs 50 on each candle's last check it never opened from 12:13:44 to 12:30:44; after the fix it opens at 12:13:44 at
Rs 85.75 on every style, once. Fix: one set `stop_lines.LOSS_STOP_RULES` (the % stops plus the rupee loss stop) read by
the gate and the evaluator. The rupee stop does reach the one alert module (kind `plan_rupee_loss`), and the loss is
compared before charges, at or past the level.
Tier A review (Opus) of 468561e4: SHIP (real evaluator readings: a loss of Rs 50.00 or more opens on the first check, Rs 49.99,
zero or any profit does not; the rupee stop's event runs equal T-06's in 7 scenarios on all three styles: one open,
no repeat, same lapse, re-arm and cooldown; opens with the daily cap used up; 1155 domain tests passed; 4 of 6 mutants
killed by the new file, one more by the suite). Pushed with the full gate: `prepush.py --full` TOTAL PASS 2009.7 s on 57d9ff49.
To file as deferred issues (from the review): the style's quiet time after the open (weekly to 09:30, monthly to
09:45) holds every loss stop, T-06 and the rupee stop alike (`alert_gate.py:334`), against REQ-170 AC-5: an owner
decision; no test pins the exact Rs 50.00 line in the new file (the wider suite does).
Plan watch box rendering (T2-01/T2-02) is now Lane R's (coordinator 12:55): Lane J's unpushed finding for them, branch
`lanej/pw-first-1127` 64ce1a50: the page gave up at the app-wide 10 s request timeout (`lib/planWatch.js` had no
per-read timeout) while the route answered in 8 s plus browser queue time; that commit gives this read 20 s and shows
"Reading the plan watch..." while a read is in flight.
Not fully explained by code alone: if #202's loss stayed past Rs 50 from 12:13:44 to 12:18, the old code would still
have opened at the 12:15 close. Please run on the PC (read-only) and send the result:

```sql
BEGIN READ ONLY;
SELECT h.id, h.rule_id, h.trigger_id, h.stage, h.value, h.threshold, h.reason, h.held_at AT TIME ZONE 'Asia/Kolkata' AS held_ist
FROM public.adjustment_held_crossings h JOIN public.strategies s ON s.id = h.strategy_id WHERE s.name = 'A-E #202' ORDER BY h.id;
SELECT r.adjustment_no, r.rule_id, r.held_at_entry, r.seen_clear
FROM public.adjustment_rule_state r JOIN public.strategies s ON s.id = r.strategy_id WHERE s.name = 'A-E #202' ORDER BY 1, 2;
SELECT g.id, g.rule_id, g.trigger_id, g.value, g.threshold
FROM public.adjustment_suggestions g JOIN public.strategies s ON s.id = g.strategy_id WHERE s.name = 'A-E #202' ORDER BY g.id;
ROLLBACK;
```
and the worker log for #202 between 12:10 and 12:20 ("writing the alert events of strategy", "has no alert preset",
pause or CHECK_FAILED lines), and #202's pinned alert style.
Class (REQ-170 AC-5), each plan guard and stop/exit rule: T-06, T-16, the 2x-credit stop and now the rupee loss stop act
on the first check past their line; the rupee profit target, T-07 and the T-10b time exit stay at the candle close
(owner question: does "conditional exit" in AC-5 include a profit target or a time exit?). Gaps listed, not changed
(each changes behaviour beyond this item): a stop during the style's quiet time is held; a candle that saw a pause takes
no sample, so a stop in it is dropped; T-06 inside a mixed (any/all) rule is judged at the candle close.

**Head: the branch head on origin** (cut from 206a9f0; only this fix: `backend/ofo/adjustment/cap_scope.py`, ADR-267
amendment 2, `tests/adjustment/test_plan_stop_cap.py` (new) and one changed example in
`tests_app/test_background_worker.py`). Independent of `hotfix/plan-watch-1127` and of Lane U's and Lane R's branches.
Highest status: Fixed, not tested.

**RCA:** the strategy's daily alert cap held the stop. `cap_scope.py` (before the fix) exempted only the user's level
watches and day rules. A-D #200 (weekly alert style, cap 4) had already raised T-03, T-14, T-01 and the T-10b time
exit, so when the rupee loss stop crossed (rule id `plan.rupee_loss`, value 162.5 against 100, from about 11:00) the
gate turned it into a held crossing with reason "daily limit" (`alert_gate.py:335`, table
`adjustment_held_crossings`), never an alert row. The 09:55 % stop passed because that trade's cap was not used up.
A rupee stop is recorded as `plan.rupee_loss`, not T-06 (T-06 is dropped while a rupee level is the stop), so "no
T-06 row" was expected; the row to look for is a held `plan.rupee_loss`.
Ruled out: a partial plan save (the plan's other rules fired), the "draft" body status and the stop stored as the
string "100" (the test with #200's exact body evaluates both), the sign (loss met when P&L <= -level,
`ofo/checks/pnl_amount.py:52`).

**Fix (class):** the plan's own stops and exits (T-06, T-16, the 2x-credit stop, the rupee loss stop and rupee
profit target, the T-10b time exit) are never held by the daily cap and do not count against it; `cap_exempt` is the
one rule both the gate and the worker's restart count read. Decision: ADR-267 amendment 2 (same delegation and reason
as ADR-267: the cap must never suppress the alert the user set). The % profit target T-07 stays capped.
Failing test first: `test_200_rupee_stop_opens_after_t03_t14_t01_and_the_time_exit` (Held instead of Opened before
the fix). Tier A review (Opus): SHIP (one path for hold and count; the exempt ids are exactly the ids the evaluator
emits for a #200-shaped body; still one alert per crossing, no flood over 5 hours of flipping; 8 of 8 mutants killed;
1140 domain tests passed).
Open from the review, not on this branch (to file as deferred issues):
- The rupee loss stop is judged only at the candle close; the % stops are judged on the first check past their line
  (`stop_lines.py:114-115` `is_stop_rule` lacks `plan.rupee_loss`; `alert_gate.py:405`, REQ-170 AC-5). When the rupee
  level is the plan's only stop its alert can wait up to one candle.
- A stored plan body may give a rule its own id (`playbook_store.py:523-533`); a T-06 renamed `my-stop` is still capped.
  No system playbook does this; it needs a body written through the API.
- No database test stores plan-exit rows and checks the worker's restart count leaves them out
  (`tests_app/test_alert_gate_storage.py:292-300`).
- Owner question: exempt T-07 (the % target) when the plan's Target is saved (ADR-267 amendment 2).

**The PC must:** pull; **restart the background worker supervisor and the API** (the gate runs in the worker);
**no frontend rebuild; no migration.**
**Confirm on the PC (read-only SQL):** `adjustment_held_crossings` for A-D #200 should hold a `plan.rupee_loss` row
with reason daily limit, value about 162.5, threshold 100, held about 11:00 to 11:05 (the query below). If there is no such row the cap is not the cause: tell me, the hunt reopens.
**Re-run:** T1-05 (a plan with a rupee stop on a strategy that already has its cap's worth of alerts that day).


#200 SQL (read-only):

```sql
-- read-only: A-D #200's plan, its alert rows and its held crossings, 27 Nov 2026 (IST)
BEGIN READ ONLY;
SELECT id, name, status, created_at FROM public.strategies WHERE name ILIKE '%A-D #200%' ORDER BY id;
SELECT p.strategy_id, p.playbook_id, p.accepted_at, p.body->>'status' AS body_status, p.body->'guards' AS guards,
       p.stop_base, (SELECT jsonb_agg(r->>'id') FROM jsonb_array_elements(p.body->'rules') r) AS rule_ids
FROM public.strategy_adjustment_plans p JOIN public.strategies s ON s.id = p.strategy_id
WHERE s.name ILIKE '%A-D #200%';
SELECT g.id, g.rule_id, g.trigger_id, g.kind, g.value, g.threshold, g.shown_at AT TIME ZONE 'Asia/Kolkata' AS shown_ist,
       g.outcome, g.worse
FROM public.adjustment_suggestions g JOIN public.strategies s ON s.id = g.strategy_id
WHERE s.name ILIKE '%A-D #200%' ORDER BY g.shown_at;
SELECT h.id, h.rule_id, h.trigger_id, h.value, h.threshold, h.reason, h.held_at AT TIME ZONE 'Asia/Kolkata' AS held_ist
FROM public.adjustment_held_crossings h JOIN public.strategies s ON s.id = h.strategy_id
WHERE s.name ILIKE '%A-D #200%' ORDER BY h.held_at;
-- today's rows on that strategy the cap counted (expect 4 before 11:05 if the cap held the stop)
SELECT count(*) FILTER (WHERE g.rule_id NOT LIKE 'watch.%' AND g.rule_id NOT LIKE 'day.%' AND g.rule_id NOT LIKE 'day:%')
FROM public.adjustment_suggestions g JOIN public.strategies s ON s.id = g.strategy_id
WHERE s.name ILIKE '%A-D #200%' AND (g.shown_at AT TIME ZONE 'Asia/Kolkata')::date = DATE '2026-11-27';
ROLLBACK;
```
## Hotfix status for the coordinator: `hotfix/plan-watch-1127` (27 Nov, Plan watch slowness)

**Head: the branch head on origin (code commits 6df734e7, b16715d1, 13c4293b, 48563be1, 6e3dc306; first pushed at 6067ca3a)** (cut from 206a9f0; only this fix: `routes/plan_watch.py`, `PlanWatch.vue`, `lib/planWatch.js`,
`routes/adjustment_history.py` and their test files). **Depends on Lane U's `hotfix/index-quote-1127`: merge Lane U's first.**
This branch has no index reader or cache of its own (coordinator split, 09:52 IST). Highest status: Fixed, not tested.

What it does:
- The Plan watch box reads at most once per 15 s (`PLAN_WATCH_MIN_READ_GAP_MS`, `lib/planWatch.js`), not on every
  5 s paper tick. The first read on open and on a strategy change is immediate. No new request goes out while one is
  unanswered (one catch-up read at most), and the timer stops when the box closes.
- While a read is slow and an earlier answer exists, the last rows stay with their as-of time, marked "Updating the
  numbers..." (REQ-119 AC-4). A failed read after a good one keeps the rows with "Could not refresh the rule check.
  Showing the last answer, as of the time shown." Only a first read with no answer shows the loading or
  not-available states.
- The route bounds its price reads (market, and the REST index quote) by one 4 s budget (`PRICE_BUDGET_S`). Past it,
  the read is cancelled and the answer is the existing "prices not live" one: lines paused or not checked, no `now`,
  no distance, nothing written. After a cut market read the REST quote is not asked at all. Without that, an instant
  (cached) REST answer would pair with the not-connected market and give HTTP 500 (Tier A MAJOR, fixed in round 2).
  The margin read after the price reads has its own 8 s timeout, so the worst case is about 12 s. It fails closed: the
  rows stay marked not current.
- No reply field, no migration, no openapi change.

**The PC must:** `git fetch origin` and check out the merged head; **restart the API**; **rebuild the frontend**
(`cd frontend && npm ci && npm run build`), because the box's read pacing is browser code. **No migration.** The worker
supervisor does not need a restart for this branch.

**Re-run on the PC (market hours):** test plan (docs/process/test-plan-2026-11-27.md) **T2-01** (Plan watch box on
the builder), **T2-02** (Plan watch on the Positions row) and **T2-16** (timing in market hours); Lane J rows L1 and L2. Then, with two or three
strategies open on Positions, the box keeps its rows (no empty box) and the API answers other pages at once. In the
browser network tab, `/plan-watch` is called about every 15 s per box, never two at once for one box.

Tier A review (Opus), round 1: FIX (1 MAJOR, 7 MINOR); round 2 fixed the MAJOR and MINORs 1 to 5: round 2 commit 48563be1 (no REST read after a cut market read, with a test; the hang tests are bounded so a regression fails instead of hanging; truthful comments; the mark and the as-of line share one slot). MINORs 6 (a strategy change mid-read waits for the old read) and 7 (below) are not changed.
For Lane U, from the review: (i) a cut `to_thread` REST read keeps its thread until urllib's 4 s timeout, so allow
one REST quote in flight per underlying; (ii) the same KeyError class exists wherever a not-connected market meets a
live ctx and a STATED spot (`approaches.roll_distance`, `ofo/adjustment/approaches.py:475`).
- Added at 11:00 IST (6e3dc306): `routes/adjustment_history.py` now does every database read (orders, contracts, the
  plan's max adjustments, the placing records) first, then gives its connection back (`release_connection`, the D-36 (c)
  helper `run_check` uses) before `paper.market_snapshot` waits on the feed. Pure reordering: `_plan_max` reads only the
  database; the answer is unchanged. Test `test_no_database_connection_is_held_while_the_market_snapshot_runs` (pool
  checked out during the snapshot: 1 on the old code, 0 now); adjustment-history tests 11 passed. Diff read by Lane J,
  no separate Opus review (a read reorder, no money or price logic).
- **`lanej/builder-open-0827` (4812a3f, the 08:30 instrument list fix): reviewed, but do NOT pull it today.** Two
  Tier A rounds (Opus); shipped after round 2 with two MAJOR findings open: the 08:35 window is hard-coded
  (`catalogue_refresh.py:36, 63, 111`), and a failed run waits an hour before the next (`:84, :112`). It changes only the
  start-up catalogue load, and today's load already ran, so pulling it mid-session gains nothing until tomorrow 08:30
  and adds a restart risk. Recommendation: pull it tonight with this branch, after the MAJORs are fixed or accepted.
Still listed for tonight, not on this branch:
- routes/playbooks.py `_tested` (:498-520) interleaves per-strategy DB reads (`_strategy_layer`) with each strategy's market read inside one loop; a release means splitting the loop into a DB pass and a market pass. Lane U edits the same file (playbooks.py:449), so it should follow Lane U's merge.
Not done this morning: the loop split is not small, and Lane U edits the same file.
Repo-scan note: `tests_app/test_kite_broker_reader.py::test_attack2_user_profile_outside_the_door_is_refused_by_the_egress_gate`
fails in this sandbox on the base 206a9f0 too (HTTP 400 from the sandbox proxy), not caused by this branch.

## Status for the coordinator (this session cannot send messages: the session-message service refuses it as untrusted)

**Full app (DB) suite on the final code head 1eb5097, run as CI runs it (GITHUB_ACTIONS=true, per-file database
clones, -m "not full_chain"): `7638 passed, 5 skipped, 23 deselected, 1 xfailed in 2917.28s` (0 failed). Skips:
trial ENDED x3 (ADR-039), EXECUTE_REPLAY_URL unset, no INDEX row in the test catalogue.**

1. Final head for 27 Nov: the head of this commit (docs only on top of 1eb5097). Merged: Lane R a2b44dd, Lane U
   12e04b9 (Change expiry), Lane D 491df12, all of Lane P, Step 2 wiring, Step 3 checks, P7, P8, S-11, the
   Not-applicable line, ADR-330 (31) with 0057.
2. Migrations the PC applies: 0054, 0055, 0056, 0057, each with its old-code-safe proof and its read-only check in
   section (a); 0057 first on the scratch copy ofo_rehearsal_1127. #753 (0058) is PARKED and not on the branch.
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

## #753 PARKED (not on this branch; migration 0058 is NOT applied tomorrow)

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

## Lines waiting for a person's approval (none written by Lane J)

- Catalogue wordings pinned "pending owner read": `stop_fired_note`, `stop_fired_note_with_line`, `alert_title_unnamed`
  (W2-A); `alert_side_closed_text` (now also names the shape that remains), `plan_sheet_reset`, `plan_sheet_reset_confirm` and
  the `labels:plan_sheet` pin (P7/P8); `change_deleted` "Deleted", `change_undeleted` "Restored" (ADR-330 (31)).
- REQ-070 AC-8 text (ADR-330 (31)); the 0057 downgrade refusal rule.
- Owner question LJ-1: answered (ADR-330 (41), the recorded fill, as built).
- Owner question LJ-2 (#753): open; 0058 parked.
