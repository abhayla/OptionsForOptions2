STATUS 21:10 | push 2 of fix/order-limits-1127 (rulings applied) | items 1 and 4: Fixed, not tested; 2: Lane N's 5e7d34c9, not built twice; 3: listed, not built | decisions needed: none (coordinator rulings of 27 Nov applied) | SAFE TO CLOSE after this push | blocker: none

# Lane K: order limits at the one door (branch fix/order-limits-1127, from bcbff80)

Highest status claimed: **Fixed, not tested.** Nothing is approved until it passes on the owner's PC.
Spec: ADR-330 (50), (51), (52) are on origin/fix/ic-live-test-1123 (head ffb84750); cited from there, not copied. ADR-081 and ADR-092 stand.

## Done
| Item | State | What |
|---|---|---|
| 1 (ADR-330 (50), (51), (52)) | Fixed, not tested | `paper_limit.check_order_size`, called by `place_checked` (the door `place_paper_orders` and `exit_tracking` both use). Per leg: the lots it will hold after EACH order of the batch (held + added, signed net) must not exceed `limits.max_lots`, default now **100** (52); applies always, a flip long to short counts as growth. Per order, every kind: units below the stored freeze quantity; an exit above it is refused (51) with a sentence naming the most one exit may carry and that the rest is exited in further orders. **No freeze quantity stored for the contract: no freeze refusal** (ADR-081, coordinator ruling 27 Nov); the lots limit still applies. A batch that does not grow a leg already over a lowered limit passes (a cut back is never trapped). |
| 2 (triage C10, ADR-330 (28)) | Not built here: Lane N already fixed it | Lane N's `5e7d34c9` (fix/last-close-1127) changes the same function (`_index_spot_held`, flag `prices_not_live_confirmed`) with its own test `tests_app/test_entry_not_live_confirmed.py`. I had built the same fix, found theirs, and REMOVED mine. Finding: the server refused only because `_index_spot_held` demanded a connected provider; no price check was involved. Open for Lane N: a held quote of any age becomes the starting point (the saved row should keep its time). |
| 4 (PC check T3-13: entry price 0) | Guard test only; NOT reproducible | Not reproducible on 206a9f0 plus my branch (the PC ran ff0448b3): `POST /paper/strategies/{id}/orders` with price 0, 0.00 or -5.00 on open and add is refused (422) already. I made the sentence name the leg: `paper_entry_price_not_above_zero` (577). Six guard tests. The PC step in "PC steps" settles whether a planned 0 is saved elsewhere (plan sheet: Lane R2). |
| 3 ("place_paper_orders waits holding a database connection") | Listed, not built | Confirmed by reading: after `place_checked` the route calls `record_basket_facts` -> `_index_spot_held` -> `hold_and_read` (up to `LEG_WAIT_S` = 3 s) while the session still holds its connection AND the strategy row lock (`FOR UPDATE` from `paper_store.place`). Lane R's "Pool fix (release before market waits)" (hotfix/plan-save-1127) and Lane N's `read_door` rewrite the same lines. Fix when merged: read the spot BEFORE `place_checked`, pass it into `record_basket_facts`, release the connection while waiting. |

## Reports
- **Paper-only path found: none.** `check_order_size(db, existing, new, settings)` is one function over stored rows; a real-order path can call it as is.
- **File owners.** Lane Q2's `tests_app/test_paper_order_lots_limit.py` pinned 10,000 and accepted 5,000 lots. Its cases are in MY file, rewritten to 50 to 52 (default 100; 5,000 sold refused; 100 sold accepted, 101 refused; a paper exit of 30 lots above a 1,800-unit freeze refused). The combined build takes my file.
- `routes/paper.py`: the old pre-check `_refuse_legs_over_limit` is removed (the door replaces it); the zero-price refusal is added. `routes/tracking.py` gets a `settings` dependency on the exit route. Build lane: merge Lane K first, then Lane V (its leg-stop-risk lines in the same file).
- The Opus review (order path) found: a trapped-exit class and four door defects; all four door defects fixed (total checked after each order, flip counts, sentence adds up); the trapped exit is gone with the ADR-081 ruling. Not built: a quote of any age as starting point (Lane N); stop-outs and settlement call `paper_store.place` directly and skip the size check (never trapped on purpose).
- Messaging to "@parent" was refused (untrusted device); this top line is the report.
- Cloud container note: a shallow clone breaks `git merge-base origin/main HEAD` in the gate (ci_checks, app_tests): run `git fetch --unshallow origin` once.

