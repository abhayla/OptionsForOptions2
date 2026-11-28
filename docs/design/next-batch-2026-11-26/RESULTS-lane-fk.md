STATUS 10:55 | item 1: fixed, not tested; item 2: done | next push: NOT PUSHED, gate cannot pass in this container | blocker: environment (see Gate)

# Lane FK: chart teardown

## Cause (corrected from the brief)
The late redraw is not only "after unmount". `tests/charges-dialog-drafts-d13-d14.test.js` stubs PayoffChart; the real
chart is never built in that file (instrumented: 0 calls). Many other test files mount the real chart and never unmount
it. Their queued redraw runs after happy-dom is torn down and reads `document` / `documentElement`; vitest reports it
against whichever file is running. Both paths are now guarded.

## Fix (class: no chart work once removed or once the DOM is gone)
- PayoffChart.vue: `gone` flag set in onUnmounted; createChart returns (destroying any chart) when gone or `document` is missing.
- AdjustPayoffChart.vue, StrategyPriceChart.vue (draw runs after `await nextTick()`): same guard.

## Proof
- New `frontend/tests/payoff-chart-teardown.test.js` (6 tests). Red on base: "late redraw after teardown" failed with
  `Cannot read properties of undefined (reading 'documentElement')` (unhandled rejection captured). Green after the fix.
  The three plain unmount tests passed on the base: the unmount-only path was already safe in Vue.
- `charges-dialog-drafts-d13-d14.test.js` x20: 20/20 `6 passed`, zero errors.
- Whole frontend unit suite x3: each 331 files, 3837 tests passed, no Errors/Unhandled lines.
- eslint --max-warnings 0 on the 3 components and the test: clean.

## Gate (3 runs, not TOTAL PASS; none of the failures is in the changed files)
Run 3 (after installing requirements-dev/app and ruff on PATH): ruff_ratchet, coverage, alembic_guard, frontend_lint,
frontend_build PASS. FAIL: app_tests (`git diff` rc 128: no base ref in this clone), ci_checks (1 of 19:
`git merge-base origin/main HEAD` failed, same missing ref), frontend_unit (log full of `ECONNREFUSED 127.0.0.1:3000`,
a local test server not reachable here; my 3 direct runs of the whole suite passed). Parked after two rounds.
Next command on a machine with full history and the local servers: `python scripts/orchestrator/prepush.py`, then
`git push -u origin fix/r3-chart-teardown-1128`.

## Item 2: other chart components
Grep: `new Chart(`, `createChart`, `nextTick`, `onMounted`, `onBeforeUnmount` under frontend/src/components.
Found and fixed: AdjustPayoffChart.vue, StrategyPriceChart.vue.

## For the owner lane (Lane FJ, not edited)
`frontend/tests/setup.js`: add `enableAutoUnmount(afterEach)` from @vue/test-utils so no test leaves a component
mounted past its file. That removes the source of the late redraws for every component, not only charts.

## Pending owner read: none (no new on-screen text).
| task | model | minutes |
|---|---|---|
| all | Sonnet | ~20 |

SAFE TO CLOSE
