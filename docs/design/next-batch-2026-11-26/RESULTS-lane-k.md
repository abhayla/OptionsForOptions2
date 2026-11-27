STATUS 20:15 | pushed head 0a88b8d1, gate TOTAL PASS | items 1 and 4: Fixed, not tested; 2: Lane N's 5e7d34c9, not built twice; 3: listed, not built | NEEDS A DECISION: SENSEX has no freeze rows so every SENSEX open is refused; one-click exit of a leg above one order's freeze limit is refused | next push: none planned | blocker: none

# Lane K: order limits at the one door (branch fix/order-limits-1127, from bcbff80)

Highest status claimed: **Fixed, not tested.** Nothing is approved until it passes on the owner's PC.

## Done
| Item | State | What |
|---|---|---|
| 1 (ADR-330 (50), (51), (52)) | Fixed, not tested | `paper_limit.check_order_size`, called by `place_checked` (the door `place_paper_orders` and `exit_tracking` both use). Per order, every kind: units below the stored freeze limit (an exit too, (51)). Per leg: held + added lots after the batch must not exceed `limits.max_lots`, default now **100** (52). A contract with no stored freeze quantity is refused by name (fail closed). A batch that does not grow a leg already over a lowered limit passes (a cut back is never trapped). |
| 2 (triage C10, ADR-330 (28)) | Not built here: Lane N already fixed it | Lane N's `5e7d34c9` (fix/last-close-1127) changes the same function (`_index_spot_held`, with a `prices_not_live_confirmed` flag from the user's confirm line) and has its own test `tests_app/test_entry_not_live_confirmed.py`. I had built the same fix, found it on reading Lane N's change, and REMOVED mine so the merge has one fix. Finding for Lane N: the server refused only because `_index_spot_held` demanded a connected provider; no price check was involved. My reading of the reviewer's point stays open for Lane N: a held quote of any age becomes the starting point (their `_index_value_not_live` returns it with its time; the saved row should keep that time). |
| 4 (PC check T3-13: entry price 0 accepted) | Fixed, not tested | On this branch the server ALREADY refused a typed 0 or negative price (422, generic sentence "A price must be above 0 and a multiple of 0.05"); I could not reproduce "accepted and saved" through `POST /paper/strategies/{id}/orders`. So the PC saw it through another path or an older build: **Lane R2 / the builder should check whether a planned entry price of 0 is saved on the plan sheet**. Added the named sentence `paper_entry_price_not_above_zero` (577), pending owner read. A typed positive price with the feed down is still accepted (ADR-330 (28)). Tests: 6 cases (0, 0.00, -5.00 on open and add). |
| 3 ("place_paper_orders waits holding a database connection") | Listed, not built | Confirmed by reading: after `place_checked` the route calls `record_basket_facts` -> `_index_spot_held` -> `hold_and_read` (up to `LEG_WAIT_S` = 3 s) while the request's session still holds its connection AND the strategy row lock (`FOR UPDATE` from `paper_store.place`). Lane R's "Pool fix (release before market waits)" on hotfix/plan-save-1127 is the same class; Lane N's `read_door` rewrites the same wait. Not built here: three branches change these lines. Fix when merged: read the spot BEFORE `place_checked` (before the row lock), pass it into `record_basket_facts`, release the connection while waiting. |

