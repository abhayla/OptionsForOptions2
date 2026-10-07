# Legacy code reuse plan and the algochanakya map

Decisions: ADR-043 (copy/adapt with provenance), ADR-047 (copy first: this map is checked before any module is
written; it is built once and never re-searched ad hoc). Surveys 2026-09-29: `docs/reference/legacy/algochanakya-survey.md`,
`ofo-newofo-survey.md`, `optionsforoptions-csharp-survey.md`. Full map: four read-only surveys on 2026-10-02 of
`D:\Abhay\Ventures\algochanakya` at commit **`bf9faf7`** (backend services; API, models, scripts, tests; frontend;
Claude skills, docs, tooling). Verdicts: COPY (as is, plus provenance header), ADAPT (copy, then change as stated),
REFERENCE (read for ideas, write ours), SKIP (never copy). Phases P0-P6 are the build plan's phases. "B" = blocked on
Zerodha's written answer (ADR-034). Line counts in parentheses. Paths are under `backend/` unless they start with
`frontend/`, `docs/`, `.claude/` or `.github/`.

## Sources
| Repo | Stack | Commit surveyed | Use |
|---|---|---|---|
| `abhayla/algochanakya` (public) | Python 3.13 / FastAPI 0.123, async SQLAlchemy 2, PostgreSQL, Redis; Vue 3.5 + Vite 7 | `2a868db` (2026-08-27); full map re-pinned to `bf9faf7` (2026-10-02) | **Main source**: platform infra, market data, broker adapter, instrument master, frontend, Kite knowledge |
| `abhayla/OFO` (private) | TypeScript / Node + React, Prisma | `ebc5cde` (2025-08-02) | Reference: Kite login handshake, WebSocket + Redis pub/sub pattern |
| `abhayla/NewOFO` (private) | TypeScript / Node + React | 2025-07-25 | Reference: option-chain and positions page layout only (its data path scrapes NSE: not allowed, ADR-012) |
| `abhayla/OptionsForOptions` (private) | C# .NET Framework 4.8 WebForms, MySQL | `3ecd877` | Reference: payoff formula shape, strategy list; nothing copyable (float money, no tests, unsafe SQL) |

## What to copy or adapt (from algochanakya, paths under `backend/app/`)
| # | Source | Verdict | Change needed | Requirements |
|---|---|---|---|---|
| 1 | `ticker/models.py` NormalizedTick, `ticker/adapter_base.py`, `ticker/pool.py`, `ticker/router.py` | ADAPT | Behind our market-data gateway; health states per ADR-015 | REQ-048, REQ-050 |
| 2 | `services/brokers/base.py` order/position/quote types + BrokerAdapter | ADAPT | Mandatory `strategy_id` on every order (ADR-002); margin preview; Zerodha only in V1, seam kept for others | REQ-054 |
| 3 | `ticker/adapters/kite.py` KiteTicker → asyncio bridge | ADAPT | Blocked until Zerodha's written answer (ADR-034) | REQ-048 |
| 4 | `kite_adapter.py` Kite → unified converters | ADAPT | Decimal fields | REQ-054, REQ-060 |
| 5 | `services/options/option_chain_cache.py` Redis cache + request coalescing | ADAPT | No cross-user sharing of one user's Zerodha data until ADR-034 is answered | REQ-050 |
| 6 | `services/options/vectorized_greeks.py` IV + Greeks | ADAPT | Moves inside the one calculation engine; results converted to Decimal at the boundary | REQ-032, REQ-034 |
| 7 | `backend/scripts/seed_strategies.py` 22 templates | ADAPT | Strike offsets per index (ADR-042); decision-support wording (ADR-003) | REQ-028 |
| 8 | `ticker/health.py`, `ticker/token_policy.py` | ADAPT | Drop TOTP auto-login; never hold Zerodha credentials (ADR-020) | REQ-049 |
| 9 | `api/.../auth.py` lines 60–175 Kite OAuth callback | REFERENCE | Rewrite: legacy stores the access token in plaintext | REQ-015 |
| 10 | `services/instrument_master.py` | ADAPT | Add BFO (SENSEX); the ONLY source of lot size and strike gap | REQ-053 |

