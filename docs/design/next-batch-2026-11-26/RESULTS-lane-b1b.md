STATUS 23:40 | items 4, 5, 6 + monitoring-state answer + issue 876 cases built; RA2 1f8e0018c merged and verified (F1 no hole, F2 hole fixed); items 1 to 3 DROPPED (RA2's); one quiet full check running | next push: this head after TOTAL PASS | blocker: none (messages to the coordinator are refused: owner's device trust; this line is the report)

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

## Verification of RA2 1f8e0018c (merged; coordinator order 17:11Z)
- F1 hole: NO. RA2 builds the answer AFTER the commit (`_answer_after_commit`: retry on a clean transaction, then the truthful "saved, but the list could not be read", HTTP 409); a swallowed read error can no longer undo a write. Proven by tests_app/test_review_closes_b1b_1128.py (5 passed): a REAL PostgreSQL error (`SELECT 1/0`) in a read after the commit answers 201 armed with the row stored; a real error before the commit stores nothing, answers an error without "armed" and does not notify the monitor; a swallowed error inside `_adjustment_marks` leaves the committed stop alone.
- F2 hole: YES. `_attempt` logged a foreign `ValueError` with its text whenever the text STARTED with one of our openings (`needs `, ...): a transport error "needs the header token key:SECRET" reached the log (test red on 1f8e0018c). FIXED structurally: only an `_OwnReason` (our maths, raised by `_own_after` around `regime` and `_bars`) is logged with its text; everything else by class only. RA2's own tests changed to raise `_OwnReason` where they expect the text; the foreign-ValueError test stays plain.
- Backstops: (c) a no-session LIVE book's `as_of` equals the close's time is asserted in test_stored_close_paper_pnl_ra2_1128 (core); (d) no session at 09:15:00 IST: NOT_CONNECTED, no figure (test_review_closes_b1b_1128).

## W-34 restart delay (PC, build 829ff65f, real link 134 ms per query: badges back 2.5 min after a worker restart)
Measured, not guessed (tests_app/test_restart_report_b1b_1128.py; worker = separate OS process, real PostgreSQL, scenario PATH-96, one trade, test-only
per-statement delay `OFO_TEST_QUERY_DELAY_MS=130` with `APP_ENV=test`; the worker now logs two `start-up:` lines at every start):
- The restart writes an empty snapshot (FE2 item 4: every trade reads "not listed" until its first check), and the first real snapshot is written only at the END of the
  first cycle, which starts only after the WHOLE strategy list was read (`run()`: `restore`, `_rebuild_safely`, then `cycle()`).
- The list read costs 39 statements for ONE trade (5.5 s at 130 ms): about 34 per trade, 4.6 s per trade on that link, so about 40 s for nine trades; the first cycle then
  adds about 1 s per trade on a closed market. On the PC the real statements are heavier (playbook bodies, `p.body::text`) and a live market adds REST and regime reads, which
  is how 2.5 minutes is reached; I could not reproduce the exact 151 s without the live reads, and say so.
- Per trade the start-up repeats reads: the strategy ownership check `SELECT 1 FROM strategies` 8 times, the plan row and the system playbook twice, the entry facts and basket facts
  twice, the gate rows twice, `clock_timestamp()` 3 times, settings and preferences twice. Cutting these to one each is about 12 statements per trade (about 1.6 s per trade, 14 s for nine).
  Those calls sit in the stores and the plan-watch readers (Lane B3's `adjustment_readers.py`, Lane B2's stores): I did not touch them. Recommendation (entrepreneur's view: a restart
  is the moment the user looks hardest, so the first report must not wait for the slowest trade): publish a trade's "watched" as soon as ITS first check ends instead of at the
  end of the whole first cycle, and read the list per trade as a stream; plus the per-request de-duplication RA2 measured (RESULTS-lane-ra2, item 7).
- FIXED here: the heartbeat was written only at the start of the first cycle, AFTER the whole list read; a list read longer than the readers' two minutes (a slow link, many trades)
  made a worker that IS up read "no worker has reported in the last 2 minutes". It is now written at once and every 10 s while the list is read (`_beat_while_starting`, test with a list
  that takes "minutes").