## Reports for the coordinator
- **ADR-081 vs the owner's 27 Nov rule.** ADR-081 says no stored freeze limit: "the review warns", no block. The owner's brief says fail closed. Built fail closed; ADR-081 needs an amendment row, I did not write one (ADR-330 lives on another branch).
- **Paper-only path found: none.** The size check is one function over stored rows; a real-order path can call `check_order_size(db, existing, new, settings)` as is. Real-order callers do not use it yet (ADR-330 (58) gap, listed).
- **File owners.** Lane Q2's `tests_app/test_paper_order_lots_limit.py` (branch test/live-day-gaps-1127) accepted 5,000 lots and pinned 10,000. Its cases are rewritten to decisions 50 to 52 in my file (default 100; 5,000 sold refused; 100 sold accepted, 101 refused). The combined build must take MY file, not Q2's.
- The old pre-check in `routes/paper.py` (`_refuse_legs_over_limit`) is removed: the door replaces it. `routes/tracking.py` gets a `settings` dependency on the exit route.
- Exit-above-freeze: the Positions row "exit" closes the whole leg; a leg held above its freeze quantity cannot be exited in one go and is refused with the sentence. Deliberate per (51); the Positions row has no partial-exit control (Lane V's file).
- Messaging: the first send to "@parent" was refused (untrusted device); a later coordinator message arrived.

## Independent Opus review (order path) and what I did with it
Verdict was REVISE (7 findings). Taken in code: (1) a reducing kind (exit, stop, settle) with no stored freeze quantity is no longer refused (it was a trapped exit: SENSEX/BSE_FO has NO freeze rows, the file load reads NSE only, and nothing schedules it); (3)(4)(5) the leg total is now checked after EACH order in stored order, a flip long to short counts as growth, and the sentence's held + added = total.
**NOT built, needs the owner or the coordinator:**
- **SENSEX: every OPEN order is refused** ("freeze quantity not known") because no BSE_FO freeze source exists. That is the owner's fail-closed rule applied as written. If SENSEX paper must work on the PC rounds, a freeze source for BSE_FO is needed first, or the owner changes the rule for contracts with no source. Step 0 below shows it.
- **One-click exit of a leg bigger than one order's limit** (54 + 46 lots held = 100, allowed; the Positions exit sends one 100-lot order, refused by (51)/ADR-092 "no splitting"). Needs an owner choice: cap a leg's total at the largest single order, allow a split exit, or give the row a partial-exit control.
- A quote of any age becomes the entry starting point when the feed is down (no age or health check, no server-side confirm line for (28)): list for Lane N / owner.
- Stop-outs and settlement call `paper_store.place` directly and skip the size check (deliberate, never trapped; "paper same as real" is not met for them).
- ADR-330 rows (50)-(52) are not in `spec/decisions/ADR-330.md` on this branch (the full file is on fix/ic-live-test-1123): the coordinator should add: "(50) the lots limit counts the total the leg will hold after the order; (51) an exit above the exchange freeze quantity is refused, paper the same as real (ADR-092 stands); (52) the default lots limit is 100 per leg. Owner 27 Nov. Real case: Add to Paper accepted 5000 lots on one leg."

## For the one-exit-door work (the REAL door does not call the lots check either; Q2 gap 9)
Not changed by me: the real door (`routes/execute.py` `execute_strategy` -> `_execute`, `ofo/execution`) is the broker path; it needs a settings dependency on the route and the held units, which I judged unsafe to add while its lane is not mine. Exactly what is needed: (1) add `settings: Annotated[Mapping[str, Decimal], Depends(get_calc_settings)]` to `execute_strategy`; (2) in `_execute`, right after `wanted = await _wanted(req, stored, units)`, for each leg compute the total it will hold (the held units `units` per symbol plus the leg's signed quantity, in lots by lot size) and raise `StrategyRefused("paper_leg_total_over_limit", ...)` with the same sentence; (3) move the pure part of `paper_limit._check_leg_totals` (the running total per leg, `max_lots`) to one shared function both doors call (it is already one function over `(held, new orders)`, the paper door passes stored rows, the real door would pass `units`); (4) the freeze check for the real door already exists (`ofo.execution.freeze_check`, review-time block), but a contract with no stored limit only WARNS there (ADR-081), the paper door now refuses: make the real review block too, or the owner says otherwise. After that, remove the strict expected-fail marks on Q2's `tests/test_order_door_parity_live_day.py` (not on this branch; its LOTS/real cell turns green). No broker order endpoint is called by any of this.

## Class
Class: every order path that must pass the size rule. Filter: callers of `paper_limit.place_checked` = 2 (`place_paper_orders`, `exit_tracking`); total-per-leg checks before 0, after 2 (both through the door). Other writers of paper orders (`paper_store.place` direct) are tests only.

## Tests run (local PostgreSQL 16 in this container, each file on a fresh database)
| File | Result |
|---|---|
| test_paper_order_lots_limit.py (17, incl. core 60+50) | 17 passed |
| test_paper_entry_price_zero.py (item 4, 6 cases) | 6 passed (26 passed with the lots file) |
| settings_lots_wiring, lots_cap_guard, leg_edit_route, settings_layers | 1, 4, 83, 53 passed |
| paper_batch_buys_first, paper_routes, paper_save_paths_fx2, paper_server_exit_price, exit_door | 12, 48, 9, 4, 37 passed |
| strategy_tracking, paper_adjustment_limit, held_entry, ic_exits_paper, ic_paper_loop_core | 29, 17, 25, 9, 1 passed |
| positions_route, basket_facts_unheld_index, paper_duplicate_leg_d60, d04_one_door | 59, 5, 2, 7 passed |
| tests/errors (template pins) | 710 passed |

Test setup change: `tests_app/conftest.py` gives every contract a very large freeze limit by default (the door fails closed otherwise); the limit tests carry `pytest.mark.real_freeze`.

## Pending owner read (new on-screen sentences; template pins say "pending owner read")
- `paper_leg_total_over_limit` (575): "{contract} would hold {total} lots after this order; a leg can hold at most {max_lots} lots ({held} held, {added} added)." Next step line: "Reduce {contract} to {room} more lots or fewer."
- `paper_entry_price_not_above_zero` (577): "The entry price for {contract} must be above 0." Next step line: "Type a price above 0 for {contract}, then add it to paper again."
- `paper_leg_freeze_unknown` (576): "The exchange freeze quantity for {contract} is not known, so an order for it cannot be checked." Next step line: "Try again after the next daily freeze file load."
- Setting "Most lots in one leg" now defaults to 100.

## Model table
| Task | Model | Minutes |
|---|---|---|
| Build, tests, RESULTS (items 1, 2) | Sonnet (this session) | about 120 |
| Independent review of the order-door change. Why Opus: order path; a wrong answer lets an oversized order through or traps an exit | Opus (reviewer) | see review note |

## PC steps (owner's PC)
**Step 0 (before anything): count the stored freeze quantities for the running indexes.** On the PC database: `SELECT exchange_segment, count(*), max(file_date) FROM public.exchange_freeze_limits GROUP BY 1;` If there are no rows for the running indexes, mark "exit above freeze" and "no freeze quantity" as **not testable on the PC, not FAIL**. Every Add to Paper is then refused with the "freeze quantity ... is not known" sentence (the fail-closed rule, expected) until the daily freeze file loads.

(a) Market CLOSED (until Mon 09:15): Add to Paper is refused by the existing market-closed gate before any size check, so the size sentences cannot be seen closed. Settings page, "Most lots in one leg" shows **100**.

(b) Monday live, freeze quantities stored:
1. Add to Paper, one NIFTY CE leg, BUY 60 lots: accepted. "Increase quantity" by 50 lots on the same leg: refused with "... would hold 110 lots after this order; a leg can hold at most 100 lots (60 held, 50 added)." Nothing added.
2. Add 40 more: accepted (100 held). Add 1 more: refused "would hold 101 lots".
3. Add 5000 lots on one leg: refused ("asks for 5000 lots; the most one order can hold is N lots", or the total sentence if under the freeze quantity).
4. A leg held above its freeze quantity: Positions row exit refused with "asks for N lots; the most one order can hold is M lots".
5. Live prices disconnected, Add to Paper with a typed entry price: accepted at the typed price (plus the confirm line from ADR-330 (28), Lane N's screen). With the feed never connected since the server started: refused "The live index price is not available...".

## To file as deferred issues
- ADR-081 amendment: no stored freeze limit now blocks (owner 27 Nov).
- The real-order path does not call `check_order_size` yet (ADR-330 (58)).
- No partial-exit control on the Positions row for a leg above its freeze quantity (Lane V).
- (done) `tests_app/golden_d38/settings.json` showed the old 10000 default; regenerated with `D38_WRITE_GOLDEN=1` (two lines: default and value 10000 to 100).

## Next
Gate (`scripts/orchestrator/prepush.py`), push 1 = items 1 and 2; item 3 ("place_paper_orders waits holding a database connection") second.
