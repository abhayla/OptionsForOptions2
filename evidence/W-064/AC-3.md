---
work_item: W-064
ac: AC-3
requirement: REQ-035
ac_fp: "4dce8468a9e1"
result: pass
verified_by: "verifier (sonnet, fresh context, final state 14b5a98)"
builder: "builder (sonnet, 3 rounds)"
date: '2026-10-09'
commands: "git worktree add --detach <SCRATCH>/verify/W-064b origin/build/W-064-screen (14b5a98); npm ci; npm run test:run; npm run build; replay API (APP_ENV=test, port 8001) + vite preview 4175; npx playwright test e2e/strategy-table.spec.ts; ad hoc scroll and route-intercept attack"
---

AC: AC-3
result: pass
commands: git worktree add --detach <SCRATCH>/verify/W-064b origin/build/W-064-screen (14b5a98); npm ci; npm run test:run; npm run build; replay API (APP_ENV=test, port 8001) + vite preview 4175; npx playwright test e2e/strategy-table.spec.ts; ad hoc scroll and route-intercept attack
observed: strategy-table.spec.ts 6 passed (sticky + highlight at 390 and 1280); vitest 27/27 on rerun; header and body offsets [0,72,144] after instant scrollLeft 200/600/max at 390 and 1280; PR #162 CI frontend job green
attack: Instant scrolls to 200, 600 and past the end at 390 and 1280: the sticky columns stay pinned with no overlap. The API response rewritten to move CURRENT from 22533.25 to 21500: exactly 21500 highlighted, so the highlight follows the API flag. A first-run vitest timeout in vendor-host-lint.test.js under load passed alone and on the full rerun.

Recorded by the orchestrator from the verifier's returned block.
