STATUS 20:10 | batch 1 PUSHED (d35ae8f54, TOTAL PASS); batch 2 built and committed: items 3, 4, 5, 6, 7 + Opus review M2/M4 fixes, full check next | next push 01:30 | blocker: send_message to @parent refused (elevated_session_untrusted_device); this line is the report

# Lane B3 results (28 Nov 2026)

Highest status claimed: Fixed, not tested on the PC.

## Item 1 (I-48): plan watch, nine rows
Real case (plan row I-48): "Plan watch answers in 6 seconds or more and the Positions page sends 34 requests a minute".
Core test: `tests_app/test_plan_watch_batch_b3_1128.py::test_nine_rows_statement_ceiling_and_each_row_its_own`.

| Measured (cloud DB test, 9 running rows of scenario ADJ-01) | Before | After |
|---|---|---|
| Statements for one batch of 9 rows | 219 (24 a row) | 162 |
| Single route plan-watch (ceiling in test_route_latency_budget.py) | 27 | 26 |

What is read once for all rows now (`routes/plan_watch.py::prefetch`, used by `routes/plan_watch_batch.py`):
- each row's stored triggers (still one read per row, moved to the prefetch), the contracts those triggers name (ONE
  `tracked_contracts.resolve` for all rows: 2 statements instead of 2 per row), the position kinds (ONE `kinds_of`);
- the expiry kind: the first row reads the stored catalogue, later rows of the same (underlying, nearest expiry)
  reuse it through `read_tracked`'s own `kinds` argument (the worker's #864 path);
- the screen-isolation read ran twice a request (`watch_of` and `run_check`): once now (the single route is one
  statement lighter too).
Fail closed: a prefetch that fails (database or anything else) changes nothing for the rows: each reads for itself, as
before. A key the prefetch did not read is read by the row. Every row's answer equals its single route's answer (the
test compares all 9) and its armed index exit shows its own level (23400 + 10 k): a row never shows another row's figures.

