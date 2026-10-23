---
work_item: W-137
ac: AC-2
requirement: REQ-113
ac_fp: "954c05ec5278"
result: pass
verified_by: "independent verifiers (Opus, fresh context; final round on 4b829faf)"
builder: "builders (Sonnet, builder sequence row 9: parts A0, A1, B, C and their fix/finish rounds)"
date: '2026-10-23'
commands: "final round: DB run; npm run test:run (551 passed, learn.test.js known CRLF); playwright e2e/feed-reconnect.spec.ts with Chrome on vite preview (2 passed, mobile-390 and desktop-1280)"
---

AC: AC-2
result: pass
commands: final round: DB run; npm run test:run (551 passed, learn.test.js known CRLF); playwright e2e/feed-reconnect.spec.ts with Chrome on vite preview (2 passed, mobile-390 and desktop-1280)
observed: backend: test_feed_restart_core - an API restart keeps the feed's one Kite connection and fresh frames reach the new API; browser: every live screen shows reconnecting from one constant, no old price live, resumes within 10 s
attack: socket refused 5 s -> reconnecting shown, nothing live, resumed within 10 s; late push on a dropped socket never live; reconnect timing 1 s x30 then 2..30 s (vitest, fake timers). Live restart against Zerodha: live check pending (row 63)

Recorded by the orchestrator from the verifier's returned block.
