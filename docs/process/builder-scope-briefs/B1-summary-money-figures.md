# W-1xx builder brief (lane B1): Builder summary money figures and the margin read

Common brief: docs/process/builder-brief.md
Core: the outcome reply carries, from the one engine, net premium (Get / Pay), itemised charges, intrinsic and time value, Reward/Risk, max profit and loss as a percentage of the user's available funds, and a margin figure that does or does not count the user's open Zerodha positions.
Proof: step 1 is an engine-level test on the recorded 1-lot NIFTY iron condor of 2026-10-15 (legs and entries in evidence/W-075): net premium credit 67.15 x 65 = Rs 4,364.75, round-trip charges Rs 214.96, max profit Rs 4,149.79, max loss Rs 8,850.21, Reward/Risk 0.47 and Risk/Reward 2.13; and the REQ-081 AC-3 case (bought 22,900 CE at 150.00, spot 22,976.85, 1 lot of 65: intrinsic Rs 4,995.25, time value Rs 4,754.75). Expected values come from the requirement text, not from running the code.
Tier: A (money figures, Zerodha funds and margin reads).

## Work item
The orchestrator allocates the W-id, writes `work/W-1xx.md` (requirement_ids REQ-081; REQ-055 read part) and its coverage-stages row; commit them unchanged. The funds percentage and the margin choice need the per-user setting store from lane A3 only for the AC-5 choice (build everything else first).

## Spec basis (quoted)
REQ-081 AC-1: "The summary shows the net premium at the planned entries"
REQ-081 AC-2: "A Charges action shows the engine's round-trip estimate itemised as ADR-082 lists it - brokerage, STT, exchange transaction charges, SEBI charges, stamp duty, GST - with the total, the date of the rates used"
REQ-081 AC-3: "The summary shows the strategy's intrinsic value (each option leg's value if it expired at the current spot) and time value (current premium minus intrinsic)"
REQ-081 AC-4: "The summary shows Reward/Risk = max profit / max loss, both including charges (ADR-082), to two decimals, with a switch to Risk/Reward."
REQ-081 AC-5: "With a Zerodha session and at least one open position, the margin line (ADR-099) offers"
REQ-081 AC-5: "The choice is a per-user setting, on by default as in Sensibull."
REQ-081 AC-6: "the planning figure is information only (ADR-099)"
REQ-081 AC-7: "Every figure in this requirement comes from the server as a money string (ADR-008); the browser formats nothing but layout."
REQ-081 AC-8: "no figure is a partial sum of the legs that do have prices"
REQ-081 AC-9: "Beside the engine's max profit and max loss the summary shows each as a percentage of the user's available funds read from Zerodha (ADR-164)"
REQ-081 AC-10: "both percentages are absent, never estimated or taken from an older read as current, and the rupee figures stay"
REQ-081 AC-11: "Wording beside the percentage follows ADR-003"
REQ-055 AC-3: "The platform's own margin figure is shown as a planning estimate; Zerodha's figure is authoritative."
REQ-055 AC-4: "show available vs required"
Scope change from ADR-165: no basket is built, so REQ-055 AC-1, AC-2 and the basket block of AC-4 are out; only the read parts above are built. REQ-081 AC-6's block-before-basket clause is moot while Execute is off.

## Copy from
Copy from: spec/technical-design/legacy-reuse.md frontend section, row `src/components/strategy/PayoffChart.vue`, `PnLCell.vue`, `SummaryCards.vue`, `StrategyHeader/Footer/Actions.vue` (COPY, P4: verify props are backend values); the in-repo `SummaryCards.vue` is that copy (its header comment records that the Risk/Reward card was dropped for want of an API value: this brief adds the value). Backend margin: the in-repo `ofo_app/kite_margin.py` and `ofo_app/outcome_margin.py` (W-081 / ADR-099); services row `services/brokers/base.py` margin preview (ADAPT) is already taken. Net premium, charges list, intrinsic / time value, funds percentage: Copy from: none - engine work, formulas are in the REQ text and `scenario-calculations.md`.

