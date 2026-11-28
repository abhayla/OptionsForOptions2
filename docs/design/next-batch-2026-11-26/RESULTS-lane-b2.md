STATUS 21:45 | BATCH 1 pushed: items 1 to 3 + the coordinator's MUST (unknown-outcome block) + the CI Redis-less Execute failure; TOTAL PASS on 507c3c86f; Opus reviews done (two) | batch 2 (items 4, 6, 7, 8 + review minors) next, due 01:30 | item 5 DROPPED (Lane R1 owns StrategyOut.position_kind) | blocker: send_message to @parent REFUSED (elevated_session_untrusted_device); messages from the coordinator reach me, mine do not; this STATUS line is the report

# Lane B2: the order-door and request-key backend lane (round 3, weekend)

Branch fix/r3-backend-b2-1128, from integration/weekend-r3-1129 with RA's 951aa698c merged. Highest claimable status: Fixed, not tested (no PC run).
Local database as CI builds it (`scripts/orchestrator/cloud_services.sh`), one test file at a time, proxy variables unset; full check `prepush.py --jobs 4`.

## What was done
| Item | State | Evidence |
|---|---|---|
| NEW MUST (coordinator 18:46): the server guarantees no second order after an unknown outcome, whatever the key or body, paper and real alike, durable, one path every order door passes | built: migration 0064 `public.order_attempts` (was 0063; renumbered after Lane RA2 took 0063_basket_facts_spot_at) (one OPEN attempt per strategy, partial unique index); `ofo_app/order_outcome.py`; dependency (function scope) on the 4 paper order routes, the tracking exit and the Execute door; `scenario_mode.misguarded_order_routes` now also fails when an order route lacks it (the Return door, which records an outcome, is excluded). A request opens its attempt first (committed); a clean refusal (`StrategyRefused`, schema 422, `UserFacingError`) closes it by what the database holds; any other end (crash, failed or late commit, cancel) leaves it OPEN = unknown; the next request looks: orders, plans or key rows written by a guarded door since the attempt began -> `stored`; nothing and older than 120 s -> `not_stored`; else REFUSED `order_outcome_unknown` (code 590), nothing stored. A table that cannot be used refuses `request_key_store_unavailable` (583). A missing strategy answers 404 first. Server-written stop and settle rows are no evidence. | tests_app/test_order_outcome_b2_1128.py 10 passed (same key other body; other key; no key; two tabs; crash after store; release when stored; release after the window; clean refusal; schema refusal; table down; 404; server stop row); tests_app/test_order_outcome_real_b2_1128.py 1 passed (Execute). Mutation: removing the guard from the paper orders route turns 7 of 8 red. |
| CI fix (coordinator 20:35): Execute with no Redis answered 503 583 | cause: `request_key.begin` raised on `KeyStoreDown` (Redis claim), failing the keyed Execute before the durable table was asked; the durable table was not at fault. Fixed by item 2 below. The e2e spec was run as the workflow step does (API with the CI placeholders, NO Redis): `npx playwright test e2e/execute-screen.spec.ts --project=desktop-1280`: 2 passed. Not reproduced on the old head (not run). | tests_app/test_order_request_key_r2_fd2.py::test_real_door_a_redis_that_cannot_be_read_still_prepares_one_plan |
| 1 I-186 F2 | already built by Lane FD5 item C (`_refuse_if_changed`, under the lock, right before `record_plan`, one transaction). Mutation here: call removed -> 2 red; with it 16 passed. Opus review confirmed it reads right. | tests_app/test_execute_revision.py |
| 1 F4 | Lane RA item 8: not redone | |
| 1 F5 | already built by Lane FD5 item E (`exit_tracking` refuses a real or unknown position first) and pinned; passes | tests_app/test_exit_door_real_fd3.py |
| 2 (a) tracking exit refuses an unknown kind | already built (FD3, FD5 E); passes | same file |
| 2 (b) durable key decides | built: `request_key.begin` returns None for a `pending` Redis record of the same strategy and body (a hint) and for a Redis that is down; `claim_in_transaction` decides; a durable table that cannot be read still refuses 583; other strategy 580 and other body 581 still refuse. Core test red before, green after. | tests_app/test_request_key_b2_1128.py 4 passed; test_order_request_key_r2_fd2.py 12; test_order_request_key_durable_fd3.py 20; test_execution_plan_store.py 103 |
| 3 Execute door deadline | built: `_stamp_request` first dependency, check after `finish_in_transaction`, own code `order_request_too_slow`. Red before (200 at 10.5 s after arrival), green after. | tests_app/test_execute_revision.py 16 passed |
| 4 I-183 | falls out of item 2: a same-key resend after a crash places once or replays; pinned by the core test and `test_an_unknown_outcome_leaves_a_hint...`. NOTE: with the new block, a resend within 120 s of a crash with NO stored rows now reads `order_outcome_unknown` (not placed); after the window it places once. | |
| 5 `StrategyOut.position_kind` | DROPPED by the coordinator (R1 builds it; ADR-330 (64) withdrawn). Built, then reverted in e1e3154da. | |

