# Builder brief: W-109 My Strategies list + Completed filter - Tier B

Common brief: docs/process/builder-brief.md
Core: a strategy saved with Save Draft appears in My Strategies after a reload, and its links open the Builder and the
Execute screen for that id.
Proof: frontend/e2e/my-strategies.spec.ts (runs in CI's app-tests job against the real API on the test database).
Spec basis: REQ-009 AC-2; REQ-038 AC-5; OQ-13; work/W-109.md.
Copy from: check spec/technical-design/legacy-reuse.md for a strategies-list page row; if none, Copy from: none - no
map row (say so in the report).
Findings checked: fixture-symbol-not-in-catalogue, wall-clock-assertion-flakes-under-load
Tier: B (display only, no money figure, no new route). Branch: build/W-109-my-strategies from origin/main.
Budget: 50 min wall-clock, 70 tool calls
Report: evidence-table

## Facts on main
- GET /strategies at backend/ofo_app/routes/strategies.py:329 returns SummaryOut (id, underlying, status, timestamps;
  :143-148), scoped to the signed-in user (:330-331). Use it as is; no backend change.
- Replace only the my-strategies and completed-strategies placeholder routes (frontend/src/router/routes.js + nav.js).
- Completed filter: list in your report the status values the route returns; show the filter only for values that
  exist. Never compute or show money on this page.
- Do not change the Strategy Builder or the Execute screen (GC-3L uses them on Monday): link to them only.

## Attack cases
1. Another user's strategies never appear (scoping test).
2. Empty list -> a plain empty state, no error.
3. A status value the page does not know -> shown as-is, not dropped.

B4: (a)-(d) n/a (display only).
Rules: no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only;
no regenerated files in the PR.
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Plus in frontend/: npm run lint, npm run test:run, npm run build; the e2e spec runs in CI.
