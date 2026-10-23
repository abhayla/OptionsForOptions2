---
work_item: W-139
ac: AC-7
requirement: REQ-114
ac_fp: "0df96a1aed55"
result: pass
verified_by: "independent verifiers (Opus, fresh context): chunk 1 Tier A review round 2 area 1 on 1c31dd05; redesign check on 7ba83146; redesign re-check on 1006ca32"
builder: "builders (Opus): chunk 1 review fix F1, F1 CI fix, independent redesign (index answer)"
date: '2026-10-23'
commands: "round 2 area 1: review2-a1/r2a.py + mutation (calendar check removed from the health path: tests/marketdata/test_market_closed_health.py 7 failed); redesign re-check: verify-redesign/v1.py, pytest -c pytest-app.ini tests_app/test_index_closed_market.py tests_app/test_rate_limit_door.py (46 passed), npx vitest run tests/index-closed-market.test.js (21 passed); DB part: CI #525"
---

AC: AC-7
result: pass
commands: round 2 area 1 review2-a1/r2a.py and the health-path mutant (killed); redesign re-check v1.py, tests_app/test_index_closed_market.py + test_rate_limit_door.py 46 passed, frontend/tests/index-closed-market.test.js 21 passed; DB part CI #525
observed: one market-state function (FeedState.market_closed / market_closed_for, backend/ofo/marketdata/feed_health.py) decides for quote health, the outcome, chain and index answers, the feed phase and the reconnect wait. On Saturday 2026-10-24 10:00 IST with Kite heartbeats every quote reads stale and every answer carries market_closed and last_price_at; the index answer is NOT_CONNECTED (never LIVE) and keeps the last value labelled stale with its time (backend/ofo_app/index_push.py:71-82, :99-103). The Strategy Builder, Option Chain, index strip, Market Context and Underlying/index view show the ADR-177 banner "Market closed. Prices are from <time>." and no live wording. Wednesday 10:00 unchanged (available / LIVE); holiday 2026-10-20, after hours and a date past the calendar read closed (fail closed). Closed-hours reconnect wait 300 s, capped by the next open (a drop at 09:14:59 reconnects at 09:15).
attack: Saturday heartbeats, holiday, Mon 15:29:59 vs 15:30:00, 2031 date; a forced 'available' quote on a closed market reads stale; health-path calendar check removed in a scratch copy - killed; frontend banner and closed-branch mutants - killed.

Recorded by the orchestrator from the verifiers' returned blocks.

History: recorded pass on 0e574b58 (Settings card only); re-verdicted FAIL by the chunk 1 Tier A review area 1 on 29d2dece (quote health ignored the calendar; the price screens read live on a closed market); fixed by F1 (one market-state path, banners) and the independent redesign (index answer), verified as above.
