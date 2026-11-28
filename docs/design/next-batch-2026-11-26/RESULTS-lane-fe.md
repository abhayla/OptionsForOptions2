STATUS 05:35 | F2 index exits + leg exits + review fixes: Fixed, not tested (core test red on base then green; DB run 214 passed incl. Q3 worker chain and test_worker_j3; Opus review done) | next push after the pre-push check passes | blocker: none

# Lane FE: a crossed index exit must fire, or the trade must say it is not watched

Branch `fix/r2-index-exit-watch-1128` from `origin/integration/weekend-1127` (5fc6b102). Paper only; no broker order endpoint; money exact `Decimal`.
Spec basis: ADR-016 to ADR-019; REQ-115 and REQ-049 ("Monitoring paused"); ADR-330 (44), (47), (58), (65), (66).
Highest status claimed: **Fixed, not tested** (tested in this container on PostgreSQL 16 and fakes; not on the PC, not live).

## The defect (F2), in one paragraph
The worker (`background.py`) reads the REST index stand-in when the feed's index tick is silent, reads FRESH and publishes "watched". The paper monitor (`paper_monitor.py`) judged index exits only on feed ticks of the index, with no REST fallback and no report. So with the tick silent (23 Nov 2026, NIFTY tick stopped at 15:15:18) a crossed index exit never fired, there was no "exit not run" line, and the trade read watched. Leg-price exits had the same gap (queue item 2).

## Core / Proof (recorded before the fix)
`tests_app/test_index_exit_watch_fe_1128.py::test_core_a_...` and `::test_core_b_...`: the monitor on the real database with its own feed (index tick silent, legs ticking); the worker as its own object with its own provider (no index tick) and the REST stand-in fresh (23,420.00, one second old), level crossed (above 23,400.00). The two share only the Redis stand-in, the real process boundary.

