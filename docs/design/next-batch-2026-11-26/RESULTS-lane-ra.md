STATUS 17:40 | DONE (committed): items 1, 2, 3, 4 (N5 N6 N7 N8), 5, 6, 7 (G1, T1), 8 (F4, FEED_MODE no_bus), heartbeat EX 120, issue 876 (a) not reproduced and (b) log line, Opus review fixes F-1 F-2 F-4 | HANDED TO RA2 (not started): plan-watch nine rows, spot_at migration, the templates sentences (Return-door text) and O-P-03 label, FE3 stop-line ids and past tense, T2, F3 (post-commit reads, Opus F-3), F7 and F8 designs (FE4), StrategyOut.position_kind, D-TG-1, durable key decides (item 9), record_plan F2 F4 F5, one market-open clock, the Q3 chain cases (d) to (l) re-run | QUESTIONS FOR THE OWNER stay as written (W-28 word, F3, F2) | blocker: none | LINK TEST 12:02 IST: send_message to @parent REFUSED, exact text: "non-retryable (elevated_session_untrusted_device): the session you named needs proof of a trusted device, and the server would not vouch for this session. Nothing was sent or changed. Do not retry before the owner allows it. This session may not reach its owner's other sessions. This session also has repositories or files attached that its owner has not yet said they trust." (the tool names confirm_repository_trust as the owner's card; I did not call it: it limits this session to the owner's trusted devices for good, which is his decision) | pushed so far: a5259db50; 08c110abe in its check

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
| 4 N5 | fixed (merge: FD5's version of the start, then Opus F-1) | tests_app/test_order_request_key_durable_fd3.py: the deadline starts at arrival (`_stamp_request`, first dependency) and is checked after the last round trip; its own code `order_request_too_slow` and sentence; 20 passed |
| 4 N6 | fixed by Lane FD5 (savepoint in `stored_kind`, always; my narrower variant was dropped in the merge); my claim-and-lock test kept | same file: a failed catalogue read keeps the request-key claim and the strategy row lock |
| 4 N7 | fixed (FD5's after-commit guard plus my before-commit read, Opus F-2) | tests_app/test_paper_triggers_routes.py: 70 passed; F-3 (other post-commit reads) listed |
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

## Item 9: re-runs on this head (before the FD5 merge; the merge touched none of the worker files)
- tests_app/test_d36_adjustment_counts.py: 6 passed. tests_app/test_worker_attaches_confirming_check.py: 1 passed.
- Lane Q3 chain (tests_app/test_plan_stop_worker_chain.py, cases (b) to (g), (i), (j), each about 5 minutes with the real worker process): NOT completed. Cases (a), (b), (c) passed (three dots) in 17 minutes; I stopped the run to merge FD5. Not re-run: (d) to (g), (i), (j), (k), (l). Run them in a worktree on the final head: `python -m pytest -c pytest-app.ini tests_app/test_plan_stop_worker_chain.py` (about 60 minutes).
- Issue 876 case (a), the corrected shape (13 of 27 on, both loss guards `loss_stop_rupees` 80 and T-06 5 percent, loss twice the level held 15 minutes, the worker a SEPARATE process, rules read clear before the loss): tests_app/test_t106_fe4_1128.py::test_t106_d_ra_...: NOT REPRODUCED. The rupee-loss alert comes at once (`plan.rupee_loss`, kind `plan_rupee_loss`) and is still open 15 minutes later, one row, no order placed. Note: with a rupee loss stop typed, `plan.rupee_loss` IS the plan's one loss stop (`rupee_loss_is_the_stop`); T-06 gives no second row, by design. Of the summed outcomes, `already_true` is the one that can swallow an armed loss rule with no alert (a rule true when tracking started and not yet seen clear), then `not_checked gap_after_open` and `no_stage_value`; the PC's rule state says seen_clear true, so none of them explains 207 from the stored facts alone. Part (b) is built: the worker now writes one INFO line per strategy and loss rule (T-06, `plan.rupee_loss`, `stop.credit_x`) that is evaluated and does not alert: `background: loss rule evaluated, no alert: strategy=<id> rule=<rule> outcome=<already_true | not_checked <code>>` (no prices), when the outcome is new or changed; a Flag writes none (tests_app/test_loss_rule_silence_ra_1128.py). On the PC, the next occurrence names itself in the worker log.

## Opus review (read-only, Opus, on a5259db50): REVISE; what was done
- F-1 MAJOR (N5): the 8 s clock started at the handler's first line, after the dependencies (settings, charge rates, the pool wait); a basket could commit 10.5 s after arrival. FIXED: `_stamp_request` is the route's first dependency (arrival), the check is the last step before the commit (after `finish_in_transaction`); test_ra_n5_f1 red on the old start, green now.
- F-2 (merge, N7): two of my N7 tests failed against FD5's `_triggers_out` (a stored stop answered `not_applicable` when the kind read fails after the commit). FIXED: the kind is read BEFORE the commit (`_refuse_real_position` returns it; cancel reads it) and passed to `_triggers_out`; FD5's after-commit guard stays as the fallback. Both tests green (70 passed in the file).
- F-3 (class, MINOR, NOT fixed): any other read after the commit (`list_for`, `tracked_contracts.resolve`, `paper_store.load`) can still answer a stored stop with a 500 (nothing is doubled: a repeat press is de-duplicated; "keep" would answer "already fired"). Design: build the post-commit answer from rows read before the commit (the trigger rows, contracts and book are read in the same transaction, passed to `_triggers_out`), or answer a plain committed-result sentence; needs a decision on the sentence (wording for the owner).
- F-4 (N8, MINOR): the expiry DELETE could wait on rows another order transaction holds. FIXED: the function deletes with `FOR UPDATE SKIP LOCKED` (it never waits). Migration 0062 up, down, up checked again.
- Items 3 (F1, G1) and 4 (F4) PASS; N6 PASS (mutation: a `db.rollback()` back in `stored_kind` fails 2 tests); N8 grants PASS (the application role cannot replace the function, change its path, delete or age a key).
- Not covered by the review: the real Execute door's deadline (`routes/execute.py` still raises `store_busy` past 8 s from its own start), the Redis key store, the rest of the merge.

## Queue of 16:17 and 16:25 (coordinator), state
| Item | State |
|---|---|
| FD5 merge, then FE4 merge | done (FD5 version kept for W-28, N5 start of the deadline replaced by arrival per F-1, N6, N7 with F-2; FE4 had merged clean earlier); the 20 changed test files pass one at a time |
| 1 plan-watch nine rows | not started; design below |
| 2 `spot_at` migration | not started; design below |
| 3 O-P-03 label | not started; design below |
| 4 templates sentences | N5 reason done (`order_request_too_slow`); the Return-door "something changed" text not started |
| 5 FE3 stop-line templates, past tense | not started |
| 6 heartbeat expiry | done (EX 120; tests_app/test_worker_heartbeat.py) |
| 7 Z2 T1 | done (`_skipped_not_paper`); T2 not started (wording only) |
| 8 FEED_MODE | done (reason `no_bus`, sentence pending owner read) |
| 9 durable key decides | not started; design below |
| 10 `record_plan` F2, F4, F5 | not started |
| issue 876 | (a) not reproduced, (b) built: see Item 9 |
| FE4 F7, F8 | designs below (not built) |
| `StrategyOut.position_kind` | not started: a frontend-facing field of `routes/strategies.py` plus the list SQL (`strategy_store._KINDS`); one `kinds_of` call per list read, test: the list names `position_kind` for paper, real, held, none |
| stale xfail marks | none on this base (item 6 of the first list) |

## For the owner lane
- Nothing needs a file outside my May-edit list for items 1 to 8. Frontend: no change (N4 exists).
- New wording for the owner to read (pending owner read; pins carry `reviewed: pending owner read`):
  - `order_request_too_slow` (N5): "This took too long, so no order was stored." / "Nothing was stored and the strategy was not changed; pressing again places the orders once." / "Placing these paper orders." / "Press Place again."
  - `monitoring_why_no_bus` (item 8): "Not being watched here: this server is not set up to share prices with its background worker, so it cannot tell."
  - `real_position_open_refused` and `real_position_add_refused` (F4): the exit sentence word for word ("Real position: exit and protect it in Kite." ...), only the code differs.
- Deploy note (N8): run migration 0062 before or after the code; the application role keeps no DELETE; a SECURITY DEFINER function `public.expire_order_request_keys()` (7 days, no argument) is the only way rows go.

## Decided for the owner
- Item 1: the three tests build the strategy first and patch `kinds_of` after (same state, no change to the door), instead of inserting rows directly.
- Item 1 pool test: made event-driven; the bound stays 0.5 s.
- Item 3 (W-28): `plan_rupee_loss` reads "Plan loss stop", the same word as `plan_loss_stop`: a loss stop typed in rupees and one typed in percent read the same word (ADR-330 (5)(a)); the figures differ. (He may want them apart: see the question below.)
- N5: the deadline counts from the request's arrival; its own refusal code and sentence (new wording above), nothing stored, the key freed.
- N6: Lane FD5's savepoint in `stored_kind` stays (always; two statements per kind read, ceilings raised by FD5 with the reason in the test); my narrower variant (only when a claim or lock is held) was dropped in the merge as the coordinator ordered.
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

## Designs for the items not built (each can be taken by a fresh lane)
- Item 9 (durable key decides): in `request_key.begin`, a Redis record in state `pending` for the same strategy and fingerprint stops refusing `request_key_in_progress`; it returns None (the Redis record is a hint) and the durable claim in the order's transaction (`claim_in_transaction`: INSERT ... ON CONFLICT DO NOTHING, then `Repeated` when another transaction committed first; it waits for an uncommitted claimant) decides. A Redis outage no longer refuses; a durable store failure still refuses with 583. Tests to change: the "unknown outcome keeps the key and a repeat is told still being placed" test in test_order_request_key_durable_fd3.py and the Redis-down refusal test; new test: a pending Redis hint with no durable row lets the repeat place once, and with a durable row replays the first result. Fail-closed check: two concurrent presses with one key store the orders once (the existing two-presses test).
- Item 2 (`spot_at`): one migration 0063 after 0062 adding a nullable `spot_at TIMESTAMPTZ` to the table that holds the basket facts (`BasketFacts`; the column list is in `entry_facts_store`/`record_basket_facts`), INSERT grant extended by that column only, `_index_spot_held` already returns `(spot, at)`; old code keeps working (nullable, additive); up, down, up check.
- Item 1 (plan-watch nine rows): batch the per-row reads in `plan_watch_batch.py` (one orders read, one contracts read, one settings read for all rows, the way W-13 did for the alert labels); FD5 measured about 25 statements per row; target: the batch of 9 rows inside the 10 s page budget, ceiling test with the statement count per row.
- Item 3 (O-P-03): in `routes/outcome.py` (ctx is None branch, `booked` is not None for a strategy with orders) answer a new catalogue sentence `outcome_running_not_live` ("prices are not live", with the stored close and its time) instead of `outcome_not_connected` ("Draft - Live data not connected"); the legs' unpriced label follows. Wording for the owner.
- FE4 F7 (slot clean-up, atomic): a Lua script (read the hash, delete only fields older than the cut-off) used when the client supports `eval`; needs fakeredis with Lua (`lupa`) in requirements-dev.
- FE4 F8 (restored pause starts of a deleted trade): drop `kept` starts of ids not named in the worker's first full cycle after a restart (a failed read must not drop them all).
- One market-open clock (FE4 F7, worker vs monitor near 09:15 and 15:30): both read `may_act.market_state(ctx, ctx.clock())` once per cycle and the worker publishes its instant in the snapshot; the route judges "watched" by that instant.

## To file as deferred issues
- F2 and F3 above (owner decision first).
- The latency ceilings in tests_app/test_route_latency_budget.py count statements; FD5 raised them by two for its savepoint; any further per-request statement must raise them on purpose.

## Models and minutes
| task | model | minutes |
|---|---|---|
| items 1 to 9, build and tests | Sonnet (this session) | about 60 |
| Opus review of N5 to N7, item 5 and G1 | Opus (reviewer agent), read-only | pending |

SAFE TO CLOSE (head: the commit this file is pushed in; what is left: everything listed under HANDED TO RA2 in the STATUS line and under "Not done" / "Designs for the items not built" above)
