# Review brief: W-108 attribution before compare (branch build/W-108-attribution) - Tier A, fresh, round 1

Common brief: docs/process/builder-brief.md (review task: read-only; hands-on attacks first)
Core: the adapter gives ADR-109 (2)'s answers for every case - an outside same-direction surplus never blocks; a
shortfall, an opposite-direction net, and Q224 shared contracts always block; recorded standalone counts as expected.
Proof: each finding cites path:line and a command run this turn.
Spec basis: ADR-109 (2) and its first consequence; REQ-060 AC-4, AC-6, AC-7 and its 2026-10-18 owner decision; Q224; ADR-105; F-42.
Copy from: none - a review.
Findings checked: verified-on-a-module-the-product-does-not-call, caller-supplied-verdict-trusted, guard-without-killing-test, test-asserts-implementation-output, held-without-platform-fill-invisible-to-ledger, broker-reply-shape-unproven-at-domain-boundary
Threat model: in scope - every way a caller or a reply can make a strategy look unblocked when its own lots are short, or blocked when only outside lots differ; out of scope - route wiring (GC-3F).
Why Opus: GC-2f core, Tier A reconciliation; it decides when real strategies get blocked.
Budget: 20 min wall-clock, 40 tool calls
Report: evidence-table

Read git show origin/build/W-108-attribution:backend/ofo_app/reconcile_attribution.py and the test file; use a scratch
worktree under the session scratchpad to run tests (remove it after).
Attacks:
1. Construct inputs where outside lots and own lots are confused: own short + outside short on one contract with
   Zerodha shorter than own (shortfall must block); own long 65 + standalone long 25 + Zerodha 130 (40 outside, not
   blocked); standalone larger than the surplus; negative standalone; standalone on a contract no strategy holds.
2. Can a caller pass held units, a compare result or a forged StoredPlan and get "not blocked"? (caller-supplied-verdict-trusted)
3. Holders on both sides (A +130, B -65): the builder fails closed - is that consistent with ADR-109 and REQ-060 AC-7, or does it block a strategy whose own lots agree? Say which, with numbers.
4. Expected values: are the tests' expected numbers hand-derived or pasted from the code's output?
5. The tag decode: a plan whose orders carry another strategy's tag - refused?
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests (reviewer: only tests_app/test_reconcile_attribution.py)
Report (under 350 words): verdict PASS / REVISE, findings (severity, path:line, one-line fix), covers the class: yes/no, evidence table.
