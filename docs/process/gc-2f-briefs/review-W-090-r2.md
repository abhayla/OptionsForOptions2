# Review brief: W-090 round 2 (PR #399, head 9b0493f) - narrow re-check

Common brief: docs/process/builder-brief.md (review task: read-only; no suite re-run beyond the named files)
Core: the three round-1 findings are fixed and nothing else changed behaviour.
Proof: one row per finding with path:line and a command run this turn.
Spec basis: REQ-034 AC-4, AC-5, AC-6; ADR-042.
Copy from: none - a review.
Findings checked: test-asserts-implementation-output, state-read-after-await
Threat model: in scope - matchesChoice and the customised flag, the breakeven test, the single config object; out of scope - everything round 1 passed.
Budget: 15 min wall-clock, 25 tool calls
Report: evidence-table

Read git diff bbcfb53 origin/build/W-090-range-step. Check: (1) the default pick rejects a push with customised true
and a custom pick needs customised true plus matching ends (vitest case present; reason about the null/undefined
customised of an older server - accepted only as default?); (2) breakevens in tests_app/test_outcome_range_params.py
are hand-derived in the docstring (73.15 net credit; 22873.15 and 22326.85) and asserted as literals; (3)
scenario_choice returns one config used by both the check and build_outcome. Optionally run
tests_app/test_outcome_range_params.py in a scratch worktree under the session scratchpad (remove it after; use
-p no:metadata on Windows).
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests (reviewer: only the one file)
Report (under 200 words): verdict PASS / REVISE, rows, evidence table.