## Sensibull screens (study folder D:\Abhay\Ventures\competitors\sensibull\2026-10-21\; never copy a screenshot or account data into the repo)
- 010-039 summary strip (catalogue-raw.md): 'Price Pay 81.3 Premium Pay 5,285', Max Profit +7,716 (+22%), Max Loss -5,285 (-15%), Breakeven, Reward/Risk 1.5 with a 1/x flip to 0.68, Time Value, Intrinsic Value, Funds Needed / Margin Needed / Margin Available with a gear for 'include existing positions'.
- 022 Charges: total 62.20 = Brokerage + STT + Exchange txn + GST + Stamp + SEBI.
- 124-129 tooltips (verbatim in bundle-findings.md section 2): Reward/Risk, Intrinsic ('value of options and NOT P&L'), Time Value, Funds Needed; 240-243: Time Value, Margin Needed and Manual P&L tooltips; 243 shows labels turning to Standalone Funds / Standalone Margin when the toggles are off.
- Differences kept on purpose: Sensibull's percentage is of funds NEEDED; ours is of available funds read from Zerodha (ADR-164), absent when unreadable. Sensibull does not warn on a margin shortfall in the builder; the planning line here is information only. Manual P&L (screen 242) is not in scope.

## What to build
1. Engine: `ofo/engine/strategy.py` already has `net_premium(strategy, price)` (`:69`); add intrinsic and time value (`ofo/engine/metrics.py` or a new `ofo/engine/values.py`), Reward/Risk (Decimal, 2 places, dash when a side is Unlimited, max loss is 0 or the strategy has mixed expiries: `MultiExpiryError`), and the percent-of-funds division (Decimal, one rounding place, absent when funds are not readable or a side is Unlimited). Charges list: extend `ofo/charges/round_trip.py` / `calculator.py` so the itemised parts and the rates date come back with the total; sum of parts equals the total to the paisa (consistency test).
2. Outcome: extend `Summary` and `Margin` in `ofo/outcome/service.py`, `serialize.py`, and the response models in `ofo_app/routes/outcome.py`; a leg without a planned entry or price makes each figure that needs it a dash with its reason (no partial sums).
3. Margin choice: `ofo_app/kite_margin.py` has `BASKET_PATH = /margins/basket?consider_positions=true` (`:35`), so TODAY the figure always counts open positions. Add the second mode (strategy alone) as a parameter of the same call; labels 'Margin needed (with your open positions)' and 'Margin needed (this strategy alone)' come from the wording catalogue; refetch only when leg, side, lots, multiplier or planned price change, never on a tick (reuse the single-flight rate handling from #448 if merged).
4. Funds: `KiteMargin.fetch_available_funds` exists (`checked_basket.py:46` uses it); read funds once per outcome build, stamp the read time, and send both with the percentages.
5. Frontend: `SummaryCards.vue` / `StrategyFooter.vue` show the new figures and the Reward/Risk switch; `components/strategy/ChargesPopup.vue` (new); `MarginLine.vue` gains the 'Count my open positions' toggle, stored through the per-user setting store (lane A3). No arithmetic in the browser (grep test: no `parseFloat`, `Number(`, `toFixed` on these values).
6. Regenerate `docs/api/openapi.json`; register new ApiModel classes in `tests_app/test_response_door.py`.

## AC status (main + evidence/)
| AC | Status |
|---|---|
| REQ-081 AC-1 net premium | partial (TOTAL row net premium cell `ofo/table/model.py:196`; `engine/strategy.py:69`; no Get / Pay line in the summary) |
| REQ-081 AC-2 charges list | partial (`charges/round_trip.py` returns the total only; evidence/W-075 AC-7 covers the total in max loss / profit) |
| REQ-081 AC-3 intrinsic / time value | missing (run one grep for intrinsic and time value in `ofo/engine/` before coding) |
| REQ-081 AC-4 Reward/Risk | missing (SummaryCards header: dropped, API sends none) |
| REQ-081 AC-5 count open positions | partial (call always sends consider_positions=true; no second mode, no toggle) |
| REQ-081 AC-6 | reduced by ADR-165 |
| REQ-081 AC-7, AC-8 | partial (dash handling exists per cell; no partial-sum rule for the new figures) |
| REQ-081 AC-9..AC-11 funds percentages | missing (funds read exists, no percentage) |
| REQ-055 AC-3 planning estimate label | partial (`MarginLine.vue` shows Zerodha figures; planning-estimate wording to check) |
| REQ-055 AC-4 available vs required | exists (`MarginLine.vue`: needed and available shown, shortfall flagged) |
| REQ-055 AC-1, AC-2 | out of scope (ADR-165) |

## Attack cases
Futures leg in the strategy (net premium dash with the reason); one leg unpriced (every figure needing it dashes); max loss 0; Unlimited max loss or profit (no ratio, no percent); mixed expiries (ratio dash, ADR-143); funds read failed or Kite session expired (percentages absent, rupee figures stay, text says why); funds read 10 minutes old on a stale feed (shows its read time, not 'now'); account with no open positions (toggle hidden, number identical both ways); account with positions where the with-positions margin is LOWER than alone; charges parts that do not sum (test fails); percent rounding at x.x5; SENSEX segment charges (BSE F&O rates); the same call fired on every tick (must be once per edit).

## Findings checked
Findings checked: money-value-computed-outside-engine, money-parsed-through-float, margin-gate-blocks-closing-basket, fallback-time-claims-missing-data, freshness-judged-on-request-start-clock, rate-gate-on-success-path-only, trust-broker-status-word, broker-reply-shape-unproven-at-domain-boundary, test-asserts-implementation-output, outcome-multi-expiry-unhandled-500

Standing items: (a) n/a: no time-budgeted job; the margin refetch is edit-driven, not timed; (b) n/a: no CI step gains an import; (c) n/a: no static detector added beyond the grep-style no-arithmetic test, which names the formatter by import source; (d) applied: Zerodha answer states are stated, no open positions, session absent, session expired, read failed, empty reply, ambiguous reply (funds missing a segment); each has a stated display and a test with a closing / entry shape from a real reply.
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Targeted tests: tests/engine/ (the metrics and values tests you add), tests/charges/, tests/outcome/, tests_app/test_outcome_margin.py, tests_app/test_outcome_route.py, tests_app/test_response_door.py; frontend: `npx vitest run tests/summary-cards.test.js tests/margin-line.test.js`, `npm run lint`, `npm run build`. Grep tests/, tests_app/, frontend/tests/ and frontend/e2e/ for every old summary string.
Rules: no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no regenerated files in the PR (the one exception is docs/api/openapi.json when an API model changes)
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table

## Open
Open: technical: REQ-081 AC-5 says the position-aware figure is 'on by default as in Sensibull', and the current code already counts positions always. Proposal: keep default on; add only the off mode.
Open: business: none found; the percent-of-funds base (available funds, not funds needed) is already decided by ADR-164 and the AC text.
Open: technical: no real case yet for AC-5 (the owner's account had no open positions on 2026-10-21, per the AC). Proposal: test with a recorded replay reply that carries a position; the live check stays in the final live window.

## Legacy map rows (copy_from_check.py)
Rows of spec/technical-design/legacy-reuse.md that name this brief's requirements. Act on each:
COPY/ADAPT -> use it (provenance header) or write in the report why not; REFERENCE -> read before
designing; SKIP -> do not re-survey.

| `app/api/routes/orders.py` (681) | REFERENCE | margins, import-positions, quote mapping; optional strategy_id (`:147-165`) and float (`:139,518,585-590`) | REQ-055, REQ-061 |
