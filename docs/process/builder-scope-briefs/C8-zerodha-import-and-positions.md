# W-1xx: Import real Zerodha positions into strategies, compare-and-block, Orders and funds views, Positions screen (REQ-104, REQ-061, REQ-060, REQ-103 read, REQ-044)

Common brief: docs/process/builder-brief.md (read it first; this file is the item part only).

Core: the user's real open Zerodha positions are read, grouped into a strategy by the user's choice, and an unexplained difference between Zerodha and the strategy blocks adjustment suggestions.
Proof: read the real Zerodha positions and order book with the owner's Kite login (live window) and group two real legs into one strategy; offline first: parse a recorded real positions reply (tests/fixtures/) through backend/ofo/reconciliation/positions.py position_line_from_kite_row and group it with grouping.py; assert the strategy's held net equals Zerodha's net per contract.

Tier: A (reads feed quantities, prices and the reconciliation block; a migration, if needed, is its own PR)

Spec basis:
REQ-104 AC-1: "reads positions and today's order book fresh, under the per-user lock"
REQ-104 AC-2: "Nothing is pre-selected and nothing is attached by default"
REQ-104 AC-3: "An attached lot keeps Zerodha's average price exactly as reported (ADR-126)"
REQ-104 AC-4: "Imported orders that are still open (not executed) are shown for information only"
REQ-104 AC-6: "Each confirmed attach, create or standalone choice is one audited event on the strategy's timeline (REQ-040)"
REQ-104 AC-7: "the import is disabled with"
REQ-061 AC-1: "On connection the platform fetches open positions and identifies possible multi-leg structures."
REQ-061 AC-4: "The grouping logic is explicit and auditable (every grouping decision recorded)."
REQ-060 AC-2: "It detects: missing platform position, unexpected broker position"
REQ-060 AC-4: "Changes made directly in Zerodha are detected, recorded, and put the strategy into Reconciliation Required"
REQ-060 AC-7: "Positions the user left standalone (REQ-061 AC-2) are recorded with their quantity and are not mismatches."
REQ-103 AC-1: "The Orders page lists every order Zerodha's order book holds for the user today, newest first"
REQ-103 AC-3: "The app offers no cancel, modify, retry or new-order button of its own"
REQ-103 AC-8: "The page reads and shows the order book; it does not store a copy of it (ADR-138 (3))"
REQ-044 AC-3: "The Positions screen shows broker-linked positions, strategy-linked positions, adjustment opportunities and P&L/risk, but actions route back to the owning strategy."
ADR-165 (2): "the user's real open Zerodha positions are imported read-only and grouped into strategies (REQ-104, REQ-061)"

Copy from: none - the domain code exists: backend/ofo/reconciliation/grouping.py (GroupSuggestion :172, AddedToStrategy, AdoptedStrategy), positions.py, compare.py (compare :399, ReconciliationReport :217), resolution.py, blocking.py, triggers.py (plan_run :91), strategy adopt_held (backend/ofo/strategy/versions.py:36). PRs #419 (stored mismatch + sticky block, migration) and #451/#452 (order-book store) land first tonight; treat their branches as existing code. The reads: backend/ofo_app/kite_reads.py fetch_positions/fetch_orders/fetch_trades.

Sensibull screens: Positions /positions 050-053 (Positions | Groups toggle, totals Total/Booked/Unbooked P&L, Closed positions toggle, View Funds drawer: Available margin, Used margin, Available cash, Opening balance, Payin, Payout, SPAN, Exposure; position menu: Open in Builder, Add to Group, Add to Drafts); Orders /orders (tabs All/Open/Executed; row: time, BUY/SELL, product, instrument, LTP, qty filled/total, price, status); Drafts 090-092 'Import Zerodha Trades'. Do NOT copy Stoploss Order or Exit Positions (order path).

Multi-broker review (read D:\Abhay\Ventures\competitors\multi-broker-architecture\2026-10-21\INDEX.md first): L8 (partial fills and net positions), traps T3 (lots vs units), T2 (partial failure reported as success: an import with one unreadable row must report partial, not success), T4 (fixed tag): our tag format is ADR-105; read tags, never write one.

## What to build
1. Import service (REQ-104): backend/ofo_app/position_import.py reads positions and today's order book fresh under the per-user lock; lists only what is not already a strategy's own fills, an adopted lot or a recorded standalone quantity (ADR-109); the user picks per position: create a new strategy, add to an existing strategy (ADR-096), or leave standalone; nothing pre-selected, closing the screen attaches nothing (AC-2). Uses grouping.py suggestions (REQ-061 AC-1, AC-4: every grouping decision recorded with who/when/what).
2. Attached lot keeps Zerodha's average price exactly (AC-3, Decimal from the string, never float; finding money-parsed-through-float), strategy reconciled at once; open (unexecuted) orders shown for information only, never attachable (AC-4). Each confirmed choice = one audited timeline event with Zerodha quantity and read time; nothing else from Zerodha's book is stored (AC-6, ADR-138 (3)).
3. Reconciliation for imported strategies (REQ-060 AC-1..AC-7 read side): run compare() after import, on reconnect, periodically (the periodic trigger is scheduled by D1), and on an order-update event from the bus (C2); a difference makes the strategy Reconciliation Required (state machine from C7), records timestamp, broker state, platform state, difference, next action, and blocks ADJUSTMENT SUGGESTIONS (not just execution) while unresolved (AC-6 as applies); standalone quantities are not mismatches (AC-7). Reuse blocking.py is_execution_blocked; add `is_suggestion_blocked` as a sibling. Manual reconciliation explicit and audited (AC-5, resolution.py exists).
4. Routes: GET import candidates, POST confirm choices (backend/ofo_app/routes/ new file position_import.py); a failed or timed-out read imports nothing; without a live session 'Reconnect Zerodha to import' (AC-7).
5. Orders page and funds view, read-only (REQ-103 AC-1..AC-8): list today's orders newest first with Zerodha's own status words; our-tag orders name their strategy else 'Placed outside this app'; an 'Open on Kite' link only, NO cancel/modify/retry/new-order control and a test that fails if one exists (AC-3); read on open and on refresh, updated from the order-update stream when connected; a failed refresh keeps the last rows with 'status as of <time> - could not refresh'; funds: available cash, used margin, available margin for F&O, Decimal two places, read time; no stored copy (AC-8).
6. Positions screen (REQ-044 AC-3/AC-4, read-only part): frontend/src/pages/LiveStrategiesPage.vue already references REQ-044; add the Positions view with broker-linked and strategy-linked positions, P&L/risk from the engine, actions routing to the owning strategy. REQ-044 AC-1/AC-2 (plan and live tabs) belong to lane A/B screens; do not duplicate.

