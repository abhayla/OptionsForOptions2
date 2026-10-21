# Builder brief: W-108 attribution before compare (#380 T1) - GC-2f core, Tier A

Common brief: docs/process/builder-brief.md
Core: per contract, the expected quantity is every strategy's held units plus the recorded standalone quantity; a
same-direction surplus of Zerodha's net beyond that is reported as outside lots and removed before
ofo.reconciliation.compare runs; compare is unchanged; the result keeps Zerodha's raw net.
Proof: tests_app/test_reconcile_attribution.py on tests/fixtures/kite_replies/ (orders, positions, trades -122104 and
-151006; tags OFS1V1L0 BUY 65, OFS1V2L0 SELL 65; lot 65): the seven cases in work/W-108.md (a)-(g) pass.
Spec basis: ADR-109 (2) and its first consequence; REQ-060 AC-4, AC-6, AC-7 and its 2026-10-18 owner decision section;
ADR-105; Q224; F-42.
Copy from: none - new app-layer adapter; the legacy-reuse map has no attribution row (reconciliation is built new).
Findings checked: verified-on-a-module-the-product-does-not-call, caller-supplied-verdict-trusted, guard-without-killing-test, held-without-platform-fill-invisible-to-ledger, test-asserts-implementation-output, broker-reply-shape-unproven-at-domain-boundary
Tier: A (reconciliation, quantities). Branch: build/W-108-attribution from origin/main. Work item: work/W-108.md.
Budget: 90 min wall-clock, 80 tool calls
Report: evidence-table

## What to build
- An adapter in backend/ofo_app/ (a new module, e.g. reconcile_attribution.py): input = the strategies' stored plan
  histories (what execute_plan.held_units takes, backend/ofo_app/execute_plan.py:188), the recorded standalone map, and
  Zerodha's positions reply parsed by the existing Kite reply adapter (backend/ofo_app/kite_replies.py); output = the
  StrategyRecords compare takes (active_version.intended_position built from held units; read
  backend/ofo/strategy/versions.py:156-157 and compare.py:385-473 first), the stripped broker net, the raw broker net,
  and the outside lots per contract.
- Call ofo.reconciliation.compare (compare.py:399) yourself; never accept a compare result or a held-units map from
  the caller (finding caller-supplied-verdict-trusted).
- Do NOT edit compare.py, execute_plan.py's existing functions, routes/execute.py or routes/execution_return.py (main is
  frozen for what GC-3L tests; no route wiring in this item).

## Attack cases the reviewer will run
1. Case (d): strategy short 65, outside long 65, Zerodha 0 -> must reach compare and block (an opposite-direction
   difference is never stripped).
2. Case (e): strategy 65 + standalone 25, Zerodha 90 -> no mismatch, nothing outside; the same with standalone NOT
   recorded -> 25 outside, not blocked.
3. Case (f): two strategies 65 each, Zerodha 65 -> both blocked (Q224), nothing outside.
4. A contract present in Zerodha's reply with net 0 and no strategy -> nothing reported.
5. Mutation: remove the same-direction check -> case (d) goes red; remove standalone from the expected sum -> case (e)
   goes red; strip before summing all strategies -> case (f) goes red. Name the killing test per guard.
6. Unknown key / missing quantity in a positions row -> fail closed (ValueError), not 0.

## B4 standing items
(a) no time-budgeted job is touched; (b) no new CI import; (c) the attribution is a plain function, not a detector;
(d) every answer state of the positions read: row present, row absent, net 0, unparseable -> each has a test and a
stated result.

Rules: no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only;
no regenerated files in the PR. Money stays Decimal; quantities int.
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Plus your file: python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_reconcile_attribution.py (no
database needed if the adapter is pure; if it needs the DB, run it through scripts/orchestrator/db_run.py - targeted
file only, the VPS PostgreSQL also serves IPODhan production).