## For the one-exit-door work (the REAL door does not call the lots check either; Q2 gap 9)
Not changed by me (the broker path, not my files). Needed: (1) `settings: Annotated[Mapping[str, Decimal], Depends(get_calc_settings)]` on `routes/execute.py` `execute_strategy`; (2) in `_execute`, right after `wanted = await _wanted(req, stored, units)`, for each leg compute the total it will hold (held units per symbol plus the leg's signed quantity, in lots) and raise `StrategyRefused("paper_leg_total_over_limit", ...)` with the same sentence; (3) move the pure running-total part of `paper_limit._check_leg_totals` to one shared function both doors call (paper passes stored rows, real passes `units`); (4) the real review's freeze block (`ofo.execution.freeze_check`) already matches the paper rule (blocks only where a quote is stored; warns where none). Then remove the strict expected-fail marks on Q2's `tests/test_order_door_parity_live_day.py` (not on this branch; its LOTS/real cell turns green). No broker order endpoint is called by any of this.

## Class
Class: every order path that must pass the size rule. Filter: callers of `paper_limit.place_checked` = 2 (`place_paper_orders`, `exit_tracking`); total-per-leg checks before 0, after 2. Other writers of paper orders (`paper_store.place` direct) are tests, stop-outs and settlement.

## Tests run (local PostgreSQL 16 in this container, each file on a fresh database)
| File | Result |
|---|---|
| test_paper_order_lots_limit.py (incl. core 60+50) and test_paper_entry_price_zero.py | 25 passed |
| settings_lots_wiring, lots_cap_guard, leg_edit_route, settings_layers | 1, 4, 83, 53 passed |
| paper_batch_buys_first, paper_routes, paper_save_paths_fx2, paper_server_exit_price, exit_door | 12, 48, 9, 4, 37 passed |
| strategy_tracking, paper_adjustment_limit, held_entry, ic_exits_paper, ic_paper_loop_core | 29, 17, 25, 9, 1 passed |
| positions_route, basket_facts_unheld_index, paper_duplicate_leg_d60, d04_one_door | 59, 5, 2, 7 passed |
| tests/errors (template pins) | 710 passed |
| `scripts/orchestrator/prepush.py` | TOTAL PASS on head 0a88b8d1 (push 1); push 2 gate result: see the pushed commit |

Test setup change: `tests_app/conftest.py` gives every contract a very large freeze limit by default; the limit tests carry `pytest.mark.real_freeze` and use real rows.

## Pending owner read (new on-screen sentences; template pins say "pending owner read")
- `paper_leg_total_over_limit` (575): "{contract} would hold {total} lots after this order; a leg can hold at most {max_lots} lots ({held} held, {added} added)." Next step: "Reduce {contract} to {room} more lots or fewer."
- `paper_exit_over_order_limit` (576): "An exit of {lots} lots on {contract} is above the most one order can carry ({max_lots} lots)." Impact: "Nothing was exited." Next step: "Exit {max_lots} lots or fewer now, then exit the rest in further orders."
- `paper_entry_price_not_above_zero` (577): "The entry price for {contract} must be above 0." Next step: "Type a price above 0 for {contract}, then add it to paper again."
- Setting "Most lots in one leg" now defaults to 100.

## Model table
| Task | Model | Minutes |
|---|---|---|
| Build, tests, gate runs, RESULTS (items 1, 2, 4) | Sonnet (this session) | about 230 |
| Independent review of the order-door change. Why Opus: order path; a wrong answer lets an oversized order through or traps an exit | Opus (reviewer) | about 5 |

## PC steps (owner's PC)
**Step 0 (before anything): count the stored freeze quantities for the running indexes.** On the PC database: `SELECT exchange_segment, count(*), max(file_date) FROM public.exchange_freeze_limits GROUP BY 1;` If there are no rows for an index (SENSEX has none: no BSE_FO source), mark "exit above freeze" for that index as **not testable on the PC, not FAIL**; the lots limit (steps 1 to 3) is testable on every index.

(a) Market CLOSED (until Mon 09:15): Add to Paper is refused by the existing market-closed gate before any size check, so the size sentences cannot be seen closed. Settings page, "Most lots in one leg" shows **100**.

(b) Monday live:
1. Add to Paper, one NIFTY CE leg, BUY 60 lots: accepted. "Increase quantity" by 50 lots on the same leg: refused "... would hold 110 lots after this order; a leg can hold at most 100 lots (60 held, 50 added)." Nothing added.
2. Add 40 more: accepted (100 held). Add 1 more: refused "would hold 101 lots".
3. Add 5000 lots on one leg: refused (the freeze sentence "asks for 5000 lots; the most one order can hold is N lots" where a freeze quantity is stored, else the total sentence).
4. Needs a stored freeze quantity (step 0): a leg held above one order's freeze limit, Positions exit: refused "An exit of N lots on <contract> is above the most one order can carry (M lots)." and the next-step line.
5. Entry price 0 (T3-13): on Add to Paper, clear the entry price of one leg to 0 (type 0) and add: expect "The entry price for <contract> must be above 0." and nothing added. If the PC still SAVES a 0 entry, note the exact screen (Add to Paper from the builder, plan sheet, or Add Selected); that is a different path from this door.

## To file as deferred issues
- No BSE_FO freeze quantity source for SENSEX: the freeze file load reads NSE only (`ofo/instruments/freeze_file.py`: joins on `NSE_FO`), nothing schedules it (`freeze_store.py`: "never scheduled"); evidence: Opus review of 27 Nov ran a BSE_FO exit with no row. SENSEX orders pass the freeze check unseen.
- Exit a large leg in slices with one confirmation (ADR-092 forbids splitting an order; the user now exits in further orders by hand).
- The real-order path does not call `check_order_size` yet (ADR-330 (58)); steps above.
- No partial-exit control on the Positions row for a leg above its freeze quantity (Lane V).
- Stop-outs and settlement skip the size check (direct `paper_store.place`).
- (done) `tests_app/golden_d38/settings.json` regenerated for the default 100.

SAFE TO CLOSE after the push of this file is confirmed (items 1, 4 done; 2 is Lane N's; 3 and the real door are listed).