NOT done (honest): the target "orders, contracts and settings read once for all rows" is only partly met. Settings
were already one read per request (app_settings and the user's preferences, 2 statements, not per row). The orders and
the traded contracts of a row are read inside `read_tracked` (`adjustment_readers.py::_tracked_on`), and the plan, facts
and records inside `routes/adjustment_check.py::run_check`; both are not in my May edit list. About 18 statements a row
remain.

## Item 2 (I-08)
Covered by item 1's tests, no separate change: 9 rows come back `ok` with lines in one batch read; a row whose read
fails is `refused` with its catalogue sentence and status while the other 8 stay `ok` and equal their single route
(`test_a_failed_shared_read_fails_no_row_and_a_failed_row_is_its_own_refusal`); a row the one time budget did not reach
stays `not_read` (existing #859 tests, still green). No feed-frame recording was added: the batch route's rows
come from the same `watch_of` the page already reads.

## Opus review of items 1 and 2 (Tier A, read-only): PASS, no finding that can cost money
Questions that held: no row shows another row's triggers, contracts, kind or expiry kind; another user's prefetched
triggers never appear and never change a 404; every failure path fails closed; a real or unknown position still gets no
paper stop line; removing the duplicate isolation read leaves no gap (`run_check` does it first). Minor, for batch 2:
M1 triggers and kinds are as of the request start, not each row's own moment (display only, next poll corrects);
M2 `release_connection` and the rollback in `prefetch` sit outside the per-row try, so a broken connection answers 500
for the whole batch (fail closed, no figure shown); M3 the prefetch counts against the 15 s budget but is not under
`wait_for`; M4 no DB test yet for a REAL position with armed triggers in a batch, another user's strategy with armed
triggers (must stay 404), or a memo hit against the single route on a real-book row.

## Item 3 (I-202, O-P-03): running trade, not a draft
Real case (plan row I-202): "A running paper trade shows the Draft Live data not connected heading above the monitoring
badge". New catalogue sentence `outcome_running_not_live` = "Prices are not live". `outcome.not_connected(..., running=True)`
puts it on the answer and on every leg; the route passes `running` when the request names a paper strategy whose book is
readable and holds an open position (`routes/outcome.py::_is_running`). Draft (paper id, no open position), plan (no
paper id), no booked reading and an unreadable book keep "Draft - Live data not connected" (fail closed: only a
readable open position is called running). Test: tests_app/test_outcome_running_b3_1128.py (red first: 2 of 6 failed,
unknown template and draft label; then green, 8 tests with item 4's two). NOT built: the stored close's as-of time. The
no-provider branch has no stored-close reader (`outcome_response` is synchronous and gets no close time); a time would need
the route to read the last-close store and pass it down. Listed under "For the owner lane". W1 screenshot after merge:
not taken (no browser walk in this lane yet; proof level: cloud test).

## Item 4: sentences
- `exit_market_closed_entries` / `exit_market_closed_entries_no_day`: in this tree they already carry NO "The market is
  closed." prefix ("Orders can be placed from 09:15 on {day}." / "Orders can be placed when it opens."), and Lane FD4's pins
  ENTRIES_DAY / ENTRIES_NO_DAY already match them. Nothing to change; no pin or string touched.
- Return door: new key `execute_return_changed` (STRATEGY_VALIDATION_589), the sentence true at Return: "Something changed
  while you were at Zerodha, so nothing was recorded from this return." It never says "no order was prepared" (Lane FD5
  review F1). The route that raises it (`routes/execute.py` `_return`, now `gate_broker_unconfirmed`) is Lane B2's: see
  "For the owner lane". Pins added to tests/errors/template_pins.json as "pending owner read" (only my two keys).

## Item 5 (I-137): deferred issues 860 to 868, 878, 879
All eleven are built and merged on this branch by earlier lanes; nothing left to build here. Not closed on GitHub by me
(closing is the coordinator's); the table is the evidence. Every test below passed this turn, one file at a time.

| issue | state | evidence (commit, test, result this turn) |
|---|---|---|
| 860 plain HH:MM time exit | done | b34ac3ae6 Lane FR item 3; tests/adjustment/test_playbook_eval.py (122 passed with test_stop_lines_fe2_1128.py) |
| 861 generic reason, unknown-kind percent stop | done | 5f70452c4 + 155d962b4; tests/adjustment/test_stop_lines_fe2_1128.py, test_settings_in_force.py |
| 862 stop crossed in one minute, old plan | done | 65a417a70 Lane FE2 item 3; tests_app/test_worker_saved_plan_fe2_1128.py (2 passed) |
| 863 first-listed leg's expiry | done | acbe43f77 + 0ed38945a; test_worker_expiry_fe2_1128.py (2), test_screen_expiry_fr_1128.py (1) |
| 864 `_tracked_on` catalogue per re-read | done | a69866531 + 2d279a5dc; test_kind_cache_fe2_1128.py (5), test_reader_kinds_fr_1128.py (6) |
| 865 unknown-kind timing style pinned | done | a6e9b6dc7; test_unknown_kind_style_fe2_1128.py (2). The owner's confirmation of the style is still his |
| 866 T-06 reason names days left | done (reason code); the wording half stays out as the brief says | 5f70452c4 + 155d962b4; tests/adjustment/test_stop_lines_fe2_1128.py |
| 867 `_checked_body` never cleared | done | 69a08c61a; test_checked_body_fe2_1128.py (2) |
| 868 paused state in worker memory only | done | f7ac668cd; test_pause_restart_fe2_1128.py (5) |
| 878 dropped strategy stays ACTIVE | done | 5d5950ea5; test_dropped_and_skew_fe2_1128.py (6) |
| 879 clock skew widens the window; heartbeat half | done | dec9e5e2b + 5d5950ea5; test_worker_heartbeat.py (27), test_dropped_and_skew_fe2_1128.py |

## Item 6 (I-25): the Plan sheet read
Measured on the cloud DB test (`test_route_latency_budget.py`, scenario ADJ-01): `GET /api/strategies/{id}/adjustment-plan`
= 21 statements (ceiling 21: with the ceiling at 20 the test fails with "21 statements"), and the single-route wall budget
(200 ms alone, instant prices) holds. Under the budget in the cloud; the ceiling already exists, so nothing was added or
raised. What the cloud cannot show: the 17 s of the PC run came over the real link to the database (21 statements at the
link's round trip) and the market and margin reads; that is PC ONLY (cloud-first rule T3). Not fixed, not claimed fixed:
re-time the Plan sheet on the PC after this branch merges.

## Item 7: handed to RA2 and mine
From RA's STATUS: plan-watch nine rows (item 1, done above), the templates sentences (Return door, item 4) and O-P-03
(item 3). Every other item on that list is in Lane B1 or B2's files (worker, monitor, record_plan, request key,
`StrategyOut.position_kind`) and stays theirs. FD5's other wording needs (c) N5 "took too long", (d) expiry_kind_unknown,
(f) six `monitoring_why_*` sentences are not keys this queue names: not touched. `spot_at`: not started, as ordered.

## Review follow-ups (Opus review of items 1 and 2)
M2 fixed (a release or rollback that raises is logged; each row then answers on its own): test
`test_a_release_that_fails_does_not_turn_the_batch_into_a_500`. M4 tests added: a REAL position in a batch gets no paper
stop line; another user's strategy is refused exactly as the single route refuses it. M1 (triggers as of the request
start) and M3 (prefetch outside the 15 s `wait_for`) stay open, display only, listed here for the next pass.

## For the owner lane
- Whoever owns `backend/ofo_app/adjustment_readers.py` and `routes/adjustment_check.py`: give `read_tracked` an optional
  `prefetched` argument (orders by strategy from `paper_book.load_owned_many`, contracts from one
  `tracked_contracts.resolve` of all rows' order contract ids), and let `run_check` take the plan and facts reads for
  many ids. Expected: about 9 statements a row saved on the orders and contracts alone. Then lower `BATCH9_CEILING` in
  `tests_app/test_plan_watch_batch_b3_1128.py`.

- Lane B2 (`routes/execute.py`, `_return`): raise `execute_return_changed` instead of `gate_broker_unconfirmed` when the
  plan or the holdings changed under the Return door (the key exists, pending owner read).
- The route that reads the stored last close (`routes/outcome.py` caller of `outcome_response`; synchronous today): pass the
  stored close's as-of time down so `outcome_running_not_live` can carry it ("with the stored close's time" in the brief).

## Decided for the owner
- The prefetch failing is never a reason to refuse a row (fail closed per row, same answers as the single route).

## Question for the owner
none

## New wording for the owner to read
- `outcome_running_not_live`: "Prices are not live" (on the answer and every leg of a running paper trade with no provider).
- `execute_return_changed` (STRATEGY_VALIDATION_589): what happened "Something changed while you were at Zerodha, so
  nothing was recorded from this return."; impact "Your orders at Zerodha are unchanged; the platform has not stored them as
  placed."; blocked "Recording this return."; next "Open the strategy, check the plan against your Zerodha orders, then press
  Return again."
Both are decision-support wording, pending owner read (pins marked so).

## New test files
- tests_app/test_plan_watch_batch_b3_1128.py (not selected by the #241 diff: nothing to register)
- tests_app/test_outcome_running_b3_1128.py (registered by me in PR241_SELECTION, the coordinator allowed it)

## Models and minutes
| task | model | minutes |
|---|---|---|
| items 1 and 2, build and tests | Sonnet (this session) | about 25 |

## Not done
The stored close's time on `outcome_running_not_live`; the W1 screenshot of I-202; the orders and traded-contracts batching (needs adjustment_readers.py).

SAFE TO CLOSE (head: the commit this file is pushed in; left: the three items above, M1/M3, the PC re-time of the Plan sheet)
