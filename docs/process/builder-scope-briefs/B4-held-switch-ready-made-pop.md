# W-1xx builder brief (lane B4): Held-feature switch, ready-made shapes and quick picks, probability of profit (built OFF in production)

Common brief: docs/process/builder-brief.md
Core: one closed-list switch module decides, in one place, whether a held feature is on; the fixed-rule strike placer and the probability-of-profit figure work end to end when the switch is on (development, test) and are absent when it is off (production without a recorded permission).
Proof: step 1 is a test on the switch: with the environment set to production, any held switch set on without a recorded permission reference makes the app refuse to start (or the config test fail); in development the same switch reads on. Then, switch on: NIFTY at spot 22,810, Bull call spread loads BUY 22,800 CE / SELL 23,000 CE; strangle distance 100, SELL side, loads SELL 22,700 PE / SELL 22,900 CE (REQ-079 examples), every strike a listed contract of the real instrument file.
Tier: A (a switch that protects what production users see; engine probability figure; strikes placed from the live spot).

## Work item
The orchestrator allocates the W-id, writes `work/W-1xx.md` (requirement_ids REQ-079, REQ-082) and its coverage-stages row; commit them unchanged. This PR merges BEFORE lane A4 (modes and setups) and before B5 / B6, which import the switch module.

## Spec basis (quoted)
REQ-079 AC-1: "Held until: the written legal answer to Q211 clears platform-placed strikes"
REQ-079 AC-2: "The builder lists the catalogue templates (REQ-028 AC-3) grouped by market view (Bullish, Bearish, Neutral, Other) with an expiry picker"
REQ-079 AC-3: "ATM is the listed strike nearest the live spot (a tie takes the lower strike)"
REQ-079 AC-4: "the loaded legs are ordinary legs the user can edit, step and Shift (REQ-076, REQ-078), and nothing is executed or saved by loading"
REQ-079 AC-5: "legs are never cleared without that answer (ADR-019)"
REQ-079 AC-6: "A template that needs an expiry the underlying does not have is refused with a plain catalogue message, never a server error."
REQ-079 AC-7: "The distances are admin settings per underlying, each a multiple of the strike step: NIFTY 50 / 100 / 150 / 200 points, SENSEX 100 / 200 / 300 / 400 points by default."
REQ-079 AC-8: "when the spot is stale or missing the load is refused with the REQ-049 reason, never placed from an old spot (ADR-015)"
REQ-079 AC-9: "which opens the builder with that template loaded per AC-3 and AC-4 for the nearest expiry the template allows"
REQ-079 AC-10: "fall under the same hold (register row MR-043)"
REQ-079 AC-11: "A test fails if production configuration turns on platform-placed strikes"
REQ-082 AC-1: "Until then the field is switched off in production and absent from the screen, not shown as a placeholder."
REQ-082 AC-2: "The engine computes the probability that the underlying at the strategy's expiry lies in a region where the expiry P&L including round-trip charges (ADR-082) is above zero"
REQ-082 AC-3: "never more precision than a whole percent (REQ-032 AC-5)"
REQ-082 AC-4: "to within 0.1 percentage point before rounding"
REQ-082 AC-5: "never an old value"
REQ-082 AC-6: "The figure is never used to sort, rank or pick strategies"
REQ-082 AC-7: "A test fails if production configuration turns on the probability-of-profit figure without a recorded reference"

## Copy from
Copy from: spec/technical-design/legacy-reuse.md strategy-template section, rows `scripts/seed_strategies.py` + `app/models/strategy_templates.py` (REFERENCE: the in-repo W-005 / W-047 library exists; fill only missing templates; `example_spot` is Float at `:62`, never copy); `app/api/routes/optionchain.py` find-by-delta / premium (ADAPT, used by lane A4 not here). The fixed-rule placement itself already exists in the domain: `atm_strike` and `resolve_template` in `ofo/strategy/model.py:283` and `:307`; reuse them. Frontend row `src/views/StrategyLibraryView.vue` (ADAPT, P5, reword 'Recommended For You'). Switch module and probability: Copy from: none - new.

