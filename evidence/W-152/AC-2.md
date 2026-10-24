---
work_item: W-152
ac: AC-2
requirement: REQ-133
ac_fp: "4329732f7311"
result: pass
verified_by: "independent verifier (Opus row 24 check on 7e9f5ee4, reproduced step 1 on the base)"
builder: "builders (Opus: row 24 20cdbbc1; Sonnet finisher 7e9f5ee4; orchestrator pin for outcome_waiting_first_price)"
date: '2026-10-24'
commands: "npx vitest run tests/strategy-live.test.js tests/live-strategies.test.js tests/execute-screen.test.js tests/live-push-match.test.js (110 passed); checker mutants M1 (any seq accepted) and M2 (unversioned push accepted) in useStrategyLive.js; pytest tests_app/test_live_frame_version.py; orchestrator mutation gate (pytest-app.ini): no version sent and version+1 killed"
---

AC: AC-2
result: pass
commands: npx vitest run tests/strategy-live.test.js tests/live-strategies.test.js tests/execute-screen.test.js tests/live-push-match.test.js (110 passed); checker mutants M1 (any seq accepted) and M2 (unversioned push accepted) in useStrategyLive.js; pytest tests_app/test_live_frame_version.py; orchestrator mutation gate (pytest-app.ini): no version sent and version+1 killed
observed: The strategy follow message carries a socket-own version (createLiveSocket versioned:true, frontend/src/composables/useStrategyLive.js); live_push.py echoes it through echo_seq; isCurrentVersion drops a push for an older version, or an unversioned push when the page sent one; the Builder, the Live Strategies card and Execute all use it
attack: M1: 24 failed, M2: 23 failed (incl. the Builder and card REQ-133 AC-2 tests); a v1 push after v2 is not drawn

Recorded by the orchestrator from the verifier's returned block.
