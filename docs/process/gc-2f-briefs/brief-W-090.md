# Builder brief: W-090 range/step + At Expiry / Estimated Now - Tier B

Common brief: docs/process/builder-brief.md
Core: a user-chosen range and step reach the outcome route and change the scenario columns the Strategy Builder shows.
Proof: tests_app/test_outcome_range_params.py: a request with a custom range/step returns exactly the levels that
range and step produce (hand-computed); frontend/e2e/strategy-range-step.spec.ts shows them.
Spec basis: REQ-034 AC-4 (user customises range and step), AC-6 (switch between the two columns); ADR-042 (SENSEX
range step); work/W-090.md.
Copy from: check spec/technical-design/legacy-reuse.md for a Strategy Builder range/step row; if none, Copy from: none -
no map row (say so in the report).
Findings checked: test-asserts-implementation-output, money-value-computed-outside-engine
Tier: B (display; the engine computes every number). Branch: build/W-090-range-step from origin/main.
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table

## Facts on main
- The outcome request already takes view (backend/ofo_app/routes/outcome.py:146); step at :231 is response-only. Add
  range/step to the request model, validated as an allow-list (closed bounds, step from the allowed set per index,
  ADR-042), then regenerate docs/api/openapi.json (python scripts/generate_openapi.py) in the same PR.
- The browser never computes a level or a P&L (vue-frontend rule): it sends range/step and shows what comes back.

## Attack cases
1. Step 0, negative, or not on the index's grid -> 4xx with the catalogue message, nothing computed.
2. Range so wide it exceeds the response cap -> refused, not truncated silently.
3. Switching At Expiry / Estimated Now keeps the chosen range/step.
4. grep tests/, tests_app/, frontend/tests/, frontend/e2e/ for any old default range/step value you change.

B4: (a) n/a; (b) n/a; (c) the request check is an allow-list; (d) n/a.
Rules: no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only;
no regenerated files in the PR except docs/api/openapi.json.
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Plus: tests_app/test_outcome_range_params.py (via scripts/orchestrator/db_run.py only if it needs the DB); in frontend/:
npm run lint, npm run test:run; the e2e spec runs in CI.
