---
work_item: W-115
ac: AC-4
requirement: REQ-008
ac_fp: "b0c879a99d43"
result: pass
verified_by: "verifier (opus, fresh context, Tier A scope; round 1 a219c3b sonnet FAIL AC-4, round 2 46d99af opus, 2026-10-19)"
builder: "builder (W-115, sonnet)"
date: '2026-10-19'
commands: "npx vitest run tests/index-live-state.test.js tests/index-view.test.js tests/home.test.js; scratch attack vitest (15 tests)"
---

AC: AC-4
result: pass
commands: npx vitest run tests/index-live-state.test.js tests/index-view.test.js tests/home.test.js; scratch attack vitest (15 tests)
observed: index-live-state 10 passed; attack 15/15 passed; round 1 (a219c3b) FAILED this AC: the strip kept the last LIVE number after its own socket dropped; round 2 (46d99af) moved the liveness state machine into useIndexAnswer, used by the page and the strip
attack: drop + fallback rejects/NOT_CONNECTED/hangs; stale read; 2 drops with reads in flight; late frame; page+strip together; unmount mid-read - no old number shown

Recorded by the orchestrator from the verifier's returned block.
