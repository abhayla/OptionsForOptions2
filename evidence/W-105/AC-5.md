---
work_item: W-105
ac: AC-5
requirement: REQ-073
ac_fp: "2831c84ef21d"
result: fail
verified_by: "verifier (opus, fresh context, GC-3 P0 item 7, main 85e38e0, 2026-10-17)"
builder: "builder (W-105)"
date: '2026-10-17'
commands: "python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_kite_login.py -rs; reads of backend/ofo_app/basket_post.py:91, live_market.py:139-146 and 262-286, routes/execute.py:148-154, broker_config.py:102-109; grep for auth middleware in backend/ofo_app"
---

AC: AC-5
result: fail
commands: python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_kite_login.py -rs; reads of backend/ofo_app/basket_post.py:91, live_market.py:139-146 and 262-286, routes/execute.py:148-154, broker_config.py:102-109; grep for auth middleware in backend/ofo_app
observed: Holds: test_another_zerodha_account_is_refused_and_nothing_is_written; startup refuses an empty KITE_EXPECTED_USER_ID; the only writer of broker_sessions is kite_callback after equal_secret(user_id, expected); every read uses OWNER_REF. Missing: BasketPost.as_form() is {url, api_key, data} with no account binding, so Kite places the basket on whichever Zerodha account is logged in on Kite's page in that browser; nothing at Execute or return checks the placing account; the app has no platform login (current_user_ref always 'owner').
attack: a caller who can reach the app while the owner's token is stored, logged in to a different Kite account in that browser, can place the basket on that account; the return reads only the owner's book and closes the plan nothing_placed without a flag. AC-5 rests on who can reach the app and which Kite account the browser uses; neither is enforced nor tested

GC-3 P0 item 7: re-verification on main of criteria whose evidence predated fingerprints.
Recorded by the orchestrator from the verifier's returned block.
