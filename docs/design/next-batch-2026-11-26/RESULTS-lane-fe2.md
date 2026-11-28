STATUS 07:25 | 1 monitor reports: Passed in cloud (core red on base, then green) | 2 nearest-leg expiry: Passed in cloud | 3 saved stop crossed in the same minute: Passed in cloud (test, no code change; mutation-checked) | 4 pause survives restart: Passed in cloud | 5 unknown-kind style: Passed in cloud (test, mutation-checked) | 6 _checked_body: Passed in cloud | 7 kind record (worker half): Passed in cloud; reader half Blocked (not my file) | 8 #878 and #879: Passed in cloud (heartbeat half of #879 Blocked: not my file) | 9 #861/#866 code: Passed in cloud; #860 Blocked (not my file); F7 decided, pinned | next push: none | blocker: none

# Lane FE2: the stop worker's open issues, on top of Lane FE's index-exit fix

Branch `fix/r2-worker-issues-1128` from `origin/fix/r2-index-exit-watch-1128` (dc25e9f). Paper only; no broker order endpoint; money exact `Decimal`.
Spec basis: ADR-016 to ADR-019; REQ-115 (AC-3, AC-4, AC-6); REQ-049 ("Monitoring paused"); REQ-165 AC-6; ADR-330 (44), (47), (58), (66).
Highest status claimed: **Passed in cloud** (PostgreSQL 16 and Redis 7 in this container, test doubles for the feed; not on the PC, not live).

## Core / Proof (item 1)
Core: two paper monitors on the real database (`tests_app/test_monitor_reports_fe2_1128.py::test_core_two_monitors_...`): monitor B has loaded only trade 1's index exit and judges it; monitor A loaded both exits and has no index reading, so it reports both "not run". Real case: the PC runs the API with more than one worker process; a monitor that has not yet reloaded writes a report that does not list a trade the other monitor cannot judge.
RED on `origin/fix/r2-index-exit-watch-1128` (before any change), output read back:
```
STATES {1: Entry(strategy_id=1, status='active', ...), 2: Entry(strategy_id=2, status='active', reason='', ...)}
E   AssertionError: trade 2's exit is judged by nobody: it must not read watched
E   assert ('active', '') == ('paused', 'stale')
```
(B's later write replaced A's "not run" report; trade 2 read watched although no monitor was judging its exit.)
GREEN after the fix: trade 1 active (monitor B judges it), trade 2 `paused` / `stale` (monitor A says not run, B does not list it).