### The start-up statement list for Lane B2 (non-money, so it can act without measuring)
Source: the statements of ONE trade at a worker start, in order (test-only echo: `OFO_TEST_QUERY_ECHO=1` with `APP_ENV=test`, worker = separate process, scenario PATH-96, plan with guards). Statement numbers are from that run; files are
under backend/ofo_app/. Avoidable = the same read done again by a different caller in the same start-up.
| # | Statement | File, function (by table or query name) | Avoidable |
|---|---|---|---|
| 1, 2 | `app_settings` count and rows | settings_cache.SettingsCache.refresh -> settings_store | no (once per process) |
| 3 | the strategy list of the owner | strategy_store (the list read of `background.owner_lister`) | no |
| 4 | `clock_timestamp()::date` (IST day) | the lister's own day read | could use the worker's clock |
| 5 | `charge_rates` of the day | charge_rates_store (`load_charge_rates`, `rates_of` of the lister) | no |
| 6 | paper orders | paper_book / paper_store load of the trade | no |
| 7, 8, 10 (+ 9, 11 savepoint) | contract rows by id, the token list, the contract rows again | tracked_contracts.resolve called twice (7 and 10) with a catalogue token read (8) between | YES: 7 and 10 are the same ids (1 statement + 2 savepoint statements) |
| 12, 16 | the plan row with `body::text` | playbook_store plan read, called twice (12 and 16); the body is the heaviest row of the start-up | YES: one read (1 heavy statement) |
| 13, 14, 15 | `UPDATE strategy_adjustment_plans SET stop_base` inside a savepoint | playbook_store `_BACKFILL_STOP_BASE` (ADR-247 backfill) | YES: a WRITE at every restart; skip when `stop_base` is already set (3 statements) |
| 17 | `min(saved_at)` of the system playbook versions | playbook_store `_ADR247_SAVED_AT` | cache per strategy type (1 per trade today) |
| 18, 19 (again 45, 46) | entry facts and basket facts | entry_facts_store `_SELECT` and `read_baskets`, read in the list and again in the first check | YES: 2 statements |
| 20, 21 | open gate rows with `strategies` join | playbook_store gate/record reads, called twice | YES: 1 statement |
| 22, 23, 24 and 25, 26, 27 | `clock_timestamp()`, `app_settings`, `user_adjustment_preferences` | settings_store and user_preferences_store.values_for via the worker's `user_values` / `preferences`, twice | YES: 6 statements to 3 (the worker's `settings_cache` already holds the settings) |
| 28, 31, 33, 36, 38, 40, 43, 47 | `SELECT 1 FROM strategies WHERE id AND user_ref AND deleted_at IS NULL` (ownership) | one inside each store function: playbook_store (gate reads, held crossings, rule state), strategy_pause_store, strategy_level_watch_store, strategy_alert_style_store | YES: 8 per trade; one check per trade-and-session is enough |
| 29, 30 | last suggestion per rule, rule ids | playbook_store (`DISTINCT ON (g.rule_id)` and the suggestion outcome read) | merge into one read |
| 32 | held crossings | playbook_store held-crossings read | no |
| 34 | `clock_timestamp()` | any of the above | YES (1) |
| 35, 37, 39 | alert style, monitor pause, level watch | strategy_alert_style_store.pin_of, strategy_pause_store, strategy_level_watch_store | one read for the three small tables |
| 41, 44 | `adjustment_rule_state` rows | playbook_store `_SELECT_STATE`, called twice | YES: 1 statement |
| 42 | `scenario_frames` | scenario only | no |
The safe subset that leaves the ownership rule alone is about 12 of the 34: the contract read, the plan read, the backfill write, the facts, the gate rows, the settings and preferences, the rule state, the clock reads.
Also seen, NOT a start-up cost, to check (Lane RA / B2): once the first cycle is over, the same three statements repeat on EVERY cycle for the same trade in a scenario whose clock does not move: ownership
`SELECT 1`, `set_config('ofo.rule_adjustment_no')` and `INSERT INTO adjustment_rule_state ... ON CONFLICT` (statements 48 to 94 of that run: 15 repeats in about 7 s). If a live worker does the same each second the
link pays 3 x 134 ms per trade per cycle; the INSERT should be written only when `held_at_entry` or `seen_clear` changed (`playbook_store._PUT_STATE`).

### Per-trade first report (built, test first)
`Worker.cycle` now writes the monitoring snapshot after EACH of the first cycle's checks (`_first_report_pending`, then once per cycle as before; `Publisher.publish` only writes on a change), so a trade's badge returns when ITS first check ends
instead of at the end of the whole cycle: tests_app/test_first_badge_b1b_1128.py (nine trades: the first report names fewer than nine, every later report names all earlier ones, the last names all nine; red before). NOT changed: the
whole strategy list is still read before the first check (about 34 statements per trade before the first check can start); streaming the list per trade is a larger change of `rebuild()` and `owner_lister` (the lapse and side-closed
passes run over the whole list), left for the owner lane.

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
