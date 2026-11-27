STATUS 23:55 | item 1: Fixed, not tested (pushed e3897b2) | item 2: Fixed, not tested | item 3: Fixed, not tested (push 2) | next push: none | blocker: none (send_message to @parent refused: untrusted device; this top line is the report)

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

## Item 3: the lots limit on the real door
New one function `ofo_app/order_lots.py::check_lots` (pure; `LegLots`). Paper (`paper_limit._check_leg_totals`) and the real door (`routes/execute.py::_refuse_lots_over_limit`, called in `_execute` after pricing and BEFORE `_gate`, so a refusal leaves no plan written) both call it. Sentence: the paper one (`paper_leg_total_over_limit`, pending owner read). No broker endpoint is called; nothing is ordered. No `routes/execute.py` file of another lane was needed beyond that file. Merged origin/test/live-day-gaps-1127 (clean). Parity marks removed: LOTS/real, LOTS/paper and FREEZE/paper (the last one turned green by Lane K); only NOT_LIVE/paper stays xfail (Lane U2/S). Tests: `tests_app/test_real_door_lots_limit.py` 9 passed (101 refused, 100 ok, 60 held + 50 refused, cut-back exit passes, two entries on one instrument add up, leading-zero held key, lot size 0 refused); `tests/test_order_door_parity_live_day.py` 10 passed, 1 xfailed; execute route files 91 passed.
Opus review (Why Opus: order path): F2 (held key with a leading zero could trap an exit), F3 (two entries on one instrument not added) and F4 (lot size 0 gave a 500) fixed and tested. Paper refactor identical to the old function on 20,000 random batches.

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
- F1 (MAJOR, Lane N's file `adjustment_readers.py:883`): `entry_facts_now` returns None when the feed is NOT CONNECTED before it reads `confirmed`; `_index_spot_held` takes the tick on the same path. A ticked first fill with the feed down stores no entry facts. Fix: in `entry_facts_now`, when not connected and `confirmed`, use `_index_value_not_live`. Also `entry_facts_now` reads the quote without a hold (the index may not be subscribed yet). Not edited: Lane N's file.
- Real door returns 422 for the lots refusal where its other refusals use 409; the page shows the message either way.