## AC status (main plus open PRs, 2026-10-21)
| AC | Status | Where |
|---|---|---|
| 061 AC-1..4 | partial | domain: grouping.py, tests/reconciliation/test_position_grouping*.py; no route, no UI |
| 060 AC-1..7 | partial | compare.py:399, triggers.py:91, blocking.py:39, resolution.py; stored mismatch = PR #419; routes only inside the Execute/return flow |
| 104 AC-1..7 | missing | no REQ-104 reference anywhere in backend |
| 103 AC-1..8 | missing | broker_status.py has status only; order-book store = #451/#452 (but AC-8 says do not store a copy: Open) |
| 044 AC-3,4 | partial | LiveStrategiesPage.vue |
| 044 AC-1,2 | lanes A/B | |

## Every answer state of each outside system
Kite positions/orders: rows (stated) = listed. Empty (empty) = 'Nothing to import - every Zerodha position already belongs to a strategy or is standalone'. Failed/timeout = 'Could not read Zerodha', imports nothing, keeps last rows labelled. Session gone (failed) = 'Reconnect Zerodha to import'. Unknown product/status word (ambiguous) = row refused and counted (finding trust-broker-status-word). Net 0 row after intraday close (flat) = hidden (is_flat_row exists). Position in a contract absent from the catalogue (not found) = shown as unresolved, not grouped (grouping.Unresolved). Same contract in two products NRML and MIS (ambiguous) = separate lines. Database: the confirm write is one transaction; failure imports nothing.

## Attack cases (reviewer: hands-on first)
- Quantities: lot size vs units mix (trap T3): a 65-unit NIFTY lot read as 65 lots.
- Same position imported twice (double click, two tabs): second is refused, no double attach.
- Position already part of a strategy: not offered again.
- User closes the dialog with boxes unticked: nothing attached.
- Average price 81.3249 from Kite: kept exactly, not rounded to 81.32.
- Zerodha net differs from strategy by one lot after an outside Kite trade: Reconciliation Required, suggestions blocked, banner with the four parts.
- Page shows a cancel button: repo test fails.
- Token or client id in an error message or log: red.

Threat model: in scope: double attach, silent regrouping, unit/lot mixups, rounding, suggestions firing on a mismatching strategy, secrets in logs; out of scope: another user's positions (one user in this scope).

Findings checked: net-only-read-misses-roundtrip, positions-reply-refused-for-non-platform-rows, resolution-on-stale-broker-copy, trust-broker-status-word, fill-not-exactly-once, held-without-platform-fill-invisible-to-ledger, shared-inflight-marker-without-owner, money-parsed-through-float, state-with-no-working-exit

Standing items: (a) n/a: no time-budgeted job here (the periodic reconcile is scheduled in D1). (b) n/a: no CI step added. (c) applies to the 'no cancel/modify/new-order control' test and the order-door scan: fail closed, name by import source. (d) applies: states above.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Targeted tests: tests/reconciliation/, tests_app/test_reconcile_*.py, tests_app/test_position_import.py (new), frontend/tests for Positions/Orders pages, tests_app/test_response_door.py
Rules: no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no regenerated files in the PR (the one exception: a changed API model regenerates docs/api/openapi.json and is registered in tests_app/test_response_door.py, per builder-brief.md).
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table

## Open
Open: technical: REQ-103 AC-8 says the Orders page does not store a copy of the order book, while PRs #451/#452 build an order-book store for reconciliation (ADR-138 (3) allows only the import choice to store). Proposal: the page reads live and never reads the store; the store stays reconciliation's own evidence; add a test that the page route imports no store module. If #451/#452 contradict ADR-138 (3), classify per spec-adherence and report.
Open: technical: merge order: after #419, #451, #452 and C7 (state machine). Live window needed: every AC (real positions, real order book, real funds; owner Kite login). Do NOT click anything in a live Zerodha order panel (incident 2026-10-21).
Open: business: none.

## Legacy map rows (copy_from_check.py)
Rows of spec/technical-design/legacy-reuse.md that name this brief's requirements. Act on each:
COPY/ADAPT -> use it (provenance header) or write in the report why not; REFERENCE -> read before
designing; SKIP -> do not re-survey.

| `services/brokers/kite_adapter.py` (584) | ADAPT | row 4; Decimal in; floats only at the SDK edge (`:163,168,218,220,326`), private to the transport | REQ-054, REQ-060 |
| `app/models/autopilot.py` logs/journal tables | REFERENCE | timeline/audit columns | REQ-040, REQ-064 |
| `src/views/PositionsView.vue` (1306), `stores/positions.js` (213), `DashboardView.vue` (505), `components/autopilot/monitoring/*` | ADAPT (P5) | strategy-scoped; reword advice (`GammaRiskAlert.vue:22`) | REQ-008, REQ-043, REQ-044 |
