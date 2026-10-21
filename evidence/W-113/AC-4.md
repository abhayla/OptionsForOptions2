---
work_item: W-113
ac: AC-4
requirement: REQ-049
ac_fp: "6d6a37a184db"
result: pass
verified_by: "verifier (sonnet, fresh context, Tier B; round 1 at 4f82043, re-verified at aaf1af8, 2026-10-19)"
builder: "builder (W-113)"
date: '2026-10-19'
commands: "cd frontend && npx vitest run tests/live-strategies.test.js tests/strategy-live.test.js tests/display-format.test.js tests/strategy-table.test.js; npm run lint; npx playwright test --list e2e/live-strategies.spec.ts (round 1)"
---

AC: AC-4
result: pass
commands: cd frontend && npx vitest run tests/live-strategies.test.js tests/strategy-live.test.js tests/display-format.test.js tests/strategy-table.test.js; npm run lint; npx playwright test --list e2e/live-strategies.spec.ts (round 1)
observed: vitest 4 files 68 passed; lint exit 0; diff 4f82043..aaf1af8: a card is paused once it was live and its own socket is not live (connecting after a drop), spot and legs hidden; first connect waits, not paused
attack: a connecting socket after a drop with the REST fallback held back -> paused, badge and dot, no figures; never-pushed card holds no figures

Round 1 (4f82043) passed with two MINORs (paused while reconnecting; a copied 'Unlimited' line), fixed in aaf1af8 and re-verified. Not yet proven: the page on live ticks (GC-5S core proof) and the replay e2e run (CI).

Recorded by the orchestrator from the verifier's returned block.
