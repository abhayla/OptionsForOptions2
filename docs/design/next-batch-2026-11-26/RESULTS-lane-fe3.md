STATUS 10:45 | 1 failed check stays failed: Passed in cloud (tests_app/test_check_failed_fe3_1128.py, 3) | 2 failed book read keeps the watch: Passed in cloud (test_kinds_unread_fe3_1128.py, 5; needs FD4's raising kinds_of to be live) | 3 report atomic, retry, expiry: Passed in cloud (test_report_atomic_fe3_1128.py, 9) | 4 pause start kept over restarts: Passed in cloud (test_pause_since_fe3_1128.py, 6) | 5 sentences: keys monitoring_why_exits_not_checked_yet, monitoring_why_book_not_read, monitoring_why_exit_not_applicable (FC3 already added index_not_live, leg_not_live, exit_not_priced, index_exits_not_run): Passed in cloud (tests/errors, 63) | 6 fired leg stop in the past tense: Passed in cloud (test_stop_fired_line_fe3_1128.py, 4) | 7 re-read period pinned: already done by Lane FE2 | issue 876 shape: NOT reproduced on this head (test_no_pin_chain_fe3_1128.py passes) | Opus review of items 1 to 4: not yet run | next push: after the review | blocker: none

# Lane FE3 results

Branch `fix/r3-worker-3-1128` from `origin/fix/r2-worker-issues-1128`, with `origin/fix/r2-plan-screens-1128` (Lane FC3) merged (clean, no conflict). Paper only; no broker order endpoint; money exact `Decimal`.
Spec basis: ADR-016 to ADR-019, REQ-115, REQ-049, REQ-165 AC-6, ADR-330 (44), (47), (58), (64), ADR-003.
Standing-direction step (docs/process/standing-direction.md): step 3 / a real defect in what is already built (the worker's stop path, issue 627 area); nothing new is started.
Highest status claimed: **Passed in cloud** (PostgreSQL 16 and Redis 7 in this container; not on the PC, not live).

## Core / Proof (item 1)
Core: `tests_app/test_check_failed_fe3_1128.py::test_core_a_failed_check_is_not_undone_by_a_cycle_that_skips_the_check`: the real worker, the real monitoring store (Redis), read back the way the API reads it. One check whose write raises (`CHECK_FAILED`), then a cycle with a fresh price whose check is held by the style's interval (30 s registry default).
RED on `origin/fix/r2-worker-issues-1128` (code unchanged, tests added), output read back:
```
READ BACK Entry(strategy_id=100, status='active', reason='', ...) MonitoringStatus.ACTIVE None
E   AssertionError: assert <MonitoringStatus.ACTIVE: 'active'> is <MonitoringStatus.PAUSED: 'paused'>
2 failed, 1 passed
```
(The check was skipped; the trade nevertheless read active.) GREEN after the fix: `3 passed`.
Deviation from the brief, stated plainly: this core test runs the worker in the test's own process, not as a separate OS process (a failed write of a separate process would need a database fault injected into it). The separate-process chain cases are used as the regression proof instead (below).

## What was built, item by item
| # | Item | Result |
|---|---|---|
| 1 | CHECK_FAILED undone by a fresh read | `Worker._fresh_read` keeps a `CHECK_FAILED` pause as it already kept `EXPIRY_KIND_UNKNOWN`; new `Worker._check_passed` (called at the end of a check that ran through) is the only place that clears it. A write that fails after that pauses the trade again (`_write_one`). Covers every `CHECK_FAILED` source (write failure, no preferences, no gate read, no preset, a raising check). Tests: the failed check stays failed through a held cycle (published state read back); a passing check clears it; a second failed write pauses again. |
| 2 | failed `kinds_of` empties the watch | `PaperMonitor.reload` now wraps `_reload`: on any read failure the last watch list is kept, `read_failures` is counted, `book_unread_since` is set, ONE warning with the traceback is logged, and the next try is 5 s away (`READ_RETRY_SECONDS`), not 60 s; `step` no longer loses a pass to a failed reload (the kept list is still judged). Only a failure longer than `BOOK_UNREAD_MAX_S` (120 s, the heartbeat rule) changes what the trades read: every kept exit is reported `book_not_read` (new why code), nothing is judged or fired on the list (ADR-330 (64): a kind that cannot be read is never stopped here), the list itself is kept so recovery is immediate. A reload that works clears it. Tests (5): kept list still fires inside the age; reads watched inside the age; reads `book_not_read` after it and fires nothing; recovers; retry period is 5 s. Depends on Lane FD4 making `kinds_of` raise: today it swallows the error and answers "unknown" (see For the owner lane 1). |
| 3 | merged report not atomic (F4), failed restart write (F6), 24 h expiry (F8) | F4: each monitor's slot is now one field of a Redis hash (`monitoring_state.exit_slots_key()`), written by one atomic `HSET` by its own monitor alone; two writers can no longer drop each other's slot. A new key, because the old one is a string (`HSET` on it would answer WRONGTYPE for up to a day). The reader (`read_exits_raw`) merges the hash fields into the same report text `decode_exits` always read. A client without hashes (the bare get/set test doubles of older tests) keeps the old string path. F8: every write renews the key's expiry (24 h) while the monitor runs (it writes at least every 10 s); a monitor's slot gone for an hour is removed by the next writer (a live slot is never that old). F6: `Publisher.restore` remembers that its restart snapshot was not written (`restore_pending`); `Worker.run` retries it before every cycle (`retry_restore`) until it lands or a real snapshot has been written. A monitor's own failed write was already retried on the next pass and still is (tested). Tests (9, real Redis). |
| 4 | pause "since" resets on a worker restart (issue 880, worker half) | FE2's restore kept `since` only until the first snapshot: a restarted worker's first cycle that had not yet checked a trade wrote a snapshot that named no trade, and the kept start was forgotten (also a second restart before the first check). Now `kept` starts of paused trades no check has answered for yet ride in every snapshot (`"kept"` field, never a strategy of the snapshot: a reader still reads the trade as not listed) and are read back by the next restore; a trade a check answers drops out of it; unanswered for a day they are dropped. Tests (6) including the real `Worker` restarted in the middle of a pause (feed stale an hour: `since` is the first start). |
| 5 | sentences | `ofo/errors/explanations.py` + `tests/errors/template_pins.json` (pins "pending owner read"). See "New wording". |
| 6 | fired stop message in the past tense | `PaperMonitor._max_loss_line` for a leg stop now asks the same engine answer as the Stops panel (`routes.paper.leg_stop_answer`, on the book before the exit, at the FILL price) and stores FC3's sentences: a loss figure -> `paper_leg_stop_fired` ("Stop fired: <leg> reached <level>; max loss at that point Rs <figure>"); unlimited -> `paper_leg_stop_fired_unlimited`; yes with no figure -> `paper_leg_stop_fired_unknown`; a book left in profit, "no", "cannot tell" or any failure -> no line. The stored line reads back through the history (`FIRED_LINE_TEMPLATES` added to the restore list). Three old assertions in `tests_app/test_stop_fired_message.py` said "no 'max loss' text at all"; they now pin the past-tense line (listed so you can see them). New: `test_stop_fired_line_fe3_1128.py` (4: normal fill Rs 12,025.00, gapped fill Rs 14,560.00, unlimited, history read-back). |
| 7 | re-read period pinned at 10 s | Already done by Lane FE2: `tests_app/test_report_race_fe2_1128.py::test_the_saved_plan_reread_period_is_ten_seconds_exactly` (`REBUILD_SECONDS == 10` and the loop sleeps exactly 10). Nothing added. |
| 876 | coordinator addition: the PC's T1-06 of 27 Nov | See "Issue 876". |

## Issue 876 (the PC's T1-06 of 27 Nov, strategy 207): reproduced or not
Test: `tests_app/test_no_pin_chain_fe3_1128.py::test_m_...`: worker as a separate OS process on a real PostgreSQL database; no style pin; the plan (whole system rule list, "Loss reaches 5 % of max loss") accepted before the loss begins; PATH-94 (loss about 10 %, twice the level, from 11:41) held 14 minutes. **Not reproduced**: the alert row is there at the first check after the loss and is still exactly one open row 14 minutes later, no "has no alert preset" line in the worker log, no order placed.
- On this head the "no pin" path cannot make the style step raise: `alert_presets.style_for(kind, days, None)` raises only for an unknown kind or days that are absent or past; with a known kind and days it answers the automatic style. Lane J3's "unknown kind" handling (`UNKNOWN_KIND_TIMING_STYLE`) is in this head. On the Friday code (206a9f0) the same unknown-kind input raised `StyleRefused`, paused the trade `CHECK_FAILED` and returned before any rule was evaluated, but that path logs "has no alert preset" and a "check skipped: no_preset" line each cycle, and the PC saw 0 skipped lines, so it does not match the stored facts.
- Not done in this push: running test m on the Friday code to say whether 206a9f0 fails it (listed under Not done). Until that run, the cause of the PC's 22 quiet minutes is **unknown**; this is a negative result on this head, not a proof that the PC's code was fine.

## Evidence
| Claim | Evidence (command run this turn + result line) |
|---|---|
| Item 1 red on the base, green after | `git stash push backend/ofo_app/background.py; pytest -c pytest-app.ini tests_app/test_check_failed_fe3_1128.py`: `2 failed, 1 passed` (trade read ACTIVE); stash popped: `3 passed` |
| Item 3 race reproduced on the old path, not on the new | the same two-monitor crossing run against a client with no hash commands: `LEGACY PATH READ {1: ('active', ''), 2: ('active', '')}` (trade 1 should read paused `index_not_live`); `test_core_two_monitors_writing_in_the_same_instant_keep_both_slots` passes on the hash |
| New tests alone | `pytest -c pytest-app.ini tests_app/test_check_failed_fe3_1128.py tests_app/test_pause_since_fe3_1128.py tests_app/test_report_atomic_fe3_1128.py tests_app/test_kinds_unread_fe3_1128.py`: 23 passed (3 + 6 + 9 + 5) |
| Worker, monitor and report suites on PostgreSQL 16 + Redis 7 | `pytest -c pytest-app.ini` over `test_worker_j3`, `test_monitoring_state`, `test_monitoring_status_route`, `test_index_exit_watch_fe_1128`, `test_monitor_reports_fe2_1128`, `test_pause_restart_fe2_1128`, `test_dropped_and_skew_fe2_1128`, `test_no_report_fe2_1128`, `test_report_race_fe2_1128`, `test_real_position_stops_fe2_1128`, `test_unknown_kind_publish_fe2_1128`, `test_stop_fired_message`, `test_stop_fired_fe2_1128`, `test_stop_fired_line_fe3_1128` and the four item files: `114 passed, 3 failed` (the three old fired-stop assertions); after editing them: `15 passed` for the three stop-message files |
| Paper monitor and background suites | `pytest -c pytest-app.ini` over `test_paper_monitor`, `test_paper_triggers_routes`, `test_paper_order_door`, `test_monitoring_pause_route`, `test_stops_choke_point`, `test_background_wire_want`, `test_background_worker`, `test_background_cycle`, `test_worker_heartbeat`: `268 passed in 194.68s` |
| Worker as a separate process (chain), cases a, h, k, l and the new m | `pytest -c pytest-app.ini tests_app/test_no_pin_chain_fe3_1128.py tests_app/test_plan_stop_worker_chain.py -k "test_m_ or test_a_ or test_h_ or test_k_ or test_l_"`: `5 passed, 8 deselected in 175.57s` |
| Template pins | `python -m pytest tests/errors/test_template_pins.py`: `63 passed` |

Not run in this push (honest): the other chain cases b to g, i, j of `test_plan_stop_worker_chain.py` (about 5 minutes each; unchanged code paths for their rules, but not re-run), `test_worker_attaches_confirming_check` and the rest of `tests_app`; the gate runs what it runs.

## For the owner lane
1. **Lane FD4**: `strategy_store.kinds_of` must raise (or return a failure flag) on a database error instead of answering "unknown" for every id (the monitor's half is done here, item 2); until then the old drop-everything behaviour stands in production. Its callers: `paper_monitor._paper_only` (this lane). A kinds read that raises also needs the strategy-store test `test_a_position_whose_kind_cannot_be_read_is_not_stopped_either` rewritten to expect the kept list.
2. **Lane FD4 (route)**: map the new why codes to these catalogue keys in `routes/monitoring_status.py` `_WHY`: `index_not_live` -> `monitoring_why_index_not_live`, `leg_not_live` -> `monitoring_why_leg_not_live`, `exit_not_priced` -> `monitoring_why_exit_not_priced`, `index_exits_not_run` -> `monitoring_why_index_exits_not_run`, `exits_not_checked_yet` -> `monitoring_why_exits_not_checked_yet`, `book_not_read` -> `monitoring_why_book_not_read`, `exit_not_applicable` -> `monitoring_why_exit_not_applicable`, `expiry_kind_unknown` -> `monitoring_why_expiry_kind_unknown`.
3. `ofo/tracking/paper_alert.py` `STOP_LINE_TEMPLATES`: add the three `paper_leg_stop_fired*` ids (this lane passes them itself in `paper_monitor.FIRED_LINE_TEMPLATES`, so nothing breaks, but one list is better).
4. An index exit's fired message still carries the exit confirmation's line (`paper_exit_widens_loss`: "After these orders, maximum loss: ... before, ... after."), which is not a past-tense sentence. FC3 wrote no past-tense sentence for it. Needs a sentence (and an owner read) if the PC sees it read as a preview.
5. Deploy note: the monitors' report moves to a new Redis key (`index_exit_slots`, a hash). For the first seconds after a mixed deployment (an old API process writing the old string key) a trade may read "exits have not been checked yet"; it clears at the new monitor's first write (at most 10 s).

## Decided for the owner (spec-conformant choices; the owner is asleep or away)
1. **A failed check stays failed until a check that ran has passed** (item 1). Spec basis: ADR-016 to ADR-019 (an unresolved state blocks, it is never assumed good), REQ-115 AC-4. Cost: a trade whose check is held by the interval after a failure reads paused for at most that interval (30 s default); a `CHECK_FAILED` pause that used to clear on the next fresh price now waits for the next real check.
2. **How long the kept watch list stands after a failed book read: 120 s** (the heartbeat rule), then no exit is judged and the trades read "not watched: could not read the book". Spec basis: ADR-330 (64) (a kind that could not be read is never stopped here), REQ-115 AC-4, ADR-016 to ADR-019 (fail closed). Cost: for up to 2 minutes a trade whose position kind turned real in that window could still be stopped on the old list (the kind of a paper trade does not change in two minutes in practice); a longer outage stops every paper exit rather than guess.
3. **The exit report is a Redis hash with a new key**, hash path only for clients that have hashes (every real Redis client); bare get/set doubles keep the old path (older tests). Spec basis: REQ-115 AC-4, AC-6 (a lost report reads as not watched and pauses a healthy trade). Why not a lock: a lock needs a "not acquired" answer the test doubles cannot give, and a hash field has no second writer.
4. **A book left in profit by a leg stop writes no loss line** (item 6) rather than "Rs 0"; "yes with no figure" says it was not worked out. Spec basis: ADR-003 (decision support, no figure that was not computed), ADR-330 (6).
5. **Level in the fired sentence is the stop's level, the figure is the fill's** ("reached 140.70 ... Rs 14,560.00" for a gap to 180.00); the body already says "exited at 180.00". Spec basis: ADR-330 (6).
6. **A third sentence beyond the five asked for** (`monitoring_why_exit_not_applicable`, for a real position's old armed paper stop): the code `exit_not_applicable` (FE2 item b) had no sentence. Spec basis: ADR-330 (64).

## Question for the owner
None. No two of the owner's rules clashed.

## New wording for the owner to read (pending owner read)
- `monitoring_why_exits_not_checked_yet`: "Not being watched: the exits have not been checked yet."
- `monitoring_why_book_not_read`: "Not being watched: the book could not be read, so the exits cannot run."
- `monitoring_why_exit_not_applicable`: "Not being watched: this is a real position, and stops here cover paper trades only."
- The four sentences of Lane FC3 for the codes `index_not_live`, `leg_not_live`, `exit_not_priced`, `index_exits_not_run` are unchanged and read: "Not being watched: the index price is not live, so the index exit cannot run." / "...a leg's price is not live, so its stop cannot run." / "...an exit has no price to compare with, so it cannot run." / "...the index exits are not running right now."
- Item 6 stores FC3's past-tense sentences ("Stop fired: <leg> reached <level>; max loss at that point Rs <figure>", "...; there was no fixed maximum loss at that point", "...; the maximum loss at that point was not worked out"); no new words from this lane.

## To file as deferred issues (not filed by me)
- Reader side of the report: when a hash slot is unreadable the whole slot is skipped; with only bad slots the report reads unreadable (kept behaviour, pinned by FE2's tests).
- The index exit's fired line is not in the past tense (For the owner lane 4).

## Not done
- Opus review of items 1 to 4 (brief: required): not yet run. This push is before it; the next push carries its findings.
- Item 1's core as a separate OS process (see Core / Proof).
- Issue 876: the same test on the Friday code (206a9f0) to say whether it failed there, and the cause in one sentence. Not run.
- Chain cases b to g, i, j re-run; `tests_app/test_worker_attaches_confirming_check.py`.
- `tests_app/test_d36_adjustment_counts.py` (FC3's PC step, unchanged by this lane).

## Tasks, models, minutes
| task | model | minutes |
|---|---|---|
| items 1 to 6, issue 876 test, tests first, fixes, RESULTS | Sonnet (this lane) | about 150 (waiting on the slow chain runs included) |
| review of items 1 to 4 (Tier A: stop and exit paths) | Opus (reviewer, read-only) | not yet run |

## PC steps (paper only)
Market closed: pull the branch; one file at a time through `scripts/orchestrator/db_run.py` (the PC's database also serves production): `tests_app/test_check_failed_fe3_1128.py`, `test_pause_since_fe3_1128.py`, `test_report_atomic_fe3_1128.py` (needs Redis), `test_kinds_unread_fe3_1128.py`, `test_stop_fired_line_fe3_1128.py`, `test_stop_fired_message.py`; and `python -m pytest tests/errors/test_template_pins.py`; expect all pass.
Live (market open, the API with TWO worker processes, one paper trade with an index exit): (1) `HGETALL` of the Redis key `ofo:feed:background:index_exit_slots` shows two fields, both rewritten at least every 10 s, and its TTL is renewed (about 86400) at each rewrite; (2) restart the worker while a trade is paused (no leg price): the "Since" time of the badge stays the original, also after a second restart seconds later; (3) fire a leg stop: the pop-up and History row read "Stop fired: <leg> reached <level>; max loss at that point Rs <figure>" with the fill's figure, never "If this stop fires"; (4) stop the database for 30 s while a paper trade with an exit is open (after Lane FD4 lands): the exit still fires if crossed, and after 2 minutes of failure the trade reads "not being watched: the book could not be read".

SAFE TO CLOSE: not yet (the Opus review of items 1 to 4 and the issue 876 run on the Friday code are open).
