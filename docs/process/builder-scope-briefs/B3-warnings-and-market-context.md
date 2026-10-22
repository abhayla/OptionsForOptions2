# W-1xx builder brief (lane B3): Builder warnings, 'How this trade works' bullets, and the market context strip

Common brief: docs/process/builder-brief.md
Core: the server returns warning codes (each only on a measured condition) with catalogue text, and one context strip (ATM IV, put-call ratio, max pain, India VIX with strike counts and as-of times) computed from the user's own feed; the browser draws strings and never builds text or numbers.
Proof: step 1 is two tests with expected values from the requirement text: (1) REQ-085 AC-2 case, a NIFTY short strangle SELL 22,700 PE / SELL 22,900 CE flags both legs, adding BUY 22,500 PE clears the put leg only; (2) REQ-106 AC-1 case, NIFTY 28-Oct, forward 24,530, ATM 24,550, CE IV 13.2 and PE IV 13.6 gives ATM IV 13.4%. Then run both on the recorded chain frames.
Tier: A (reads live OI, bid / ask and IV; ATM IV comes from the engine).

## Work item
The orchestrator allocates the W-id, writes `work/W-1xx.md` (requirement_ids REQ-085, REQ-106) and its coverage-stages row; commit them unchanged. Lane C owns the shared per-snapshot computation of REQ-050 (Step 3); see Open for what to do if it has not landed.

## Spec basis (quoted)
REQ-085 AC-1: "The engine's builder reply carries a list of warning codes per strategy and per leg"
REQ-085 AC-1: "never text built in the browser"
REQ-085 AC-2: "unhedged_short fires for a sold option leg with no bought option of the same type and expiry further out of the money in the strategy"
REQ-085 AC-3: "weekend_holiday_decay fires when the next trading day is two or more calendar days away"
REQ-085 AC-4: "low_liquidity fires for a leg with no trade in the last 5 minutes, no bid or no offer, or a bid-ask spread wider than 10% of the mid price"
REQ-085 AC-5: "Warning texts state the condition and the number only"
REQ-085 AC-6: "Held until: an events data source, its licence and its cost are cleared"
REQ-085 AC-7: "A Custom Strategy shows no bullets and a link to Learn."
REQ-085 AC-8: "A warning or bullet whose data is missing is left out with no placeholder"
REQ-085 AC-9: "A test fails if production configuration turns on the market_event warning code without a recorded reference"
REQ-106 AC-1: "ATM IV is the mean of the CE and PE implied volatilities at the strike nearest the expiry's parity forward (ADR-061)"
REQ-106 AC-2: "Put-call ratio is total put open interest divided by total call open interest over the strikes the platform holds for that expiry, to two decimals"
REQ-106 AC-3: "Max pain is the strike, among the held strikes, at which the total intrinsic value owed to option holders (sum over strikes of OI x intrinsic value at that strike) is smallest; ties go to the strike nearest the forward."
REQ-106 AC-4: "India VIX is the index's last price from the user's own feed"
REQ-106 AC-5: "Each value is computed once per market snapshot and shared by every user entitled to that data"
REQ-106 AC-6: "with fewer than 5 strikes holding OI on either side, PCR and max pain show"
REQ-106 AC-7: "Wording is descriptive only (ADR-003)"
REQ-106 AC-8: "an underlying whose data the user is not entitled to see shows no strip rather than another user's data (ADR-053)"

## Copy from
Copy from: spec/technical-design/legacy-reuse.md services section, rows `services/options/{expected_move,gamma_risk,iv_metrics,oi_analysis,theta_curve}_service.py` (REFERENCE: algorithms only, Decimal rebuild) for PCR / max pain / ATM IV ideas; utils row `app/utils/market_hours.py` (ADAPT: its hard-coded 2026 holiday list is wrong, F-54: never copy it); the dated trading-day calendar is in open PR #455 (gc6/mkt-hours, parked, branch kept; plan names it as `Copy from:` for later steps): adopt its data file and loader, not its Execute hours rule. 'How this trade works' text: Copy from: none - it reuses the Learn texts already in `frontend/src/lib/learnContent.js` (REQ-011, one home for the text).

## Sensibull screens (study folder D:\Abhay\Ventures\competitors\sensibull\2026-10-21\; never copy a screenshot or account data into the repo)
- 026-031 Info panel, F&O Data tab: Fut OI chg, ATM strike, PCR 0.86, Lot size, ATM IV 14.1, Max Pain 23000, IV Percentile 68 (percentile is REQ-107, held, lane B5), India VIX 15; Events tab; Fut. Prices tab.
- 'Insights' link and 'Your warnings' drawer (BUILDER PASS 2, text in bundle-findings.md sections 2.1-2.3): chips Decay (theta_bleed), Stoploss, Event, Delivery, Shortfall Penalty; per-leg liquidity codes `ltt-check-failure`, `high-bid-offer-spread`, `no-bid-offer`; 039: a short strangle shows no warning in the builder itself.
- 083-084 Easy Options 'More Details': 'How does this trade work?' bullets in plain words with the user's strikes.
- Differences kept on purpose: Sensibull's Stoploss insight tells the user to 'place a stop loss, or buy lower put(s)' (advice); here a warning states the condition and the number only (AC-5, ADR-003). Delivery and Shortfall Penalty are stock-underlying insights, not in scope (indices only, ADR-157).

