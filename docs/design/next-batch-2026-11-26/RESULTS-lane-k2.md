STATUS 22:50 | item 1: Fixed, not tested (pushed) | item 2: Fixed, not tested (K's tests pass after merge) | item 3: in progress | next push ~23:40 | blocker: none (send_message to @parent refused: untrusted device; this top line is the report)

# Lane K2, 27 Nov 2026 (branch fix/order-door-2-1127, from fix/order-limits-1127 8880aa24)

Highest status: **Fixed, not tested.** Paper only; no broker order endpoint called.

## Item 1: the one-argument edit
Merged origin/fix/last-close-1127. Only `tests/orchestrator/test_select_app_tests.py` conflicted; kept both sides' entries once. Only ONE call existed (`routes/paper.py` `entry_facts`, called from `place_paper_orders`; no second near 1404). `entry_facts` now takes `confirmed` and the door passes `confirmed=body.prices_not_live_confirmed` to `entry_facts_now`.
Core proof (before the edit): `tests_app/test_order_door_entry_facts_confirmed.py` 7 failed (no way to pass the tick). After: pass.

| Case | Result |
|---|---|
| ticked, stale index -> facts stored (spot 24087.30) | pass |
| unticked, stale index -> None, nothing stored | pass |
| live index, with or without tick -> facts as before | pass |
| UNHEALTHY / crossed_quote / zero index, ticked -> None | pass |
| door source passes `confirmed=body.prices_not_live_confirmed` | pass |

Two tests the merge made stale were updated: `test_paper_routes::test_a_bad_price_is_422...` (0 and -5.00 now get Lane K's sentence 577 first) and `test_basket_facts_unheld_index` (Lane N's read door leases; no per-request release).

## Item 2: Lane K's limits after the merge
`tests_app/test_paper_order_lots_limit.py` + `test_paper_entry_price_zero.py`: 25 passed on the merged tree (local PostgreSQL 16): 101 refused; 60 then 50 refused; exit above stored freeze refused; no stored freeze: not refused for freeze; default 100.

## Gate
`prepush.py --jobs 2` TOTAL PASS (default `--jobs 4` failed only `paper-leg-readers-guard` N-07 on its 15 s timeout under load; passes alone in 4 s).

## To file as deferred issues
- `frontend/tests/paper-leg-readers-guard.test.js` N-07 scan exceeds its 15 s timeout when 4 gate jobs run on 4 cores.
- Lane N: `test_basket_facts_unheld_index` asserted per-request release (stale after read_door leases).

## Model table
| Task | Model | Minutes |
|---|---|---|
| Items 1, 2, gate runs | Sonnet (this session) | about 90 |
