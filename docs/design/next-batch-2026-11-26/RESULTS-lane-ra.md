STATUS 16:25 | queue 1-9 built and committed on fix/r3-leftovers-1128, gate on the head running, Opus review pending | next push when the gate ends TOTAL PASS | blocker: none (the message to the coordinator is refused: needs the owner's device trust; this line is the report)

# Lane RA: round 3 leftovers (base integration/weekend-r2-1128 17385d88, merged fix/r4-worker-4-1128: clean, no conflict)

Highest claimable status: Fixed, not tested (no PC test run). Local database: PostgreSQL 16 built as the CI job builds it
(`ofo_test`, role `ofo_app` non-superuser), one test file at a time (`OFO_TEST_DB_PER_FILE=1`), proxy variables unset.
Ruff for the ratchet: the pinned `ruff==0.15.12` (`pip install ruff==0.15.12`), not the one at /root/.local/bin (0.16.9 counts
other rules).

## What was done (queue order)
| Item | State | Evidence (test file, counts this head) |
|---|---|---|
| 1 three failing tests | fixed | tests_app/test_real_position_stops_fe2_1128.py: before: `StrategyRefused: real_position_exit_refused` at paper_store.py:140 (raised from the `_strategy` helper's `paper_store.place`, because the tests patched `kinds_of` to "unknown" BEFORE building the strategy); after: 5 passed. The door is untouched. |
| 1 timing test | machine speed, not a hold | see "Item 1: the pool test" |
| 2 N2 route half | fixed | tests_app/test_monitoring_status_route.py: 10 passed (red before: 2 failed); test_reasons_fe4_1128.py 27 passed |
| 3 W-28 | fixed | tests_app/test_alert_routes.py: the new pin passed; `_KIND_WORDS["plan_rupee_loss"] = "Plan loss stop"` |
| 4 N4 | already fixed on this head (Lane FJ 00345b57d), test exists | frontend/tests/stops-not-applicable-real-r3-fj.test.js: 5 passed. No change. |
| 4 N5 | fixed | tests_app/test_order_request_key_durable_fd3.py: the deadline starts at the request's arrival (`_stamp_request`, the first dependency, before the pool wait); its own code `order_request_too_slow` and sentence; red before (new test failed on the old start point), then 19 passed |
| 4 N6 | fixed | same file: a failed catalogue read keeps the request-key claim and the strategy row lock; the savepoint is taken only when one is held (`ofo_app/txn_holds.py`), so the latency ceilings (tests_app/test_route_latency_budget.py: 7 passed, 1 xfailed as before) are not raised; red before (`request_key_store_unavailable`) |
| 4 N7 | fixed | tests_app/test_paper_triggers_routes.py: 3 new tests; the kind is read before the commit and handed to `_triggers_out`; red before (500 after a stored stop), then 70 passed |
| 4 N8 | fixed | migration 0062 (one head, up, down, up checked; migration guard OK); tests in test_order_request_key_durable_fd3.py: the app role inserts the 6 columns only, cannot DELETE; expiry removes only rows older than 7 days |
| 5 F1 | green, no fix needed | tests_app/test_held_stop_ra_1128.py: a stop armed BEFORE the held row exists: 0 fires, no stop order, left armed, reported once; market open and closed. Mutation: without `_paper_only` both cases fail. |
| 6 slow-price marks | nothing to remove on this base | the three strict marks are not in tests_app/test_slow_price_source_live_day.py on this head (they exist only on other branches); 10 passed as plain tests |
| 7 G1 stop/settle | fixed | paper_store.py: a `stop` is refused (real_position_exit_refused) unless the position reads paper; `settle` stays allowed (ADR-292 line 22); both pinned in test_held_stop_ra_1128.py |
| 8 F4 | fixed | own codes `real_position_open_refused`, `real_position_add_refused`, `real_position_exit_refused`; one sentence word for word; tests/errors 711 passed |
| 8 F2, F3 | not changed | see "Question for the owner" |
| 9 re-runs | see "Item 9" | |

## Item 1: the pool test (cause)
Z2 saw `test_thread_executor_stalled_by_broker_reads_does_not_slow_health_or_the_paper_read` fail; FE4 saw
`test_plan_watch_connections_held_while_the_rest_reader_stalls` fail its precondition on a Saturday clock. Not reproduced
idle here on a Saturday clock (3 of 3 green before the change). Measured with a probe: the fixed `sleep(0.3)` / `sleep(0.5)`
snapshot fell inside each request's own database phase (about 25 queries, 150 to 335 ms of work per request, on 4 cores); there
the pool reads `checkedout=4` once and `0` once for the same code, and /health (it takes a pooled connection) queues behind
the 4 connections. Under 6 busy CPU loops the OLD test failed 3 of 5 (paper mix, plan-watch measure, executor test); the NEW
passes 5 of 5 under the same load and 3 of 3 idle. So: machine speed, not a hold across the wait (plan-watch's `run_check` calls
`release_connection` before the REST read, D-36 (c)). Fix: the measurement starts only after every stalled reader was reached
(event-driven, at most 20 s, then a stated failure); the 0.5 s /health bound is not widened. After that point /health takes
0.01 s and the pool reads 0 checked out. The `reads == 0` case of FE4 (Saturday clock) could not be reproduced; with the
wait it can no longer fail by timing, and "not reached" is now a stated failure.

## Item 9: re-runs on this head
(counts are filled in below when the runs end)

## For the owner lane
- Nothing needs a file outside my May-edit list for items 1 to 8. Frontend: no change (N4 exists).
- New wording for the owner to read (pending owner read; pins carry `reviewed: pending owner read`):
  - `order_request_too_slow` (N5): "This took too long, so no order was stored." / "Nothing was stored and the strategy was not changed; pressing again places the orders once." / "Placing these paper orders." / "Press Place again."
  - `real_position_open_refused` and `real_position_add_refused` (F4): the exit sentence word for word ("Real position: exit and protect it in Kite." ...), only the code differs.
- Deploy note (N8): run migration 0062 before or after the code; the application role keeps no DELETE; a SECURITY DEFINER function `public.expire_order_request_keys()` (7 days, no argument) is the only way rows go.

## Decided for the owner
- Item 1: the three tests build the strategy first and patch `kinds_of` after (same state, no change to the door), instead of inserting rows directly.
- Item 1 pool test: made event-driven; the bound stays 0.5 s.
- Item 3 (W-28): `plan_rupee_loss` reads "Plan loss stop", the same word as `plan_loss_stop`: a loss stop typed in rupees and one typed in percent read the same word (ADR-330 (5)(a)); the figures differ. (He may want them apart: see the question below.)
- N5: the deadline counts from the request's arrival; its own refusal code and sentence (new wording above), nothing stored, the key freed.
- N6: a savepoint around the catalogue read only when the session holds a claim or the strategy row lock (a read-only request pays no extra statement; the explicit statement-count ceilings are untouched).
- N8: the expiry is a SECURITY DEFINER function with a fixed 7-day window instead of a DELETE grant to the application role (a DELETE grant would let the role remove a fresh key, the guard against a double order). The claim path runs it at most once an hour per process, in its own savepoint; a failure is logged and never touches the claim.
- G1: `settle` is allowed on a held or real position because ADR-292 line 22 says a held condor settles at expiry through the paper settlement (the contract expired at the exchange: a fact, not an action on the real position); `stop` is refused unless the position reads paper. Pinned both ways.
- F2, F3: left as they are (fail closed; see the question).
- Item 6: nothing to do on this base.

## Question for the owner
1. W-28: should a loss stop typed in rupees and one typed in percent read the same word on Alerts > Active ("Plan loss stop"), or apart ("Plan rupee stop" / "Plan loss stop")? Recommendation: the same word (ADR-330 (5)(a)); the figure already tells the unit.
2. F3 (Lane FD5 review): an execution plan row that was prepared but never sent still makes the strategy read as a real position, so paper orders are refused with the Kite sentence. Two of his rules clash: fail closed, because the app cannot see whether the basket was sent in Kite (ADR-016 to ADR-019), against "an unsent form must not block practice". Recommendation: keep fail-closed, and add an explicit "I did not send it" button on the plan that closes the open plan row (a deliberate act, so nothing is guessed).
3. F2 (Lane FD5 review, order path on only): a paper order placed first and a real basket sent after reads as PAPER (`kind_of`: a paper order and no held entry). Treating it as real would turn off the stops of a paper trade whose user only opened Execute and abandoned the form (the same ambiguity as F3). Recommendation: decide F3 first; then a strategy with both a plan row and paper orders reads "unknown" (neither Exit nor Stops, with the line saying why) until the owner or the user states which it is.

## Not done (exact designs so a fresh lane can take them; nothing is left half built)
- Worker slot clean-up (FE3 F7): `monitoring_state.py` lines ~573 to 588 read the exit-slot hash (`hgetall`) and `hdel` the slots older than an hour in two steps; a monitor that writes between them loses its fresh slot for up to 10 s. Design: one Redis Lua script (`EVAL`: read the hash, delete only fields whose `at` is older than the cut-off, return them), used when the client supports `eval`; the bare get/set test doubles keep today's two-step path. Test on real Redis: a monitor refreshing its slot between the read and the delete keeps its slot (the script makes the window zero), plus a test on the fallback path. Needs real Redis in the test; not built here because the repo's Redis stand-in (fakeredis) must run Lua (`pip install fakeredis[lua]`) and `requirements-dev.txt` pins no lupa.
- Restored pause start times (FE3 F8): `Publisher.restore` brings back `kept` pause starts of a trade that was deleted in the meantime; if the deleted trade's id comes back with the same reason it shows the old "since". Design: the worker only restores a kept start for an id it answers in its FIRST cycle; ids not named in the first full cycle are dropped from `kept` at the end of that cycle (so a deleted trade's start never outlives one cycle). Test: restore with ids {1, 2}, first cycle names {1}: after the cycle `kept` holds only 1. Not built: it needs the worker's cycle loop and a decision whether "first full cycle" means the cycle after the strategies read succeeded (a failed read must not drop every kept start).
- One market-open clock for the worker and the monitor (FE4 F7): the worker decides with `market_closed_for(provider, now)` (`background.py::feed_state`, its own `now`), the monitor with `may_act.market_open(feed.ctx, now)` (the feed context's clock); near 09:15 and 15:30 the two `now` values can sit on different sides of the bell for seconds, so a trade reads "watched" while the monitor does not fire, or the reverse. Design: both call `may_act.market_state(ctx, at)` with `at = ctx.clock()` read ONCE per worker cycle and once per monitor step, and the worker publishes its `at` in the snapshot (`monitoring_state` already carries a stamp); the reader (route) judges "watched" with the market state of the snapshot's `at`, never its own clock. Test: a fake ctx clock at 09:14:59 then 09:15:01 across one worker cycle and one monitor step; both answer from the same instant. Not built: it touches `background.py` and `paper_monitor.py` market judgements at once, and needs the settings-reader guard that names `paper_monitor.py` by line number updated (the guard's own test) in the same change.
- Lane Q3 cases (b) to (g), (i), (j), test_worker_attaches_confirming_check.py and test_d36_adjustment_counts.py re-run: see "Item 9" counts.
- Frontend: nothing. N4 was already fixed.

## To file as deferred issues
- F2 and F3 above (owner decision first).
- The latency ceilings in tests_app/test_route_latency_budget.py count statements; a SAVEPOINT is two statements: any future per-request savepoint must go through `txn_holds` or raise the ceilings on purpose.

## Models and minutes
| task | model | minutes |
|---|---|---|
| items 1 to 9, build and tests | Sonnet (this session) | about 60 |
| Opus review of N5 to N7, item 5 and G1 | Opus (reviewer agent), read-only | pending |