## Opus reviews (read-only, Opus)
- Review 1 (items 1 to 3): PASS. No path where two presses with one key both store; no stale check stores on a changed plan. Six MINOR findings, not fixed (batch 2): (1) a refused second press that passed the hint frees the first press's Redis record (`begin` should say whether it created the record); (2) a racing repeat can read `gate_dependencies_unsatisfied` instead of "already prepared"; (3) a repeat that passes the hint does all the Zerodha reads before it is refused (Kite budget, pool); (4) no test races two keyed requests through the real doors (a structural test: lock, claim, writes, finish, commit with no release between); (5) stale comments naming 582 (`request_key.py` `finish` docstring, paper.py:1513); (6) Redis calls up to 2 s each.
- Review 2 (the outcome block): REVISE; money-relevant ones FIXED in 788fad5c2: F1 (a monitor stop or settlement row closed an open attempt as stored: now excluded), F2 (an insert before the door's 404 answered 503: ownership read first), F3 (schema 422 left the attempt open: now clean), F4 (close ran after the response: `scope="function"`), F7 (grant narrowed to user_ref, strategy_id, door, state). Not fixed, listed: F5 (the exit and trigger doors have no arrival deadline before commit; each statement is capped by statement_timeout 30 s; a late duplicate exit is refused by the locked-net check, a late duplicate stop by the ADR-317 dedupe); F6 (the route check runs at start-up only in scenario mode; in production it is the CI test `test_scenario_isolation`; it checks the guard is present, not that it is first: a "runs first" assertion and a mutation test for the outcome guard are batch 2).

## Decided for the owner
- Redis is a hint (item 2): a Redis outage no longer refuses a keyed order; the durable table decides; a table that cannot be read refuses.
- The block is per strategy, not per user: one open attempt per strategy. While a request runs, a second request for the same strategy (second tab, double click with another key) is refused with the unknown-outcome sentence, so this also serialises order requests per strategy; no money effect, a rare "try again" for the user.
- Window 120 s (`SETTLE_SECONDS`): the unknown-outcome window the request key already used; after it, an attempt with nothing stored is released. The Return door is not guarded (it records an outcome); it does not close an open attempt in this build (the window and the stored-rows check do): listed under "For the owner lane".
- Code 590 for the new sentence (587 was taken by `real_position_open_refused`); if Lane B3 or R1 picked 590 the unique-code test fails on merge: renumber mine.
- The exit and trigger doors keep their own refusals; the block runs before them (a refused exit during an unknown attempt reads the unknown-outcome sentence).
- RA's F3 and F2: not built.

## Question for the owner
- RA's F3 and F2 are overtaken by the withdrawal of ADR-330 (64) (Lane R1); nothing for B2.
- Is "try again in a couple of minutes" the right wording for a refused second press? (See New wording.)

## For the owner lane
- Lane B3 (`ofo/errors/templates.py`, owner of the sentence keys): my sentence `order_outcome_unknown` (code 590) and its pin are already in the tree (tests/errors/template_pins.json, "pending owner read"); keep them on merge.
- Lane B1: `tests_app/test_exit_door_real_fd3.py::test_n7_a_stop_stored_then_a_failed_kind_read_still_answers_success_with_the_line_unknown` failed on this base (`calls["n"] >= 2`, got 1) before my work; RA's F-2 moved the kind read before the commit. It passed in the final full check on this head (the file now belongs to the merge); recheck after R1's `kinds_of` change.
- Lane B1 (paper.py, edited by me in 4 decorators only: `Depends(guard_paper_outcome, scope="function")` and one import). A new paper order route must carry it; `misguarded_order_routes` names the missing one.
- Frontend (FJ2): a refused order may answer 409 with the new sentence; the page should keep its lock and read the strategy's orders (the sentence says so). No new field.
- The Return door could close the open Execute attempt when the user records the outcome (faster release than 120 s): `routes/execution_return.py` is not on my list.

## New wording for the owner to read
- `order_outcome_unknown` (code 590): "An earlier order for this strategy has no known result yet." / "No order was stored by this request; another order now could double the position." / "Placing these orders." / "Read the strategy's orders, then try again in a couple of minutes."
- `order_request_too_slow` on the Execute door: already listed by Lane RA.

## New test files
- tests_app/test_request_key_b2_1128.py
- tests_app/test_order_outcome_b2_1128.py
- tests_app/test_order_outcome_real_b2_1128.py
(none is selected by the PR241 selector; no registration line was needed)

## Existing tests changed
- test_order_request_key_r2_fd2.py (3 tests: a Redis pending hint and a Redis outage no longer refuse); test_order_request_key_durable_fd3.py (1); test_execute_revision.py (the deadline test, a `tweak` hook, the DB-free apps stub the outcome guard); test_order_path_switch.py and test_browser_never_decides_eligibility.py (DB-free apps stub the guard).

## Not done (batch 2)
- Items 6 (re-run RA's cancel-ids and deadline tests on this head), 7, 8 (cross-reviews), and the review minors above.

## Models and minutes
| task | model | minutes |
|---|---|---|
| build and tests | Sonnet (this session) | about 150 |
| Opus review 1 (items 1 to 3) | Opus (reviewer, read-only) | 8 |
| Opus review 2 (outcome block) | Opus (reviewer, read-only) | 12 |
