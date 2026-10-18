# Review brief: W-089 broker settings (PR on build/W-089-broker-settings) - Tier A, fresh, round 1

Common brief: docs/process/builder-brief.md (review task: read-only; hands-on attacks first; no suite re-run)
Core: the status route reports the four statuses truthfully from real state, leaks no secret, Disconnect needs the
owner and keeps every other table, and the changes to kite_reads.py and live_market.py cannot alter any read or the
live feed Monday's run uses.
Proof: each finding cites path:line and a command run this turn.
Spec basis: REQ-015 AC-4, AC-8; REQ-051 AC-1; ADR-020; work/W-089.md.
Copy from: none - a review.
Findings checked: liveness-from-a-file-nobody-deletes, liveness-from-shared-subscribers, secret-filter-by-key-name, staleness-by-last-change-age, guard-without-killing-test, state-read-after-await
Threat model: in scope - the status reply's keys, the Disconnect door, the note_read() side effect in kite_reads.py, current_state() in live_market.py; out of scope - Kite's own login page.
Why Opus: Tier A - the diff touches kite_reads.py and live_market.py on the live order path.
Budget: 20 min wall-clock, 40 tool calls
Report: evidence-table

Read: gh pr diff <PR> --repo abhayla/OptionsForOptions2 (or git diff origin/main...origin/build/W-089-broker-settings).
Attacks:
1. kite_reads.py note_read(): can it raise, block, or change a reply on any path (failed read, partial read)? Is it
   called only after a successful reply? Mutation: what test dies without it?
2. live_market.current_state(): read-only? any lock/await that could stall the feed or a request?
3. Status allow-list: reply keys a closed set (generated test)? Any path where Connected is the default?
4. Disconnect: POST only, owner only, ends only the session row; strategies/plans/audit untouched (test proves it?).
5. Mutation: delete each guard (expiry check, feed-running check, owner check) and name the test that goes red; run
   the targeted tests on a scratch worktree under the session scratchpad if needed, then remove it.
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests (reviewer: targeted files only)
Report (under 300 words): verdict PASS / REVISE, findings (severity, path:line, one-line fix), evidence table.