## Sensibull screens (study folder D:\Abhay\Ventures\competitors\sensibull\2026-10-21\; never copy a screenshot or account data into the repo)
- 010 and 011/012: ready-made catalogue filtered Bullish / Bearish / Neutral / Others with an Expiry picker; one click loads real legs at ATM (Bull Call Spread = B 23000 CE / S 23200 CE, 27 Oct); 100-134 deep dive lists the 36 shapes; preset-matrix.md section 'How Sensibull places the preset strikes' (spread second strike 200 points on NIFTY, 400 on SENSEX; condor shorts ATM +/- 1 step-unit with wings another 200) is a comparison for the rule, not a source of numbers: the rule is the template data (REQ-079 AC-3).
- 032-038: Strangles tab Quick Select 50 / 100 / 150 / 200 points; Straddles tab; 'You are changing strategy type' prompt.
- Summary strip POP 42% and its tooltip (124-129, bundle-findings.md section 2): 'This is a mathematical probability ...'.
- 160-170 Learn Options Strategies: per-strategy page with 'Open in Builder'.
- Differences kept on purpose: loaded legs carry the label 'Strikes placed by a fixed rule - change them' until the user edits the strike; POP is labelled a model estimate and never used to rank (Sensibull ranks by profit; ADR-003, ADR-055); everything stays off in production until Q211 clears in writing.

## What to build
1. `ofo_app/held_switches.py` (new): a CLOSED list of switch names (platform_strikes, probability_of_profit, delayed_prices, history_charts, events_calendar, fii_dii, market_event_warning, strategy_price_history), each read from ONE source (one function reads the configuration, nothing else reads an environment variable for a held switch: finding setting-read-from-two-sources), each with its permission reference field; on in development and test only, or in production only with the setting on AND a non-empty reference. An unknown switch name raises. Endpoint `GET /api/features` returns only which held features are on, so the browser hides the rest (absent, not greyed).
2. Production-config test (REQ-079 AC-11, REQ-082 AC-7; the same test serves B5 and B6): loads the production config and fails if any switch is on without a reference; it also fails if a new switch name appears in code without being in the list and in this test.
3. Placer: `ofo/strategy/placement.py` (new): `place_template(template, expiry, spot, strike_gap, listed_strikes)` using `resolve_template`; `place_quick_pick(kind, distance, side, ...)` for straddle / strangle with distances from admin settings per underlying (defaults from AC-7); refuses with the REQ-049 reason on a stale or missing spot and with a catalogue message when the expiry is missing (ADR-157 example: calendar spread with no next monthly expiry). Lane A4 calls this function; keep its signature small and documented.
4. Routes: `POST /api/strategies/load-template` and `POST /api/strategies/quick-pick` in a new `ofo_app/routes/ready_made.py`; both answer with the held reason when the switch is off and place nothing.
5. POP: `ofo/engine/pop.py` (new): lognormal probability under the engine's model (Black-Scholes, parity forward, implied yield, ATM IV of the expiry) over the profit regions of the expiry P&L including charges; reuse the region logic in `ofo/engine/metrics.py` (`_loss_regions`) but do NOT infer regions from breakevens alone (finding loss-region-inferred-from-breakevens); whole percent; a dash with the reason for mixed expiries, missing IV or stale spot. Put it in the outcome reply only when `probability_of_profit` is on.
6. Frontend: ready-made list with market-view tabs and expiry picker, Replace/Cancel prompt (AC-5), the fixed-rule label, quick-pick controls, POP figure with its label; all rendered only when `/api/features` lists them. Learn page 'Open in Builder' link (`pages/LearnPage.vue`).
7. Regenerate `docs/api/openapi.json`; register new ApiModel classes in `tests_app/test_response_door.py`.

## AC status (main + evidence/)
| AC | Status |
|---|---|
| REQ-079 AC-1, AC-11 switch + test | missing (no held-feature mechanism exists: a repo search for Q211 or a feature flag finds nothing in backend/ or frontend/src) |
| REQ-079 AC-2, AC-9 | missing (Learn page and strategy list exist, W-117 / W-047) |
| REQ-079 AC-3, AC-4 | partial (`resolve_template` places by offsets in the domain; no route, no label) |
| REQ-079 AC-5, AC-6, AC-7, AC-8 | missing |
| REQ-079 AC-10 | covered by lane A4 (delta modes) through this PR's switch |
| REQ-082 AC-1..AC-7 | missing |

