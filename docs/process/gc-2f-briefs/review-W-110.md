# Review brief: W-110 money guard (branch build/W-110-money-guard) - Tier B guard, round 1

Common brief: docs/process/builder-brief.md (review task: read-only; hands-on attacks first; no suite re-run)
Core: the scan flags money arithmetic outside the engine across backend/ and frontend/src, the allow-list is right, and
each of the 9 pinned lines on main is classified correctly (real violation vs false alarm).
Proof: each finding cites path:line and a command run this turn.
Spec basis: REQ-063 AC-3; ADR-008; spec/business-rules/scenario-calculations.md; finding money-value-computed-outside-engine.
Copy from: none - a review.
Findings checked: guard-as-forbidden-list, guard-by-banned-shapes, guard-without-killing-test, money-value-computed-outside-engine
Threat model: in scope - arithmetic on money-named values in backend/ and frontend/src outside the allowed engine modules; out of scope - forged code built at run time, generated files, test files.
Why Opus: the 9-line triage decides whether parts of the execution and table code break ADR-008's one-engine rule (money paths).
Budget: 20 min wall-clock, 40 tool calls
Report: evidence-table

Read: git fetch origin build/W-110-money-guard; git show origin/build/W-110-money-guard:tests/test_money_outside_engine.py.
Do:
1. For each of the 9 KNOWN_ON_MAIN lines, read the code on main and classify: REAL (a money/P&L figure computed
   outside the one engine, ADR-008) or FALSE (not money, e.g. strike distance; or the module IS part of the engine per
   spec/business-rules/scenario-calculations.md and the allow-list should name it). One line each with path:line.
2. Attack the scan: a money value under a name the matcher misses (e.g. amount, value, cost, net), a computed money
   figure passed through a helper, Decimal arithmetic in frontend/src (Number() on an API string), sum() over a
   generator of premiums. Say which escape and whether it is in scope.
3. Is the baseline keyed robustly (a reformatted line vs a moved line)?
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests (reviewer: run only tests/test_money_outside_engine.py on the branch)
Report (under 350 words): verdict PASS / REVISE, the 9-line table (REAL/FALSE + reason), escapes found, evidence table.
