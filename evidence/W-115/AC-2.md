---
work_item: W-115
ac: AC-2
requirement: REQ-008
ac_fp: "56b07830ac77"
result: fail
verified_by: "verifier (opus, fresh context, Tier A scope; round 1 a219c3b sonnet FAIL AC-4, round 2 46d99af opus, 2026-10-19)"
builder: "builder (W-115, sonnet)"
date: '2026-10-19'
commands: "npx vitest run tests/index-live-state.test.js tests/index-view.test.js tests/home.test.js"
---

AC: AC-2
result: fail
commands: npx vitest run tests/index-live-state.test.js tests/index-view.test.js tests/home.test.js
observed: home.test.js 7 passed; Home's state comes only from GET /strategies (a reply that is not a list -> error, no guessed state); new and has-strategies states correct
attack: failed read and non-array reply -> error state (pass); the third AC state (active strategies, Important Alerts, what needs attention) is absent: parked as #433 (the store allows only status draft; alerts are GC-4)

Recorded by the orchestrator from the verifier's returned block.
