STATUS 23:05 | items 4, 5, 6 + monitoring-state answer + issue 876 cases built on RA2's head dc1aeebd8; items 1 to 3 DROPPED (RA2 built them, coordinator order 16:37Z); full check running | next push: this head after TOTAL PASS | blocker: none (messages to the coordinator are refused: owner's device trust; this line is the report)

# Lane B1b: worker, monitor, alerts, paper P&L (successor of Lane RA2; base origin/fix/r3-leftovers-2-1128 dc1aeebd8, integration/weekend-r3-1129 already merged there)

Highest claimable status: Fixed, not tested (no PC run). Local database: PostgreSQL 16 `ofo_test`, role `ofo_app` non-superuser,
one test file at a time (`OFO_TEST_DB_PER_FILE=1`, proxies unset). Ruff: the pinned `ruff==0.15.12`.

## What was done
| Item | State | Evidence |
|---|---|---|
| PC observation: monitoring state "empty" with 5 trades monitored, market closed | answered, no defect | tests_app/test_five_closed_b1b_1128.py: 2 passed. The worker's own cycle with five trades at a closed market writes all five with `market_closed` (Lane FE3's fix); the route answers `[]` only for a request with NO `ids` (the page always sends them); an asked id nobody names reads paused `not_listed`, never watched. |
| 4 calendar unknown reads NOT_CONNECTED | built | tests_app/test_unknown_calendar_book_b1b_1128.py: 2 passed (core red before: LIVE). `_stored_close_snapshot` returns None when `market_calendar.market_status` is NO_CALENDAR. `_served` also needs a live price WITH a quote time (code kept; the backstop TEST is Lane RA2's). |
| 5 history, no session | built | tests_app/test_history_stored_close_b1b_1128.py: 3 passed (core red before: `prices_not_live`); test_adjustment_history 4, _approach 4, _other_user 2, _why 2 passed. |
| 6 one market-open clock | built, Opus-reviewed | tests_app/test_market_clock_b1b_1128.py: 11 passed; core mutation (drop the worker rule) fails; bell and close tests added after the review. Neighbours (before the review fix): test_paper_monitor 35, test_monitoring_state 10, test_background_worker 33, test_background_cycle 76, test_worker_j3 6, test_plan_stop_worker_chain 12, test_worker_heartbeat 27, test_report_race 4, test_monitor_reports_fe2 13, test_held_stop_ra 8, test_monitoring_status_route 11. |
| Issue 876, the two untried cases | not reproduced | tests_app/test_t106_b1b_1128.py: (b) the worker restarts AFTER the loss began: 1 passed, the alert comes. (a) a loss within five minutes of entry: Lane RA's tests (c) and (l) in test_plan_stop_worker_chain.py already run it (PATH-96 enters at the loss), green: NOT reproduced. |
| Doubled "The market is closed." prefix | wording choice, not a defect | See "Question for the owner". |

## Items 1, 2, 3 (dropped, with my findings for RA2's versions)
Coordinator order 28 Nov 16:37Z: Lane RA2 built the stored-stop answer, the scenario adx message and the unreadable slot. I had built the same three
and an Opus review of them found two money or secret defects that RA2's versions should be checked against (my branch `b1b-backup-items-1-3` in this
container is not pushed; the tests are small):
- F1 MAJOR: `_adjustment_marks` (routes/paper.py) swallows its own read error. If the answer is built BEFORE the commit, a PostgreSQL error aborts the
  transaction, `COMMIT` then answers ROLLBACK with no exception, and the route says "armed" with nothing stored. The marks read needs a savepoint
  (`async with db.begin_nested():`). Test: make the resolve inside `_adjustment_marks` run `SELECT 1/0` and expect 201 with one stored row.
- F2 MAJOR: logging the text of a plain `ValueError` in `regime_inputs._attempt` can write the Kite access token (http.client puts a whole header value
  in its text). Log the text only for our own maths errors (a ValueError subclass raised by `regime` / `_bars`); everything else by class only.
- F3/F4 minor (unreadable slot): a stopped monitor's slot with a readable time must stay ignored like a readable stopped slot; an `Infinity` id in a
  skipped slot must not raise (`OverflowError` escaped `decode_exits`).

