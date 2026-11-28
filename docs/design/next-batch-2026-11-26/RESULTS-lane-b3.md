STATUS 00:20 | CLOSING PUSH pending its check: W-02 fix = ONE batch answer of nine rows 219 -> 136 -> 12 -> 10 QUERIES, the same 10 for 3 rows (the count does not grow with rows); at the owner's 134 ms a query that is 10 x 0.134 = 1.3 s of database time, was 88 queries / 11.8 s | fires_at carried by not-checked rows (W-30) | duplicate template dropped, RA2's execution_return_changed used; entries wording pinned to the build, owner question written | wave 1 merged | O-P-03 FRONTEND FIELD: `paper_strategy_id` on the outcome request | blocker: send_message to @parent refused; this line is the report

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

CUT 2 (21:05, the coordinator allowed `adjustment_readers.py` for the plan-watch reads only): `read_tracked` takes an optional
`prefetched=Prefetched(orders, contracts)`; the batch reads every row's paper orders with ONE `load_owned_many` (owner
filter in the query) and resolves the orders' and triggers' contracts with ONE `resolve`. A strategy or contract the
batch did not read is read by the row, exactly as before (a real-book strategy has no paper orders and takes the real
path); `read_tracked` without `prefetched` is unchanged. 9 rows: 162 -> 136 statements (ceiling 136 in
test_plan_watch_batch_b3_1128.py; red first at 140 with 162 measured). Equality test: `read_tracked` with and without
the batch reads returns the same Tracked (the clock stamp `taken_at` aside), with all rows read, with only one row read,
and a missing id stays None. Orders are as of the request start, like the triggers (M1). Total: 219 -> 136, 24 -> 15 a
row; what is left per row sits in `run_check` (plan, facts, records, pause, isolation), not in this lane's files.

EARLIER NOTE (before cut 2): the target "orders, contracts and settings read once for all rows" was only partly met. Settings
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

## PC round 2 W-02 (the owner's real database connection): the cost is round trips, not statements
Measured by the owner on build 829ff65f: 16.4 to 19.3 s per batch answer, 88 queries, 11.8 s of database time (about 134 ms
a query over his connection); in three minutes no planned box showed its rule rows. The cloud had measured 218 ms because
its database is next door, so the statement counts 219 -> 136 were the wrong goal. Built (test first):
- `backend/ofo_app/plan_watch_prefetch.py` (new): the batch reads EVERY table of the check path once for all its rows, in
  ONE statement (`= ANY(:ids)`, each table as an array of rows with native types); then, for the length of the request, the
  session's `execute` answers the check path's per-row statements (recognised by exact text, with the row's id and user
  taken from its parameters) from memory: marker, ownership, pause, entry facts, basket facts, rule memory, plan, open and
  dismissed records, triggers, the ADR-247 time. The per-row code is NOT changed: the same rows go through the same
  converters. Anything unrecognised, any id or user the batch did not read, any write goes to the database as before. A
  reworded store statement stops matching (slower, never different) and `test_every_statement_copy_equals_the_stores_own`
  fails. The ownership statement is learned from `strategy_store.owns` at run time (its SQL has one home).
- Same answer: `test_nine_rows_each_row_its_own_and_a_fixed_number_of_queries` compares every row of the batch with its
  single route and checks each row's own armed level; the read_tracked equality test is unchanged.
- Count, MEASURED on nine strategies: 219 queries before, 10 now (12 at the first push; the rows' orders and the position kinds joined the combined statement). `test_the_query_count_does_not_grow_with_the_number_of_rows`
  runs 3 rows and 9 rows and requires the same count. The 10: 3 request settings, 1 combined read (every table, orders and kinds included), contracts 2,
  the expiry kind of the first row 3 (savepoint, catalogue, release), the ADR-247 time 1.
- The owner's connection, modelled (the repo forbids wall-clock asserts, tests/test_no_wall_clock_asserts.py; a test proves
  cost by counting): 134 ms per query x 10 = 1.3 s, asserted under the plan's 2 s (`LINK_S_PER_QUERY`, `PAGE_BUDGET_S`).
  Before: 88 queries x 134 ms = 11.8 s by the owner's measure.
- Why 11 page requests and not 9 [Likely, not run in a browser]: `frontend/src/components/strategy/PaperStrategies.vue`
  (`watch([planIds, goodReadToken], readPlanBatches)`, about lines 335 to 370) cancels the batch in flight and asks again
  every time a good positions read changes `goodReadToken`; with each answer taking 16 to 19 s, the batch was cancelled by
  the next refresh before it finished (so no rule rows, "Updating the numbers..."), plus up to 3 "not read" re-asks a row.
  The page does not ask twice per row. With an answer of about 1.6 s of database time the race is gone; a frontend lane could
  still let an in-flight batch for the same ids finish instead of cancelling it (`readPlanBatches`, `lib/planWatchQueue.js`).
- Still per answer, not this lane's files: the 3 settings reads of the request dependencies and the savepoint trio of the
  first row's expiry kind could go too (12 -> 6): see "For the owner lane".

