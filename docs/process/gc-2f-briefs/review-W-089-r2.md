# Review brief: W-089 round 2 (PR #397, head 4d93001) - Tier A, fresh, narrow

Common brief: docs/process/builder-brief.md (review task: read-only; hands-on attacks first)
Core: the five round-1 findings are fixed, and the new _fetch wrapper in kite_reads.py changes no read's result,
error code or timing for any caller (the Execute and return routes use these reads).
Proof: each finding cites path:line and a command run this turn.
Spec basis: REQ-015 AC-4, AC-8; ADR-020 (Q94: broker features stop until reconnect).
Copy from: none - a review.
Findings checked: guard-without-killing-test, state-read-after-await, liveness-from-shared-subscribers
Threat model: in scope - live_market.stop_current, the Disconnect handler, kite_reads._fetch/_data and every fetch's note_read placement; out of scope - Kite's login page.
Why Opus: Tier A round 2 - kite_reads.py is on the live order path.
Budget: 20 min wall-clock, 40 tool calls
Report: evidence-table

Read: git diff 92f156f origin/build/W-089-broker-settings (round-1 changes) and the full diff vs origin/main.
Attacks:
1. _fetch/_data: for each existing error code and success path, is the exception type, code and returned value
   identical to main's? (Run tests_app/test_kite_reads.py and test_execute_replay.py, test_execution_return.py in a
   scratch worktree under the session scratchpad; remove it after.)
2. stop_current(): can it raise or hang if the feed is mid-reconnect, already stopped, or never registered? Does it
   leave a later login able to start a fresh feed (live_market.pick_up_login)?
3. forget() on token/unavailable: a transient 500 now shows Position sync Disconnected - acceptable per REQ-015 AC-4
   wording? (state it, no new finding unless it misleads).
4. Round-1 items 1-5: FIXED / NOT FIXED with line.
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests (reviewer: targeted files only)
Report (under 300 words): verdict PASS / REVISE, findings (severity, path:line, one-line fix), evidence table.