## The full map (algochanakya `bf9faf7`, 2026-10-02)
Rows 1-10 above stay valid (re-confirmed at `bf9faf7`; row 9 lives in `app/api/routes/auth.py`).

### M1 Platform (P1)
| Source | Verdict | Change / conflict | REQ |
|---|---|---|---|
| `app/database.py` (92) | ADAPT | keep async engine, `async_sessionmaker(expire_on_commit=False)`, `Base`, `get_db`; drop `convert_decimals_to_float` (`:11-24`, float money), `init_db`/`create_all` (bypasses migrations), Redis bits, host print | REQ-064 |
| `server_default=func.now()` on `DateTime(timezone=True)` (`app/models/users.py:20`) | COPY | plus our BEFORE INSERT trigger (ADR-023 clock) | REQ-064 |
| `app/config.py` (86) | ADAPT | pattern only: `SettingsConfigDict`, required DB URL; drop broker/TOTP/AI fields (`:23-25` Kite app credentials) | REQ-063 |
| `app/api/routes/health.py` (43) | COPY | DB check only at first | - |
| `app/main.py` (355) | REFERENCE | lifespan pattern only; broker-tangled startup, `create_all`, global handler leaks `str(exc)` (`:293-307`) | REQ-065 |
| `alembic.ini` (147), `alembic/env.py` (102) | ADAPT | env is sync (rewrites asyncpg URL to psycopg2): use the async template; explicit model imports | - |
| `alembic/versions/*` (41) | SKIP | messy history tied to legacy tables; fresh baseline | - |
| `.github/scripts/alembic-migration-guard.py` + test | ADAPT | as a project script under `scripts/` | - |
| `tests/conftest.py` (637) | REFERENCE | copy only the `client` fixture pattern (`dependency_overrides[get_db]` + `AsyncClient(ASGITransport)`); SQLite + shims (`:104`) conflict with real-Postgres tests | - |
| `pytest.ini` (21) | ADAPT | keep `asyncio_mode=auto`, loop scope, markers; drop Allure/coverage addopts | - |
| `requirements.txt` (78) | REFERENCE | take pins only: fastapi 0.123.5, starlette 0.50.0, SQLAlchemy 2.0.44, alembic 1.17.2, asyncpg 0.31.0, pydantic 2.12.5, pydantic-settings 2.12.0, redis 7.1.0, httpx 0.28.1, uvicorn 0.38.0, cryptography 46.0.3; drop aiosqlite, other brokers, upstox-totp/pyotp (ADR-020), anthropic/sklearn, python-jose/passlib | - |
| `.github/workflows/backend-tests.yml` (148) | ADAPT -> `app-tests.yml` | postgres:16 + redis:7 services, health checks, `alembic upgrade head`; Python 3.12; drop Codecov/Allure; ADR-046 path filter | - |
| `scripts/generate_openapi.py` (44) | COPY | contract check per phase | - |
| `.pre-commit-config.yaml` | ADAPT | ruff, detect-secrets baseline, no-.env, file hygiene | REQ-063 |
| `ruff.toml` (52) | REFERENCE | | - |
| `app/utils/encryption.py` (125) | REFERENCE | Fernet key derived from `JWT_SECRET`: use a dedicated key if field encryption is needed | REQ-063 |
| `app/utils/jwt.py` (63), `dependencies.py` (171), `user_resolver.py` (105), `app/api/routes/auth.py` (515), `app/models/users.py` (60) | SKIP | legacy auth/users (Kite-as-login; token embeds broker connection) | REQ-012 |
| `app/websocket/manager.py` (520), `routes.py` (181) | REFERENCE | connection manager pattern; `ticker/router.py` is the better base | REQ-048 |

