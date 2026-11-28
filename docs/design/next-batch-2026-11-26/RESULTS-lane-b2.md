STATUS 19:15 | batch 1 (items 1 to 3) and item 5 built and committed locally; Opus review and the full check next | next push (batch 1) due 22:30 | blocker: send_message to @parent REFUSED (elevated_session_untrusted_device, same text as Lane RA's link test); this STATUS line on the pushed branch is the report

# Lane B2: the order-door and request-key backend lane (round 3, weekend)

Branch fix/r3-backend-b2-1128, from integration/weekend-r3-1129 (e2da71f50) with RA's 951aa698c merged (clean).
Highest claimable status: Fixed, not tested (no PC run). Local database as the CI job builds it
(`scripts/orchestrator/cloud_services.sh`), one test file at a time (`OFO_TEST_DB_PER_FILE=1`), proxy variables unset.

## What was done
| Item | State | Evidence |
|---|---|---|
| 1 I-186 F2 (re-check adopted holdings and the revision in the plan's transaction) | already built by Lane FD5 item C (`_refuse_if_changed`, under the strategy lock, right before `record_plan`, same transaction; `record_plan`'s only caller is that door). Not rebuilt. Mutation done here: with the call removed, `test_r3_a_holding_adopted_during_the_waits...` and `test_r3_a_strategy_saved_during_the_waits...` go red (2 failed); with it, 16 passed | tests_app/test_execute_revision.py |
| 1 F4 | done by Lane RA (item 8): not redone | |
| 1 F5 (a plan-only strategy: 409 before 404) | already built by Lane FD5 item E (`exit_tracking` refuses a real or unknown position first, tracking.py:551), pinned by `test_f5_a_plan_only_real_strategy_answers_the_real_position_refusal_before_not_found`, which passes on this head. `record_plan` has no 404 path after `lock_strategy`: every `PlanStoreError` is one 409 (`gate_dependencies_unsatisfied`) at the door | tests_app/test_exit_door_real_fd3.py (13 of 14 pass; the one failure is outside my items, see "For the owner lane") |
| 2 (a) the tracking exit refuses an unknown kind | already built (FD3 item 1, FD5 item E); `test_i158_an_unknown_kind_is_refused_at_the_tracking_exit` passes | tests_app/test_exit_door_real_fd3.py |
| 2 (b) durable key decides | built: `request_key.begin` returns None for a `pending` Redis record of the same strategy and body (a hint) and for a Redis that is down; `claim_in_transaction` (INSERT ... ON CONFLICT DO NOTHING, waits for an uncommitted claimant, `Repeated` after its commit) decides; a durable table that cannot be read still refuses 583 (`lookup`). Other strategy (580) and other body (581) still refuse at the hint. Core test red before (582 and 583), 4 passed after | tests_app/test_request_key_b2_1128.py 4 passed; test_order_request_key_r2_fd2.py 12 passed; test_order_request_key_durable_fd3.py 20 passed; test_execution_plan_store.py 103 passed |
| 3 Execute door deadline | built: `_stamp_request` is the router's first dependency (arrival), the check follows `finish_in_transaction`, own code `order_request_too_slow` (was `store_busy`, counted from the handler's first line). Red before (200 at 10.5 s after arrival), green after | tests_app/test_execute_revision.py 16 passed (new: test_b2_item3_...; changed: test_g_...) |
| 4 I-183 same-key resend after the durable claim | falls out of item 2; pinned by `test_core_a_pending_redis_hint...` (the second press replays, count unchanged) and the changed `test_an_unknown_outcome_leaves_a_hint...` | same files |
| 5 `StrategyOut.position_kind` / `position_kind_text` | built (`_kind_of` via `store.kinds_of` and `position_kind.line_of`; a failed read answers "unknown", never paper; own savepoint). Red 4 of 4 before, green after; detail equals list for paper, held (real), plan-only (real), draft (none) | tests_app/test_strategy_kind_b2_1128.py 4 passed; test_response_door.py 215 passed (golden bytes updated, new fields after `versions`); test_reply_inventory.py 24 passed (two reviewer notes written); test_route_latency_budget.py 7 passed, 1 xfailed |

## Decided for the owner
- Item 2: Redis is a hint. A Redis outage no longer refuses a keyed order (it was 503, code 583): the durable table decides, and a table that cannot be read still refuses. A request whose first try crashed after the commit began no longer sits behind 582 for 10 minutes: the repeat finds the committed row (replay) or places once.
- Item 2: a second request that passed the hint and is then refused calls `free` on the Redis record, which may delete the first request's still-running hint. No money effect (the table guards the double order); a later press during the first one's run also passes the hint and waits on the durable claim.
- Item 3: the same refusal sentence as the paper door (`order_request_too_slow`), no new wording.
- Item 5: `position_kind` costs one extra statement per StrategyOut answer; a failed read is "unknown" (fail closed). The latency budget test still passes.
- RA's F3 and F2: not built, the fail-closed reading kept.

## Question for the owner
- RA's F3 (a prepared but never sent plan row reads as a real position, so paper orders are refused) and F2 (a paper order first, then a real basket reads as paper): unchanged, owner decision first (RESULTS-lane-ra, "Question for the owner" 2 and 3).

## For the owner lane
- Lane B1: `tests_app/test_exit_door_real_fd3.py::test_n7_a_stop_stored_then_a_failed_kind_read_still_answers_success_with_the_line_unknown` fails on this base (`assert calls["n"] >= 2`, got 1): RA's F-2 moved the kind read before the commit, so the "second call fails" step is never reached. The assertion should be `>= 1` (the stop is stored and the answer is 201 either way). Not mine.
- Frontend (FJ2): `StrategyOut` now carries `position_kind` and `position_kind_text`, the same values as the list row.

## New wording for the owner to read
- None new. Item 3 uses the existing `order_request_too_slow` sentence.

## New test files
- tests_app/test_request_key_b2_1128.py
- tests_app/test_strategy_kind_b2_1128.py

## Not done
- Items 6, 7, 8 (batch 2).

## Models and minutes
| task | model | minutes |
|---|---|---|
| items 1 to 3 and 5, build and tests | Sonnet (this session) | about 25 |
