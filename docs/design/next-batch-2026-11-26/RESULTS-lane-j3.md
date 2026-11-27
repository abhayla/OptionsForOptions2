STATUS 00:50 | items 1, 2, 3: built, Opus-reviewed (round 1 fixed); R3 NOT merged (its files fail the gate: see Merges); item 4 table below | next push: after prepush TOTAL PASS | blocker: R3 needs its own fixes before it can merge

# Lane J3 results (27 Nov 2026; branch hotfix/worker-2-1127 from worker-join c1eb7a67)

## Merges (read this first)
- `origin/test/worker-chain-1127` (Q3): clean. `origin/chore/gate-speed-1127` (G2): one conflict in the generated `knowledge/findings/INDEX.md`, resolved by regenerating it.
- `origin/hotfix/plan-read-2-1127` (R3): **CONFLICT: knowledge/findings/INDEX.md and docs/design/next-batch-2026-11-26/RESULTS-lane-j.md** (not mine). I first merged it anyway (taking my side of those two documents) because items 1 and 2 are about R3's "kind not known" state. The pre-push gate then failed on files that are R3's or other lanes' (below), so **R3 is NOT in this branch** (a local backup branch `j3-with-r3-backup` held that merge; not pushed). Failures with R3 merged on this base (`prepush.py`, 27 Nov 19:06 UTC):
  1. `tests_app/test_rest_spot_door_scan.py::test_no_route_awaits_a_rest_spot_reader_before_the_tick_is_judged`: R3's `routes/plan_watch.py:308` (`await rest_reader(underlying)` inside its budget wrapper `_budgeted.rest`) is a route await of a rest reader outside the one door (Lane U's scan). For lane R3: read through `outcome.index_spot_of`, or give the scan the wrapper.
  2. `frontend/tests/action-ends-with-result-live-day.test.js` (Save plan: fivexx, timeout) and `frontend/tests/blank-optional-fields-live-day.test.js` (`lib/planWatch.js` blank optional texts: no_plan_text, armed_heading, as_of_text, lines.0.reason): 16 tests red against R3's frontend changes. For lane R3 / Y.
  Without R3 the worker's "kind not known" state cannot occur (`state_of` defaults to weekly; `approaches.roll_distance` raises `KeyError: ''` for an empty kind), so my items 1 and 2 tests build that state in the worker's own state step (`_state_without_kind`); they run unchanged on a base that has R3. **When R3 is merged, rerun `tests_app/test_worker_j3.py` and Q3's cases.**
- Q3's strict expected-fail marks (`FIXED_BY_LOSS_STOP`) are deleted (this tree carries both fixes, as Q3 said the build lane must).

## Item 1: a trade whose expiry kind is not known keeps its kind-free rules
Core and proof: `tests_app/test_worker_j3.py::test_a_far_month_leg_of_unknown_kind_still_raises_the_rupee_loss_stop`. Before the fix (seen on the R3-merged tree; again as a mutation of the fix on this tree), read back: status PAUSED, reason CHECK_FAILED, log line `strategy 100 has no alert preset: days to expiry unknown: None`, no alert event (loss Rs 1,612 against a Rs 1 stop). After: ACTIVE and the `plan.rupee_loss` event is raised.
Fix (`background.py`, `_evaluate_and_gate`): `StyleRefused` with `days_left is None` and no pin no longer pauses; the gate TIMING uses `UNKNOWN_KIND_TIMING_STYLE = "intraday"` (fastest; plan exits have no candle, quiet time or cap in the gate anyway). The evaluation itself answers "not checked" for every rule that needs the kind (R3's code, unchanged): T-06 and T-16 (stop lines not supplied), the stage rows, T-09, T-10b day count. The rupee stop and the time exit run.
Decision recorded (B2, product-neutral): the timing style is "intraday", not a guessed weekly/monthly row. No stage row is ever read on a guess.

## Item 2: same kind row for the same trade
- Failing test first: `test_the_kind_is_read_for_the_nearest_leg_not_the_first_one_listed` (worker asked for the kind of 9 Nov; the nearest leg is 2 Nov). Fix: `market_inputs` calls `expiry_kind_of(min(leg expiries), ...)`, as `read_market` does.
- I did NOT change the chain/forward/ATM expiry (still `legs[0]`): the screen reads the first leg's chain, and the worker must match it (a test compares the two states). Listed below.
- "Pass the kind into Tracked" (R3 point 3): not needed for the answer: `state_of` uses `market.expiry_kind or position.expiry_kind`, so the market's kind (now the nearest leg's) already wins. The cost R3 named (catalogue loaded per strategy per rebuild) is in `adjustment_readers._tracked_on`, R3's file; listed below.