### M2 Instruments, market hours, constants (P1 W-053 / P3)
| Source | Verdict | Change / conflict | REQ |
|---|---|---|---|
| `app/models/instruments.py` (51) | ADAPT | Numeric strike/tick with Decimal defaults (float `0.05` default), unique (exchange, token), drop `source_broker` | REQ-053 |
| `tests/backend/instruments/test_instrument_master.py` | ADAPT | as test cases for our catalogue persistence | REQ-053 |
| `app/services/instrument_master.py` (414) | REFERENCE | row 10; our W-006 parser already exists: take BFO/SENSEX handling only | REQ-053 |
| `app/services/instruments.py` (278) | SKIP | superseded | - |
| `app/utils/market_hours.py` (138) | ADAPT | add holiday calendar and BSE hours | REQ-049 |
| `app/utils/tradingsymbol.py` (63) | REFERENCE | catalogue is the one source of symbols | REQ-053 |
| `app/constants/trading.py` (158), `strategy_types.py` (421), `enums.py` (375), `websocket.py` (65), `brokers.py` (29) | REFERENCE | hardcoded lot sizes conflict with REQ-053; strategy-type names/categories useful | REQ-028 |
| `services/brokers/market_data/ticker/index_token_maps.py` (42) | REFERENCE | hardcoded tokens; use the catalogue | REQ-053 |
| `app/models/eod_option_snapshot.py` (51) | ADAPT (P5) | Decimal snapshot shape for the historical tier | REQ-051 |

### M3 Market data pipeline (P3b, B)
| Source | Verdict | Change / conflict | REQ |
|---|---|---|---|
| `services/brokers/market_data/ticker/models.py` (84) | ADAPT | row 1; fix float serialization `:61-69` | REQ-049 |
| `ticker/adapter_base.py` (273), `ticker/router.py` (377) | ADAPT | row 1; router gets auth + entitlement checks | REQ-048 |
| `ticker/pool.py` (414) | ADAPT | row 1; drop `can_auto_refresh`/`refresh_broker_token` (`:23-24`) and platform credentials | REQ-048, REQ-050 |
| `ticker/adapters/kite.py` (319) | ADAPT | row 3 | REQ-048 |
| `ticker/health.py` (334), `ticker/token_policy.py` (154) | ADAPT | row 8; map to ADR-015 states; drop TOTP categories `:7,17,25-36` | REQ-049 |
| `ticker/failover.py` (287), `ticker/adapters/{dhan,fyers,paytm,smartapi,upstox}.py` | SKIP | multi-broker | - |
| `market_data/market_data_base.py` (520) | ADAPT | trim to Zerodha, behind our gateway | REQ-048 |
| `market_data/kite_adapter.py` (440) | ADAPT | user's own session token only, server-side | REQ-048, REQ-053 |
| `market_data/rate_limiter.py` (135) | COPY | set Kite limits (legacy had 3 req/s; Kite docs say 10, verify at P3a) | REQ-050 |
| `market_data/exceptions.py` (80) | ADAPT | map to REQ-065 classes | REQ-065 |
| `market_data/auth_tracking.py` (102) | REFERENCE | token-expiry detection idea | REQ-015 |
| `market_data/{symbol_converter,token_manager,instrument_query,ticker_base,failover_fetch,factory}.py`, other-broker adapters, `app/models/broker_instrument_tokens.py` | SKIP | cross-broker mapping/failover, platform-wide token; keyed on a Zerodha symbol string with converters for 2 of 6 brokers (spec/findings.md F-09); our identity is (exchange, exchange_token) per ADR-050 | REQ-054 |
| OpenAlgo `broker/<name>/` plugin layout (github.com/marketcalls/openalgo; not algochanakya) | REFERENCE | design reference only (login, orders, data, mapping, contract master, capability file); licence checked 2026-10-07: AGPL-3.0, so no code is ever copied, ideas only (F-08, F-13, ADR-050) | REQ-054 |
| `services/options/option_chain_live_engine.py` (222) | ADAPT | strip platform-wide assumptions | REQ-029, REQ-050 |
| `services/options/option_chain_cache.py` (145) | ADAPT | row 5; no cross-user sharing until ADR-034 | REQ-050 |
| `services/options/option_chain_prefetch.py` (149), `startup_chain_warmup.py` (270), `option_chain_service.py` (458) | REFERENCE | built on the platform adapter / duplicates | REQ-050 |
| `services/options/vectorized_greeks.py` (225) | REFERENCE | row 6; our engine already has Black-Scholes (W-002): numeric cross-check only | REQ-032 |
| `tests/factories/ticks.py` (220), `tests/backend/brokers/` (normalized tick, health monitor, pool, token policy, iv solver, kite ticker) | ADAPT | Decimal; with the ticker copy | REQ-049 |
| `tests/fixtures/record_broker_responses.py`, `record_raw_responses.py`, `record_websocket_ticks.py` | ADAPT | recorder pattern for Kite fixtures; recorded upstox files carry PII: never copy | REQ-054 |