- Opus review (Tier A) of this change: REVISE, no finding that can cost money; no row got another row's or another user's
  data in any run (store level, 39 statements compared, and end to end with a pause in force, open and dismissed records,
  entry and basket facts, rule memory, a soft-deleted strategy). Fixed, test first: F1 a strategy id the user does not own
  (or a deleted one) raised inside the prefetch and dropped every shared read (71 queries for 3 rows; now 17 for 3 rows plus
  one missing id, the row's own refusal costs 5); F2 any statement that is not a read now drops the memory, so the
  stop-base backfill's re-read sees the write; F3 a cancellation between the install and the return restores the session;
  F4 the cut-off time memo is kept per parameters. Not fixed, listed: F5 the served rows are namedtuples without
  `_mapping`, `.keys()`, `.scalars()` (every current caller uses first, all, one_or_none, scalar_one_or_none and
  positions or field names); M1 triggers, pause and records are as of the request start for every row.

- Opus review (Tier A, narrow) of the orders and kinds tables and of W-30: orders and kinds served from memory equal the
  database row for row and type for type (13 asked lists, another user, a write and re-reads); REVISE for two points, both fixed
  test first: F1 the plan's rupee PROFIT target (trigger id = rule id = `plan.rupee_profit`) was classified as a stop, so
  W-30 would have shown it at minus its level (`fires_at -600` on a 600 rupee target); it is now a target at plus its
  amount (`target` kind, `distance` rupees still to go). The same one-line classification also corrects the CHECKED line of
  that rule, which showed `stop` / `fires_at -600` / distance 700 before this lane (a wrong figure that existed already:
  recorded under "Found, not assigned" because the brief said checked rows stay unchanged; this row changes from wrong to
  right on purpose); F2 `_serve_many` returned an id's orders twice when the asked list repeated it (`= ANY` returns them
  once; no caller does that today, a position netted twice would double): now once per id.

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
- Return door: my key `execute_return_changed` duplicated Lane RA2's `execution_return_changed` (same sentence, same code
  STRATEGY_VALIDATION_589, and the route uses RA2's). DROPPED at the wave 1 merge (28 Nov 23:50); my test now holds RA2's
  template to the same guard: it must not say "prepared" (Lane FD5 review F1). RA2's sentence passes. The two wordings of
  the entries sentences: see "Question for the owner".

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
- 12 -> 6 queries per answer: `app_settings`, the user's adjustment preferences and `clock_timestamp()` are read once per
  request by the dependencies (settings loaders, market context); one shared read or a short process cache saves 3. The
  expiry-kind catalogue read (savepoint, select, release) of the first row could use a process cache keyed by (underlying,
  expiry) and saves 3 more.
- In-row duplicate reads of the plan-watch/adjustment-check path (RA2's 8 of 27, mapped to call sites this session; none is
  in a file this lane may edit; each is "pass the value already read", output unchanged, statement count pinned by
  `test_query_ceiling` and `BATCH9_CEILING`):
  1. entry facts read twice: `routes/adjustment_check.py:528` (`entry_facts_in(db, id)`) and `adjustment_check.py:731`
     (`evaluate_stored` reads them again): let `evaluate_stored` take `entry_facts=`.
  2. the plan row twice: `adjustment_check.py:219` (`plan_for`) and `plan_saved_before_adr247` right after it: pass `plan`.
  3. the suggestion records twice: `routes/adjustment_check.py:357-359` (`open_suggestions` then `dismissed_holding`, same
     table): one read for both.
  4. the strategy ownership check twice or more (`playbook_store.require_owned`: `rule_states`, `pause_in_force`,
     `open_suggestions`, ... each runs `SELECT 1 FROM strategies`): the check ran once in `run_check` already.
  5. contract rows by id x3 and the token list x2: two of the three now come once for the batch (cut 2); the single route
     still resolves per row (the armed lines and the tracked read each call `resolve`).
- The latency rig: fixed in this lane (`test_route_latency_budget.py` now seeds ten distinct strategies through `seed_rows`;
  before, all ten were id 1). Ceilings were not raised; the 10-concurrent wall budget still holds with ten real rows.
- Frontend (O-P-03, Lane FJ2 or whoever takes it): the label is chosen from the outcome request's `paper_strategy_id`
  (`ofo_app/routes/outcome.py::get_booked`, the strategy has an open position). The builder sends it (`bookedFields`,
  `frontend/src/lib/targetBlock.js`); a page that shows the "Draft - Live data not connected" heading for a running trade
  must send `paper_strategy_id` in its outcome request, else it still gets the draft label. [Guessing] which page that is;
  I did not trace it in the frontend (not my files).
- (DONE in cut 2 for `read_tracked`; the plan, facts and records reads in `run_check` remain) Whoever owns `routes/adjustment_check.py`: give `read_tracked` an optional
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
The Add-to-Paper dialog line shown when the market is closed was worded two ways by two lanes (28 Nov):
- Lane FD4 / this lane's first reading (no prefix): "Orders can be placed from 09:15 on Monday 30 Nov." and "Orders can be placed when it opens."
- Lane RA2 item 9, the wording IN THE BUILD (prefix added, pins moved with it): "The market is closed. Orders can be placed from
  09:15 on Monday 30 Nov." and "The market is closed. Orders can be placed when it opens."
