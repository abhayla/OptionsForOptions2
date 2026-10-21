# Review brief: W-110 round 2 (PR #396, head 548462e) - narrow re-check

Common brief: docs/process/builder-brief.md (review task: read-only; no suite re-run beyond the one file)
Core: the round-1 escapes are caught or listed as documented limits, and NOT_MONEY_ON_MAIN exempts only non-money lines.
Proof: one row per round-1 item with path:line.
Spec basis: REQ-063 AC-3; ADR-008.
Copy from: none - a review.
Findings checked: guard-as-forbidden-list, guard-without-killing-test, money-value-computed-outside-engine
Threat model: in scope - the round-1 escapes (tokens value/loss/profit/unrealized, annotated and tuple aliases, comprehensions, PnL camelCase, JS unary plus, bracket keys, next-line operator, parenthesised operand); out of scope - the limits the docstring now lists.
Budget: 15 min wall-clock, 25 tool calls
Report: evidence-table

Read git show origin/build/W-110-money-guard:tests/test_money_outside_engine.py. For each round-1 item (1 tokens + pin
table/model.py:257 and :359; 2 aliases; 3 camelCase; 4 JS shapes; 5 mutation asserts; 6 docstring limits): FIXED /
NOT FIXED with line. Then read each of the 11 NOT_MONEY_ON_MAIN lines on main and say whether any is actually money
(that would be a silenced violation). Optionally run the one test in a scratch worktree under the session scratchpad
(remove it after).
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests (reviewer: only tests/test_money_outside_engine.py)
Report (under 200 words): verdict PASS / REVISE, rows, evidence table.
