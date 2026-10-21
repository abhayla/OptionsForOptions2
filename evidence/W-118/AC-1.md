---
work_item: W-118
ac: AC-1
requirement: REQ-029
ac_fp: "b0abe057d492"
result: pass
verified_by: "verifier (sonnet, fresh context, Tier B; round 1 f6aa87e FAIL, round 2 9cf0592, 2026-10-19)"
builder: "builder (W-118, sonnet, 2 rounds)"
date: '2026-10-19'
commands: "npx vitest run tests/option-chain.test.js tests/strategy-live.test.js tests/live-push-match.test.js; npm run lint; scratch vitest.attack.config.mjs (9 attacks)"
---

AC: AC-1
result: pass
commands: npx vitest run tests/option-chain.test.js tests/strategy-live.test.js tests/live-push-match.test.js; npm run lint; scratch vitest.attack.config.mjs (9 attacks)
observed: 37 tests passed, lint clean, 9 attack tests passed. Round 1 (f6aa87e) FAILED with a CRITICAL (NIFTY numbers under the SENSEX label after an underlying switch); round 2 (9cf0592) clears the answer at once on either choice change. Live check 2026-10-19 14:32 IST on the run build: NIFTY 22865.45 live, full Calls | Strike | Puts table.
attack: A1/A2 slow and failing catalogue after a switch: no old number, late NIFTY push ignored; B1 NIFTY->SENSEX->NIFTY fast with reads in flight: nothing leaks; B3 late old-expiry push ignored; B4 stale fallback ignored; B5 unmount closes the socket.

Recorded by the orchestrator from the verifier's returned block.