Is the prefix printed twice on a screen? In `PaperConfirmDialog.vue` the dialog prints ONE line, the server's `entries_sentence`
alone (`marketLine`); with the build's wording it reads "The market is closed. Orders can be placed when it opens." once. If
that dialog shows another "The market is closed." line beside it, the prefix repeats; I could not see the rendered screen
from the cloud. Until the owner answers, `test_the_entries_sentences_are_the_wording_in_the_build` pins the build's wording.

## Found, not assigned
- The plan's rupee PROFIT target line showed `kind stop`, `fires_at` minus its amount and a wrong distance before this lane
  (`routes/plan_watch.py`, kind mapping by trigger id `T-07` only; the rupee rows' trigger id is `plan.rupee_profit`).
  Changed here by the same classification fix that W-30 needed; tell the board that a CHECKED rupee-profit line's figures
  moved (from wrong to right). Evidence: `tests_app/test_plan_watch_fires_at_b3_1128.py` (evaluator ids).
- `frontend/src/components/strategy/PaperStrategies.vue` (`watch([planIds, goodReadToken], readPlanBatches)`, about lines 335 to
  370) cancels the batch in flight each time a good positions read changes `goodReadToken`; on the owner's connection (16 to 19 s
  an answer) the batch never finished, which fits "no planned box showed its rule rows" and 11 requests in 3 minutes. [Likely,
  not run in a browser.] With a 1.3 s answer the race should be gone; letting an in-flight batch for the same ids finish is
  the safer page behaviour.
- The Opus review's minor points on `plan_watch_prefetch.py` (served rows are namedtuples without `_mapping` / `.keys()` /
  `.scalars()`; reads are as of the request start for every row): listed above under the review, not defects today.
- Items still outside this lane's files (see "For the owner lane"): the 3 per-request settings reads, the first row's
  expiry-kind catalogue read, and the in-row duplicate reads of the single route (`run_check`).

## New wording for the owner to read
- `outcome_running_not_live`: "Prices are not live" (on the answer and every leg of a running paper trade with no provider).
- (DROPPED, 28 Nov 23:50: Lane RA2's `execution_return_changed` carries the same sentence, code 589 and is used by the route; the guard
  "must not say no order was prepared" is kept in `test_the_return_door_changed_sentence_does_not_claim_no_order_was_prepared`.) was: what happened "Something changed while you were at Zerodha, so
  nothing was recorded from this return."; impact "Your orders at Zerodha are unchanged; the platform has not stored them as
  placed."; blocked "Recording this return."; next "Open the strategy, check the plan against your Zerodha orders, then press
  Return again."
Both are decision-support wording, pending owner read (pins marked so).

## New test files
- tests_app/test_plan_watch_batch_b3_1128.py (not selected by the #241 diff: nothing to register)
- tests_app/test_outcome_running_b3_1128.py (registered by me in PR241_SELECTION, the coordinator allowed it)
- tests_app/test_plan_watch_fires_at_b3_1128.py (stand-ins, no database; not selected by the #241 diff)

## Models and minutes
| task | model | minutes |
|---|---|---|
| items 1 and 2, build and tests | Sonnet (this session) | about 25 |

## Not done
The stored close's time on `outcome_running_not_live`; the W1 screenshot of I-202; the orders and traded-contracts batching (needs adjustment_readers.py).

SAFE TO CLOSE (head: the commit this file is pushed in; left: the three items above, M1/M3, the PC re-time of the Plan sheet)

## Friction (for the coordinator to copy into docs/process/friction-log.md, which is not in this lane's files)
| what cost time | cost | proposed fix |
|---|---|---|
| A fresh cloud session had no Python or frontend dependencies: DB tests failed on `import httpx`, the first `prepush.py` stopped at "frontend/node_modules is missing", and the test database had no migrations | about 15 min, the 1 h check's first start wasted | the environment setup script runs `pip install -r requirements-app.txt -r requirements-dev.txt`, `npm ci` in frontend/ and the alembic upgrade through `db_run.py` |
| `send_message` to the coordinator refused 3 times (elevated_session_untrusted_device); the coordinator reached the lane but the lane could not answer | no report channel except the STATUS line | the owner decides on the trust card, or the brief says "STATUS line is the report" up front |
| `git checkout <file>` blocked by the discard guard for a file holding only my own probe | 2 retries | none needed; the guard is right, remove a probe with an edit |
| The shared test database `ofo_test` (the template per-file clones copy) held rows left by a run that wrote to it directly: a check I stopped mid-run, or a helper's run without `OFO_TEST_DB_PER_FILE=1`; the next file then met "8 leg stops, expected 2" | 20 min of reading | clear with `SET LOCAL session_replication_role = replica; TRUNCATE public.strategies CASCADE; TRUNCATE public.catalogue_contracts CASCADE` in one transaction (the alert-style guard refuses a plain truncate); better: `db_run.py` refuses a write run on `ofo_test` itself without the per-file flag |