## Attack cases
Production config with a switch on and an empty or whitespace reference (fails); reference present but switch off (stays off); unknown switch name in code (raises at import); a request body, header or query that tries to turn a switch on (ignored); switch flipped at runtime without a restart (read once or re-read, but from the one function); template on an underlying lacking its expiry (message, not 500); spot stale (refused with the reason); ATM tie (lower strike); quick pick distance not a multiple of the strike step (refused); loading into a builder with legs (prompt first); POP for a single sold put equals the model probability of ending above its breakeven within 0.1 pp (independent calculation in the test); POP for mixed expiries (dash); POP sorted or ranked anywhere (test greps the code for sort keys using it).

Threat model: in scope any request-supplied value (body, header, query, cookie) trying to change a held switch, a production configuration with a switch on and no reference, a new switch name added in code but not registered; out of scope the owner editing the production configuration file with a real reference (owner-edited by design) and a hosting provider overriding environment variables.

## Findings checked
Findings checked: setting-read-from-two-sources, guard-as-forbidden-list, guard-without-killing-test, privilege-guard-as-denylist, loss-region-inferred-from-breakevens, outcome-multi-expiry-unhandled-500, fallback-time-claims-missing-data, money-value-computed-outside-engine, advice-wording-denylist-per-module, store-filled-only-by-tests

Standing items: (a) n/a: no time-budgeted job; (b) n/a: no CI step gains an import; (c) applied: the production-config test is an allow-list (the closed switch list), names the switch module by import source, and fails closed on a switch name it cannot resolve; mutation: delete the reference check and name the test that goes red; (d) applied: the switch answer states (on, off, setting unreadable, reference empty, unknown name) each have a defined result and a test; spot and expiry states are attack cases.
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Targeted tests: tests_app/test_held_switches.py (new), tests_app/test_production_config_switches.py (new), tests/strategy/test_placement.py (new), tests/engine/test_pop.py (new), tests_app/test_ready_made_route.py (new), tests_app/test_response_door.py; frontend: `npx vitest run tests/ready-made.test.js tests/features.test.js`, `npm run lint`, `npm run build`.
Rules: no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no regenerated files in the PR (the one exception is docs/api/openapi.json when an API model changes)
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table

## Open
Open: technical: the template data says how many strike steps from ATM each strike sits (REQ-079 AC-3), but the catalogue (`ofo/strategy/catalogue.yaml`, about 20 templates; count them first) carries offsets already; check each of the 21 against the Sensibull rule table before relying on them and list any template with no usable offsets. Proposal: templates without offsets are not listed (absent), recorded in the report.
Open: business: none new. The owner-held items stay held: the Q211 written legal answer and its label wording are already the spec's conditions.

## Legacy map rows (copy_from_check.py)
Rows of spec/technical-design/legacy-reuse.md that name this brief's requirements. Act on each:
COPY/ADAPT -> use it (provenance header) or write in the report why not; REFERENCE -> read before
designing; SKIP -> do not re-survey.

| `app/utils/market_hours.py` (138) | ADAPT | add holiday calendar and BSE hours; its hard-coded 2026 holiday list is wrong (F-54): never copy it, use the dated NSE data file (ADR-119) | REQ-049 |
| `app/constants/trading.py` (158), `strategy_types.py` (421), `enums.py` (375), `websocket.py` (65), `brokers.py` (29) | REFERENCE | hardcoded lot sizes conflict with REQ-053; strategy-type names/categories useful | REQ-028 |
| `ticker/health.py` (334), `ticker/token_policy.py` (154) | ADAPT | row 8; map to ADR-015 states; drop TOTP categories `:7,17,25-36` | REQ-049 |
| `services/options/vectorized_greeks.py` (225) | REFERENCE | row 6; our engine already has Black-Scholes (W-002): numeric cross-check only | REQ-032 |
| `tests/factories/ticks.py` (220), `tests/backend/brokers/` (normalized tick, health monitor, pool, token policy, iv solver, kite ticker) | ADAPT | Decimal; with the ticker copy | REQ-049 |
| `services/options/{greeks_calculator,pnl_calculator,payoff_calculator}.py` | SKIP | float calculators outside the one engine (formula cross-check only) | REQ-032, REQ-033 |
| `src/services/priceService.js` (251) | ADAPT (P3b) | polling fallback only; change math from the backend | REQ-049 |
| `src/components/common/MarketStatusBanner.vue`, `DataSourceBadge.vue` | ADAPT (P3b) | data-health indicator | REQ-049 |
