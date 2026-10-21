# Review brief: GC-3L precondition re-check after GC-2f (chain rule 3, scoped, fresh)

Common brief: docs/process/builder-brief.md (review task: read-only)
Core: Monday's GC-3L (contract + delta + runbook) is still correct on main as it is tonight, given ADR-109 and the
GC-2f close-out; nothing merged tonight changes what it tests.
Proof: each finding cites path:line and a command run this turn.
Spec basis: ADR-108; ADR-109; docs/process/goal-chain.md chain rule 3.
Copy from: none - a review.
Findings checked: verified-on-a-module-the-product-does-not-call
Why Opus: chain rule 3 - it precedes a real-money run.
Budget: 15 min wall-clock, 30 tool calls
Report: evidence-table

Read on main (git pull first): docs/process/goal-contract-GC-3L-2026-10-19.md,
docs/process/goal-contract-GC-3L-delta-2026-10-18.md, docs/process/gc-3l-runbook-2026-10-19.md,
spec/decisions/ADR-108.md, spec/decisions/ADR-109.md, docs/process/goal-chain.md.
Check:
1. `git log --oneline 298eab3..origin/main` and `git diff --stat 298eab3 origin/main`: only docs/spec/views/work/knowledge
   paths changed since GC-3L's review (no product code); name the newest product-code commit and its CI run state.
2. Does ADR-109 (app-owned lots; outside surplus never blocks) contradict any GC-3L step or ADR-108 rule as they will
   run Monday on today's code (which still blocks only a shortfall - main's strategy_blocked)? A conflict only if
   Monday's run would behave differently from what the runbook tells the owner.
3. The delta's 08:30 fallback prompt and the GC-2f lock rule read correctly.
4. Open lock branches on origin (git ls-remote origin 'lock/*') - report.
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests (reviewer: none - read-only)
Threat model: in scope - GC-3L's steps vs main and ADR-108/109; out of scope - the held GC-2f PRs.
Report (under 250 words): verdict READY / CHANGES NEEDED, findings (severity, path:line, one-line fix), evidence table.