### M4 Broker connection and execution (P4, B)
| Source | Verdict | Change / conflict | REQ |
|---|---|---|---|
| `services/brokers/base.py` (503) | ADAPT | row 2; mandatory `strategy_id`; public `place_order` (`:286`) / `place_basket_order` (`:358`) removed: only `send_guard._Transport.submit` | REQ-054 |
| `services/brokers/kite_adapter.py` (584) | ADAPT | row 4; Decimal in; floats only at the SDK edge (`:163,168,218,220,326`), private to the transport | REQ-054, REQ-060 |
| `app/api/routes/auth.py:60-175` | REFERENCE | row 9; token stored only via the secure mechanism | REQ-015 |
| `app/api/routes/orders.py` (681) | REFERENCE | margins, import-positions, quote mapping; optional strategy_id (`:147-165`) and float (`:139,518,585-590`) | REQ-055, REQ-061 |
| `app/api/routes/positions.py` (569) | REFERENCE / SKIP | `grouped`/`annotated` reads are reference (REQ-044); exit/add/exit-all (`:254,304,354`) break ADR-002 | REQ-044 |
| `app/models/autopilot.py` (1130) order/batch/leg tables | REFERENCE | NOT NULL strategy_id + Numeric are good templates; `execution_mode` auto (`:89,167,628`) breaks ADR-009/017 | REQ-057, REQ-058 |
| `app/models/strategies.py` (57) | REFERENCE | leg shape with Decimal; needs versions/state; loose `order_id` string | REQ-038 |
| `services/autopilot/order_executor.py` (1128), `confirmation_service.py` (529), `kill_switch.py` (410) | REFERENCE | retry (`:80`) conflicts with REQ-058 | REQ-056, REQ-059 |
| `app/models/broker_connections.py`, `broker_api_credentials.py`, `*_credentials.py`, routes `zerodha_credentials.py`, `settings_credentials.py` | SKIP | plaintext/stored broker secrets (`broker_connections.py:21`, `broker_api_credentials.py:50-58`) | REQ-063 |
| other-broker routes/adapters, `factory.py`, `platform_token_refresh.py`, `data_source_warmup.py`, `services/legacy/*`, `services/deprecated/*` | SKIP | multi-broker, TOTP auto-login, orders without strategy | - |

### M5 Strategy building (P4 slice / P5)
| Source | Verdict | Change / conflict | REQ |
|---|---|---|---|
| `scripts/seed_strategies.py` (1312), `app/models/strategy_templates.py` (75) | REFERENCE | row 7; our W-005/W-047 library exists: fill only missing templates; `example_spot` Float (`:62`) | REQ-028 |
| `app/api/routes/strategy_wizard.py` (596), `app/schemas/strategy_templates.py` (211) | ADAPT | wizard + compare for the Guided Builder; drop `deploy` (AutoPilot) | REQ-024, REQ-069 |
| `app/api/routes/optionchain.py` (1285) find-by-delta/premium, `options.py` (277) | ADAPT | split into service + route; Decimal; lot size/strikes from the catalogue | REQ-027, REQ-029 |
| `app/api/routes/strategy.py` (752), `ofo.py` (275), `app/schemas/strategies.py` (252), `ofo.py` (211) | REFERENCE / SKIP | float P&L calculators (`schemas/strategies.py:150-162`), optional strategy_id (`:184`) | REQ-038 |
| `services/ofo_calculator.py` (697) | REFERENCE | combination-search idea only; float; second calculator | REQ-069 |
| `services/options/{greeks_calculator,pnl_calculator,payoff_calculator}.py` | SKIP | float calculators outside the one engine (formula cross-check only) | REQ-032, REQ-033 |
| `services/options/{expected_move,gamma_risk,iv_metrics,oi_analysis,theta_curve}_service.py` | REFERENCE | algorithms for REQ-026 / REQ-047 | REQ-026, REQ-047 |
| `services/options/{eod_snapshot_service,nse_fetcher}.py` | SKIP | NSE scraping (ADR-012) | - |

