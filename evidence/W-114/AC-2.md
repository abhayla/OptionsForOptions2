---
work_item: W-114
ac: AC-2
requirement: REQ-072
ac_fp: "d0a6b6685613"
result: pass
verified_by: "verifier (opus, fresh context, Tier A; round 1 dbc4d84 FAIL, round 2 7740aa8 PASS, 2026-10-19)"
builder: "builder (W-114, sonnet round 2; opus round 1)"
date: '2026-10-19'
commands: "git diff dbc4d84 7740aa8 --stat; cd frontend && npx vitest run tests/index-view.test.js; npm run lint; python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_index_live.py; scratchpad attack tests run on 7740aa8 and on the dbc4d84 page"
---

AC: AC-2
result: pass
commands: git diff dbc4d84 7740aa8 --stat; cd frontend && npx vitest run tests/index-view.test.js; npm run lint; python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_index_live.py; scratchpad attack tests run on 7740aa8 and on the dbc4d84 page
observed: Round 1 (dbc4d84, Tier A Opus): backend held - two holders 2->1->0 and the survivor ticks, fallback with another holder NOT_CONNECTED with no value, 50-change burst 0 pushes then 1, money as strings; FAIL on the page (old value kept after a drop with a failing fallback). Round 2 (7740aa8, Tier A Opus): frontend-only diff; 11/11 vitest; lint clean; 18 passed; attacks 4/4 pass on round 2, 3/4 fail on round 1
attack: two drops with reads in flight resolving LIVE out of order; fallback held then new socket push; drop checked before the fallback settles; 10 failed reconnects (passes on dbc4d84 too, catches nothing). None showed a value without a fresh LIVE answer. Open-but-silent socket is the known server-side gap (staleness-by-last-change-age), not claimed. Live-tick proof: pending (after GC-3L).

Recorded by the orchestrator from the verifier's returned block.
