# W-1xx: Adjustment Opportunity panel, Before/After and what the user did (REQ-046, REQ-112, REQ-045 AC-9)

Common brief: docs/process/builder-brief.md (read it first; this file is the item part only).

Core: picking a generic approach on a detected opportunity shows Before and After legs, P&L, margin, Greeks, breakevens and payoff, each After number equal to what the engine gives for the changed legs.
Proof: on the recorded replay: take the golden iron condor with condition 1 firing, pick 'close leg', and compare the After column (max profit, max loss, breakevens, net delta) with a direct engine run on the legs minus that leg, written as a hand computation in the test; the same call through the real route.

Tier: A (Before/After P&L, margin, Greeks and breakevens are money numbers; one engine only)

Spec basis:
REQ-046 AC-1: "Layer 1 'Why detected': exact market condition, relevant strike/breakeven, current distance, trigger metric, and the rule where applicable."
REQ-046 AC-3: "Layer 3 'Possible approaches': generic approaches with a short explanation; no automatic recommendation."
REQ-046 AC-4: "the user picks an approach; the platform builds the configuration and shows Before/After legs, P&L, risk, margin, Greeks, breakevens and payoff; the user decides."
REQ-046 AC-5: "explains the exact condition, strike/breakeven, distance, metric/rule, timestamp and data state"
REQ-112 AC-4: "Each outcome change is an append-only timeline entry (REQ-040) linking the suggestion id"
REQ-112 AC-3: "are set only from Zerodha's confirmed fills (REQ-057 AC-2), never from the user pressing Execute"
REQ-112 AC-6: "Wording is neutral (ADR-003)"
REQ-045 AC-9: "The Positions area offers adjustment solutions for live strategies, not only a positions table"
ADR-165 (6): "the Opportunity panel with Before/After (REQ-046) and alerts"

Copy from: none - the engine (backend/ofo/engine/, backend/ofo/scenario/) and table (backend/ofo/table/) compute every number; reuse the Builder summary and payoff components from lanes A/B for the After column. Margin: the read-only margin calculation backend/ofo_app/kite_margin.py / outcome_margin.py.

Sensibull screens: Builder summary strip and payoff graph 012-021 and 042-045 (Max Profit, Max Loss, Breakeven, Funds Needed / Margin Needed); what-if sliders 012-021; 'Profit left / Loss left' for existing positions (catalogue-raw.md lines 279-280); Positions menu 'Open in Builder' 050-053. There is no Sensibull Before/After or Opportunity panel in the study.

