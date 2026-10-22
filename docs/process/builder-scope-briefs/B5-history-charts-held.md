# W-1xx builder brief (lane B5): Strategy price history and market history charts (built OFF in production)

Common brief: docs/process/builder-brief.md
Core: a chart series is computed on the server from the platform's own STORED bars and end-of-day snapshots, with gaps kept as gaps, and the chart appears only when its switch is on.
Proof: step 1 is a server test on REAL stored bars (the platform's own recording, or a backfill of a recent day through `ofo_app/kite_history.py` run once by the orchestrator and saved as a recorded fixture under `tests/fixtures/kite_history/`): for a NIFTY bull call spread BUY 23,000 CE / SELL 23,200 CE the series value at one bar where the legs traded at 81.30 and 30.00 is -51.30 (REQ-091 AC-2 example, expected value from the requirement text), and a bar where one leg has no stored price is a gap.
Tier: B (history series and display; no order path; the switch itself is lane B4's Tier A module). The reviewer checks gaps, the absent-when-off rule and the no-return-wording rule.

## Work item
The orchestrator allocates the W-id, writes `work/W-1xx.md` (requirement_ids REQ-091, REQ-107) and its coverage-stages row; commit them unchanged. Depends on lane B4 (held-switch module `ofo_app/held_switches.py`, merged first) and on lane C Step 3 historical storage (REQ-051); read what `ofo/history/` and `ofo_app/history_store.py` already store before building any new table.

## Spec basis (quoted)
REQ-091 AC-1: "Held until: Zerodha or a licensed data vendor confirms in writing that historical data may be shown to users"
REQ-091 AC-2: "the combined net price per unit (sells minus buys) at each bar over up to the last 15 trading days"
REQ-091 AC-3: "A debit strategy plots as a negative price"
REQ-091 AC-4: "a bar where any leg has no stored price is a gap, never interpolated"
REQ-091 AC-5: "limits the chart to the days all legs have, with the reason shown"
REQ-091 AC-6: "The chart shows prices only, never P&L since a past date, and carries no return wording (ADR-055 (1))."
REQ-091 AC-7: "A test fails if production configuration turns on the builder's Strategy price tab without a recorded reference"
REQ-107 AC-1: "One server setting per chart family switches it on; all default off."
REQ-107 AC-2: "IV percentile is the percent of trading days in the last 252 on which the underlying's end-of-day ATM IV (REQ-106 AC-1 method) was below today's ATM IV"
REQ-107 AC-3: "Every series comes from stored history (REQ-051), never from the browser calling a vendor (ADR-012)."
REQ-107 AC-4: "the profile from the latest snapshot and labelled with its time"
REQ-107 AC-5: "A missing day or interval is drawn as a gap, never interpolated"
REQ-107 AC-6: "no chart computes a P&L"
REQ-107 AC-7: "Wording is descriptive (ADR-003)"
REQ-107 AC-8: "an underlying with too little history follows AC-2's"
Not built here: REQ-108 (events calendar, FII and DII). It has no cleared data source (ADR-012 forbids scraping NSE) so its core cannot be proven on real input; per the prove-the-core-first rule the build around it stops. See Open: business.

## Copy from
Copy from: spec/technical-design/legacy-reuse.md instruments / history rows, `app/models/eod_option_snapshot.py` (ADAPT, P5: Decimal snapshot shape for the historical tier, REQ-051); `src/views/OFOView.vue` etc. are SKIP. In-repo history modules (`ofo/history/bars.py`, `candles.py`, `recorder.py`, `store.py`, `finalize.py`, `ofo_app/history_store.py`) are the adapted copy: reuse. Charts: Copy from: none - the repo already uses chart.js in `PayoffChart.vue`.

## Sensibull screens (study folder D:\Abhay\Ventures\competitors\sensibull\2026-10-21\; never copy a screenshot or account data into the repo)
- 010-039 chart tab 'Strategy Chart' (catalogue-raw.md): combined strategy price vs the month future over about 2 weeks, 'Invert Price' toggle, debit strategy plotted as a NEGATIVE price (BUILDER PASS 2, screens 215-217).
- 140-153 Analyse pages: IV Chart (ATM IV candles / line vs NIFTY, date range), Open Interest sub-tabs (Option OI vs Time: daily Put / Call OI + PCR; Multistrike), Live Options Charts (Auto ATM Straddle LTP / VWAP, per-expiry, timeframes 1m..1d), 026-031 IV Percentile 68 in the Info panel; 027 candle chart with OI Profile beside it.
- Differences kept on purpose: no VWAP or replay scrubber, no FII / DII 'Bullish / Bearish strength' labels or verdict text (ADR-003, ADR-055); every chart and field is absent, not a placeholder, while its switch is off.

## What to build
1. Server series (`ofo/history/series.py`, new, Decimal): `strategy_price_series(legs, window, interval)` (sells minus buys per unit, gap where any leg lacks a stored price, backfilled spans marked, newest point time returned, window cut to the days all legs exist with the reason); `atm_iv_eod(underlying, day)` using the REQ-106 AC-1 method (lane B3's `ofo/marketdata/context.py` if merged, else the engine's `implied_vol` directly); `iv_percentile(series)` over the last 252 trading days with a dash and 'not enough history' under 200 stored days; OI per day, ATM straddle price per interval, OI profile from the latest snapshot.
2. Routes in a new `ofo_app/routes/history_charts.py`: one per chart family, each returning the held reason (or 404-equivalent absence) when its switch is off; prices as strings; stale series marked 'not updating - as of <time>' when the newest point is older than its interval during market hours.
3. Frontend (chart.js; for candles `chartjs-chart-financial`, MIT, pinned in `frontend/package.json` and recorded in the licence note of the report; if you find a licence problem stop and report): 'Strategy price' tab in the Builder with Invert switch (shown only when `/api/features` lists `strategy_price_history`); an analysis page for IV percentile and IV chart, OI over time, straddle chart, candle + OI profile (only when `history_charts` is listed).
4. The AC-7 / AC-1 production-config test is lane B4's test: register these two switch names there (in its closed list) and add one assertion each, do not write a second config reader.
5. Regenerate `docs/api/openapi.json`; register new ApiModel classes in `tests_app/test_response_door.py`.

## AC status (main + evidence/)
| AC | Status |
|---|---|
| REQ-091 AC-1, AC-7 switch | missing (B4 builds the module; this PR registers its names) |
| REQ-091 AC-2..AC-6 | missing (bars are stored: `ofo/history/store.py`, `ofo_app/history_store.py`; no strategy series) |
| REQ-107 AC-1 | missing (same switch module) |
| REQ-107 AC-2..AC-8 | missing |
| REQ-108 AC-1..AC-8 | blocked on a data-source decision (not built) |

## Attack cases
One leg listed for 6 days of the 15 (window cut with the reason '... listed from 14 Oct; showing 6 days'); a bar with a leg stored but 0 price (absent, gap); holiday inside the window (no bar, no interpolation); backfilled span (marked); 199 stored days (percentile dash), 252 days with equal values (percent below today = 0, not 50); ATM strike changing day to day (series uses the then-ATM strike); switch off (route absent, no field in any reply, no tab in the DOM); switch on in test, then off in the same process (route answers off); newest point older than its interval at 11:00 (marked not updating); a chart label containing 'bullish', 'expect', 'should' (wording test fails); user asks for 30 days (clamped to 15 with the reason).

## Findings checked
Findings checked: fallback-time-claims-missing-data, freshness-judged-on-request-start-clock, last-live-answer-kept-after-drop, daily-load-misses-intraday-additions, aggregate-across-mixed-instrument-kinds, setting-read-from-two-sources, advice-wording-denylist-per-module, store-filled-only-by-tests, verified-on-a-module-the-product-does-not-call

Standing items: (a) n/a: no time-budgeted job is added here (the recording job belongs to lane C); (b) n/a: no CI step gains an import beyond the frontend dependency installed by the existing step; (c) n/a: no static detector added; the wording test is an allow-list; (d) applied: answer states of stored history (full, partial, backfilled, stale, absent, too short) each have a stated chart result and a test.
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Targeted tests: tests/history/test_series.py (new), tests_app/test_history_charts_route.py (new), tests_app/test_held_switches.py (B4's file: add the two names), tests_app/test_response_door.py; frontend: `npx vitest run tests/strategy-price.test.js tests/history-charts.test.js`, `npm run lint`, `npm run build`.
Rules: no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no regenerated files in the PR (the one exception is docs/api/openapi.json when an API model changes)
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table

## Open
Open: business: REQ-108 needs the owner to name an events source and an FII / DII source, with licence and cost (ADR-156 (3), ADR-012). Business call: it is spend and a licence. Spec basis: REQ-108 AC-1 and its held_until front matter say each feature stays off until its source, licence and cost are cleared with the owner; none is named (searched: REQ-108, ADR-156, ADR-161). Recommendation: leave REQ-108 unbuilt until a source is named; the events section of REQ-085 stays off with it.
Open: technical: charting library. REQ-091 AC-1 asks for the library licence to be checked. Proposal: chart.js (already used, MIT) plus chartjs-chart-financial (MIT) for candles; no TradingView widget (licence and attribution terms); the production switch test keeps requiring a recorded licence reference.
Open: technical: if lane C's REQ-051 storage is not merged, build against `ofo/history/` as it is; report any missing table as a gap, do not create a second history store.
