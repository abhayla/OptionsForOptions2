# W-1xx: Tracking complete - strategy states, tracked P&L rest, typed fills, manual P&L (REQ-039, REQ-109 AC-3..AC-8, REQ-077 typed fills, REQ-089)

Common brief: docs/process/builder-brief.md (read it first; this file is the item part only).

Core: a strategy moves Draft -> Active (tracked) -> Completed through recorded transitions, and a typed fill price changes the tracked P&L exactly as the engine computes it.
Proof: on the recorded replay: save a NIFTY iron condor, Start tracking (W-122), type the actual fill price of one leg, and read the engine's tracked P&L equal to a hand calculation (Decimal, to the paisa), with the state history showing every transition with time. Live window: the same on live prices.

Tier: A (money numbers: tracked P&L, manual P&L in payoff, typed prices; migration lives in its own PR first)

Spec basis:
REQ-039 AC-2: "Every state change is an explicit recorded transition; state is never inferred only from order rows."
REQ-039 AC-3: "Every important non-normal state shows what happened, when, what is blocked and the next action"
REQ-109 AC-3: "A paper-tracked strategy can never be executed as paper"
REQ-109 AC-4: "records each leg's exit price at that moment on the same basis and freezes the paper P&L"
REQ-109 AC-5: "a paper exit at that moment is refused with"
REQ-109 AC-6: "uses delayed prices only when REQ-105's mode is on"
REQ-109 AC-7: "A paper leg whose contract expires is closed at the settlement price as on a real leg (ADR-083)"
REQ-109 AC-8: "Monitoring rules and alerts may run on a paper strategy"
REQ-077 AC-1: "Each leg's planned entry can be typed by the user."
REQ-077 AC-2: "A typed price must be a positive multiple of the contract's tick size read from the instrument file"
REQ-089 AC-1: "On a strategy the user can add one manual P&L amount in rupees, positive or negative"
REQ-089 AC-3: "the manual amount is counted in the strategy's payoff, max profit, max loss and breakevens"
REQ-089 AC-5: "A manual amount never reaches Zerodha, reconciliation (ADR-018), the margin check or any order"
ADR-165 (2): "the user may type the price actually obtained when the trade was placed by hand on Kite (REQ-077)"

Copy from: none - builds on W-122 (branch build/W-122-track-detect: backend/ofo/tracking/paper.py, backend/ofo_app/tracking_store.py, routes/tracking.py, migration 0019_strategy_tracking.py) and the settlement code backend/ofo/reconciliation/settlement.py:settle_expired_legs; reuse them.

Sensibull screens: Draft Portfolios / paper trading 090-092 (Net Positions | Orderbook, Add Orders Manually, per-leg Lots Avg LTP Booked Unbooked P&L, Convert to Real Trade is NOT built) and 115-119, 218-224 in catalogue-raw.md; Manual P/L row (pencil edit, reset arrow) 010 and 025 'Show Manual P&L'; BUILDER PASS 2 manual P&L text (stored per strategy, affects payoff, breakeven, max profit, max loss, POP).

Multi-broker review (read D:\Abhay\Ventures\competitors\multi-broker-architecture\2026-10-21\INDEX.md first): trap T5 (a global paper/live switch diverts every running strategy): tracking is per strategy and a paper record can never reach an order path; T3 (lots vs units): quantities in units.

