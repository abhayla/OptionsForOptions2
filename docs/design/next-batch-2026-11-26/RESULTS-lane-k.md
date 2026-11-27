STATUS 18:10 | item 1 and 2: Fixed, not tested (on the owner's PC); Opus review + gate pending | next push: after gate | blocker: none

# Lane K: order limits at the one door (branch fix/order-limits-1127, from bcbff80)

Highest status claimed: **Fixed, not tested.** Nothing is approved until it passes on the owner's PC.

## Done
| Item | State | What |
|---|---|---|
| 1 (ADR-330 (50), (51), (52)) | Fixed, not tested | `paper_limit.check_order_size`, called by `place_checked` (the door `place_paper_orders` and `exit_tracking` both use). Per order, every kind: units below the stored freeze limit (an exit too, (51)). Per leg: held + added lots after the batch must not exceed `limits.max_lots`, default now **100** (52). A contract with no stored freeze quantity is refused by name (fail closed). A batch that does not grow a leg already over a lowered limit passes (a cut back is never trapped). |
| 2 (triage C10, ADR-330 (28)) | Fixed, not tested | The refusal was not the price check: `_index_spot_held` (basket starting point, ADR-283 (1)) refused whenever the provider was "not connected". It now uses the last captured index quote the provider still holds; no quote at all still refuses (`paper_index_price_unavailable`: a starting point is never invented). The typed price itself was never refused. |
| 3 | Not started | See "Next". |

## Reports for the coordinator
- **ADR-081 vs the owner's 27 Nov rule.** ADR-081 says no stored freeze limit: "the review warns", no block. The owner's brief says fail closed. Built fail closed; ADR-081 needs an amendment row, I did not write one (ADR-330 lives on another branch).
- **Paper-only path found: none.** The size check is one function over stored rows; a real-order path can call `check_order_size(db, existing, new, settings)` as is. Real-order callers do not use it yet (ADR-330 (58) gap, listed).
- **File owners.** Lane Q2's `tests_app/test_paper_order_lots_limit.py` (branch test/live-day-gaps-1127) accepted 5,000 lots and pinned 10,000. Its cases are rewritten to decisions 50 to 52 in my file (default 100; 5,000 sold refused; 100 sold accepted, 101 refused). The combined build must take MY file, not Q2's.
- The old pre-check in `routes/paper.py` (`_refuse_legs_over_limit`) is removed: the door replaces it. `routes/tracking.py` gets a `settings` dependency on the exit route.
- Exit-above-freeze: the Positions row "exit" closes the whole leg; a leg held above its freeze quantity cannot be exited in one go and is refused with the sentence. Deliberate per (51); the Positions row has no partial-exit control (Lane V's file).
- Messaging: the first send to "@parent" was refused (untrusted device); a later coordinator message arrived.

## Class
Class: every order path that must pass the size rule. Filter: callers of `paper_limit.place_checked` = 2 (`place_paper_orders`, `exit_tracking`); total-per-leg checks before 0, after 2 (both through the door). Other writers of paper orders (`paper_store.place` direct) are tests only.

## Tests run (local PostgreSQL 16 in this container, each file on a fresh database)
| File | Result |
|---|---|
| test_paper_order_lots_limit.py (17, incl. core 60+50) | 17 passed |
| test_paper_feed_down_typed_price.py | 2 passed |
| settings_lots_wiring, lots_cap_guard, leg_edit_route, settings_layers | 1, 4, 83, 53 passed |
| paper_batch_buys_first, paper_routes, paper_save_paths_fx2, paper_server_exit_price, exit_door | 12, 48, 9, 4, 37 passed |
| strategy_tracking, paper_adjustment_limit, held_entry, ic_exits_paper, ic_paper_loop_core | 29, 17, 25, 9, 1 passed |
| positions_route, basket_facts_unheld_index, paper_duplicate_leg_d60, d04_one_door | 59, 5, 2, 7 passed |
| tests/errors (template pins) | 710 passed |

Test setup change: `tests_app/conftest.py` gives every contract a very large freeze limit by default (the door fails closed otherwise); the limit tests carry `pytest.mark.real_freeze`.

## Pending owner read (new on-screen sentences; template pins say "pending owner read")
- `paper_leg_total_over_limit` (575): "{contract} would hold {total} lots after this order; a leg can hold at most {max_lots} lots ({held} held, {added} added)." Next step line: "Reduce {contract} to {room} more lots or fewer."
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
