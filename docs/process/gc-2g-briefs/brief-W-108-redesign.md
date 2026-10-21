# Builder brief: W-108 independent redesign of the open-plan case (#405) - GC-2g core, Tier A

Common brief: docs/process/builder-brief.md
Core: an OPEN plan never makes the app's own lots read as outside and never clears a mismatch: a contract touched by
an open plan whose orders are not all final at Zerodha is reported PENDING (not outside, not agreeing) and its
strategy is blocked; once every one of the plan's orders is final in Zerodha's order book, their filled quantities
count as the strategy's own and the normal comparison applies.
Proof: tests_app/test_reconcile_attribution.py new cases on the real 2026-10-16 replies in tests/fixtures/kite_replies/
(orders-122104: tag OFS1V1L0 BUY 65 COMPLETE, filled 65; positions-122104: net 65; lot 65): plan 1 OPEN with that
order COMPLETE at Zerodha and Zerodha net 65 -> strategy 1 not blocked, nothing outside, nothing pending (fills read
from the order book); the same plan OPEN with the order row status rewritten to OPEN -> contract pending, strategy 1
blocked, 0 outside; the plan closed filled 65 -> agrees, nothing outside; the seven ADR-109 cases and the existing
tests still pass.
Spec basis: ADR-110 (decision and its consequence); ADR-109 (2); REQ-060 AC-6, AC-7; ADR-105; ADR-016; Q224; issue
#405.

ADR-110: "makes no own/outside split for it"
ADR-110: "The strategy is blocked until the plan closes."
ADR-110: "(by the app's tag) in a final state"
ADR-110: "so a plan the user never returns to cannot hide a shortfall or outside lots for good."
Copy from: none - redesign of an app-layer adapter already on build/W-108-attribution; the legacy-reuse map has no
attribution row (reconciliation is built new).
Findings checked: state-with-no-working-exit, caller-supplied-verdict-trusted, held-without-platform-fill-invisible-to-ledger, broker-reply-shape-unproven-at-domain-boundary, guard-without-killing-test, test-asserts-implementation-output
Threat model: in scope - the open-plan read (tag lookup in Zerodha's parsed order book, final-state allow-list, a
missing/duplicated/mismatched row), the StoreReader seam, the outside cap; out of scope - route wiring, the stored
sticky block, the reconcile screen (GC-3F), forged Python objects (ADR-098).
Why Opus: Tier A independent redesign after a round-2 MAJOR on reconciliation quantities (CLAUDE.md fast delivery 5).
Tier: A. You are a FRESH builder: you did not build W-108. Branch: build/W-108-attribution (draft PR #398, head
0db9fa9). In your worktree: `git fetch origin` then `git checkout -B build/W-108-attribution origin/build/W-108-attribution`;
push to that same branch. Work item: work/W-108.md (update its proof/next_action text for the pending state in the same
branch; class 1 correction, not a status change).
Budget: 90 min wall-clock, 80 tool calls
Report: evidence-table

## Read first
#405 (`gh issue view 405`), docs/process/gc-2f-briefs/review-W-108-r2.md and review-W-108.md, ADR-110, ADR-109, the
module backend/ofo_app/reconcile_attribution.py and its tests, backend/ofo_app/kite_replies.py:254-284
(`BrokerOrderRow`, `orders_from_reply`), backend/ofo_app/execution_plan_store.py:80-135 (`PlanOrder`, `StoredPlan`,
status open/closed), backend/ofo_app/execute_plan.py:188-199 (`held_units`: an unclosed order counts 0).

## What to build (the redesign; your design inside these results)
1. New input: Zerodha's order book as parsed by `kite_replies.orders_from_reply` (a sequence of `BrokerOrderRow`),
   passed beside `broker_net`. This module still imports no Kite module (REQ-063 AC-1 provider scan).
