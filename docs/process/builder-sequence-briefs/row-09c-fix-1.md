# Row 9 part C fix round 1: REQ-113 (W-137) - two browser tests that die without their guard

Common brief: docs/process/builder-brief.md (Budget hard stop: at 24 calls start nothing new, commit, report).
Size: S, 2 files, 2 items
CI: app job `frontend` (`npm run test:run`, vitest: `frontend/tests/index-view.test.js`,
`frontend/tests/feed-reconnect.test.js`; vars: none). Locally `npm run lint` and `npm run test:run` in `frontend/`
(`tests/learn.test.js` fails on this Windows checkout only, a CRLF line end - known, not yours).
Expected (orchestrator, before dispatch 00:10 IST): 15 min / ~70k (R5: small follow-up -> fresh agent).

Core: the index socket never sends a body, and "reconnecting" never shows on a first connect after a stop.
Proof: each new test is red on its mutant (F4: drop the `sendBody` guard in `onopen`; F1: drop the `everLive` reset on
`off` in `useReconnecting`) and green on the code. The A1+C verifier's mutation copies are in
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\b9b5cb32-ea0c-400f-80e1-fbd7045cbf2a\scratchpad\verify-09a1c`.

Spec basis: REQ-113 AC-2: "Browser websockets reconnect to the new API and resume within 10 s, showing "reconnecting"
meanwhile and never an old price as live (ADR-015)."
Copy from: none - tests only.

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1`. PART B IS BUILT IN THE SAME
TREE AT THE SAME TIME (backend and tests_app): touch ONLY the two test files below; commit ONLY them with
`git commit -F <msg> -- <your paths>` as its own call; never `git stash`, `checkout --`, `reset`, `restore`, `add -A`;
do NOT push. Scratch: `...\b9b5cb32-ea0c-400f-80e1-fbd7045cbf2a\scratchpad\row09c-fix1`.

## What to do (tests only)
1. F4: in `frontend/tests/index-view.test.js` (near line 64), open the fake socket (`ws.serverOpen()`) BEFORE
   `expect(ws.sent).toEqual([])`, so the test proves nothing is sent on open.
2. F1: in `frontend/tests/feed-reconnect.test.js`, live -> `stop()` -> `follow()` again: while connecting, the
   reconnecting flag is false (a first connect is not a reconnect).
Run each mutant in a scratch copy: red; then the real code: green.

Attack list: (each names its test file)
1. The index socket sends nothing after open (`frontend/tests/index-view.test.js`).
2. A stop then a new follow shows no "reconnecting" while the first connect is pending (`frontend/tests/feed-reconnect.test.js`).
3. A drop after the new follow has been live does show "reconnecting" (`frontend/tests/feed-reconnect.test.js`).
4. The existing index tests still pass (`frontend/tests/index-view.test.js`).
5. The existing reconnect tests still pass (`frontend/tests/feed-reconnect.test.js`).

Standing items: (a) n/a: no time-budgeted job; (b) n/a: no CI step changes; (c) n/a: no static detector; (d) n/a: tests only, the socket answer states are already listed in feed-reconnect.test.js.
Threat model: in scope - the index socket sending a body, a false "reconnecting" on first connect; out of scope - server side.
Findings checked: wall-clock-assertion-flakes-under-load
Reviewer checklist: each test red on its mutant; fake timers only; no product-code change; no new duplicated literal;
reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no regenerated files in the PR.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 15 min wall-clock, 30 tool calls
Report: evidence-table
