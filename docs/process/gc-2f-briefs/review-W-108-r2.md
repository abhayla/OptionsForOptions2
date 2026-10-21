# Review brief: W-108 round 2 (PR #398, head 0db9fa9) - Tier A, fresh, narrow

Common brief: docs/process/builder-brief.md (review task: read-only; hands-on attacks first)
Core: no caller can hide a plan or a strategy; a recorded standalone only adds to the expected quantity; two stored ids
of one contract add up; the seven ADR-109 cases still hold.
Proof: each finding cites path:line and a command run this turn.
Spec basis: ADR-109 (2); REQ-060 AC-4, AC-6, AC-7 and its 2026-10-18 owner decision; Q224.
Copy from: none - a review.
Findings checked: caller-supplied-verdict-trusted, guard-without-killing-test, test-asserts-implementation-output
Threat model: in scope - the store-reader seam (list_strategies, plans_for), the Account/Sources checks, the standalone direction rule, the per-key sum; out of scope - route wiring (GC-3F).
Why Opus: Tier A round 2 of the GC-2f core.
Budget: 20 min wall-clock, 40 tool calls
Report: evidence-table

Read git diff 0e5372b origin/build/W-108-attribution. Attacks:
1. Can a caller still pass a subset? (a custom StoreReader subclass, a reader returning a filtered list, a strategy
   status filter in list_strategies, a user_ref for another user) - each refused or harmless?
2. Does list_strategies return EVERY strategy of the user (read its SQL on main), and plans_for EVERY plan (any
   status/limit filter)? path:line.
3. Standalone direction table (own +65, standalone -25: Zerodha 40/65/130/0) and a standalone-only contract - by hand.
4. Round-1 items 1-3: FIXED / NOT FIXED with line; run tests_app/test_reconcile_attribution.py in a scratch worktree
   under the session scratchpad (use -p no:metadata on Windows; remove the worktree after).
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests (reviewer: only the one file)
Report (under 300 words): verdict PASS / REVISE, findings (severity, path:line, one-line fix), covers the class: yes/no, evidence table.
