# Builder brief: #370 flaky e2e (saved draft missing after reload) - Tier B, root cause first

Common brief: docs/process/builder-brief.md
Core: the root cause of frontend/e2e/strategy-save-draft.spec.ts:71 not finding open-draft-<id> after a reload,
proven from a failing CI run's trace or the code path, before any fix.
Proof: the named mechanism (e.g. the saved list's ordering, limit or date filter hides the new draft, or the reload
races the list fetch) shown with path:line and, where possible, a deterministic local reproduction; then the class fix.
Spec basis: issue #370; REQ-038 AC-5 (a saved draft is stored and listed).
Copy from: none - test/list fix.
Findings checked: wall-clock-assertion-flakes-under-load, fixture-symbol-not-in-catalogue, parallel-branches-green-alone-red-together
Tier: B. Branch: build/fix-370-draft-list from origin/main.
Budget: 60 min wall-clock, 70 tool calls
Report: evidence-table

## Rules
- Hard cap: if no root cause is proven within 45 minutes, stop, push nothing, and report what was ruled out with
  evidence (the contract parks #370 after 1 h). Never raise a timeout as the fix.
- Failing runs to read: app-tests 39033719880 and 39034787611 (gh run view <id> --log-failed; download the Playwright
  trace artifact if present with gh run download).
- If the cause is a list rule (limit/order/date filter vs TEST_CATALOGUE_DATE 2026-10-16 against the real date), fix
  the rule or the test's assumption at class level, and grep every e2e spec that reads the saved list.
- Do not change the Strategy Builder's Save Draft behaviour or the Execute screen (GC-3L uses them Monday); a list
  route or test change is fine.

Rules: no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only;
no regenerated files in the PR.
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Plus in frontend/: npm run lint, npm run test:run; the e2e runs in CI.
