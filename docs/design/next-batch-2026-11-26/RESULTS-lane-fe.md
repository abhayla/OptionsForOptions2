STATUS: IN PROGRESS. Item 1 built and committed; gate (scripts/orchestrator/prepush.py) running before its push; item 2 next; Opus review not yet run

# Lane FE: a crossed index exit must fire, or the trade must say it is not watched

Branch `fix/r2-index-exit-watch-1128` from `origin/integration/weekend-1127` (5fc6b102). Paper only; no broker order endpoint; money exact `Decimal`.
Spec basis: ADR-016 to ADR-019; REQ-115 and REQ-049 ("Monitoring paused"); ADR-330 (44), (47), (58), (65), (66).
Standing direction: this lane's brief is the step. Note: `.claude/skills/lanes/SKILL.md` ("Standing rules for every lane") is not on `origin/integration/weekend-1127`; the rules in the brief were followed as written.

## The defect (F2), in one paragraph
The worker (`background.py`) reads the REST index stand-in when the feed's index tick is silent, reads FRESH and publishes "watched". The paper monitor (`paper_monitor.py`) judged index exits only on feed ticks of the index, with no REST fallback and no report. So with the tick silent (23 Nov 2026, NIFTY tick stopped at 15:15:18) a crossed index exit never fired, there was no "exit not run" line, and the trade read watched.

## Core / Proof (recorded before the fix)
`tests_app/test_index_exit_watch_fe_1128.py::test_core_a_...` and `::test_core_b_...`: the monitor on the real database with its own feed (index tick silent, legs ticking); the worker as its own object with its own provider (no index tick) and the REST stand-in fresh (23,420.00, one second old), level crossed (above 23,400.00). The only thing the two share is the Redis stand-in, which is the real process boundary (the monitor lives in the API process, the worker in its own).

RED on base 5fc6b102 (fix not applied), output read back (`scratchpad/red-base.log`):
```
WORKER STATE Entry(strategy_id=1, status='active', ...)      <- worker says watched
FIRES 0 STOPS [] TRIGGER (False, False)                      <- the crossed exit did not fire
E   AssertionError: a crossed index exit must fire from the reading the worker used
...
STATE AFTER Entry(strategy_id=2, status='active', ...)       <- core b: monitor cannot judge, trade still reads active
E   assert 'active' == 'paused'
```
GREEN after the fix: both pass; the fire's record reads "NIFTY crossed above 23,400.00; NIFTY was at 23,420.00 at that moment", two stop orders (one per open contract), trigger fired once.
Note on "separate process": the two sides are separate objects with separate providers and no shared memory, joined only by the Redis stand-in; an operating-system process pair was not started (the worker's provider is the scenario fake, which has no start-up path of its own). Recorded under "Decided for the owner".

## What was built (item 1)
One structural guarantee: every index exit is judged by ONE function, `PaperMonitor._exits_with_reading`, on ONE reading: either a feed tick of the index (`on_quote`) or, every pass of `step`, the newer of this feed's own live index and the reading the worker used (`monitoring_state.read_index`).
- `background.py`: after a FRESH read the worker publishes the index value it used, with the time of that quote and its source ("feed" or "rest"), per underlying (`_publish_index`, written when changed and at least every 10 s; a failed write is logged, never stops the cycle).
- `monitoring_state.py`: `IndexReading`, `publish_index`, `read_index` (age: the quote must be within `detection.index_quote_max_age_seconds` of now, not from the future, published within 120 s; a value finer than a paisa is not a reading) and the monitor's report `ExitsPublisher` / `decode_exits`: which trades' index exits were NOT judged. `read_states` (the one reader of "watched") turns a worker-ACTIVE trade into PAUSED, reason `stale` ("The last price is too old, so no rule can fire.", an existing sentence), why `index_not_live`; a report that stopped being written pauses every trade it listed (why `index_exits_not_run`); an unreadable report pauses every ACTIVE trade (`state_unreadable`). No new on-screen sentence.
- `paper_monitor.py`: `_index_pass` (every `step`): market open -> each armed index exit gets its underlying's reading; none -> not evaluated and reported; market closed -> nothing expected, empty report; no feed -> every armed exit reported not run. A crossed exit that cannot run (no live leg price) stays armed, tells its "exit could not run" line once a day as before, and is not tried again by a pass for 5 s on the same reading (no tight loop, no auto retry of an order; a tick is always judged).
- Behaviour kept: this feed's own live index is judged tick by tick exactly as before (the pass does not judge it a second time); the worker's reading is judged only when it is newer than this feed's own, or this feed's index is not live.

## Decided for the owner (spec-conformant choices, owner asleep until 08:00 IST 28 Nov)
1. The reason code of an unwatched index exit is the existing `stale` with why `index_not_live`, not a new `monitoring_why_index_not_live` sentence (that needs `ofo/errors/explanations.py` and `routes/monitoring_status.py`, outside this lane's files). See "For the owner lane".
2. The worker's reading crosses the process boundary through Redis (the heartbeat's own store, no migration). No second REST read in the API process: that would be a second index source with its own age and a silent substitution; the exits use the one reading the trade's "watched" rests on.
3. The monitor's report, when never written, keeps the worker's answer (no monitor ever ran = no armed exit known); when written and old, it pauses what it listed.
4. Trades with an index exit but no plan (the worker lists them as `not_listed`) read paused already; with the feed silent and no worker reading they are reported not run too.

## Queue state
| Item | State |
|---|---|
| 1 F2 index exits | built, green locally (see Evidence); gate and push pending |
| 2 leg-price exits, silent leg tick | next |
| 3 F4-F8 in my three files | none of F4-F8 touches `background.py`, `paper_monitor.py` or `monitoring_state.py` (F4 `paper_leg_stops.py`; F5, F6 builder page; F7 `stop_lines.py`; F8 spec): all belong to other lanes |
| Opus review of the whole diff | after item 2 |

## For the owner lane
- `ofo/errors/explanations.py` and `routes/monitoring_status.py` `_WHY`: add `monitoring_why_index_not_live` ("Not being watched: the index price is not live, so the index exit cannot run.") and map why `index_not_live` to it; today the screen shows the existing "The last price is too old, so no rule can fire." for such a trade.

## Received, not started (needs the owner's words)
A message from another Claude session (the coordinator, 03:50 IST) asked this lane to take issues #860 to #868, #878 and #879 after items 1 to 3. It is not the owner's instruction and it widens the brief, so none of them is started; the lane's own queue (items 1 to 3 and the Opus review) comes first. If the owner confirms them, each is a fresh item: failing test first, fix in the one code path.