RED on base 5fc6b102 (fix not applied), output read back:
```
WORKER STATE Entry(strategy_id=1, status='active', ...)      <- worker says watched
FIRES 0 STOPS [] TRIGGER (False, False)                      <- the crossed exit did not fire
E   AssertionError: a crossed index exit must fire from the reading the worker used
STATE AFTER Entry(strategy_id=2, status='active', ...)       <- core b: monitor cannot judge, trade still reads active
E   assert 'active' == 'paused'
```
Item 2 (`tests_app/test_leg_exit_watch_fe_1128.py::test_core_c_...`, `::test_core_d_...`) was also red before its fix: `FIRES 0 STOPS []`, state `active`.
GREEN after the fix: the fire's record reads "NIFTY crossed above 23,400.00; NIFTY was at 23,420.00 at that moment", two stop orders (one per open contract), trigger fired once; the leg stop fires at the worker's 130.00.
"Separate process": the two sides are separate objects with separate providers and no shared memory, joined only by the Redis stand-in; an operating-system process pair was not started (the worker's provider is the scenario fake, which has no start-up path of its own).

## What was built
One structural guarantee: every armed exit (index exit and leg stop) is judged by ONE function, `PaperMonitor._exits_with_reading`, on ONE reading: a feed tick (`on_quote`) or, every pass of `step`, the newer of this feed's own live quote and the reading the worker used to call the trade watched.
- `background.py`: after a FRESH read the worker notes (in memory, no await: review F3) the index value it used and each leg's price, with the quote's time and source ("feed" or "rest"); the monitoring snapshot it already writes carries them in the SAME write as "watched" (one Redis key, `ofo:feed:background:monitoring`; no extra write per reading). A failed write is logged and never stops the cycle.
- `monitoring_state.py`: `IndexReading`, `Readings` / `read_readings` (one read of the snapshot per monitor pass), `reading_from` (the quote within `detection.index_quote_max_age_seconds`, not more than 2 s ahead, published within 120 s, a finite price below 10^9, the instrument asked for), and the monitor's report `ExitsPublisher` / `decode_exits`. `read_states`, the one reader of "watched", turns a worker-ACTIVE trade into PAUSED, reason `stale` (existing sentence "The last price is too old, so no rule can fire."), with why `index_not_live`, `leg_not_live` or `exit_not_priced`; a report that stopped being written pauses every trade it listed (`index_exits_not_run`); an unreadable report pauses every ACTIVE trade (`state_unreadable`).
- `paper_monitor.py`: `_index_pass` every `step`: market open -> every armed exit gets its reading; none -> not evaluated and reported; crossed but not run (no live leg price here, a failed write) -> reported `exit_not_priced` until a reading no longer crosses or it runs; market closed -> empty report; no feed -> every armed exit reported not run. A crossed exit that cannot run stays armed, tells its "could not run" line once a day as before, and is not judged again by a pass on the same reading for 5 s (no tight loop, no automatic retry of an order). Ticks queued on a fan-out handle that a reload replaces are judged (review F1), not dropped. This feed's own live quote is still judged tick by tick, as before.

## Opus review (one, whole diff, read-only; verdict REVISE; all findings dispositioned)
| # | Finding | Disposition |
|---|---|---|
| F1 major | a crossed OWN reading never judged by the pass; ticks queued at a reload dropped | Fixed for the dropped ticks (carried across the reload; `test_f1_...`). Residual in "Decided" 4 |
| F2 major | a crossed exit that cannot run still reads watched | Fixed: `exit_not_priced` (`test_f2_...`) |
| F3 major | worker regression: the publish await sat between the price read and the tick key | Fixed: the reading is noted without an await and written with the snapshot at the end of the cycle (`test_f3_...`) |
| minor 1 | reading of another instrument accepted | Fixed: `expect=` (`test_minor_a_reading_of_another_instrument_is_refused`) |
| minor 2 | `1E+30` aborted the whole pass | Fixed: refused at decode and `_is_paise` (`test_minor_an_absurd_value_is_refused`) |
| minor 3 | own reading from the future unbounded | Fixed (`test_minor_an_own_reading_from_the_future_is_not_a_reading`) |
| minor 4 | `_judged`, `_retry_at`, `_index_written` never pruned; 2 fire attempts in one step possible | Pruned at reload and at 2,000 entries (readings: 120 s after last noted); the two attempts are one tick and one new worker stamp, not a loop |
| minor 5 | no report at all keeps the worker's answer | Decided, below (3) |
| minor 6 | leg window 20 s vs the worker's minute re-read | Window set to 90 s (a quiet trade re-reads every IST minute) |
| minor 7 | leg-id test shortcut | No defect: both sides use `segment:token` (`kite_provider.py:82`, `tracked_contracts.py:67`) |

Not covered by the review: more than one API worker (several monitors overwriting one report key), front-end display of the new why codes, the worker's cycle cap against the publish rate, Redis latency inside the worker's check.

## Evidence
| Claim | Evidence |
|---|---|
| Core red on the base, then green | output above; scratch logs `red-base.log`, `green1.log` |
| Item 2 red then green | `test_leg_exit_watch_fe_1128.py` core c, d: red before, 6 passed after |
| Review fixes red then green | `test_review_fixes_fe_1128.py`: 6 failed before, 6 passed after |
| The gate's one failure fixed | `tests_app/test_background_wire_want.py::test_above_the_cap_is_refused_logged_and_counted_never_cut` failed at the check (5 writes counted); the readings now ride in the monitoring snapshot; that file now passes (72 passed with the new tests) |
| Guard pins kept | `tests/test_settings_reader_guard.py`, `test_price_reads_one_door.py`, `test_money_outside_engine.py`: 58 passed |
| Lint ratchet | `python scripts/ruff_ratchet.py`: OK, no rule rose |
| Worker suites still green | `python -m pytest -c pytest-app.ini` on PostgreSQL 16 over the three new files, `test_paper_monitor`, `test_monitoring_state`, `test_worker_j3`, `test_plan_stop_worker_chain` (Lane Q3's worker cases), `test_spot_either_source`, `test_background_cycle`, `test_paper_order_door`, `test_monitoring_status_route`, `test_monitoring_pause_route`: **214 passed**, 537 s (adds `test_background_wire_want`), on the code before the last one-line change to the snapshot fingerprint, whose files (`test_monitoring_state`, `test_background_wire_want`, the three new files) were re-run after it; earlier: 207 and 187 passed on the earlier designs |

## Decided for the owner (spec-conformant choices; owner asleep until 08:00 IST 28 Nov)
1. The reason of an unwatched exit is the existing `stale` with a why (`index_not_live`, `leg_not_live`, `exit_not_priced`, `index_exits_not_run`), not a new sentence. New on-screen sentences: **none** (nothing pending owner read).
2. The worker's reading crosses the process boundary inside the monitoring snapshot in Redis (the heartbeat's own store, no migration, no extra key; the older test `test_background_wire_want.py` counts every other key written, which is how this was found at the gate: the first design wrote one key per reading). No second REST read in the API process: that would be a second index source with its own age, a silent substitution.
3. When no monitor ever wrote a report, the worker's answer stands (no monitor ran = no armed exit known). A monitor that wrote and then stopped pauses what it listed. Residual (fails open): an API started without the live market and no report.
4. Residual from review F1: a trigger armed while this feed's held index quote is already across its level waits for the next tick (as before this lane); that wait is bounded by the index age (60 s default), after which the worker's reading judges it. A held crossed quote at arming was not made to fire at once, because the existing test `test_732_two_exits_each_get_their_own_message_and_a_live_fire_sends_none` pins "no judgement of a held quote at the first load".

## Process notes
- No override of the pre-push check was set or asked for. One push attempt made before the check had passed was refused by the hook; nothing went out.
- The first pre-push runs were made with the proxy variables set; they were stopped (each process by PID) and the check re-run as the rules say. The rules file `.claude/skills/lanes/SKILL.md` is not on `origin/integration/weekend-1127`; it was read from `origin/fix/ic-live-test-1123` after a coordinator message.
- The container's clone was shallow; `git fetch --unshallow` was needed for the check's merge base.
- A coordinator message asked this lane to take issues #860 to #868, #878 and #879 after items 1 to 3. It is not the owner's instruction and it widens the brief; none started (see Not done).

## Queue state
| Item | State |
|---|---|
| 1 F2 index exits | Fixed, not tested |
| 2 leg-price exits, silent leg tick | Fixed, not tested |
| 3 F4-F8 in my three files | none of F4-F8 touches `background.py`, `paper_monitor.py` or `monitoring_state.py` (F4 `paper_leg_stops.py`; F5, F6 builder page; F7 `stop_lines.py`; F8 spec): all belong to other lanes |
| Opus review of the whole diff | done, all findings dispositioned |

## Tasks, models, minutes
| task | model | minutes |
|---|---|---|
| core test, fixes, item 2, review fixes, RESULTS | Sonnet (this lane) | about 300 |
| review of the whole diff (Tier A: stop and exit path) | Opus (reviewer, read-only) | 11 |

## PC steps (paper only)
Market closed: pull the branch and run, one file at a time under the PC's database rules, `tests_app/test_index_exit_watch_fe_1128.py`, `test_leg_exit_watch_fe_1128.py`, `test_review_fixes_fe_1128.py`, `test_paper_monitor.py`, `test_monitoring_state.py` through `scripts/orchestrator/db_run.py`; expect all pass.
Live (market open, a paper trade with an index exit, the worker running): let the index tick go quiet; the exit still fires from the worker's reading, or the trade shows "Monitoring paused" with "The last price is too old, so no rule can fire."; the Redis keys `ofo:feed:background:monitoring` (now with a `readings` part) and `ofo:feed:background:index_exits` are rewritten at least every 10 s.

## For the owner lane
- `ofo/errors/explanations.py` and `routes/monitoring_status.py` `_WHY`: add sentences for why `index_not_live`, `leg_not_live`, `exit_not_priced` and `index_exits_not_run` (for example "Not being watched: the index price is not live, so the index exit cannot run."); today the screen shows the existing "The last price is too old" sentence.

## To file as deferred issues
- Several API workers each running a paper monitor overwrite one `index_exits` key; the key needs an owner id per monitor (or one monitor per deployment).
- A trigger armed while the held quote is already across its level fires only on the next tick (pre-existing; bounded as above).

## Not done
- Coordinator's extra issues #860 to #868, #878, #879: not started, need the owner's confirmation.