## What to build
1. Backend: backend/ofo/adjustment/before_after.py: given a strategy's legs and a picked kind from the D3 enum plus the user's parameters (which leg, new strike, quantity), build the changed legs mechanically (no recommendation, no strike chosen by the platform unprompted: AC-5 of REQ-045) and return Before and After through the ONE engine: legs, P&L, max profit/loss, breakevens, net Delta/Gamma/Theta/Vega, margin (Kite margin calculation, read only: failed read = 'Margin unavailable', never a guess), DTE, payoff points. No order is built, no basket.
2. Panel (layers 1 to 4 of REQ-046): Layer 1 why detected (condition, strike/breakeven, distance, metric, rule); Layer 2 current state (P&L, max P/L, breakevens, Greeks, margin utilisation, DTE, relevant IV/OI/LTP); Layer 3 generic approaches (no recommendation); Layer 4 pick -> Before/After, 'the user decides'. 'Why am I seeing this?' with condition, strike, distance, metric/rule, timestamp and data state (AC-5). Route + frontend/src/components/ for the panel, opened from the strategy and from the Positions area (045 AC-9, shown in C8's Positions screen).
3. REQ-112 outcome records: one record per suggestion (id, trigger record, shown-at, kind) with outcomes Dismissed (optional reason from a short list), Acted on, Completed, Partly completed, Lapsed; append-only timeline entries (REQ-040) linking the suggestion id; at most one final outcome; grouped triggers record one outcome each; 'Why did this trigger?' also shows outcome and time (AC-5); neutral wording: 'You dismissed this', never 'You missed this opportunity' (AC-6). PR 1 of 2 is the migration (suggestions, suggestion_outcomes), own PR.
4. 'Completed' and 'Partly completed' only from Zerodha-confirmed position change seen by the reconciliation read of C8 (AC-3), never from a button. 'Acted on' = see Open: business.
5. Paper/tracked strategies: panel and Before/After work on a tracked strategy and on an imported one; label 'Paper strategy' where C7 requires it.
6. Platform-view switch (D3 item 8) hides the generic approaches and suggestions as 'the platform's view' in production until Q211.

## AC status (main plus open PRs, 2026-10-21)
| AC | Status | Where |
|---|---|---|
| 046 AC-1..5 | missing | no REQ-046 reference anywhere in backend or frontend |
| 112 AC-1..6 | missing | |
| 045 AC-9 | missing | Positions screen is C8 |
| engine support | exists | backend/ofo/engine/, scenario/, table/ |

## Every answer state of each outside system
Engine (stated) = numbers as Decimal strings with two decimals on the way out. Leg price missing (absent) = After column 'unavailable', no number from a default. Margin read failed/timeouts (failed) = 'Margin unavailable' for that column only. Picked kind not applicable to the strategy (invalid, e.g. close a leg of a one-leg strategy) = refused with the catalogue message. Strategy changed while the panel is open (ambiguous) = the strategy version in the request must equal the current version, else 'Your plan changed - review it again' (the same text REQ-119 AC-5 uses, built here for the tracking route). Database: outcome write failure = outcome not recorded, UI says so, no silent success.

## Attack cases (reviewer: hands-on first)
- After column computed by a second code path (copy of payoff maths): money-value-computed-outside-engine red.
- A float in the After numbers: red; 4539.65173942700 style strings: red (2-decimal strings).
- Pick 'move strike' to a strike not in the catalogue: refused, snapped list only (finding fixture-symbol-not-in-catalogue / grid values come from the grid).
- Stale quotes: panel shows paused, no Before/After.
- Dismiss twice: one final outcome. Dismiss then Completed: append-only, the final outcome rule enforced.
- Wording scan: 'missed', 'should', 'best' red.

Threat model: in scope: After numbers diverging from the engine, stale data driving an After, double final outcomes, advice wording; out of scope: which approach is correct (owner specifics), order placement.

Findings checked: money-value-computed-outside-engine, money-parsed-through-float, loss-region-inferred-from-breakevens, margin-gate-blocks-closing-basket, advice-wording-denylist-per-module, fixture-symbol-not-in-catalogue, last-live-answer-kept-after-drop, test-asserts-implementation-output

Standing items: (a) n/a: no time-budgeted job (the panel is request-time; detections are D3). (b) n/a: no CI step added. (c) applies to the wording scan: names the catalogue by import source and fails closed on shapes it cannot resolve. (d) applies: engine, margin and database states above.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Targeted tests: tests/adjustment/, tests/engine/ and tests/scenario/ for the files touched, tests_app/test_outcome_margin.py, tests_app/test_kite_margin_client.py, tests_app/test_response_door.py, frontend/tests for the panel
Rules: no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no regenerated files in the PR (the one exception: a changed API model regenerates docs/api/openapi.json and is registered in tests_app/test_response_door.py, per builder-brief.md).
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table

## Open
Open: business: REQ-112 AC-2 defines 'Acted on' as 'the user built the Before/After and prepared a basket from it', but no basket exists in this scope (ADR-165). What does the user press? Recommended: a button 'I will place this on Kite myself' after Before/After; the suggestion is then 'Acted on - not sent by this app', and 'Completed' appears only when the next Zerodha read shows the matching position change. Why only the owner decides: it changes what the user sees and reads. Spec basis: REQ-112 AC-2/AC-3, ADR-165 (1) 'the Place order / Execute action may be replaced'.
Open: technical: Before/After for the twelve kinds is mechanical leg editing; kinds that need a strike choice take it as a user input, never a platform pick. Margin read is the only Kite call. Live window needed: Before/After margin on a real strategy (owner Kite login).

## Legacy map rows (copy_from_check.py)
Rows of spec/technical-design/legacy-reuse.md that name this brief's requirements. Act on each:
COPY/ADAPT -> use it (provenance header) or write in the report why not; REFERENCE -> read before
designing; SKIP -> do not re-survey.

| `app/models/autopilot.py` (1130) order/batch/leg tables | REFERENCE | NOT NULL strategy_id + Numeric are good templates; `execution_mode` auto (`:89,167,628`) breaks ADR-009/017 | REQ-057, REQ-058 |
| `services/autopilot/adjustment_engine.py` (1388) | REFERENCE | auto default (`:246`); Alert + Prepare only | REQ-042, REQ-045 |
| `services/autopilot/{delta_band,delta_rebalance,dte_zone,trailing_stop,premium_tracker,adjustment_cost_tracker}*.py` | REFERENCE | trigger definitions | REQ-045, REQ-047 |
| `app/models/autopilot.py` logs/journal tables | REFERENCE | timeline/audit columns | REQ-040, REQ-064 |
