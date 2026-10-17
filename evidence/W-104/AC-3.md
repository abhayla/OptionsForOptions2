---
work_item: W-104
ac: AC-3
requirement: REQ-073
ac_fp: "ae5eb5706f3d"
result: pass
verified_by: "verifier (opus, fresh context, GC-3 P0 item 7, main 85e38e0, 2026-10-17)"
builder: "builder (W-105)"
date: '2026-10-17'
commands: "python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_kite_login.py -rs (181 passed); python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_execution_return.py tests_app/test_execute_replay.py -rs (62 passed, 4 DB skipped locally); gh run view 39044144680 --log (App tests on main 85e38e0: 2492 passed, 4 skipped, none in test_execution_return.py)"
---

AC: AC-3
result: pass
commands: python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_kite_login.py -rs (181 passed); python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_execution_return.py tests_app/test_execute_replay.py -rs (62 passed, 4 DB skipped locally); gh run view 39044144680 --log (App tests on main 85e38e0: 2492 passed, 4 skipped, none in test_execution_return.py)
observed: broker.py:242-247 answers a callback with NO state parameter with a 302 to FRONTEND_ORIGIN/execution/returned before any state-store, exchange or DB call (test_ac3_a_basket_return_lands_on_the_returned_page_with_no_exchange_store_or_state; location carries none of the query). execution_return._read_zerodha reads orders, trades and positions in one fresh read; any read error -> 409, nothing changed; classify: closed basket / 0-filled terminal -> nothing_placed, 1 of 2 legs -> partial; reconcile per strategy; every Kite call a GET. CI ran test_core_real_order_return_entry_then_exit, test_ac3_external_order_recorded_once_and_closed_basket_is_nothing_placed, test_ac3_core_a_plan_from_yesterday_is_never_closed_from_an_empty_book. ExecutionReturnedPage.vue runs nothing on load; it only offers Check with Zerodha.
attack: empty or forged state with a request_token still refused broker_state_invalid; request_token never reaches the address bar; no Kite write and no automatic retry in the return (re-run adds no audit events); a half/unreadable reply refuses the whole return (409); an earlier-day plan never closed from today's book. Gap: a partial close is proven on the pure classify function only, no route-level DB test drives it; W-105 names only the landing test file, the read-back half is in tests_app/test_execution_return.py (W-096)

GC-3 P0 item 7: re-verification on main of criteria whose evidence predated fingerprints.
Recorded by the orchestrator from the verifier's returned block.