### M6 Monitoring, rules, adjustments (P5, reference only)
| Source | Verdict | Change / conflict | REQ |
|---|---|---|---|
| `services/autopilot/condition_engine.py` (1096) | REFERENCE | condition vocabulary; rebuild on Decimal | REQ-041 |
| `services/autopilot/strategy_monitor.py` (1876) | REFERENCE | trigger loop | REQ-043 |
| `services/autopilot/adjustment_engine.py` (1388) | REFERENCE | auto default (`:246`); Alert + Prepare only | REQ-042, REQ-045 |
| `services/autopilot/{delta_band,delta_rebalance,dte_zone,trailing_stop,premium_tracker,adjustment_cost_tracker}*.py` | REFERENCE | trigger definitions | REQ-045, REQ-047 |
| `services/autopilot/{strike_finder_service,strategy_converter,template_service,suggestion_engine,position_sizing,position_leg_service,leg_actions_service,break_trade_service,staged_entry_service}.py` | REFERENCE | leg exit/add actions break ADR-002 | REQ-027, REQ-037 |
| `app/models/autopilot.py` logs/journal tables | REFERENCE | timeline/audit columns | REQ-040, REQ-064 |
| `services/autopilot/{analytics,reports,trade_journal,backtest,whatif_simulator}.py`, `app/api/v1/autopilot/*` | SKIP | no REQ / auto-execution / second calculator | - |