## Item 6 (cause, design, Opus review)
Cause (FE4 F7): the worker (`background.feed_state` / `market_closed_for`) and the monitor (`may_act.market_open(feed.ctx, now)`) each asked the
calendar with their own clock. Now the worker's snapshot carries `market_open` at its own instant `at` (`monitoring_state.encode`, `Publisher.publish`,
`Worker._market_open_now`: open only when no monitored trade's provider says closed; a flip is written at once, it is in the fingerprint). The monitor
(`PaperMonitor._read_worker_clock`, `_market_open`) uses its OWN fresh clock for the open and the close; the worker's answer counts only as a real
disagreement about ITS instant (closed while our rule says open at that same instant), and only while the snapshot is under 120 s old.
Opus review (read-only, 44 tool calls): REVISE. F1 MAJOR: my first version AND-ed the worker's last answer, so a worker "closed" of 09:14:58 blocked a
stop at 09:15:01 (a gap-open fires at a later price) and a dead worker blocked stops up to 120 s. FIXED as above; tests: the bell (09:14:58 worker
closed, 09:15:01 monitor: fires) and the close (15:29:59 worker open, 15:30:01 monitor: nothing fires). Minor findings, not fixed:
- the reader side still judges "watched" from the worker's last snapshot: at 15:30 a trade reads watched until the worker's next cycle (1 to 2 s, or one
  long cycle with more than 200 trades). Smallest change: in `read_states`, demote ACTIVE to PAUSED `market_closed` when the snapshot's `market_open` is
  false or the reader's calendar at `now` says closed.
- a Redis read (2 s timeout) now runs before the queued ticks of each pass; the snapshot key is read twice per pass (`read_market_open`, `read_readings`).
- several providers (not reachable today: one provider for every owner): one closed answer would block every user.
- pre-existing: a tick stamped 15:29:59.8 and drained after 15:30:00 is dropped (the gate uses drain time).
- item 5: `AdjustmentHistoryOut` carries no as-of time for a stored close (same gap as the book's display); no test of the history with no session in market hours.

## For the owner lane
- D-TG2-2 (item 7): the T-09 title lives in playbook DATA (`backend/ofo/adjustment/system_playbooks.json`, `triggers.T-09.label`, ten copies; stored
  copies by migration 0051): "A short leg's premium falls to Rs or below (close for pennies)" has no number because the limit differs by stage (3 / 3 / 2).
  A released playbook is not changed in place: a NEW playbook version needs the label with a `{limit}` placeholder rendered with the current stage's value
  where the title is shown (the condition line already carries the amount: ₹2.45 (rule ₹3.00)).
- Frontend (Lane RA2 note, open): print `as_of` of a LIVE stored-close book.

## Decided for the owner
- Item 4: `feed_health.py` (not in my list) is untouched: its fail-closed answer is right for orders; the paper book now asks the calendar itself.
- Tests live in tests_app/ (a file under tests/ may not import ofo_app: `test_no_app_imports`); not registered in PR241_SELECTION (a new entry breaks `test_pr241_diff_selects_both_red_files_within_the_cap`, RA2 note).
- The empty list of the PC's observation is by design (no `ids`); the route is not changed.

## Question for the owner
- The Add to Paper dialog can print two sentences that both start "The market is closed." (`exit_market_closed` and `exit_market_closed_entries`, explanations.py lines 1577 to 1586), each a whole catalogue sentence, built by `ofo_app/exit_market.py` and printed one under the other. It is a wording choice, not a double print by two code paths. Recommendation: keep the first whole and make the second start at "Orders can be placed from 09:15 on <day>." (the wording is the owner's to approve).

## New wording for the owner to read
None from this lane (the worker-log lines are not shown to a user).

## To file as deferred issues
- Pre-existing, connected session on a day the calendar cannot answer: `display_price` serves a stale quote as LIVE (`FeedState.market_closed` counts an unknown day as closed; `ofo/tracking/paper.py:120-133`, `feed_health.py:149-152`). Class: unknown calendar counts as closed for prices.
- The reader-side gap and the minor review findings of item 6 above.

## Not done
- Items 1 to 3: Lane RA2's (merge its head; run `b1b-backup-items-1-3`'s F1 and F2 tests against it, see above).
- Item 7: a new playbook version (owner lane). Plan-watch duplicates: Lane B3. O-P-03: needs a frontend field first.

| task | model | minutes |
|---|---|---|
| items 4, 5, 6, PC observation, 876 cases | Sonnet (this lane) | 70 |
| Opus review of items 1, 2, 4 (71 tool calls) and of item 6 (44) | Opus | 20 |