2. For each OPEN stored plan: find each of its orders in the order book by the app's tag (`PlanOrder.tag`).
   Final = an allow-list of Zerodha status words: COMPLETE, CANCELLED, REJECTED. Every other word (OPEN, TRIGGER
   PENDING, AMO REQ RECEIVED, MODIFY..., unknown text) is not final. The answer states (B4 (d)), each with a test and
   a stated result:
   - every order final -> use each row's `filled_quantity` as that order's fill in memory (never stored here) and
     compare as normal (ADR-109 (2)), even though Check was never pressed;
   - any order not final -> PENDING;
   - any order absent from the order book (never placed, or placed on an earlier day: Kite's order book is today's
     only) -> PENDING;
   - two rows with one tag -> PENDING with its own reason (never summed silently);
   - a row whose tag is the plan's but whose side, tradingsymbol or quantity differs from the stored order -> fail
     closed (`AttributionError`).
3. PENDING, per ADR-110: every contract the open plan's orders touch is reported pending, with the strategy id, the
   plan number and the reason; on a pending contract NOTHING is split as outside and nothing agrees; the strategy is
   blocked. Other strategies holding the same contract are blocked too (their lots cannot be told apart while one plan
   is unknown; Q224 already blocks two holders), and outside lots on it are not reported. Contracts no open plan
   touches are attributed as today. Expose pending in `Attribution` (a mapping contract -> who/why) and one
   `blocked` set = compare's blocked strategies plus every pending one; never mutate compare's report and do not edit
   compare.py.
4. MINOR 1: refuse a `StoreReader` whose calls are not the default store functions unless `APP_ENV` is exactly
   `test` (reuse the settings helper in backend/ofo_app/config.py; do not read os.environ ad hoc if a helper exists).
5. MINOR 2: the outside count never exceeds Zerodha's holding on that side (|outside| <= |raw net|, same sign).
   Case: own +65, standalone -100, Zerodha +65 must not report 100 outside; report the recorded standalone that
   Zerodha does not show (a `standalone_unseen` entry or equivalent) and let compare decide the block - work the
   expected values out by hand in the test docstring.
6. Flip the pinned test `test_ac7_unfilled_plan_holds_nothing` (tests_app/test_reconcile_attribution.py:259-266): an
   open plan with no fill and no order-book row is PENDING (blocked), not 65 outside.

## Attack cases the reviewer will run
1. Plan open + order COMPLETE at Zerodha (real orders-122104) + Zerodha net 0 (short) -> blocked by compare
   (mismatch), not pending forever.
2. Plan open + order OPEN -> pending, blocked, 0 outside, even with Zerodha net 130.
3. Plan open, user never returned, order absent, Zerodha 0 -> pending, blocked.
4. Plan open with two orders, one COMPLETE and one OPEN -> pending.
5. Plan open + order CANCELLED filled 0, Zerodha 65 -> not pending; 65 outside; strategy holds 0 there.
6. Two strategies on one contract, strategy 2's plan open -> both blocked; strategy 1's other contracts unaffected.
7. Unknown status text (`PUT ORDER REQ RECEIVED`, lowercase `complete`) -> not final.
8. Mutation: delete each new guard (final allow-list, absent-row branch, duplicate-tag branch, mismatched-row check,
   pending blocks the strategy, no outside split on a pending contract, the outside cap, the StoreReader check) -> name
   the test that goes red for each. Report the list.

## B4 standing items
(a) no time-budgeted job is touched; (b) no new CI import; (c) the order-book read is a plain function on parsed rows,
not a detector, and the final-state rule is an allow-list (finding guard-as-forbidden-list); (d) the stored-data
states, each tested: plan open / closed / exited; fills stored or not; order row present final / present not final /
absent / duplicated / mismatched; other strategies on the contract; a standalone recorded on the contract.

Rules: no new duplicated literal (if the status words already have a home, reuse it; else one constant here); reuse
the existing helper; ruff/mypy baselines must not rise; targeted tests only; no regenerated files in the PR. Money
stays Decimal; quantities int. Do NOT edit compare.py, execute_plan.py's existing functions, routes/, or
kite_replies.py. Do not open a PR (it exists). Windows local pytest: add `-p no:metadata` (#403).
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Plus your file: python -m pytest -q -p no:cacheprovider -p no:metadata -c pytest-app.ini tests_app/test_reconcile_attribution.py
(pure, no database; if it needs one, run it through scripts/orchestrator/db_run.py, that file only - the VPS
PostgreSQL also serves IPODhan production). Also run tests/marketdata/test_provider_replaceable.py.
