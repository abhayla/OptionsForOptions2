# Review brief: PR #395 (#370 e2e pool budget) - Tier B, diff only, round 1

Common brief: docs/process/builder-brief.md (review task: read-only; diff only; no suite re-run)
Core: the e2e API processes can no longer exhaust the ofo_app role's connection limit, and production defaults are
unchanged.
Proof: each finding cites path:line from gh pr diff 395.
Spec basis: issue #370; ADR-048.
Copy from: none - a review.
Findings checked: setting-read-from-two-sources, guard-without-killing-test
Threat model: in scope - the e2e job's API processes and the pool-budget repo_scan test; out of scope - production connection sizing (defaults unchanged).
Budget: 10 min wall-clock, 20 tool calls
Report: evidence-table

Check gh pr diff 395 --repo abhayla/OptionsForOptions2: (1) DB_POOL_SIZE / DB_MAX_OVERFLOW defaults equal
SQLAlchemy's (5 / 10) so a deploy without them behaves as before; invalid values refused; (2) all three e2e API starts
set the budget and 3 x (1+0) leaves room under CONNECTION LIMIT 5 for seeding/tests; (3) is pool 1 / overflow 0 enough
for one API process serving parallel Playwright workers (a request waiting on the single connection vs timing out:
what is the pool timeout?); (4) the repo_scan test really fails when a start lacks the budget (read it; say whether a
removed env line would be caught).
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests (reviewer: not run; diff only)
Report (under 200 words): verdict PASS / REVISE with findings (path:line, one-line fix) and the evidence table.
