---
work_item: W-065
ac: AC-4
requirement: REQ-035
ac_fp: "faa18f01993e"
result: pass
verified_by: "verifier (fresh Opus, round 2)"
builder: "builder (Sonnet r2; Opus p3 r1)"
date: '2026-10-15'
commands: "python tools/ac_fp.py REQ-035 AC-4 --yaml -> faa18f01993e; db_run.py ... python attack_r2.py -> A1 NOT_CONNECTED with AC-5 text 09:20:09 AM, no table, ltp None; control COMPUTED; db_run.py ... pytest -c pytest-app.ini tests_app/test_strategy_live_push.py tests_app/test_outcome_route.py tests_app/test_openapi_drift.py -> 37 passed; mutant (fallback ignored) on test_ac5_two_holders... -> 1 failed 'COMPUTED' == 'NOT_CONNECTED'; npm run lint -> exit 0; npx vitest run -> 87 passed (7 files); vite build -> exit 0; replay API :8001 + vite preview :4175 + npx playwright test e2e/strategy-live.spec.ts -> 4 passed (1280 + 390); servers killed by PID. Live push proven on real Kite data 2026-10-15 (57 pushes 13:47, 49 pushes 14:09; docs/research/kite-proof-2026-10-07/w065-ws-proof-2026-10-15*.json)."
---

AC: AC-4
result: pass
commands: python tools/ac_fp.py REQ-035 AC-4 --yaml -> faa18f01993e; db_run.py ... python attack_r2.py -> A1 NOT_CONNECTED with AC-5 text 09:20:09 AM, no table, ltp None; control COMPUTED; db_run.py ... pytest -c pytest-app.ini tests_app/test_strategy_live_push.py tests_app/test_outcome_route.py tests_app/test_openapi_drift.py -> 37 passed; mutant (fallback ignored) on test_ac5_two_holders... -> 1 failed 'COMPUTED' == 'NOT_CONNECTED'; npm run lint -> exit 0; npx vitest run -> 87 passed (7 files); vite build -> exit 0; replay API :8001 + vite preview :4175 + npx playwright test e2e/strategy-live.spec.ts -> 4 passed (1280 + 390); servers killed by PID. Live push proven on real Kite data 2026-10-15 (57 pushes 13:47, 49 pushes 14:09; docs/research/kite-proof-2026-10-07/w065-ws-proof-2026-10-15*.json).
observed: Round 1 (f5f6681) FAILED: with a second socket on the same legs, the REST fallback after this page's socket dropped answered COMPUTED, unlabelled (finding liveness-from-shared-subscribers). Round 2 (26b3df4): two holders, this page's socket dropped, REST with fallback=true -> NOT_CONNECTED, 'Live market data disconnected. Last updated: 09:20:09 AM. Live strategy monitoring is paused.', no table/summary, every leg ltp None; advanced level adds no advanced_details. Without the flag -> COMPUTED (default kept). A non-boolean flag -> 422. The page sets the flag in onDown, clears it only on a leg-matching push from the current socket, keeps the not-live message during fallback reloads, and drops a push whose legs differ. Pushes drive LTP and Unrealized P&L; no browser arithmetic on money; no token on the socket URL; nothing clipped at 390/1280. Orchestrator re-ran attack_r2.py: same A1/control output.
attack: (1) Round 1 two-holder attack with fallback=true: held. (2) Flag-clearing paths (reconnect before first push, leg edit or UX change during the outage, MAX_ATTEMPTS off): all keep fallback=true until a matching push (code read; test gap in #234). (3) Push matching: reversed leg order and '42.7'/'42.70'/'100'/'0.5' still match; draft-URL lots "2" or "042.70" normalized by the server -> pushes dropped (LOW, no in-app producer, #234). (4) fallback on the socket makes every push not-live (LOW, safe direction, #234). OpenAPI drift test green. (5) Round 1 LOW items (late push of the previous strategy, flicker) fixed. Mutation ignoring the flag turns the app test red.

Recorded by the orchestrator from the verifier's returned block.