## What was built, item by item
| # | Item | Result |
|---|---|---|
| 1 | Several API workers overwrite one `index_exits` key | The report is one slot per monitor (`ExitsPublisher(owner)`, a fresh id per monitor), read-merged-written; `decode_exits` merges: a trade is judged when ANY fresh monitor lists it as evaluated; else the why of a fresh monitor that lists it not run; with no fresh monitor, every trade any slot lists reads `index_exits_not_run`; a stopped monitor's slot is ignored while a fresh one exists; slots older than 1 h are dropped by the next writer; the key expires after 1 day. Old flat-format reports and any other shape read as unreadable (fail closed). |
| 2 | #863 chain, forward, ATM IV from `legs[0]` | `background.primary_expiry` = the nearest leg's expiry, the one the kind is read for; used by `market_inputs`, `daily_iv_of` and the window tokens. `read.chains.get(expiry, ())` (an absent chain = no forward, never a crash). Red before: forward and rows asked for 28 Dec, kind for 9 Nov. |
| 3 | #862 stop typed and crossed in one minute | Closed by Lane J3's re-read (every 10 s) and "plan changed" lift; proved by `test_worker_saved_plan_fe2_1128.py` (old check raises nothing; saved plan + `rebuild()` + next cycle inside a 600 s interval raises exactly one `plan.rupee_loss`). Mutation: with the two holds' lifts removed (`_plan_changed` and the pop in `rebuild`) the test fails (`1 == 2`). No code change. |
| 4 | #868 paused state lost on restart | No migration: Redis, the snapshot's own key. `Publisher.restore` (called first by `Worker.run`): keeps `since` of each PAUSED trade (snapshot at most 1 day old), then writes a snapshot that names no trade, so every trade reads paused `not_listed` until its first check has run (before: the dead worker's ACTIVE answers stood for up to 2 minutes). An ACTIVE trade's `since` starts again. Red before: `active` read before the first check. |
| 5 | #865 unknown-kind timing style | Behaviour stated and pinned: no pin and no kind -> `intraday` (the fastest; watched, not paused); a known kind keeps its own style (`weekly`). Mutation to `monthly` fails the test. |
| 6 | #867 `_checked_body` never pruned | Pruned in `_drop_stale_writes` for a strategy no longer listed; a failed read (`Listed.unread`) keeps it. Red before: the entry stayed. |
| 7 | #864 catalogue read per strategy per re-read | Worker half: `Worker.kinds` records the kind each check used (`market.expiry_kind or position.expiry_kind`, never `""`), keyed `(underlying, nearest expiry)`, pruned when the expiry has gone by; `main` shares it with `owner_lister`, which passes `kinds=` to `read_tracked` ONLY when `READER_TAKES_KINDS` is True (False until the reader half is made), so nothing breaks before it. Reader half: "For the owner lane". |
| 8 | #878 dropped strategy stays ACTIVE; #879 clock skew widens the window | #878: `status`, `paused_reason`, `paused_why`, `user_paused_until` dropped for a strategy that left the list (a failed read is not leaving); it then reads `not_listed`, paused. #879: `monitoring_state._current`: a stamp must be at most 120 s old and at most 5 s AHEAD of the reader (before: +-120 s, so a worker clock 100 s ahead made 220 s); applied to the snapshot, the readings and the report slots. The heartbeat half is `feed_bus.py`: "For the owner lane". |
| 9 | #860, #861, #866, F7 | #861/#866: `stop_lines.EXPIRY_KIND_UNKNOWN` ("stop_expiry_kind_unknown"), mapped to the existing "days left not available" sentence (fail closed) until Lane FC3 gives it its own; the producer is `playbook_eval` / `settings_in_force` (not mine): "For the owner lane". #860: `playbook_eval.py:_t10b` (not mine): "For the owner lane". F7: pinned, not changed (see Decided). |

## Evidence
| Claim | Evidence (command run this turn + result line) |
|---|---|
| Item 1 core red on the base, then green | `tests_app/test_monitor_reports_fe2_1128.py::test_core_two_monitors_...` on `dc25e9f`: `assert ('active', '') == ('paused', 'stale')`; after the fix: passed |
| Every affected suite on PostgreSQL 16 + Redis 7, fresh database (`python -m pytest -c pytest-app.ini` over 23 files: the 8 new files, Lane FE's three, `test_plan_stop_worker_chain` (Lane Q3's worker cases), `test_worker_j3`, `test_paper_monitor`, `test_monitoring_state`, `test_background_cycle`, `test_background_wire_want`, `test_background_worker`, `test_spot_either_source`, `test_paper_order_door`, `test_monitoring_status_route`, `test_monitoring_pause_route`, `test_stops_choke_point`) | `296 passed, 1 failed in 592.98s`; the one failure was my own new test of the review's F3 (its second step legitimately reloaded); corrected, re-run: `tests_app/test_monitor_reports_fe2_1128.py` 13 passed. Total of the corrected set: 297 passed. |
| Item 3 test can fail | mutation: `_plan_changed` returns False and the `_last_check` pop removed -> `assert 1 == 2`; restored -> 2 passed |
| Item 5 test can fail | mutation `UNKNOWN_KIND_TIMING_STYLE = "monthly"` -> 1 failed; restored -> 2 passed |
| Items 2, 4, 6, 8 red before the fix | item 2: forward asked for 28 Dec; item 4: `active` before the first check; item 6: the entry stayed; item 8: ACTIVE kept and a stamp 100 s ahead read fresh (4 failed before, all pass after) |
| Item 9 and the stop-line pins | `python -m pytest tests/adjustment/test_stop_lines_fe2_1128.py tests_app/test_stops_choke_point.py`: 16 passed |
| Lint ratchet | `python scripts/ruff_ratchet.py`: OK, no rule rose |
| Pre-push check on the pushed head | `python scripts/orchestrator/prepush.py --jobs 2` on the pushed head: the TOTAL line is in the head commit's message (a result written into the file would change the commit it describes) |