## What to build
Prerequisite: W-122 merged (the action label is Start tracking per ADR-166 on branch docs/builder-scope-run1, not yet on main, so it is not quoted here; figures keep the not-real label of REQ-109 AC-2) (AC-1/AC-2 of REQ-109 and Q253 condition 1 are THERE; do not rebuild). Land the migration for this brief (state transitions table, manual P&L table, typed fill column) as its own small PR first; this brief is the code PR that stacks on it.
1. State machine REQ-039: backend/ofo/strategy/versions.py has ACTIVE/adopt_held; add backend/ofo/strategy/state_machine.py with the twelve states of AC-1 as a closed enum, an allow-list of legal transitions, every transition stored with time, from, to, reason (AC-2). The tracking states used in this scope: Draft, Active (tracking), Monitoring Paused, Reconciliation Required, Completed, Exited, Archived; Execution in Progress and Partially Executed exist in the enum but nothing in this scope can enter them (no order path). Non-normal states carry what/when/blocked/next action (AC-3) from the reviewed catalogue (backend/ofo/errors/).
2. REQ-109 remainder: paper exit by leg that freezes P&L (AC-4); refused with the stale-price message when a price is not live (AC-5); delayed-price labelling only when REQ-105 mode is on (AC-6; REQ-105 is held and off, so build the label path behind that switch); expiry closes at the settlement price labelled 'Paper - settled at expiry' (AC-7, use settle_expired_legs); alerts on a paper strategy say 'Paper strategy' first (AC-8, text consumed by D5). AC-3: no paper record can reach Execute, the basket builder or a trigger builder; Execute is already off, add the test that any order-door import from tracking code fails the repo scan.
3. REQ-077 typed fills: on a tracked strategy the user types the price actually obtained; label 'Your price' with time; validated as a positive multiple of the tick size from the instrument file with at most two decimals (reuse lane A's validator if merged: Open); stored with the entry; the engine recomputes tracked P&L with it (AC-1, AC-2 as it applies to tracking entries). The builder-side typed prices and Reset Prices (AC-3..AC-9) belong to lane A.
4. REQ-089 manual P&L: add/edit/remove one amount, 2 decimals, optional note, shown on its own line 'Added by you - not from Zerodha', counted in payoff, max profit, max loss, breakevens through the ONE engine with the note 'includes +Rs 300.00 added by you' and a 'Leave out my manual P&L' switch; each change is a timeline entry and an audit-log entry with old and new values (AC-4); the fills figure is identical with and without it, tested (AC-5).
5. Routes in backend/ofo_app/routes/tracking.py (W-122) and strategies.py; new ApiModels: regenerate docs/api/openapi.json and register in tests_app/test_response_door.py.

## AC status (main plus open PRs, 2026-10-21)
| AC | Status | Where |
|---|---|---|
| 039 AC-1 | partial | strategy states in backend/ofo/strategy/versions.py (versions only), no twelve-state enum |
| 039 AC-2 | missing | |
| 039 AC-3 | partial | error templates exist, none for tracking states |
| 109 AC-1,2 | in progress | W-122, branch build/W-122-track-detect |
| 109 AC-3 | partial | refused-by-construction in W-122; scan test missing |
| 109 AC-4..AC-8 | missing | |
| 077 typed fill (AC-1,2,4) | missing | tracking store has entry price only |
| 077 AC-3,5..9 | lane A | builder |
| 089 AC-1..5 | missing | no REQ-089 reference anywhere in backend |

## Every answer state of each outside system
Prices (live feed): fresh (stated) = capture. Stale/missing (failed) = 'Prices are not live; try again when they update', nothing stored. Empty strategy (empty) = refuse Start tracking. Typed price not a tick multiple (ambiguous) = refuse with the four-part message. Strategy already tracked (duplicate) = refuse, never a second entry. Expiry day: settlement price not yet published (absent) = leg stays open, labelled 'awaiting settlement'. Database: transition write fails = the state does not change (one transaction); a state read of an unknown value (ambiguous) = fail closed to Monitoring Paused. Manual P&L: zero, text, three decimals, huge value = refused (AC-1).

## Attack cases (reviewer: hands-on first)
- Illegal transition Completed -> Active: refused; the allow-list test enumerates every pair, generated, not hand-listed.
- Two Start tracking requests at once: one entry.
- Manual P&L added then the fills figure compared with and without: identical to the paisa.
- Manual amount 1e15 or '12.345': refused.
- Typed price 81.32 on tick 0.05: refused; 0, negative, 'abc': refused.
- A paper entry posted to any order route: refused and the repo scan stays green only because tracking code imports no order door.
- Leg expires while tracked: closed at the settlement price, not at the last LTP.
- Float anywhere in the money path: findings money-parsed-through-float.

Threat model: in scope: illegal transitions, double entries, manual P&L leaking into reconciliation or fills, floats; out of scope: a user editing another user's strategy (single owner scope, per-user separation is the launch scope: new code takes the user from the session).

Findings checked: money-value-computed-outside-engine, money-parsed-through-float, fill-not-exactly-once, state-with-no-working-exit, state-read-after-await, store-filled-only-by-tests, identifier-unique-only-by-convention, held-without-platform-fill-invisible-to-ledger, guard-without-killing-test

Standing items: (a) n/a: no time-budgeted job (the monitor job is D1). (b) n/a: no CI step added. (c) applies to the 'tracking code imports no order door' scan: names the door by import source, fails closed on re-exports and renames. (d) applies: prices and settlement states above.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Targeted tests: tests/tracking/, tests/strategy/, tests/reconciliation/test_settlement*.py, tests_app/test_strategy_tracking.py (W-122), tests_app/test_response_door.py, tests/engine/ if a payoff function is touched
Rules: no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no regenerated files in the PR (the one exception: a changed API model regenerates docs/api/openapi.json and is registered in tests_app/test_response_door.py, per builder-brief.md).
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table

## Open
Open: technical: REQ-077's tick-size validator is built in lane A; proposal: import it from lane A's module if merged, else write it once in backend/ofo/strategy/entry_price.py and let lane A reuse it (one home, no copies). Coordinate in the integrator's merge order: this brief after lane A's leg-row PR.
Open: technical: migration numbering. 0018 on main, 0019 W-122, #419 and #451 carry 0018/0020 per their titles; the builder reads `ls backend/ofo_app/alembic/versions` at start and takes the next free number.
Open: business: REQ-089 AC-3 counts the manual amount in the payoff 'as in Sensibull'; AC-2 says never summed into one unlabelled figure. Both are already written in REQ-089 and agree; no question. Live window needed: tracked P&L on live prices.
