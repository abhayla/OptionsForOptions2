# Review brief: PR #393 (W-109 My Strategies) - Tier B, diff only, round 1

Common brief: docs/process/builder-brief.md (review task: read-only; diff only; no suite re-run)
Core: the page lists the signed-in user's saved strategies from GET /strategies, links to Builder and Execute, shows
no money, and changes only the two placeholder routes.
Proof: each finding cites path:line from gh pr diff 393.
Spec basis: REQ-009 AC-2; REQ-038 AC-5; work/W-109.md.
Copy from: none - a review.
Findings checked: money-value-computed-outside-engine, test-asserts-implementation-output
Budget: 10 min wall-clock, 20 tool calls
Report: evidence-table

Check: gh pr diff 393 --repo abhayla/OptionsForOptions2. (1) only the my-strategies and completed-strategies routes
changed; Builder and Execute pages untouched; (2) no money figure or arithmetic in the page; (3) Open in Builder loads
the draft the same way the Builder already does (no new save path); (4) the e2e asserts the real saved id, not a
hard-coded one; (5) vue-frontend rules: script setup, :key on v-for, no v-html, API paths from the shared api module.
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests (reviewer: not run; diff only)
Report (under 200 words): verdict PASS / REVISE with findings (path:line, one-line fix) and the evidence table.