## What to build
1. Engine/service: `ofo/outcome/warnings.py` (new): pure functions returning codes per strategy and per leg for `unhedged_short`, `weekend_holiday_decay` (engine total theta times the days, from the market calendar), `low_liquidity` (last trade time, bid / ask, spread vs mid; the two thresholds read from admin settings, defaults 5 minutes and 10%), `expiry_day` (move the W-086 logic out of `ofo/errors/explanations.py:829` into the same list so there is one list, keeping its text), and `market_event` (never emitted; AC-9 test below).
2. Text: add the warning and bullet templates to the reviewed catalogue (`ofo/errors/templates.py` / `explanations.py` pattern) with an allow-list wording test (condition + number only; ADR-003 words refused).
3. Bullets: from the matched template (`ofo/strategy/matching.py`) and the Learn texts; a Custom Strategy returns no bullets and a Learn link; numbers inside a bullet come from the engine.
4. Context strip: `ofo/marketdata/context.py` (new) computing ATM IV (engine `implied_vol` at the strike nearest `parity_forward`), PCR and max pain over the held strikes with the strike count, India VIX through the instrument store like the index spot (no typed token); `GET /api/market/context` in a new `ofo_app/routes/market_context.py`; every value carries its as-of time; fewer than 5 strikes with OI on a side gives a dash.
5. Frontend: warnings area in the Builder (`No warnings for this strategy` when empty), per-leg chips, 'How this trade works' block; `pages/MarketContextPage.vue` (today a 13-line shell) and a compact strip in the Builder header.
6. AC-9 style test: production configuration cannot turn on `market_event` (and nothing else here is held); regenerate `docs/api/openapi.json`; register new ApiModel classes in `tests_app/test_response_door.py`.

## AC status (main + evidence/)
| AC | Status |
|---|---|
| REQ-085 AC-1 codes list | missing (only the execute-review flags `flag_expiry_day_*` exist, `ofo/errors/explanations.py:829-839`) |
| REQ-085 AC-2, AC-3, AC-4 | missing |
| REQ-085 AC-5, AC-8 | missing (wording test to add) |
| REQ-085 AC-6, AC-9 market_event held | missing |
| REQ-085 AC-7 bullets | missing (Learn texts exist in `frontend/src/lib/learnContent.js`, W-117) |
| REQ-106 AC-1..AC-8 | missing (`frontend/src/pages/MarketContextPage.vue` is a shell; the index spot read exists in `routes/indices.py`) |

## Attack cases
Short call and short put with a bought option of the wrong type or farther-in expiry (still flagged); calendar spread (bought leg on a later expiry does not hedge by the AC-2 test: write the expected result from the AC text); Friday close with a Monday holiday (3 days: weekend plus holiday); theta exactly zero (no weekend warning); leg with no depth (shows 'Liquidity unknown - no live depth', never a verdict); spread of exactly 10% (not wider: no flag); strike with OI absent (left out of PCR and max pain, count drops); all OI on one side; ties in max pain (nearest the forward); India VIX instrument missing from the store (VIX dash with reason, not another token); feed stale (all values dash with 'not available - as of <time>'); SENSEX (ADR-157 covers both indices); a user not entitled to the data (no strip).

## Findings checked
Findings checked: advice-wording-denylist-per-module, guard-as-forbidden-list, fallback-time-claims-missing-data, last-live-answer-kept-after-drop, freshness-judged-on-request-start-clock, aggregate-across-mixed-instrument-kinds, instrument-identity-keyed-on-one-broker, setting-read-from-two-sources, money-value-computed-outside-engine, test-asserts-implementation-output

Standing items: (a) n/a: no time-budgeted job; (b) n/a: no CI step gains an import; (c) applied: the wording allow-list test names the catalogue by import source and fails closed on a string it cannot classify; (d) applied: depth answer states (trade seen, no trade, no bid, no ask, no depth, stale) each decide low_liquidity or unknown and have a test; OI answer states (present, absent, stale) decide PCR and max pain.
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Targeted tests: tests/outcome/test_warnings.py (new), tests/marketdata/test_context.py (new), tests/errors/ (catalogue tests you touch), tests_app/test_market_context_route.py (new), tests_app/test_response_door.py; frontend: `npx vitest run tests/warnings.test.js tests/market-context.test.js`, `npm run lint`, `npm run build`.
Rules: no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no regenerated files in the PR (the one exception is docs/api/openapi.json when an API model changes)
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table

## Open
Open: technical: REQ-106 AC-5 says compute once per snapshot and share across users, which is lane C's REQ-050 work. Proposal: until it lands, compute per request from the requesting user's feed with a cache keyed by (underlying, expiry, snapshot time); one user today, so nothing is shared yet.
Open: technical: the market calendar for AC-3 comes from PR #455's data file (parked). Proposal: copy only the dated holiday file and its loader into a new module; if the file is not usable, the weekend rule alone fires and holidays are listed as an unmeasured gap in the report.
Open: business: none found.

## Legacy map rows (copy_from_check.py)
Rows of spec/technical-design/legacy-reuse.md that name this brief's requirements. Act on each:
COPY/ADAPT -> use it (provenance header) or write in the report why not; REFERENCE -> read before
designing; SKIP -> do not re-survey.

| `ticker/pool.py` (414) | ADAPT | row 1; drop `can_auto_refresh`/`refresh_broker_token` (`:23-24`) and platform credentials | REQ-048, REQ-050 |
| `market_data/rate_limiter.py` (135) | COPY | set Kite limits (legacy had 3 req/s; Kite docs say 10, verify at P3a) | REQ-050 |
| `services/options/option_chain_live_engine.py` (222) | ADAPT | strip platform-wide assumptions | REQ-029, REQ-050 |
| `services/options/option_chain_cache.py` (145) | ADAPT | row 5; no cross-user sharing until ADR-034 | REQ-050 |
| `services/options/option_chain_prefetch.py` (149), `startup_chain_warmup.py` (270), `option_chain_service.py` (458) | REFERENCE | built on the platform adapter / duplicates | REQ-050 |