## Opus review (one, whole diff, read-only; Why Opus: stop and exit paths)
One Opus review of the whole diff against `origin/fix/r2-index-exit-watch-1128` (read-only, 7 minutes). Verdict REVISE; round 1 used; every finding dispositioned:
| # | Finding | Disposition |
|---|---|---|
| F1 major (new) | a dead monitor's "watching" claim beat the live monitor's "not run" for up to 120 s after an API restart | Fixed: a claim counts only while its slot is at most `WATCH_FRESH_S` = 30 s old (monitors renew every 10 s); an older claim reads `index_exits_not_run`. Tests `test_review_f1_*` |
| F2 major (older, kept by item 8) | a strategy whose re-list read failed stayed published ACTIVE while no longer checked | Fixed structurally: only strategies in `Worker.monitors` are published; the rest read `not_listed`. Test in `test_dropped_and_skew_fe2_1128.py` |
| F3 major (older) | a monitor whose first load failed published an empty "watching" slot | Fixed: a monitor that has loaded nothing makes no claim (`_ever_loaded`) and retries after 5 s. Test `test_review_f3_*` |
| F4 minor | the merged write is read-merge-write: a lost update stands up to 10 s | Not changed: Decided 1 and "To file"; a hash field per monitor removes it |
| F5 minor | one bad slot poisoned the whole report | Fixed: a bad slot is skipped; a report with no readable slot is unreadable (`test_review_f5_*`) |
| F6 minor | a failed restart write leaves the old answers standing until the snapshot ages out (120 s) | Not changed: the store is then down for the worker's own writes too; listed |
| F7 minor | worker and screen read different expiries for a far-first calendar trade | Not changed (the screen is not this lane's file); the docstring that claimed otherwise is corrected; "For the owner lane" 1: land with this branch |
| F8 minor | the 24 h key expiry turns "stopped" into "never wrote" | Not changed: the monitor starts with the API; after-hours slots are empty anyway |
| also | the live lister was not given the kind record (only the scenario one) | Fixed: both wirings share the record |

## Decided for the owner (spec-conformant choices; the owner is asleep until 08:00 IST 28 Nov)
1. **Item 1: merged, not "one writer".** Each monitor writes its own slot; a trade is "watched" if a monitor that renewed its claim in the last 30 s judges it. Why: every monitor judges every armed exit, and a process without the live feed (or one that has not reloaded) must not turn a covered trade paused, nor hide a trade nobody covers. Residuals: (a) the write is read-merge-write, not atomic: two writes in the same millisecond can drop one slot; it is rewritten at the next due write (at most 10 s) and a missing slot only makes a trade read as covered by the others, never a stale "watched" for a trade nobody judges for longer than that. (b) When no monitor has EVER written a report the worker's answer stands (Lane FE's decision 3): the existing tests `test_monitoring_state.py` and the status-route tests pin "no report = worker's answer", and they are not this lane's files. Reading "no report" as not watched needs those tests changed: "For the owner lane".
2. **Item 2: the worker uses the nearest leg; the screen still reads `legs[0]`** until the owner lane makes the screen half (below). For a trade whose legs share one expiry nothing differs. For a calendar trade listed far-leg-first the worker's forward, ATM IV and rows are now of the nearer expiry (the one the kind and the plan's stage are read for); the screen's are of the far one until the one-line change. Spec basis: ADR-330 (44), (58) (one rule for paper and real, one expiry per trade); chosen because the worker's own kind already read the nearest leg (two expiries inside one state was the defect).
3. **Item 3: no code change.** Lane J3's fix already closes the gap; a stop saved already crossed alerts at the next cycle after the re-read (at most 10 s + 1 cycle).
4. **Item 4: Redis, not a table.** REQ-165 AC-6 asks that a late or restarted worker never reads as current. A restart writes an empty snapshot first. No table is needed (no migration, nothing for Lane FD).
5. **Item 5: the timing style for an unknown expiry kind is `intraday`** (Lane J3's decision, now pinned): the gate's candle is 1 minute, plan exits are unaffected (they have no candle). Owner choice still open (J3 F4): intraday is noisier than monthly for the flags that still run on such a trade.
6. **Item 8: a strategy that left the list reads "not listed", paused.** Its entries are dropped, not kept as ACTIVE; a read that merely failed keeps them.
7. **Item 9, F7: the mixed-rule classification stays.** `plan_exit_rule_ids` marks a body rule as a plan exit when ANY member names a loss stop, the % profit target or the time exit: that is the text of ADR-330 (47). The loss stops themselves are the fixed `stop.*` lines (the body rules of T-06 and T-16 are not evaluated), so a mixed rule never doubles a stop; the extra alerts of a mixed rule are the price of never delaying a plan exit. Changing it to "all members" would put a profit target or time exit inside a mixed rule behind the candle close, quiet time and daily cap: a delayed exit costs money, a repeated alert costs attention. Pinned by `tests/adjustment/test_stop_lines_fe2_1128.py`; needs an owner decision to change.
8. New on-screen sentences: **none** (pending owner read: none). The proposed sentence for the new reason code is under "For the owner lane".

## For the owner lane (exact changes in files this lane may not edit)
1. `backend/ofo_app/adjustment_readers.py:722` (`read_market`), screen half of #863: `underlying, expiry = position.underlying, position.legs[0].expiry` -> `expiry = min(x.expiry for x in position.legs)` (the same rule as `background.primary_expiry`; it already reads the kind for `min(x.expiry ...)` three lines below). Then the screen and the worker read one expiry for chain, forward and ATM IV. Check `tests_app` compare tests that build a calendar trade (the worker-vs-screen state compare of Lane J3).
2. `backend/ofo_app/adjustment_readers.py`, reader half of #864: `read_tracked(strategy_id, rates, db=None, kinds=None)` and `_tracked_on(db, strategy_id, rates, kinds=None)`; in `_stored_kind_or_empty(db, underlying, legs, kinds=None)`: `nearest = min(x.expiry for x in legs)`; `if kinds is not None and (kind := kinds.get((underlying, nearest))): return kind` before `stored_kind(...)`. Then set `background.READER_TAKES_KINDS = True` (one line; it is False now because a keyword the reader does not know would fail every strategy's read, and the door-names guard forbids reflecting on the reader to find out). The record holds only a non-empty kind, so "not known" is still read from the catalogue.
3. `backend/ofo/adjustment/playbook_eval.py:_t10b` (#860): in the `parts[1] == ON_EXPIRY` branch, `_limit(c, "T-10b")` raises "not checked: days left" when the kind is unknown, although the plan's own time is the limit and the day is known to be expiry day. Change: call `_limit` only when `c.state.days_left is not None`; the `is_expiry_day(today, expiry)` test below it stays. Test: a plain "HH:MM" time exit with an unknown kind on expiry day fires at that time; on another day it answers `waits_expiry_day`.
4. `backend/ofo/adjustment/playbook_eval.py:_stop_answer` and `ofo_app/settings_in_force.py:stops_of` (#861/#866): when the state has no stops because the expiry kind is empty, answer `sl.not_checked_code(sl.EXPIRY_KIND_UNKNOWN)` (today: `sl.STOPS_NOT_SUPPLIED`, "stop lines not supplied", which does not name the missing fact). `ofo/errors/templates.py` (Lane FC3): add `_trig("expiry_kind_unknown", ...)` and point `stop_lines.NOT_CHECKED[EXPIRY_KIND_UNKNOWN]` at `adjust_trigger_expiry_kind_unknown`. Proposed words, pending owner read: "Not checked: this trade's expiry type (weekly or monthly) is not known, so the percent stop has no value."
5. `backend/ofo_app/feed_bus.py:read_heartbeat_state` (#879 heartbeat half): the heartbeat age is judged with `abs(...)`; make it one-sided like `monitoring_state._current` (at most 120 s old, at most 5 s ahead).
6. Lane FE's open item: sentences for the why codes `index_not_live`, `leg_not_live`, `exit_not_priced`, `index_exits_not_run` (`ofo/errors/explanations.py` and `routes/monitoring_status.py` `_WHY`); unchanged by this lane.
7. To read "no report at all" as not watched (brief item 1: a missing report must read as not watched): in `monitoring_state._with_index_exits`, `raw is None` -> `{i: _paused_unreadable(e)}`; this needs `tests_app/test_monitoring_state.py` and the status-route tests to write an empty report first (they assume "no report = the worker's answer"). Not done here because those test files are not this lane's.

## To file as deferred issues (not filed by me)
- The merged report is read-merge-write, not atomic (a Lua script or one hash field per monitor would be): at most one slot is lost for at most 10 s.
- Reader half of #864, screen half of #863, `_t10b` (#860), the expiry-kind sentence (#861/#866), heartbeat skew (#879): owner lane, above.
- The unknown-kind timing style is noisier than monthly for T-02, T-18, S-02 (J3 F4): owner choice.

## Not done
- Nothing from the queue was skipped. Items 7, 8 (heartbeat half), 9 (#860, the evaluator half of #861/#866) are partly "For the owner lane" because their files are not this lane's.

## Tasks, models, minutes
| task | model | minutes |
|---|---|---|
| items 1 to 9: tests first, fixes, mutation checks, RESULTS | Sonnet (this lane) | about 60 |
| review of the whole diff (Tier A: stop and exit paths) | Opus (reviewer, read-only) | 7 |

## PC steps (paper only)
Market closed: pull the branch; one file at a time through `scripts/orchestrator/db_run.py` (the PC's database also serves production): `tests_app/test_monitor_reports_fe2_1128.py`, `test_worker_expiry_fe2_1128.py`, `test_worker_saved_plan_fe2_1128.py`, `test_pause_restart_fe2_1128.py`, `test_unknown_kind_style_fe2_1128.py`, `test_checked_body_fe2_1128.py`, `test_kind_cache_fe2_1128.py`, `test_dropped_and_skew_fe2_1128.py`, plus Lane FE's three files and `test_monitoring_state.py`; and `python -m pytest tests/adjustment/test_stop_lines_fe2_1128.py`; expect all pass.
Live (market open, the API started with TWO worker processes, one paper trade with an index exit): (1) in Redis the key `ofo:feed:background:index_exits` holds two `owners` slots, both rewritten at least every 10 s; stop one API process: its slot ages out and the trade stays watched while the other judges it; stop both: the trade reads "Monitoring paused" within 2 minutes. (2) Restart the worker with a paused trade: right after the start every trade reads "Monitoring paused" (not listed), the paused one keeps its original since time, and the others read watched after their first check. (3) Exit a trade (all legs): its entry leaves `ofo:feed:background:monitoring` at the next re-read (10 s).

SAFE TO CLOSE (code head 811b0ff plus this RESULTS commit; what is left: the "For the owner lane" list above)
