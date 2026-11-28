STATUS 08:58 | items 1-3 PASS pushed (9facc09); item 4 NOT reproduced; item 5 DONE (29 failed / 8104 passed), push pending gate | next: none | blocker: none (parent session refused my message: untrusted device; this line is the report)

# Lane TF results (branch test/r2-gaps-1128, base integration/weekend-1127)

Status wording: highest claim is "Fixed, not tested" for product; these are tests only.

## Items
| # | Item | State | Test / count |
|---|------|-------|--------------|
| 1 | I-51 stops warning | PASS, pushed 2cad4f3 | tests_app/test_leg_stop_lines_tf_1128.py: 9 passed (fresh PostgreSQL 16, ofo_app role). Mutation: removing "(worst case: {index} at zero)" from the template makes 5 of 9 fail; reverted. |
| 2 | I-125 | PASS, pushed e6dbcb2 | tests_app/test_plan_rebuild_tf_1128.py: 2 passed (worker as its own process, PATH-90, private database). Mutation: REBUILD_SECONDS 10 -> 20 makes both fail; reverted. |
| 3 | I-80 DB half | PASS, pushed 9facc09 | tests_app/test_bulk_delete_undo_tf_1128.py: 6 passed (35 s, one case waits a real 31 s). Mutations: a 30 s expiry on the Undo query fails the hold case; dropping `deleted_at IS NOT NULL` from the Undo query fails the double-Undo case; both reverted. Already covered before (not repeated): test_strategy_bulk_delete.py (12 deleted/2 kept with 3 running, summary forms, stale/foreign ids, one failing item, per-id Undo of a batch) and test_history_delete_entries.py (3-row bulk delete and Undo write Deleted + Restored). Added: Undo after the 30 s hold, Dismiss leaves rows/history/paper orders kept, partial Undo, double Undo, stale-revision Undo, a running paper trade deleted, off the worker list, back with its orders. |
| 4 | I-74 browser | NOT REPRODUCED after two honest tries (steps below); nothing to pin | no test added |
| 5 | Whole tests_app suite | DONE, FAILURES | 29 failed, 8104 passed, 6 skipped, 23 deselected (full_chain), 3 xfailed in 61 min 10 s; fresh database, CI's flags and environment incl. GITHUB_ACTIONS=true, Redis up; 18 of the 29 failing tests named below (details under Item 5) |

## Defects found
- Item 5: see "Item 5": 29 failing tests; (a) and (b) are for a fix lane (stale key sets; statement ceilings one over on adjustment-check, adjustment-plan, plan-watch).
- Item 4: see the side observation (builder `?strategy=1` says the paper position could not be read, no failing request).
- (item 1, observation, not a defect) ADR-330 (55) F2 case: a bare put whose max loss comes from elsewhere prints
  "Max loss then: Rs 17,65,125.00." with no case named (tests_app/test_leg_stop_risk.py, test_55_review_f2). The loss
  figure is then not labelled "worst case"; this follows the ADR text ("named only when true"). If the owner wants every
  figure labelled, that is a wording decision for a fix lane.

## Item 4 (I-74): steps and what was seen
Set-up: PostgreSQL 16, database named exactly `ofo_dev` (fresh, migrated to 0059), the app's own scenario catalogue, API `uvicorn ofo_app.main:create_app` on 8765
(APP_ENV=development, OFO_SCENARIO), `vite preview` on 4173 proxying `/api` to it, the scenario worker `python -m ofo_app.background`, preinstalled
Chromium through Playwright (no `playwright install`). All servers stopped by PID at the end. Screenshots stayed in the container (not in the repo).
- Try 1, `OFO_SCENARIO=ADJ-02`, `scripts/seed_scenario.py ADJ-02` (strategy 1), plan from the system iron-condor playbook saved with `playbook_store.accept_plan`:
  `GET /strategies/1/adjustment-check` answers T-01, T-03, T-09 as flags and A-26 suggested, but every `suggestion_id` is null and
  `public.adjustment_suggestions` stays empty: the worker log says "strategy 1 check skipped: not_ticked" (a one-frame ADJ scenario never ticks, even after
  `scenario_mode.write_frame`). So no alert exists to open the builder from. Alerts page: "No alerts yet".
