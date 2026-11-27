# Lane Q2 STATUS (27 Nov 2026, late evening IST) - read this block first

STATUS: PARTIAL, budget (300 tool calls) is spent; SAFE TO CLOSE after this push, with the leftovers below for a fresh lane.
Pushed heads: fbbb7319 (gaps 4, 3), 5bdfdde0 (gaps 2, 6, 5, 1, 8, 7), f6815024 (gap 9 + gap 8 revised), then this push (items 4 and 5 of the coordinator's replacement order). send_message to "@parent" is refused for this lane (untrusted device): this block is the report.

Coordinator's replacement order, item by item:
1. Plan-stop chain against a REAL database with the worker as a SEPARATE process: NOT DONE. Found and proved this far (`tests_app/test_plan_stop_worker_process.py`, strict xfail, run on origin/hotfix/loss-stop-1127 against local PostgreSQL 16): the product ALREADY has the separate worker process, `python -m ofo_app.background` with `OFO_SCENARIO=<id>` and `APP_ENV=test` (`background._serve_scenario`: the scenario's recorded prices, the scenario's own clock = a market minute, the real gate and store). It starts, monitors the seeded strategy ("1 strategies monitored") and writes its checks to the log. BUT a one-snapshot scenario such as ADJ-01 never ticks in that process: the log says `check skipped: not_ticked`, so no alert can open. NEXT STEP for the lane that continues: use a PATH-xx scenario (`scenario_mode.is_path`; the worker calls `sync_frame`, which reads the frame index the test writes with `scenario_mode.write_frame(conn, id, frame)`), type the plan's stop (`playbook_store.accept_plan` with `guards.loss_stop_rupees`, as in the test), start the process, advance frames, and count rows in `public.adjustment_suggestions` per rule. Cases still to write: crossed on a fresh trade; crossed when saved; crossed at entry and raised after 5 minutes (ADR-330 (47)); cap used up does not hold a plan exit; a time exit; exiting the last leg closes the alerts. The in-memory chain (same cases, same gate and evaluator, no database, no process) is `tests/adjustment/test_plan_stop_to_alert_chain.py`: on 206a9f0 it fails exactly the cap cells (all five guard kinds) and the rupee stop that crosses and dips; on origin/hotfix/loss-stop-1127 all 28 cells pass (the six strict xfails turn into failures there: delete them in the merge).
2. Price replay tool: cancelled by the coordinator. Not built.
3. Hold-back tool (T2-08, T1-23): built and tested without a socket: `tests_app/holdback.py` (rules file, `filter_frame`, `RouteDelay`, `create_app` wrapper), 7 tests. The route delay (T2-08) can be started now: `OFO_HOLDBACK_FILE=<rules.json> python -m uvicorn --factory holdback:create_app --app-dir tests_app` (rules key `delay_routes`). NOT dry-run: the Kite socket relay for one contract's price (T1-23) and the 70 s index silence is NOT built, so it was not run against `feed_launcher.py`'s `ws_url` fake socket. Say plainly to the owner: T1-23 leaves Monday's first block unless a lane builds `tests_app/holdback_relay.py` (design in the section "Gap 7" below) and dry-runs it.
4. Lots-limit file: REMOVED in this push (`tests_app/test_paper_order_lots_limit.py` is deleted; Lane K owns it). Its six cases are in the Lane-K hand-over: default 100 (52); 100 accepted; 101 and 5,000 refused; total the leg will hold counted (50); a paper exit of 30 lots above the 1,800 freeze refused (51). Measured on 206a9f0: all refusals are accepted today (201), default is 10,000.
5. Strict expected failures, with the branch that fixes each (the build lane deletes the mark in the same merge):
   - tests/adjustment/test_plan_stop_to_alert_chain.py, dict `XFAIL` (6 cells: all 5 kinds "crossed_after_4_other_alerts", and rupee_loss "crosses_and_dips_before_candle_close") -> origin/hotfix/loss-stop-1127
   - tests_app/test_clock_boundary_0830.py `test_started_0807_reloads_at_0835_whatever_ran_at_start_up` -> origin/lanej/builder-open-0827
   - tests_app/test_clock_boundary_0830.py `test_the_list_loaded_at_0807_is_still_usable_at_0831` -> none (owner question LJ-3)
   - tests_app/test_slow_price_source_live_day.py `test_other_routes_answer_while_paper_reads_wait_on_a_stalled_price` (2) -> origin/hotfix/api-blocking-1127
   - tests_app/test_slow_price_source_live_day.py `test_a_5_second_stalled_quote_does_not_make_live_ticks_not_live` -> origin/hotfix/plan-watch-load-1127 (also hotfix/plan-watch-1127)
   - tests_app/test_load_live_day.py `..._every_third_quote_stalled_8_seconds_...` -> origin/hotfix/plan-watch-load-1127
   - tests_app/test_load_live_day.py `test_the_adjustment_check_under_the_same_stalled_quote_...` -> none (the adjustment check has no price budget; deferred issue)
   - frontend/tests/blank-optional-fields-live-day.test.js, 13 `it.fails` (blank "" / "   " in planWatch) -> origin/hotfix/plan-watch-load-1127 (9d39c82f)
   - tests/test_order_door_parity_live_day.py (4) -> the one order door (ADR-330 (58)); lots limit is missing on BOTH doors
   - tests_app/test_plan_stop_worker_process.py (1) -> the PATH-scenario work above
6. Parity tests from Lane E's list (docs/design/paper-real-audit-2026-11-27.md, section C): NOT STARTED (the list was not on my branch). `tests/test_order_door_parity_live_day.py` (source scan, FILE:LINE) is the base to extend.

Bad news: items 1 and 6 are the two the weekend needs most and neither is done. Gap 5 (every action ends with one sentence) and plain load (gap 1) pass on 206a9f0: the code is right there. DB tests of this lane skip in the cloud gate (no database); they were run here on a local PostgreSQL 16 built the way CI builds it.


# Lane Q2 (tests, live-day gaps), 27 Nov 2026 - branch `test/live-day-gaps-1127` from 206a9f0

(The lane-Q2 results of 26 Nov, screens Wave 2, follow below this section unchanged.)

## Status lines (send_message to "@parent" was REFUSED: elevated_session_untrusted_device; the same lines are here)
- LANE Q2 ALIVE (27 Nov, 14:50 IST start). Paper only; tests and test tools only; no file under backend/ofo, backend/ofo_app or frontend/src changed.
- Push 1: gaps 4 and 3 (see table). head fbbb7319 | gate PASS (prepush TOTAL PASS 2597 s) | re-test: nothing on the PC; unit tests only
- Push 2: gaps 2, 6, 5, 1, 8, 7. head 5bdfdde0 | gate PASS (prepush TOTAL PASS 2649 s) | re-test: nothing on the PC; unit tests only
- Push 3: head f6815024 | gate PASS (prepush TOTAL PASS 2570 s) | gap 9 and gap 8 revised.

Bad news first:
- Of 8 gaps, 5 test files FAIL on 206a9f0 where a named fix exists; gap 5 (every action ends with a result) and the plain load test (gap 1) PASS on 206a9f0: the code is right for those at this load, so they are guards, not proofs of a defect.
- One finding no named fix branch covers: the adjustment check awaits its REST quote with no budget (plan-watch has one). Strict xfail in `tests_app/test_load_live_day.py`; to file as a deferred issue.
- Gap 8 changed with your 17:00 IST decisions: 5,000 lots on one paper leg is now a defect (default limit 100, total counted, paper exit above freeze refused). The paper-order door never calls `check_lots`; the REAL door does not call it either (gap 9 shows the lots limit missing on both doors).
- Gap 9: the decision-level half of your request (the same order gives the same decision and message on both doors up to the adapter) needs the one door and a fake-adapter harness for `/execute`; not built. What is built is the source parity test with FILE:LINE and the paper-door HTTP cases of gap 8.
- "Two users" is not testable in v1: `current_user_ref()` returns one owner constant. The load test uses two browser sessions of that owner.
- Strict xfails turn into FAILURES when a fix branch is merged (XPASS strict): that is the signal to delete the mark. Each reason names the branch.
- A DB worker variant of gap 4 was not built (the cloud gate has no database; the chain test is in memory: real evaluator, real readings, real gate, restore from rows). The DB tests of this lane (gaps 1, 2, 8) were run here against a local PostgreSQL 16 built by the same steps as CI; they SKIP in the gate (no TEST_DATABASE_URL).

## Gap table

| Gap | Test file | Fails on 206a9f0? | Which fix branch makes it pass |
|---|---|---|---|
| 4 plan stop to alert, 5 guard kinds x 5 situations (28 cells) | tests/adjustment/test_plan_stop_to_alert_chain.py | yes, 6 cells (strict xfail): all 5 kinds "crossed after 4 other alerts" (daily cap); rupee stop crosses and dips before the candle close. The other 22 pass today | origin/hotfix/loss-stop-1127 (6 XPASS there; checked in a worktree) |
| 3 clock 08:07 -> 08:35 reload | tests_app/test_clock_boundary_0830.py | yes (strict xfail): first reload at 09:07 | origin/lanej/builder-open-0827 (XPASS there; checked) |
| 3 list loaded 08:07 usable at 08:31 | same file | yes (strict xfail) | none: REQ-053 AC-3 as written; owner question LJ-3 |
| 3 clock across 15:30 (ADR-330 (36)) | tests/marketdata/test_clock_boundary_1530.py | no (guard) | n/a |
| 3 candle close; loss stop crossed before the quiet time; 5-minute at-entry pop-up | tests/adjustment/test_clock_boundary_candle_and_quiet.py | no (guards) | n/a |
| 2 slow price source: pool not held by a paper read waiting on a stalled price | tests_app/test_slow_price_source_live_day.py (2 cases) | yes (strict xfail) | origin/hotfix/api-blocking-1127 |
| 2 5 s stalled quote: plan-watch answers inside 4.8 s, no "paused" line | same file | yes (strict xfail) | origin/hotfix/plan-watch-load-1127 (and hotfix/plan-watch-1127) |
| 2 plan-watch / adjustment-check do not hold the pool; a 429 quote never turns live ticks into "not live" | same file (7 cases) | no (guards) | n/a |
| 6 blank optional texts still render: lib/planWatch.js and lib/paperList.js | frontend/tests/blank-optional-fields-live-day.test.js (shared walker `blankVariants`) | yes, 13 cases for planWatch with "" or "   " (`it.fails`); null / absent pass; paperList passes | origin/hotfix/plan-watch-load-1127 (9d39c82f; the 13 fail there = delete `.fails`) |
| 5 every action ends with one sentence: Save plan, Delete, Undo (components / flow), Add to Paper and Exit (door + outcome rule) x slow 2xx, 4xx, 5xx, timeout | frontend/tests/action-ends-with-result-live-day.test.js + helper frontend/tests/_actionOutcomes.js | no (20 cases pass: guards) | n/a. Not covered: the Exit / Add to Paper dialog components mounted per outcome (see leftovers) |
| 1 load: 10 running trades, 2 browsers x 3 rounds, 186 requests | tests_app/test_load_live_day.py | plain load: no (guard; 0 "not live", pool peak 4 of 4). Same load with every 3rd quote stalled 8 s, answered inside 6 s: yes (strict xfail) | origin/hotfix/plan-watch-load-1127 for plan-watch / book / positions. The adjustment check alone stays red on every branch: no named fix |
| 8 order door limit, per the coordinator's decisions (50) total the leg will hold, (51) paper exit above freeze refused, (52) default 100 lots | tests_app/test_paper_order_lots_limit.py (6 cases; FILE REMOVED in push 4, Lane K owns it) | yes: 5 strict xfails (default is 10,000 today; 101 and 5,000 lots accepted; total not counted; exit of 30 lots above the 1,800 freeze accepted); 100 lots accepted passes | none: ADR-330 (50)(51)(52) are not in the tree and no branch applies them |
| 9 parity of the paper and real order doors (ADR-330 (58)): check inventory + branch scan | tests/test_order_door_parity_live_day.py (11 cases, source scan, no database, no broker) | yes: 4 strict xfails: lots limit missing on BOTH doors; freeze check and the one "prices not live" refusal code missing on the paper door. Duplicate-leg check is shared (passes). Branch scan: 0 paper-only branches in the real path, 0 real-only in the paper path, 0 in the shared alert module (guards) | none: the one order door |
| 7 hold-back tools | tests_app/holdback.py + tests_app/test_holdback_tool.py (7 tests) | n/a (a tool) | n/a |

## Gap 7: hold-back tools for the screen tester (design; what lives in test folders is built)
Built (no product code touched; nothing in backend/ imports it): `tests_app/holdback.py`.
- One rules file, JSON, path in the environment variable `OFO_HOLDBACK_FILE` (read only by these tools; re-read when its modification time changes, so the tester edits it during the session; absent file = no rule). Keys: `withhold_tokens` (a), `silence` {tokens, from, seconds} (b), `delay_routes` [{prefix, suffix, seconds, from, until}] (c). Times need an offset (+05:30); a naive time is refused.
- `filter_frame(rules, frame, now)`: takes one raw Kite binary message, removes the packets of a silenced token, rewrites the packet count, drops a message left empty; heartbeats and bytes that do not parse pass unchanged.
- `RouteDelay` (ASGI middleware) and `create_app()`: `python -m uvicorn --factory holdback.create_app --app-dir tests_app` starts the REAL API wrapped by the delay, instead of `ofo_app.main:create_app`. This is (c), complete.
- As the brief lists them: (a) produces T1-23, (b) produces AX-01, (c) produces T2-08 (I have not seen the check texts; the mapping is the brief's order).
Proposed, NOT built (it needs a live Kite socket, which this container cannot reach, so it would be unverified):
- `tests_app/holdback_relay.py`, a Kite WebSocket relay for (a) and (b). `tests_app/feed_launcher.py feed <config.json>` already runs the REAL feed process over a configurable `ws_url` under the egress test mode (loopback only, no product switch). The relay listens on 127.0.0.1 as "Kite", opens the real Kite socket upstream with the owner's token (from the environment, never an argument), passes the feed's subscribe messages up, and passes every binary message down through `filter_frame`. The owner starts the feed through the launcher with `ws_url` = the relay for the test session.
- Why not a Redis key: the feed writes to `ofo:feed:<user>:ticks` and the API reads that name; the product has no seam that makes the dev feed honour a "withhold" key, so it would need a product change. The relay needs none.
- Index tokens: NIFTY 50 is 256265 in Kite's list; take every other token from the instrument CSV the session loaded, never from memory.

## task | model that did it
| Task | Model |
|---|---|
| Reading the code and spec, all eight gaps, all tests and test tools, this file | Sonnet (this lane) |
| Local PostgreSQL 16 set-up, runs on 206a9f0 and on the fix branches, gates | Sonnet (this lane) |
| Mechanical steps with a Haiku helper | none used |

## Leftovers (To file as deferred issues; the coordinator files them)
1. The adjustment check awaits its REST quote with no budget (plan-watch has one, REQ-119 AC-4). Test: `test_the_adjustment_check_under_the_same_stalled_quote_answers_inside_6_seconds`.
2. Neither order door calls `check_lots`; the paper door has no freeze check and its own refusal codes for "prices not live". Tests: gap 8 file and `test_the_check_is_reached_from_this_door`.
3. Gap 9 decision-level parity (needs the one door + a fake-adapter harness for `/execute`). A DB-backed worker variant of the plan-stop chain (gap 4) and component mounts of the Exit / Add to Paper dialogs per outcome (gap 5).
4. The hold-back relay (gap 7, above).
5. "Two users": v1 has one owner reference; a multi-user load test waits for real accounts.

# Lane Q2 results (screens, Wave 2), 26 Nov 2026

Branch `feat/nb-screens-w2-1126`, cut from `origin/refactor/modular-doors` `db57d05`, then merged
`origin/fix/ic-live-test-1123` `f38630d` and `origin/feat/nb-screens-1126` `f6a1c8a` (merged base `83107be2`, gated and
pushed first). No PR. Paper only; no broker order endpoint is called; no migration. The highest status claimed for any
item is **Fixed, not tested**: the owner tests on his PC in market hours.

Standing-direction step: "iron-condor depth (freeze lifted 2026-11-26)" for new behaviour; step 4 item 10 for the defects.

Spec basis: ADR-330 (8), (10), (14), (15), (17) with the owner's 26 Nov answers; ADR-292, ADR-293 (1); ADR-201 (2)
(SPEC CHANGE, replaced by ADR-330 (10)); ADR-207; ADR-016 to ADR-019; ADR-008; ADR-003; ADR-281; ADR-320; ADR-321.
New wording is in REQ-070 (AC-7 and a body paragraph), REQ-081 and REQ-109 (body paragraphs, including the paragraph
"SPEC CHANGE (ADR-330 (10) replaces ADR-201 (2))"). No new decision row was written. ADR-201 itself is not edited: the
coordinator adds the superseded-by note (candidate row **ADR-NB-1**: "OD-1, one Positions list, supersedes ADR-201 (2)";
the plan's section 5 list item (6)).

## Per item

| Item | Status | Root cause (one sentence) | Class before / after |
|---|---|---|---|
| S-06 page wiring | Fixed, not tested | The builder page never passed `summary` to `SummaryCards`, so the basis line had no data. | 1 screen. Also fixed the Wave 1 quirk: the line is hidden when both max figures read "Not available". |
| S-14 Exit on the Live card | Fixed, not tested | The card had no Exit; Wave 1 waited for the refactor's exit door. | 1 card. Exit is a link to the Positions page (`?tab=paper&strategy=<id>&exit=<id>`) that opens the page's own confirm through `usePaperExit` + `ExitButton` + `PaperConfirmDialog`; the card holds no exit code. Hosting the composable would have copied about 80 lines of flow. Tier A review: REVISE, then PASS. |
| S-25 run-together number columns | Fixed, not tested | Table cells had no horizontal padding and headers were not aligned like their cells. | 9 tables without the shared class before, 0 after (one `.num-table` rule in `style.css`). A source-scan test fails on a table in these files without it. |
| S-01 bulk delete (ADR-330 (8)) | Fixed, not tested | New feature. | One route `POST /strategies/bulk-delete` runs the SAME `delete_draft` rule per id in its own savepoint; no second rule. Running paper strategies are deleted; the confirmation says how many are running. |
| S-03 wrong refusal for a held strategy | Fixed, not tested | `delete_draft` raised only `DELETE_AFTER_BASKET`, so a held strategy got "Orders were already sent". | Every refused row. After: one `_HELD_SQL` rule feeds both the list flag `held_at_broker` and the refusal reason; "This strategy is marked as held at your broker, so it cannot be deleted." |
| S-04 Rename under the mouse | Fixed, not tested | The confirm box replaced Delete inside the same action cluster, shifting Rename. | Every row confirm on My Strategies; the confirm is now its own full-width line below the row. The builder keeps its inline confirm. |
| S-05 bare "Loading..." | Fixed, not tested | No timeout and no retry on the list read. | My Strategies and Completed: skeleton, then after failure or 15 s "Could not load your strategies. Nothing was changed." with Retry. Not a speed fix. |
| S-02 ERR-6960F002 | **Open (not guessed)** | Not known without the owner's API log. | New measured fact (see Findings): `delete_draft` raises a raw database lock error (sqlstate 55P03) when another connection holds the row lock, which the route turns into ERR-xxxx. |
| Q2 one Positions list (ADR-330 (10)) | Fixed, not tested | New feature (SPEC CHANGE to ADR-201 (2)). | One list: filter All / Real / Paper (default All; `?tab=paper` gives Paper, `?tab=positions` gives Real, an `exit` link forces Paper); "PAPER" tag on every paper group, "REAL (Zerodha)" on every real group; two totals "Real P&L" and "Paper P&L", never summed; the second `/paper/strategies` read on the page was removed (PaperStrategies is the only paper reader and the only exit host). |
| Exit confirmation titles | Fixed, not tested | Titles were literals ("Exit paper positions", "Review paper orders"). | One door `positionKindWord` / `exitConfirmTitle` / `reviewConfirmTitle` in `lib/paperDrafts.js`: "Exit Paper positions", "Review Paper orders"; "Real (Zerodha order)" is built and tested but no real exit button exists (ADR-281). An unknown kind throws (fails closed). |
| S-28 Add orders on Completed | Fixed, not tested | The button was drawn for every group. | Completed groups show "Open in Builder" only. |
| S-23 fired stop stays "armed" | Fixed, not tested | PaperStops read its triggers once on mount. | 1 of 2 trigger readers was mount-only, 0 after; it re-reads on the list's good-read token, no new timer. |
| S-19 Stops panel without the index | Fixed, not tested | The panel asked for an index level and never read the index. | Reads `useIndexAnswer` (the strip's reader): "NIFTY now 25,735.00 as of 10:41:05", or "Index values unavailable." with no digits. |
| S-26 Stops panel jumps while typing | Fixed, not tested (cause structural) | Reason and status lines (`ce-reason`, `stop-reason`, error, saved) appeared and disappeared in the flow with no reserved height; measured in jsdom that inputs were never re-mounted. | Every such line is now in an always-rendered reserved slot; the form is keyed on strategy id. jsdom cannot measure pixels: the 16 px is confirmed only on screen. |
| S-15 screen half (ADR-330 (15)) | Fixed, not tested; **shows nothing until Lane P serves `closed_text`** | The total had no line saying it includes closed trades. | The screen prints the server's `closed_text` verbatim under the Paper total when served, never built in the browser. |

## Tests: red, then green

| Test file | Red before the fix | Green after |
|---|---|---|
| `frontend/tests/summary-basis-page-s06.test.js` (new) | 3 failed: "Cannot call text on an empty DOMWrapper" x2, "expected true to be false" | pass |
| `frontend/tests/paper-exit-link-s14.test.js` (new) | round 1: 1 failed; round 2: 7 failed (e.g. "expected '48' to be undefined") | 11 pass |
| `frontend/tests/number-tables-s25.test.js` (new) | 3 failed (rule missing, 9 tables, 18 headers) | pass |
| `frontend/tests/my-strategies-bulk.test.js` (new) | 15 of 16 failed | pass |
| `tests_app/test_strategy_bulk_delete.py` (new, DB) | 11 of 11 failed | 11 pass (local disposable PostgreSQL 16) |
| `tests_app/test_strategy_delete_app.py` (changed: held now expects the held sentence) | it asserted the old sentence | 31 pass |
| `frontend/tests/paper-stops.test.js` (changed) | 5 failed (S-23 "expected 'armed' to be 'fired'"; S-19/S-26 ids missing) | 32 pass |
| `frontend/tests/paper-completed-actions.test.js` (new) | 2 of 2 failed | pass |
| `frontend/tests/positions-one-list.test.js` (new) | 12 of 14 failed | pass |
| `frontend/tests/exit-title-door.test.js` (new), `chunk-c-round2.test.js` (new) | 5 of 5, 6 of 6 failed | pass |
| Changed with reason "ADR-330 (10) replaces ADR-201 (2)": `paper-tabs.test.js`, `positions-page.test.js`, `paper-list-4b.test.js`; pins "Exit Paper positions" / "Review Paper orders" in `builder-drafts-exit`, `paper-dialog-safe`, `paper-place-refresh`, `paper-exit-link-s14`, `exit-title-door` | | pass |

Guards: `one-door-screens.test.js` gained rule 5 (Positions files make no order calls and import no exit pieces; the
literal "Real (Zerodha order)" lives only in `lib/paperDrafts.js`; mutation checks failed the rule as expected); its
known bypasses are written above the rule. `leg-emitters-guard`, `test_paper_orders_one_door.py`,
`test_door_names_private.py`, `test_door_rebinding_and_asgi_scan.py` stay green.

## Known minors shipped (2-round limit reached)

1. A hand-typed URL with a duplicated `exit` parameter (`exit=48&exit=50`) opens the confirm for 48 (no POST without a click).
2. The try/catch round `router.replace` cannot catch a rejected promise; no router guard exists today, so unreachable.
3. The note "This strategy has no open paper legs to exit." also shows for an unreadable row and is not cleared by a later good read.
4. The held-with-a-plan DB test was written with its fix, not seen red first.
5. Bulk delete reads each selected row's revision with one GET per row (list rows carry no revision); a server `revision` on list rows would remove the N reads.

## Findings (for the coordinator)

- **S-02 candidate cause, measured:** with a second connection holding `FOR UPDATE` on a strategy row and `lock_timeout`
  300 ms, `strategy_store.delete_draft` raised `DBAPIError` (`LockNotAvailableError`, sqlstate 55P03); `_run` in
  `routes/strategies.py` re-raises non-store errors, so the user sees ERR-xxxx. The owner's case would be the 30 s
  `statement_timeout` (plan candidate (a)). No lock code changed. Candidate deferred issue: "a lock wait on delete ends
  as a raw 500, not a refusal sentence"; the reproducing DB test needs the admin engine for clean-up.
- **Worktree base:** helper worktrees made with isolation were cut from `main`, not from the lane branch, three times
  out of six; each brief now opens with a base check (`git merge-base --is-ancestor <base> HEAD`). Candidate harvest
  issue for the kit.
- **YAML in spec front matter:** a `\'` inside a single-quoted YAML scalar made REQ-070 unparseable; the builders'
  vitest checks read raw text and passed; `coverage.py` caught it. Fixed in `291e8055`.

## Owner questions

`docs/design/next-batch-2026-11-26/owner-questions-lane-q2.md`: LQ2-1, "Real P&L" has no server figure
(`/positions` returns units only); built meanwhile: a dash with "Real P&L is not shown yet: the server does not price
Zerodha positions."

## Owner screen-check list (paper only, market hours; Ctrl+F5 first)

1. **S-06.** Open a strategy in the Strategy Builder that has never been placed.
   - Expected: under Breakeven, the line "Max Profit and Max Loss are after charges estimated at entry prices; breakevens are before charges."
   - Open a placed paper strategy. Expected: the line appears once, not twice.
2. **S-14 Exit.** Open Live Strategies. On a running paper strategy's card, click "Exit".
   - Expected: Current positions opens with the Paper filter on, and the confirmation titled "Exit Paper positions" opens for that strategy's open legs.
   - Click Cancel. Expected: nothing is sent; the dialog does not come back by itself after a few seconds.
   - Expected: a Completed strategy's card has no "Exit".
3. **S-25.** Open a placed paper strategy in the builder. Check the Orderbook, the net positions table, the closed rows, and the payoff / greeks tables under the chart; then a Live card's leg table.
   - Expected: every number column (e.g. Qty 65 and Price 101.20) is visibly separate and sits under its own header.
4. **S-01 bulk delete.** Open My Strategies.
   - Tick two rows. Expected: the button reads "Delete selected (2)".
   - Type in the search box, then click "Select all N shown". Expected: only the rows still shown are ticked.
   - Tick rows including one Running paper strategy and click Delete selected. Expected: "Delete N strategies? 1 of them are running." (the exact count).
   - Confirm. Expected: a result line such as "3 deleted"; any kept row is named with its reason.
   - Click Undo. Expected: every deleted strategy is back in the list.
5. **S-03.** Find a strategy marked held at your broker (e.g. Held IC k10).
   - Expected: it has no tick box and shows "This strategy is marked as held at your broker, so it cannot be deleted." (not "Orders were already sent").
6. **S-04.** On any row, click Delete without moving the mouse.
   - Expected: the confirmation opens as its own line below the row; Rename stays where it was and the mouse is not over it.
7. **S-05.** Reload My Strategies.
   - Expected: grey placeholder rows while it loads, never a bare "Loading...". If the read fails: "Could not load your strategies. Nothing was changed." with Retry.
8. **Q2 one list.** Open Current positions.
   - Expected: no Paper tab; three buttons All / Real / Paper with All selected; paper strategies each tagged "PAPER"; at the top two totals "Real P&L" and "Paper P&L" and no third figure.
   - Expected: "Real P&L" shows a dash with "Real P&L is not shown yet: the server does not price Zerodha positions." (LQ2-1).
   - Click Real. Expected: paper rows disappear; Paper P&L stays at the top. Click Paper. Expected: only paper rows.
   - From the builder's compact paper list, click its "Current positions" link. Expected: the page opens on Paper.
   - With no Zerodha positions open, Expected: the real part reads "No open Zerodha positions." and the paper rows still show below.
9. **Exit title.** On a running paper strategy, click Exit. Expected: the title reads "Exit Paper positions".
10. **S-28.** Tick "Show closed positions" if needed and find a Completed strategy.
    - Expected: only "Open in Builder", no "Add orders". A Running one still shows both.
11. **S-23.** Arm a leg stop on a running paper strategy close to the live price; wait until it fires (the leg closes).
    - Expected: within one refresh (about 5 s), without reloading, the Stops panel row reads "fired", not "armed".
12. **S-19.** Open the Stops panel. Expected: a line "NIFTY now <value> as of <time>" equal to the index strip at the top of the page; with the feed down, "Index values unavailable." and no number.
13. **S-26.** In the Stops panel, type a level slowly (e.g. 24500.07) while prices update.
    - Expected: the boxes do not move up or down while the reason line under them appears or changes.
14. **S-15.** Not visible yet: it waits for Lane P's `closed_text`. After that merge, a line "Includes N closed strategies ..." shows under the Paper P&L total.
