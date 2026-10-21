# W-1xx builder brief (lane B2): Payoff chart with both curves, what-if controls, expected-move bands, OI bars, Greeks panel

Common brief: docs/process/builder-brief.md
Core: ONE engine reply for one strategy state returns the At Expiry curve, the Estimated curve for the target date, the P&L and breakevens at the target level, the Greeks there, the one and two standard-deviation levels and the OI per strike; the chart only draws it.
Proof: step 1 is an engine test with expected values computed independently in the test (a separate Black-Scholes helper written in the test file, not the engine's): NIFTY 22,800 / 23,000 bull call spread, target level 23,000, target date two days before expiry, IV +2 points (ADR-151 example) gives the P&L at that point and the breakeven at that date; and the REQ-027 expected-move case: NIFTY 23,047, ATM IV 12%, 7 days gives +/-383 and +/-766 points. Real frames: replay mode, `OUTCOME_REPLAY=1`.
Tier: A (engine P&L, Estimated curve, Greeks, breakevens; reads live OI). Size L: if over 1,000 product lines, push part 1 (engine + route: REQ-083 AC-1..AC-4, REQ-084 AC-4..AC-6, REQ-034 AC-6) and part 2 (UI + OI overlay + Greeks panel) as stacked PRs.

## Work item
The orchestrator allocates the W-id, writes `work/W-1xx.md` (requirement_ids REQ-083, REQ-084, REQ-034; REQ-034 AC-6 is built here, see Open) and its coverage-stages row; commit them unchanged. W-090 (todo, REQ-034 scenario range controls) overlaps `ScenarioControls.vue`: read it first and do not duplicate it.

## Spec basis (quoted)
REQ-083 AC-1: "The payoff chart draws the At Expiry curve and the Estimated curve on the same axes"
REQ-083 AC-1: "Both curves come from one engine reply for the same strategy state, never from two calls that could be for different edits"
REQ-083 AC-2: "The browser never interpolates or computes a money value between computed points (ADR-008)."
REQ-083 AC-3: "the chart draws the expiry curve only, with the reason under the legend"
REQ-083 AC-4: "computed on the server by the REQ-027 formula (spot x ATM IV x square root of calendar days / 365)"
REQ-083 AC-5: "It uses today's live OI only, no history (ADR-066)."
REQ-083 AC-5: "The overlay is on by default at Standard and Advanced and off at Guided."
REQ-083 AC-6: "it never draws zero-height bars as if OI were zero"
REQ-083 AC-7: "the browser never extends a curve beyond the points it was sent"
REQ-084 AC-1: "the server sends its limits and step (the strike gap)"
REQ-084 AC-2: "sets a date and time between now and the strategy's first expiry at 15:30 IST"
REQ-084 AC-3: "An IV-change control sets one offset in volatility points (steps of 0.1, for example +2.0) applied to every leg's own IV"
REQ-084 AC-3: "A resulting IV at or below 0 is refused with the reason."
REQ-084 AC-4: "The browser sends only the inputs"
REQ-084 AC-5: "At Expiry figures stay exact and unlabelled as estimates"
REQ-084 AC-6: "What-if inputs are analysis only: they are not saved with the strategy"
REQ-084 AC-7: "the target-level control still gives At Expiry P&L at that level"
REQ-084 AC-8: "a toggle between per unit and per position (times the lot size from the instrument file and the lots)"
REQ-084 AC-9: "The browser does not multiply Greeks into rupees."
REQ-034 AC-6: "The browser only sends the inputs; every what-if number comes from the one server engine (ADR-008)."
REQ-034 AC-8: "The payoff graph and the scenario table come from the same engine."

## Copy from
Copy from: spec/technical-design/legacy-reuse.md frontend section, row `src/components/strategy/PayoffChart.vue` (COPY, P4: verify props are backend values; the in-repo copy draws one view as Profit / Loss series with chart.js: extend it); services section rows `services/options/{expected_move,gamma_risk,iv_metrics,oi_analysis,theta_curve}_service.py` (REFERENCE: algorithms for REQ-026 / REQ-047, not code) and `services/options/vectorized_greeks.py` (REFERENCE: numeric cross-check only, row 6/91). Rows for `payoff_calculator.py` / `pnl_calculator.py` are SKIP (float calculators outside the one engine): never copy. Greeks panel, what-if, OI overlay: Copy from: none.

## Sensibull screens (study folder D:\Abhay\Ventures\competitors\sensibull\2026-10-21\; never copy a screenshot or account data into the repo)
- 012-021 Payoff Graph tab: green / red expiry line + blue target-date curve, OI bars (call red, put green) on the same x axis, SD bands -2SD -1SD 1SD 2SD on the top axis, current-price marker, Zoom Out / In; hover tooltip 'When price is at 23,480 +2.2% | Expected P&L on Wed, 21 Oct -4,696 | Expiry date -9,401' (screens 122-123 for hover); 124-129: tooltips.
- 020 What-if: 'NIFTY Target' slider + number box, 'Date: 4D to expiry' slider with < > steps, each with Reset; 212-217: Payoff Table (Target Interval 10 / 25 / 50 / 100, Show %), P&L Table, Greeks tab ('Multiply by Lot Size': delta 0.52 -> 34); 246: SD Fixed vs Dynamic; lower panel Strikewise IVs with -/+ and Offset, Reset IVs; Standard Deviation table (1SD 448.8 pts).
- OI overlay: screen with 'Change in OI' switch (BUILDER PASS 2), tooltip 'OI overlay is not available for MCX, USDINR and far expiries'.
- Differences kept on purpose: Sensibull prices with Black-76; this engine uses the pricing model of ADR-063 (Black-Scholes, parity forward, implied yield) and includes round-trip charges (ADR-082); the Estimated numbers are always labelled as model estimates (ADR-151); OI is today's only, no history (ADR-066).

## What to build
1. Engine inputs: extend the model inputs (`ofo/engine/inputs.py`, `model.py`) and `ofo/engine/estimate.py` (`estimate_now`, `estimate_now_grid`) with `target_date` and `iv_offset` (and per-leg IV edits at Advanced); the valuation time becomes the target date, clamped to now..first expiry 15:30 IST with a flag the screen can show; IV result at or below 0 is refused with the catalogue reason.
2. Reply: `ofo/outcome/service.py` / `serialize.py` / `ofo_app/routes/outcome.py` return both curves in one reply (`payoff_points` today holds one view: add `estimated_points` for the same levels), P&L and breakevens at the target, Greeks at the target, per-unit and per-position Greeks with the engine's rupee examples, the 1 SD / 2 SD levels (reuse `ExpectedMove` in `ofo/scenario/levels.py:59`), and the OI per strike for the strategy's expiry with the time read (from the chain read in `ofo_app/chain_push.py`, never zero-filled).
3. Zoom: the engine returns points for a requested range (existing `range_start` / `range_end` on `OutcomeRequest`); the browser never extends a curve.
4. Frontend: `PayoffChart.vue` draws both curves, hover shows both server values at the nearest computed level, SD lines, OI bars with an OI / OI change switch and the 'OI not available for this expiry' state; `components/strategy/WhatIfControls.vue` (target level, target date, IV offset, Reset each, estimate label); `components/strategy/GreeksPanel.vue` (Advanced: per leg and total, per unit / per position, rupee examples as sentences from the server). What-if inputs live in component state only (not saved with the strategy, not in the stored definition).
5. Regenerate `docs/api/openapi.json`; register new ApiModel classes in `tests_app/test_response_door.py`; grep tests, `tests_app/`, `frontend/tests/`, `frontend/e2e/` for the old `payoff` reply shape and update every hit.

## AC status (main + evidence/)
| AC | Status |
|---|---|
| REQ-034 AC-1..AC-5, AC-7, AC-8 | exists, verified (evidence/W-003 AC-2..AC-6, AC-8; W-063 AC-1, AC-8; W-066 AC-7); AC-6 first half (At Expiry / Estimated Now columns) verified, what-if half missing |
| REQ-083 AC-1 | partial (`PayoffOut` has one view per call, `routes/outcome.py`; `estimate_now_grid` exists) |
| REQ-083 AC-2 hover | missing |
| REQ-083 AC-3 | partial (estimate unavailable state exists in `ScenarioOut`) |
| REQ-083 AC-4 SD bands | partial (ExpectedMove formula in `scenario/levels.py` serves the default range; no bands in the reply) |
| REQ-083 AC-5, AC-6 OI overlay | missing (OI exists per chain cell, not joined to the outcome) |
| REQ-083 AC-7 zoom | partial (range override exists) |
| REQ-084 AC-1..AC-3 controls | missing |
| REQ-084 AC-4 engine reply at target | missing |
| REQ-084 AC-5..AC-7 | missing |
| REQ-084 AC-8, AC-9 Greeks panel + rupee examples | partial (TOTAL row Greeks in `ofo/table/model.py`; no panel, no toggle, no examples) |

## Attack cases
Target date after expiry (clamped, screen says so); target date earlier than now; IV offset making one leg's IV zero; leg with no IV (expiry curve only, reason under legend); mixed expiries (ADR-143 worst-case line, no estimate); OI missing for the expiry (message, no zero bars); OI stale (older than its interval during market hours: marked); spot stale (target-level control still gives At Expiry); hover between two computed points (nearest computed level, no interpolation; test fails if the browser multiplies or averages); 1 SD with ATM IV missing (bands absent, reason); Greeks of a futures leg (delta 1, others 0, `_FUTURES_PER_UNIT_GREEKS`); what-if values must not appear in a saved definition (round-trip test); two quick edits (older reply never draws).

## Findings checked
Findings checked: money-value-computed-outside-engine, loss-region-inferred-from-breakevens, outcome-multi-expiry-unhandled-500, fallback-time-claims-missing-data, last-live-answer-kept-after-drop, freshness-judged-on-request-start-clock, aggregate-across-mixed-instrument-kinds, test-asserts-implementation-output, money-parsed-through-float

Standing items: (a) n/a: no time-budgeted job; (b) n/a: no CI step gains an import; (c) applied: the no-browser-arithmetic test lists the allowed formatting helpers by import source and fails on any other use of arithmetic on a server value, including re-exports; (d) applied: answer states of the feed and engine (OI present, OI absent, OI stale, IV present, IV absent, spot stale, expiry mixed) are attack cases with a stated display each.
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Targeted tests: tests/engine/ (estimate, inputs, greeks tests you touch), tests/scenario/, tests/outcome/, tests_app/test_outcome_route.py, tests_app/test_response_door.py; frontend: `npx vitest run tests/payoff-chart.test.js tests/whatif.test.js tests/greeks-panel.test.js`, `npm run lint`, `npm run build`.
Rules: no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no regenerated files in the PR (the one exception is docs/api/openapi.json when an API model changes)
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table

## Open
Open: technical: REQ-034 AC-6 (what-if inputs) is listed under lane A but is the same feature as REQ-084 AC-1..AC-4; one implementation here, lane A does not build it.
Open: technical: SD days. REQ-083 AC-4 uses calendar days to the nearest expiry or the target date; Sensibull offers Fixed N days (default 7) and Dynamic (screen 246). Proposal: build the REQ-083 rule only; a Fixed-days mode is not in the spec and is not built.
Open: business: none found; the model-estimate label wording is fixed in ADR-151 / REQ-084 AC-5.