- Try 2, `OFO_SCENARIO=PATH-90` (the path scenario of Lane Q3's chain), seeded, pinned `intraday`, plan with a Rs 1,000 loss stop, frames 0 to 2 written: one open
  alert "Plan rupee stop: 4608.5000 (rule 1000.0000), fired at 11:42" with "Exit the position" and "Continue with the position". Clicking "Exit the position" opens
  the exit sheet on the Alerts page itself (not the builder) with all 4 legs listed (NIFTY 9 Nov 22800 PE, 23400 CE, 22600 PE, 23600 CE), each Exit, about prices,
  Cancel / Confirm: legs shown. Nothing was confirmed. The builder opened by URL with the alert id (`/strategy/builder?strategy=1&adjust=1&basket=4`) shows the trade
  ("Open legs 4", the four legs with IV/OI/LTP). Neither scenario produces an adjustment opportunity with a prepared basket, which is the precondition of the 27 Nov 13:03 case
  (ADR-330 (53)); so the case is NOT reproduced and no pin is written. A real one needs an opportunity that opens (a tick on an ADJ scenario) on the PC.
- Side observation, not proven to be I-74 (for a fix lane): `/strategy/builder?strategy=1` alone (no `adjust`) on PATH-90 shows "This strategy's paper position could not be
  read, so it is not shown. Try again." and no legs, on 3 loads in 2 sessions, while `GET /paper/strategies/1` answers 200 with legs and greeks and the page
  sees no failing request (no HTTP status >= 400, no failed request, no page error). Steps: seed PATH-90 as above, open that URL, wait 9 s.

## Item 5: the whole tests_app suite, once
Command (CI's own): `python -m pytest -c pytest-app.ini -q -rs --durations=60 -p no:cacheprovider -m "not full_chain"` with OFO_REQUIRE_DB_TESTS=1,
TEST_DATABASE_URL (role ofo_app) and TEST_ADMIN_DATABASE_URL (postgres) on a freshly created and migrated (0059) database, REDIS_URL, the throwaway broker settings, the
history-scale variables, and `GITHUB_ACTIONS=true` (this is what makes conftest clone one database per file; see below). Started 07:48 IST, 61 min.
Result: **29 failed, 8104 passed, 6 skipped, 23 deselected, 3 xfailed.** The first failure is at about 2 percent, not at 17 percent.
CI's `-rs` prints no list of failed tests, and the log was interleaved with debug prints, so 18 of the 29 failing tests are named (file | test | first error line); the other 11
were not recovered: re-run the files below with `-rf` to name them.
- test_alert_routes.py | test_active_answer_history_replies_and_errors (and test_a_worse_reading_shows_escalated_at_and_the_worse_line_in_active_and_history) | reply key set has extra 'position_kind', 'position_kind_text'
- test_background_worker.py | test_a_fired_stop_note_is_stored_when_the_monitor_clock_is_ahead, test_a_plan_stop_alert_is_stored_when_the_worker_clock_is_ahead | TooManyConnectionsError: too many connections for role "ofo_app" (the role has CONNECTION LIMIT 5)
- test_d38_page_counts.py | test_plan_counts_and_reply | "plan: the reply changed"
- test_egress_gate_doors.py | test_r2_a_passed_in_raw_httpx_client, test_r2_the_login_adapter_with_a_raw_client, test_r3_unicode_dot_host_from_a_non_door_module | httpcore.ProxyError: 502 Bad Gateway / KiteExchangeError('kite_unavailable') (the container's outbound proxy)
- test_execution_return.py | test_real_first_fill_stores_entry_facts_once[ltp0-iv0-stored0] and [ltp1-None-stored1] | INTERNAL_SYSTEM_002 "An unexpected server error stopped this request"
- test_migration_0059_last_close.py | test_attack2_user_profile_outside_the_door_is_refused_by_the_egress_gate | urllib.error.HTTPError: HTTP Error 400 (outbound proxy)
- test_pinned_clock.py | test_seed_then_routes_offer_the_fixture_only_under_the_pin | dict mismatch ('default_exp...')
- test_pool_not_held_across_market_wait.py | test_plan_watch_connections_held_while_the_rest_reader_stalls | "the REST reader was not reached"
- test_risk_exit_not_gated.py | test_a_gated_adjustment_rule_never_delays_the_conditional_exit | `[] == [(1, 'open')]`
- test_route_latency_budget.py | test_query_ceiling[adjustment-check] 20 vs 19, [adjustment-plan] 19 vs 18, [plan-watch] 24 vs 23 | statement count one over the ceiling
- test_slow_price_source_live_day.py | test_batch_plan_watch_query_ceiling | "batch of one row: 24 statements"
- (file not recovered) | test_a_5_second_stalled_quote_does_not_make_live_ticks_not_live

Proven cause for the first failing group (test_alert_routes.py, preceded by test_alert_preferences.py), on fresh databases each time:
1. alone: 2 failed, 8 passed. 2. after test_alert_preferences.py: 2 failed, 18 passed. 3. same with GITHUB_ACTIONS=true: 2 failed, 18 passed.
So it is NOT rows left behind: it fails alone on a fresh database. First error (tests_app/test_alert_routes.py:46): the reply has two extra keys, `position_kind` and
`position_kind_text` (ADR-330 (64)); the test's expected key set was not updated. A wrong (stale) test, not a product defect. Fix: add the two keys to the expected set (test file; fix lane).
- test_clock_ahead_records.py (Lane Z/TE's list): passes alone (2 passed) and after its predecessor test_checked_basket_proof_params.py (4 passed, with and without GITHUB_ACTIONS); in this
  run it is not in the failing list. So the "rows left behind" reading is NOT proven by this run for it.
- Cause of the earlier Lane Z/TE failures: unproven. What this run shows instead: with per-file clones on (GITHUB_ACTIONS=true) the failures come from (a) stale tests (test_alert_routes,
  likely test_d38_page_counts, test_pinned_clock), (b) statement ceilings one over (test_route_latency_budget x3, test_slow_price_source_live_day): a real, small product drift to
  fix or re-baseline, (c) the container's outbound proxy (test_egress_gate_doors x3, test_migration_0059_last_close): environment only, CI has no proxy, (d) role connection limit
  (test_background_worker x2: CONNECTION LIMIT 5 plus many open pools), (e) test_execution_return, test_risk_exit_not_gated, test_pool_not_held_across_market_wait: not analysed (out of time).
  Whether the same files also fail on Friday's untouched base was not run.

## Decided for the owner
- Item 1: "short" pinned as each line at most 80 characters (real longest is 59), exactly three lines, one fact per line.

- Item 2: the wait window is 10 s + 4 s slack counted in polls (no clock read, tests/test_no_wall_clock_asserts.py). The
  slack covers one re-list's run time; Lane TE's 15 s is outside it. Observable used: the worker's own log line
  "background: N strategies monitored" (written at the end of every rebuild), no product seam added.
- Item 2: the plan-removed direction was not tested (the table that holds a plan was not verified); not claimed.

- Item 3: Dismiss and the 30 s hold are on-screen only (frontend/src/pages/MyStrategiesPage.vue); the server half pinned is: no expiry on Undo, nothing purged. The screen half is Lane TB's / the owner's T2-09 on the PC.

## For the owner lane
- none yet

## Pending owner read (new on-screen sentences)
- none (tests only)

## To file as deferred issues
- tests_app: stale key set in test_alert_routes.py:46 (position_kind, position_kind_text); the 4 statement-ceiling tests; the unanalysed three of item 5.
- none yet

## Set-up notes
- No scripts/orchestrator/cloud_services.sh in this branch: used `pg_ctlcluster 16 main start`, redis-server, roles as
  app-tests.yml, `pip install -r requirements-app.txt -r requirements-dev.txt` (container had none).

## Models
| task | model | minutes |
|------|-------|---------|
| item 1 | Sonnet | 20 |
| gate runs (3, env fixes) | Sonnet | 60 |
| item 2 | Sonnet | 25 |
| item 3 | Sonnet | 25 |
