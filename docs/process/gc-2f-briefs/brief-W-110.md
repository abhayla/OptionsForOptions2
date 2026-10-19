# Builder brief: W-110 repo-wide money guard (REQ-063 AC-3) - Tier B

Common brief: docs/process/builder-brief.md
Core: a repo_scan test fails when a money or P&L figure is computed outside the calculation engine, anywhere in
backend/ or frontend/src, and passes on main.
Proof: mutation - a planted premium times quantity in backend/ofo_app and in a frontend/src .vue/.js file turns
tests/test_money_outside_engine.py red; main is green.
Spec basis: REQ-063 AC-3; ADR-008; the GC-1 audit docs/process/4a-closeout-audit-2026-10-16.md; finding
money-value-computed-outside-engine; work/W-110.md.
Copy from: none - a repo scan test; the existing guard over backend/ofo/rules/ is the pattern to widen (find it first:
grep tests/ for the finding id or for backend/ofo/rules).
Findings checked: money-value-computed-outside-engine, guard-as-forbidden-list, guard-by-banned-shapes, repo-wide-scan-outside-targeted-tests, guard-without-killing-test
Threat model: in scope - arithmetic on money-named values (premium, price, pnl, charges, margin, ltp and their Decimal/Number conversions) in backend/ofo_app and frontend/src outside the engine's allowed modules; out of scope - forged code built at run time, generated files, test files.
Tier: B (a test). Branch: build/W-110-money-guard from origin/main.
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table

## Rules
- The allowed homes are an allow-list (engine and scenario modules, the money helpers, chart-only Number() calls the
  vue rule permits); everything else is scanned (finding guard-as-forbidden-list).
- If main itself has violations, list each with path:line in the report and do NOT silence them: a real violation on
  main is a finding (file it as a deferred issue text in your report; the orchestrator files it).
- Mark the test repo_scan. Update knowledge/findings/money-value-computed-outside-engine.json's guard reference (no
  INDEX regeneration in this PR).

B4: (c) the scan fails closed on shapes it cannot resolve (aliased imports, re-exports) and names its guard by import
source, not identifier text.
Rules: no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only;
no regenerated files in the PR.
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