## Item 3: a saved plan is watched within one re-read
Measured/named: the plan is loaded by `Worker.rebuild()`, run by `_rebuild_loop` every `REBUILD_SECONDS` = **30 s** (+ the time of the re-read). Two more holds then applied to the first check with the new plan: the style's own interval (`speeds`: weekly 30 s, monthly 120 s, in `_last_check`) and the unchanged-price signature/tick. Worst case before: about 33 s + 30 s (weekly) or + 120 s (monthly).
Failing test first (worker as its own OS process, Q3's harness): case (k): loss Rs 4,608 crossed, plan without stop, the Rs 1,000 stop saved, row expected within 15 s. Before: failed (log: `strategy 1 check skipped: interval`). Also unit test `test_the_worker_rereads_a_saved_plan_within_ten_seconds` (red with 30).
Fix: `REBUILD_SECONDS = 10`; and a changed plan is checked at once: `Worker._checked_body` records the plan body each check ran with; `_plan_changed()` lifts the tick, signature and interval holds for the first check with a different body. (Round 1 of the Opus review: the first version popped `_last_check` in `rebuild()` before its database awaits, so a check running with the OLD plan in that window used the pop up and re-held the new one; the structural version compares bodies at the check, and `test_a_plan_saved_during_an_old_check_is_checked_at_once_not_after_interval` fails if `_plan_changed` is disabled: mutation run.) Cost: one extra check per changed plan; the re-read is 3x as frequent (a list read plus gate reads per strategy per 10 s; measure on the PC with many strategies).
Bound now: save to alert about 10 s + one cycle (1 s), within the one minute asked.

## Opus review of items 1 to 3 (Why Opus: stop path). Verdict REVISE, round 1 used
| Finding | Result |
|---|---|
| F1 MAJOR: the pop ran before the re-read's awaits; an old-plan check re-held the new plan | Fixed structurally (`_checked_body`), mutation test |
| F2 MINOR: a refused pin was replaced by "intraday" when the kind is unknown | Fixed (fallback only with no pin) + test |
| F3 MINOR: no test caught the pop or the style choice | Interval/pop covered by the new unit test and chain case (k); the style choice (intraday vs monthly) is NOT tested (a mutation to "monthly" passes): listed |
| F4 MINOR: intraday timing is noisier than monthly for the flags that still run on an unknown-kind trade (candle 1 vs 15 min, cap 6 vs 2) | Not changed: noise, not lost money; plan exits are unaffected. Listed (owner choice: or give those flags no reading while the kind is unknown) |
| F5 observation: a far-month trade on the system plan shows as watched while T-06/T-07/T-09/T-10b are "not checked" (no rupee stop by default); the T-06 reason text says "stop lines not supplied", not "expiry kind not known" | Not changed (R3's/`playbook_eval`'s words). Listed; owner question: should a trade with NO checkable exit show "Monitoring paused"? |

## Item 4: Q3 cases (a) to (j) on real PostgreSQL 16 (as CI builds it), this head, worker as its own process
| Case | Result | Note |
|---|---|---|
| (a) loss stop crossed on a fresh trade | PASS | row at the 11:42 check |
| (b) crossed when the plan is saved | PASS | |
| (c) crossed at entry, raised after 5 min | PASS | |
| (d) daily cap used up | PASS | |
| (e) rupee stop crosses and dips back | PASS | |
| (f) profit target | PASS | |
| (g) time exit | PASS | |
| (h) 10 % loss, 5 % rule, held 14 min | PASS | the PC's failure is still NOT reproduced |
| (i) trade that cannot be priced | PASS | no row; worker reads STALE |
| (j) exiting the last leg closes the alert | PASS | |
| (k) NEW: saved with stop already crossed | PASS | red before the fix |
| (l) NEW: the PC's #207 plan shape | PASS | see below |
No fail, so no failing alert row to show. Two runs of 6 cases each (a to f 248 s, g to l 210 s); an earlier full run of (a) to (k) also passed (438 s) before the review fixes.

### Case (h) / T1-06 of 27 Nov 13:28: what the PC's trade was (from PR #722 comments, read by a helper, quoted)
Strategy #207 (A-G), plan accepted 13:13:33 (one second after the entry at 13:13:32): `guards.loss_stop_rupees = "80"` AND T-06 "Loss reaches this % of max loss" weekly `["50","5","40"]` (Middle stage 5), stop base credit 4,511.00, max loss 1,989.00; the expiry 1 Dec (4 days left); the loss was Rs 250.47 at 13:35 (past Rs 80 and 5 % since about 13:14); 0 suggestion rows for #207; worker log (restart 12:53) minute lines show `recomputes {207: 2}` and 0 tracebacks; re-confirmed after the 13:36 restart. Not stated: strategy type, expiry kind, pin.
Case (l) builds exactly that shape (rupee 80 plus T-06 `[50,5,40]`, whole rule list on, PATH-96: entered at a loss, 5-minute entry period): the row comes after the period. So the PC's failure is not the plan shape alone.

## For the PC (exact rows needed to find the failure; table and column names, no values)
1. The plan body of strategy 207 as stored (the playbook plan row: `body`, and its accepted-at time) and the strategy's alert style pin (`strategy_alert_style` pin column).
2. `public.paper_orders`: `created_at`, `side`, `quantity`, `price` of the first basket of strategy 207 (the entry time that starts the 5-minute period, ADR-330 (47)); and whether the trade is paper or real (the `mode` column of the strategy).
3. `public.adjustment_suggestions`: every row of strategy 207 for 27 Nov (`rule_id`, `kind`, `shown_at`, `outcome`, `answer`), including dismissed ones: a dismissed or answered earlier row of the same rule silences it (ADR-236).
4. The gate rows of strategy 207 (the table `playbook_store.load_gate_rows` reads: last record per rule and today's count) and the worker log lines `strategy 207 check skipped: <reason>` between 13:14 and 13:36 (the reasons: interval, not_ticked, unchanged, prices_*, no_preset, no_gate_read).
With 1 to 4 the question "which hold kept #207 from alerting" is answered; guesses without them are not worth a build.

## For lane R3 / other lanes
- For lane R3 (`adjustment_readers._tracked_on`): the catalogue is still read per strategy per re-read; with the re-read now 10 s, pass the kind from the worker's own market read, or cache it, if the hold time shows it. For `playbook_eval` (not mine): a T-06 "not checked" reason that names the missing expiry kind.
- For lane K2 / Y (`routes/paper.py`, pages): none from this lane.

## Monday 09:15 steps on named trades (the market is closed now: highest status "Passed in cloud")
1. Item 3 (saved stop already crossed): on any open trade that is at a loss, open Customise, type a rupee stop smaller than the current loss (for example 50 when the loss is 250), Save, and look at Alerts > Active. Expected: a "Stop Rs 50 reached" row within 15 seconds of Save (not "after the next minute"). Read the worker log: `strategy <id> check skipped:` must not say `interval` for that strategy right after the save.
2. Item 1 (kind not known): the far-month trade, one with a leg past the last listed future (30 Mar 2027 style) once such a trade exists on Monday; type a rupee stop below the loss: the row comes, and the percent stop line of that trade says "not checked" (not paused). If no such trade exists, record "no real case Monday".
3. Item 2 (nearest leg): a monthly trade whose legs were entered far leg first: compare the stop % of its plan sheet with the % the alert's reason names; they must be the monthly row's value. Use A-G #207 only if its legs are the same expiry (then nothing to compare: say so).

## To file as deferred issues (not filed by me)
1. `background.py`: chain, forward and ATM IV still read `legs[0].expiry`, the kind reads the nearest leg (the screen is the same). A trade whose first-listed leg is not the nearest prices its market from the far chain. Needs the screen and the worker changed together.
2. `_tracked_on` catalogue read per strategy per re-read (R3's #2), now 3x as frequent.
3. The unknown-kind timing style ("intraday"): no test fixes the choice; flags that still run on such a trade (T-02, T-18, S-02) get intraday candle and cap (noisier).
4. A far-month trade on the system plan reads as watched with every exit "not checked" (F5): owner decision whether it should show "Monitoring paused"; and the T-06 reason text should name the missing expiry kind.
5. `Worker._checked_body` keeps one entry per strategy ever checked (no removal when a strategy leaves the list); small, not harmful.
6. Q3's note stands: the paused state lives in memory only (REQ-165 AC-6 "not built"); case (i) proves the alert side only.

## task / model / minutes
| Task | Model | Minutes |
|---|---|---|
| Items 1 to 4, tests, RESULTS | Sonnet (this lane) | about 150 |
| Independent review of items 1 to 3 (stop path) | Opus (reviewer) | about 7 |
| Read PR #722 comments for the T1-06 plan shape | Haiku | about 1 |
