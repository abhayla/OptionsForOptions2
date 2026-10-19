# Builder brief: W-111 Positions screen part 1 (REQ-044 AC-3) - Tier A, stacked on W-108

Common brief: docs/process/builder-brief.md
Core: on the recorded 2026-10-16 positions reply, a read route and the Positions page show the strategy's own 65 and
nothing outside; on a derived reply with 130 they show 65 own and 65 outside lots, apart, with no P&L figure.
Proof: tests_app/test_positions_route.py on tests/fixtures/kite_positions/positions-2026-10-16-one-ce.json and
tests/fixtures/kite_replies/positions-*.json; frontend/e2e/positions.spec.ts.
Spec basis: REQ-044 AC-3 and its 2026-10-18 owner decision; ADR-109 (2), (5); REQ-009 AC-3; ADR-027; work/W-111.md.
Copy from: check spec/technical-design/legacy-reuse.md for a positions page row; if none, Copy from: none - no map row (say so).
Findings checked: caller-supplied-verdict-trusted, money-value-computed-outside-engine, broker-reply-shape-unproven-at-domain-boundary, trust-broker-status-word
Threat model: in scope - the read route's attribution (it must call W-108's attribute_and_compare, never take held units or outside lots from the client) and the page showing quantities only; out of scope - P&L, margin, Greeks (part 2).
Tier: A (a read feeding quantities). Branch: build/W-111-positions, created FROM origin/build/W-108-attribution (stacked).
Budget: 75 min wall-clock, 80 tool calls
Report: evidence-table

## What to build
- A GET read route (new module under backend/ofo_app/routes/) that reads Zerodha positions through the existing Kite
  read path used by the return route (find it: kite_reads / kite_replies.positions_from_reply), the strategies' stored
  plans and the recorded standalone map, and calls reconcile_attribution.attribute_and_compare (W-108). Reply: per
  contract - own units per strategy (with a link target to that strategy), outside units, blocked yes/no; closed key set.
- The Positions pages: replace the current-positions and strategy-linked-positions placeholders in
  frontend/src/router/routes.js; show quantities and the strategy link only. No money figure anywhere, no order button
  (ADR-002, ADR-027: actions route back to the strategy).
- Without a live Kite session the route answers a plain catalogue message (not an empty list pretending all is flat).
- Do NOT touch routes/execute.py, routes/execution_return.py, the Execute screen or the Strategy Builder.
- Regenerate docs/api/openapi.json in the same PR.

## Attack cases
1. Client-supplied held units or outside lots are ignored (route takes none).
2. No session / failed read -> the catalogue message, never "no positions".
3. 130 vs own 65 -> 65 outside, strategy not blocked; 0 vs own 65 -> blocked shown.
4. Reply keys are a closed set (generated test); no price, pnl, margin key.
B4: (d) every answer state of the positions read (present, absent, empty, failed, no session) has a test and stated page text.
Rules: no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only;
no regenerated files in the PR except docs/api/openapi.json.
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Plus tests_app/test_positions_route.py (DB via scripts/orchestrator/db_run.py, targeted only; delete frontend/node_modules
before the guard tests); in frontend/: npm run lint, npm run test:run.