### M7 Frontend (`frontend/`, P2a skeleton, then P3b/P4/P5)
| Source | Verdict | Change / conflict | REQ |
|---|---|---|---|
| `package.json` | ADAPT | vue 3.5, vue-router 4.6, pinia 3, axios, chart.js, vite 7, vitest (bump), eslint/prettier; styling per the styling ADR; drop autoprefixer | ADR-043 |
| `vite.config.js` (25), `eslint.config.js` (48), `main.js` (13), `index.html` | COPY / ADAPT | add `/api`, `/ws` dev proxy; eslint ban on vendor hosts; remove `kite-theme.css` | ADR-012 |
| `src/router/index.js` (234) | ADAPT | structure (lazy routes, meta flags, once-only auth guard); new route table; UX-only entitlement guard | REQ-009 |
| `src/services/api.js` (45) | ADAPT | same-origin base, httpOnly cookie instead of localStorage (`:15`), REQ-065 error mapper | REQ-063 |
| `src/components/layout/KiteLayout.vue` (80), `KiteHeader.vue` (715) | ADAPT | rename and restyle (not Zerodha's look); strip broker switching | REQ-009 |
| `src/composables/useToast.js`, `useScrollIndicator.js`; `src/tests/setup.js`, `tests/helpers/*` | COPY | | REQ-065 |
| `playwright.config.js` (92), `tests/e2e/` pages/fixtures, `data-testid` convention | ADAPT | mocked backend, no real broker login | REQ-067 |
| `src/composables/autopilot/useWebSocket.js` (505) + test (832) | ADAPT (P3b) | token off the query string (`:53`); decouple from autopilot | REQ-043, REQ-048 |
| `src/services/priceService.js` (251) | ADAPT (P3b) | polling fallback only; change math from the backend | REQ-049 |
| `src/stores/optionchain.js` (550), `views/OptionChainView.vue` (1240), `components/optionchain/StrikeFinder.vue` (342) | ADAPT (P3b/P5) | no local ATM fallback (`:155`); strike logic in the backend | REQ-027, REQ-029 |
| `src/components/common/MarketStatusBanner.vue`, `DataSourceBadge.vue` | ADAPT (P3b) | data-health indicator | REQ-049 |
| `src/views/StrategyBuilderView.vue` (2094), `stores/strategy.js` (969) | ADAPT (P4) | split; delete client P&L (`stores/strategy.js:722-743`), price fallbacks (`:359-374`), basket call (`:622`) | REQ-034, REQ-035, REQ-036 |
| `src/components/strategy/PayoffChart.vue`, `PnLCell.vue`, `SummaryCards.vue`, `StrategyHeader/Footer/Actions.vue` | COPY (P4) | verify props are backend values | REQ-034, REQ-035 |
| `src/components/strategy/StrategyLegRow.vue` (299), `assets/styles/strategy-table.css` (234) | ADAPT (P4) | remove P&L at `:229` | REQ-035 |
| `src/components/strategy/BasketOrderModal.vue` (156) | ADAPT (P4) | becomes the execution-plan review with backend margin/totals | REQ-056 |
| `src/components/settings/KiteSettings.vue` (388), `views/AuthCallbackView.vue` (81) | ADAPT (P4) | no token in URL | REQ-015 |
| `src/views/LoginView.vue` (606), `SettingsView.vue` (608), `stores/auth.js` (263) | ADAPT (P2b) | Google + WhatsApp OTP, Zerodha connect, cookie auth | REQ-012, REQ-013 |
| `src/views/StrategyLibraryView.vue` (653), `stores/strategyLibrary.js` (409), `StrategyWizardModal.vue` | ADAPT (P5) | "Recommended For You" (`:30`) reworded | REQ-025, REQ-069 |
| `src/views/PositionsView.vue` (1306), `stores/positions.js` (213), `DashboardView.vue` (505), `components/autopilot/monitoring/*` | ADAPT (P5) | strategy-scoped; reword advice (`GammaRiskAlert.vue:22`) | REQ-008, REQ-043, REQ-044 |
| `components/autopilot/builder/*`, `adjustments/*`, `views/autopilot/*`, `stores/autopilot.js` (2166) | REFERENCE | client P&L (`stores/autopilot.js:961`), advice strings (`StrategyDetailView.vue:306-325`, `BreakTradeWizard.vue:188,243`) | REQ-041, REQ-046 |
| `views/{Watchlist,OFO}View.vue`, `components/{watchlist,ofo,ai}/*`, `stores/{ofo,aiConfig,aiAnalytics,watchlist}.js`, per-broker settings/credential services, `views/ai/*`, `MarketDataSourceToggle.vue` | SKIP | no REQ; standalone "Place Order" (`OFOResultCard.vue:103-110`); vendor keys; advice wording | - |

### M8 Skills, rules, hooks, docs (P0 unless noted)
| Source | Verdict | Target / change |
|---|---|---|
| user-level skill `zerodha-expert` (474 + 11 references) | REUSE as is | already installed; ignore its AlgoChanakya section and dead `broker-shared` link |
| algochanakya Kite facts (token expiry ~6 AM / NOT_REFRESHABLE, `token api_key:access_token`, WS paise vs REST rupees, 3000 tokens x 3 connections, 10 req/s, no option-chain or Greeks API) | REUSE via `zerodha-expert` | already in that skill with links to kite.trade docs and a "Last verified" table; no separate skill (it would duplicate). Unverified for this project until the P3a proof |
| `.claude/agents/options-greeks-reviewer.md` | ADAPTED (P0) | `.claude/skills/options-math-review/`; its 7% / 252-day defaults replaced by the spec's admin rate (default 6.5%, Q248) and calendar days / 365 (ADR-008) |
| `.claude/skills/investigate-option-chain-ltp-zero`, `websocket-subscription-flow`, `debug-websocket-ticks` | ADAPT (P3b) | `.claude/skills/option-chain-debug/` |
| `.claude/rules/decimal-not-float-prices.md` | ADAPTED (P0) | `.claude/rules/project/decimal-money-boundaries.md`, path-scoped to app/frontend; money serialized as a string, never a JSON float |
| `.claude/rules/token-auto-refresh.md` | ADAPT (P3b) | with `token_policy.py`: Kite only, NOT_REFRESHABLE, no TOTP, no automatic retry (REQ-058) |
| `.claude/hooks/secret-scanner.py` | ADAPTED (P0) | `scripts/hooks/secret_scan.py` + `tests/hooks/test_secret_scan.py`, wired in `.claude/project/hooks.json`; also scans Markdown |
| `docs/features/ofo/REQUIREMENTS.md` (63), `README.md` (68), `docs/plans/ofo-implementation-plan.md` (396) | COPY | `docs/reference/legacy/ofo/`; reference for REQ-069 (ranking rules would be a SPEC CHANGE) |
| `docs/decisions/TICKER-DESIGN-SPEC.md` (659), `docs/architecture/websocket.md` (335), `docs/specs/option-chain-performance-spec.md` (292), `docs/plans/cmp-fallback.md` (75) | COPY after secret scrub | `docs/reference/legacy/ticker/`, `option-chain/` |
| `docs/troubleshooting/zerodha-oauth-login-issues.md` (856), `docs/architecture/authentication.md` (404) | COPY after secret scrub (P4) | `docs/reference/legacy/` |
| `docs/architecture/broker-abstraction.md`, `market-data-abstraction.md`, `credential-flow-analysis.md`, `docs/prod/*`, `docs/testing/e2e-test-rules.md` | REFERENCE | |
| `docs/guides/database-setup.md`, `database-troubleshooting.md`, `vps-postgres-config.md`, `AUTONOMOUS-IMPLEMENTATION-PLAN.md` | NEVER COPY | contain secrets |
| other skills (workflow, learning, autopilot, ai, vue, fastapi scaffolding, other brokers), agents, hooks, `settings.local.json` | SKIP | duplicate or conflict with the kit's deliver/intake |

### M9 Not covered by any legacy repo (written new)
Registration and identity (Google + WhatsApp OTP via the shared Notifier gateway, ADR-040), entitlements, billing,
referrals, admin, notifications, the audit hash chain store, the trusted clock.

## Not reused
Every legacy P&L/payoff/scenario calculator (float money, logic copied in several places); positions
exit/add/exit-all endpoints and optional `strategy_id` on orders (break ADR-002); AutoPilot auto-execution
(`execution_mode='auto'` default breaks ADR-009/ADR-017); legacy auth/users; there is no legacy registration,
entitlement, payments or admin code in any repo.

## Risks found in the legacy repos (owner actions)
- `algochanakya` is **public** and two docs files contain a real-format Kite API key and secret (file:line in the
  survey; values never copied). Owner to regenerate the secret in the Kite developer console.
- `algochanakya` recorded Upstox test fixtures contain the owner's email.
- `OptionsForOptions` (private) has a Google client secret, a Telegram bot token and a MySQL password in code.

## Broker adapter boundary (W-026, REQ-036 AC-1..AC-3, ADR-002; added 2026-09-29)
Any broker adapter copied or adapted from `algochanakya` (or written new) plugs in at exactly one point:
- It implements only the private transport `ofo.execution.send_guard._Transport.submit(request) -> broker order id`,
  passed by the caller of `submit_confirmed` (argument `submitter=`), which wraps it in a broker sink it creates
  itself; the transport is never called from anywhere else. It never receives an `Order`, a plan or a
  preparation, only a `_BrokerRequest` built by that sink. (Corrected 2026-09-29: an earlier draft said the
  transport is constructed only inside `send_guard.py`, which the code does not do.)
- The sink (`_BrokerSink`) derives every broker field from the strategy's bound `StrategyRecord` and the instrument
  catalogue: trading symbol (underlying, instrument type, expiry, strike to the one catalogue entry), side (the leg's
  side; Close uses the opposite), quantity (within the room the record and the fill ledger leave), strategy and
  version. It refuses anything else and then calls the transport.
- The only public route to the sink is `ofo.execution.partial.submit_confirmed`. A runtime test walks every `ofo`
  module and fails if any other public name returns or accepts a request, transport or sink.
- Trust boundary: this stops accidental misuse by platform code. Code running in the same process can still reach
  private names, or import a raw broker client, on purpose; that is out of scope and must be caught in review.
  The adapter must not expose any public "place order" function of its own.
