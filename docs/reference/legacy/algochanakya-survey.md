<!-- Read-only survey, 2026-09-29, by an independent reader in the owner session. Secret VALUES were never copied; only file:line pointers. -->

# Legacy survey: algochanakya (read-only, 2026-09-29)

## 1. Identity

| Item | Value |
|---|---|
| Path / URL | `D:\Abhay\Ventures\algochanakya`, origin `github.com/abhayla/algochanakya` — **PUBLIC repo, no LICENSE file** (`gh repo view`) |
| Branches | Default branch `main`. Local checkout on `chore/plugins-first-migration` (last commit 2026-07-13, 7 behind / 5 ahead of origin/main). **No difference in `backend/app` or `frontend/src` between HEAD and origin/main** (`git diff --stat` empty) — the survey applies to main. |
| origin/main head | `2a868db` 2026-08-27 "rules: globs: -> paths:" (tooling only). Last app-code commit on main: 2026-07-01 (#60). First commit 2025-12-02; 485 commits on main. Top 5: 2a868db (rules), 3aff089 (CI allure), 7b128d8 (CI minutes), f30eda0 (PR gate), 3161ba7 (playwright bump). |
| Backend | Python 3.13, FastAPI 0.123.5, Starlette 0.50, Pydantic 2.12, SQLAlchemy 2.0.44 async + asyncpg 0.31, Alembic 1.17.2, PostgreSQL, Redis (redis-py 7.1), APScheduler 3.11, numpy 2.3.5 / scipy 1.16 / pandas 3.0.1 / scikit-learn 1.6.1, kiteconnect 5.0.1, smartapi-python 1.5.5, upstox-totp 1.0.8, PyJWT + python-jose, cryptography (Fernet), anthropic 0.39 |
| Frontend | Vue 3.5 (plain JS SFCs, no TypeScript), Vite 7.2, Pinia 3, vue-router 4.6, Tailwind 4.1, Chart.js 4.5, axios |
| Tests | pytest (SQLite in-memory with dialect shims), Vitest 2.1 + happy-dom, Playwright 1.61 E2E, Allure |
| Size (tracked, excl. node_modules/venv/build) | 1,978 tracked files. App code: **Python 85,288 LOC** (`backend/app`), **Vue 65,655 LOC + JS 8,963 LOC** (`frontend/src`). Tests: backend 210 files / 65,436 LOC, frontend 11 files / 4,197 LOC, E2E 202 files / 47,143 LOC. Plus 929 `.md` files (mostly Claude tooling/docs). |
| Test count | ~2,973 backend `def test_`, ~254 Vitest cases, ~1,582 Playwright `test(` (static count of source, not executed) |
| Do tests run? | **Unverified locally (not run, per brief). CI: workflow "Backend Tests" has 238 runs on GitHub — 232 failure, 6 cancelled, 0 success.** Latest failure (run 33396805388, 2026-08-31) is a dependency install error (`numpy==2.5.2` needs Python >=3.12 on the runner's Python). Every main-branch run since 2026-03-24 is red for both Backend and E2E. No local test report exists (`backend/test-evidence/…` holds only screenshots). |

Architecture: every broker behind two adapter hierarchies — `BrokerAdapter` (orders; `backend/app/services/brokers/base.py:231`) and `MarketDataBrokerAdapter` (data; `services/brokers/market_data/market_data_base.py`), plus a WebSocket `TickerAdapter` layer (`services/brokers/market_data/ticker/`). 6 brokers: Zerodha, AngelOne, Upstox, Dhan, Fyers, Paytm. Browser talks only to the backend (REST + backend WebSocket); no vendor URL appears in `frontend/src` (grep).

## 2 + 3. Feature inventory and verdicts

Legend: COPY / ADAPT / REFERENCE / SKIP. "HR" = breaks a hard rule of OptionsForOptions2.

### A. Broker adapter interface (orders) — REQ-053, REQ-054, REQ-057
- Files: `services/brokers/base.py` (503 LOC): `UnifiedOrder`, `UnifiedPosition`, `UnifiedQuote` dataclasses (all money `Decimal`, :96-207), enums `OrderSide/OrderType/ProductType/OrderStatus`, `BrokerCapabilities`, abstract `BrokerAdapter` (place/modify/cancel/get order(s), positions, ltp/quote, margins, profile, instruments). Adapter selection via `services/brokers/` registry (294 LOC).
- Quality: Decimal money at the interface (good). Defects: `place_basket_order` default (base.py:358) swallows each leg's exception into REJECTED and continues — a partial basket with no stop; `get_kite_client()` escape hatch (base.py:492) leaks the SDK; Kite adapter overrides `place_basket_order` with a **different signature** (dicts, kite_adapter.py:276) so the interface is not honoured; no margin-preview method (`basket_order_margins`/`order_margins` absent — grep 0 hits); no strategy id anywhere in the order model.
- Verdict: **ADAPT.** Copy the unified dataclasses + enums + the ABC shape as the seed for REQ-054; add `strategy_id` as a required field (ADR-002), add margin preview (REQ-055), remove `get_kite_client`, make basket placement return per-leg submitted/rejected without converting "order id returned" into success (ADR-017), and stop at the first rejection per the execution plan rules (REQ-058).

### B. Zerodha (Kite) order adapter — REQ-054, REQ-057, REQ-058
- Files: `services/brokers/kite_adapter.py` (584 LOC).
- Quality: converts Kite responses to Decimal via `Decimal(str(x))` (:365-517, good); sends `float(order.price)` to the SDK (:163, :218, :326 — acceptable at the SDK boundary only). Synchronous `kiteconnect` calls made inside `async def` (blocks the event loop). `place_basket_order` labels a leg `"success": True` as soon as an order id comes back (:333) — **HR: submitted != executed (ADR-017)** if a caller reads it as filled. Product hard-coded `NRML` (:321). No retry (good).
- Verdict: **ADAPT** — the Kite field mapping (`_convert_kite_order` :351, `_convert_kite_position` :402, quote depth parsing :482) is the reusable part; rewrite placement to return SUBMITTED status and move SDK calls to a thread.

### C. Other broker adapters (AngelOne, Upstox, Dhan, Fyers, Paytm) — REQ-054 (later)
- Files: `services/brokers/{angelone,upstox_order,dhan_order,fyers_order,paytm_order}_adapter.py` (437-493 LOC each), market-data adapters `services/brokers/market_data/*_adapter.py` (440-841 LOC), ticker adapters `ticker/adapters/*.py` (319-910 LOC). None override `place_basket_order`, so the positions exit route (which passes dicts) only works on Kite. ROADMAP (2026-03-20) says Fyers/Paytm/Dhan flows were never tested with real accounts.
- Verdict: **SKIP for V1** (ADR-001 V1 broker = Zerodha only). Keep as **REFERENCE** when broker #2 is added; they prove the seam shape.

### D. Zerodha login / session / token — REQ-015, REQ-014, REQ-063
- Files: `api/routes/auth.py:34` (`/zerodha/login`), `:60-175` (`/zerodha/callback`: `generate_session`, `profile()`, `resolve_or_create_user`, writes `BrokerConnection`), `:227` validate, `:329` disconnect; `models/broker_connections.py`; `utils/encryption.py`; `api/routes/zerodha_credentials.py`.
- Quality / HR:
  - Zerodha login **is** the user's identity (user auto-created from Kite profile, auth.py:103). OptionsForOptions2 has separate registration then a Zerodha connection with Client ID binding (REQ-012, REQ-014, ADR-021/022) — model mismatch.
  - Kite `access_token` stored **plaintext** (`broker_connections.access_token`, comment "encrypted in production" at models/broker_connections.py:20 but the callback writes it raw, auth.py:126/135) — **HR (ADR-029 security boundaries)**.
  - Platform JWT passed in the redirect **URL query string** (auth.py:163) and exception text echoed into the redirect URL (auth.py:172); JWT kept in `localStorage` (frontend `stores/auth.js:22,62`).
  - Fernet key for stored broker secrets is derived from `JWT_SECRET` (utils/encryption.py:23-33) — one secret for two jobs.
- Verdict: **REFERENCE.** The 30-line happy path (request_token → generate_session → profile → store) is correct Kite usage; rewrite with encrypted token storage, Client ID binding, daily-expiry handling (ADR-020), and cookie/session transport.

### E. Market data + WebSocket ticker — REQ-048, REQ-049, REQ-050, REQ-052
- Files: `ticker/models.py` (`NormalizedTick`, Decimal prices :36-58), `ticker/adapter_base.py`, `ticker/pool.py` (ref-counted one-connection-per-broker `TickerPool`), `ticker/router.py` (fan-out to users), `ticker/failover.py`, `ticker/health.py` (334 LOC), `ticker/adapters/kite.py` (KiteTicker threaded → asyncio bridge, reconnect callback :90), `websocket/manager.py` (520 LOC), `services/options/option_chain_cache.py` (Redis cache with request coalescing, `get_or_compute` :89).
- Quality: this is the best-engineered part — shared computation, ref counting, health, failover, Decimal ticks. Concerns: `to_dict` converts Decimal to float for transport (models.py:61-68, fine for display only); **silent failover** between brokers and to EOD snapshots (optionchain.py:50-220) conflicts with ADR-015 (stale/unavailable data must be shown, per-strategy monitoring status); **platform-level tokens for AngelOne/Upstox are auto-refreshed with stored PIN + TOTP secret and written back into `.env`** (`platform_token_refresh.py:1-200`, `upstox-totp` "handles Cloudflare bot detection" :76) — automated vendor login, a licensing/ToS risk under REQ-052 / ADR-014; option chain computed from **one user's Zerodha session is cached under (underlying, expiry) and served to other users** (optionchain.py:494-560 + cache key) — directly the question ADR-034 says must be asked of Zerodha in writing first.
- Verdict: **ADAPT** — copy `NormalizedTick`, `TickerAdapter` base, `TickerPool`/`TickerRouter`, health and the Redis coalescing cache as the pipeline skeleton; remove multi-vendor silent failover and the TOTP auto-login; add explicit data-health states. Do not ship the shared-user-token behaviour until ADR-034's written answer exists.

### F. Option chain — REQ-029, REQ-030, REQ-031
- Files: `api/routes/optionchain.py` (≈1,290 LOC; `/chain` :1110, OI analysis :1169, find-by-delta :1204, find-by-premium :1246; **inline** `calculate_iv` :222, `calculate_greeks` :274, `calculate_max_pain` :323), `services/option_chain_service.py` (458), `services/options/option_chain_live_engine.py`, `vectorized_greeks.py` (numpy IV+Greeks batch), `eod_snapshot_service.py`, `option_chain_prefetch.py`, `startup_chain_warmup.py`; frontend `views/OptionChainView.vue` (1,240 LOC), `stores/optionchain.js` (550), `components/optionchain/StrikeFinder.vue`.
- Quality: feature-rich (PCR, max pain, OI, Greeks, strike finder by delta/premium — maps to REQ-027 strike modes). A second copy of Black-Scholes lives in the route file (**HR: one calculation engine, ADR-008**). Validates underlying against the hard-coded `LOT_SIZES` dict (:1128) instead of the instrument master. Instrument master defaults to NFO only (`services/instrument_master.py:52`) — SENSEX options live on BFO (REQ-001 needs SENSEX). Tests exist (`backend/tests/backend/options/test_option_chain_ltp_zero.py`, `test_phase2_vectorized_greeks.py`, `test_phase3_live_engine.py`).
- Verdict: **ADAPT** — `vectorized_greeks.py` (numpy IV/Greeks, 225 LOC) is a good candidate for the "Estimated Now" / Greeks part of the one engine; the chain assembly + max pain/PCR logic is **REFERENCE**; the Vue view is **REFERENCE** for layout (it does not carry the leg-selection/import semantics of REQ-030).

### G. P&L / payoff / scenario engine — REQ-032, REQ-033, REQ-034, REQ-035
- Files: `services/options/pnl_calculator.py` (424; `calculate_pnl_grid` :73, intrinsic :185, Black-Scholes :202, breakeven interpolation :245), `services/options/payoff_calculator.py` (477, AutoPilot), `services/options/greeks_calculator.py` (698), `services/ofo_calculator.py` (697), `services/autopilot/whatif_simulator.py` (630); Black-Scholes/norm_cdf/intrinsic re-implemented in **at least 5 more files** (grep: optionchain route, adjustment_engine, 3 AI services).
- Quality / HR:
  - **Float money everywhere** — `pnl_calculator.py` 26 `float` vs 1 `Decimal`; `payoff_calculator.py` 35 vs 1 — **HR ADR-008 / scenario-calculations §5** (the spec's own measured example: float gives `-322.4999999999998`).
  - **Many engines**, not one — **HR ADR-008**.
  - Max profit / max loss = max/min over the sampled grid (pnl_calculator.py:165-166), so "unlimited" is never detected — contradicts §3 "computed from the payoff".
  - Default lot size 75 inside the engine (:120) and `get_lot_size` falls back to **25** for unknown underlyings (`constants/trading.py:105`); lot sizes typed in a dict "Updated November 2024" (:28) — spec says lot size always comes from the instrument master.
  - Flat 15% default volatility for "current" mode (:79).
  - The expiry formula itself matches spec §1 (`(intrinsic − entry) × qty × ±1`, :148) and uses entry price, not LTP (matches ADR-035).
- Verdict: **REFERENCE only.** Rewrite the engine in Decimal per `scenario-calculations.md`, with the Iron Condor golden test first; the legacy `backend/tests/backend/options/test_pnl_calculator.py` can be mined for extra cases.

### H. Strategy builder, strategy model and templates — REQ-024, REQ-028, REQ-038, REQ-069, REQ-070
- Files: `models/strategies.py` (Strategy + StrategyLeg; `DECIMAL(10,2)` strike/entry/exit :42-46, `share_code`), `api/routes/strategy.py` (CRUD, `/calculate` :552, share :660), `models/strategy_templates.py`, `api/routes/strategy_wizard.py`, **`backend/scripts/seed_strategies.py` (1,312 LOC, 22 templates with `legs_config`, outlook, IV preference, risk, margin text)**, `services/autopilot/template_service.py` (8 system templates :395-657); frontend `views/StrategyBuilderView.vue` (2,094 LOC), `stores/strategy.js` (969), `components/strategy/*` (wizard, compare, deploy, details modals).
- Quality: builder asks the backend for the P&L grid (no browser-side math — good). Template leg offsets are fixed index points (`strike_offset: 100`, seed_strategies.py:29-30) — not step-aware for SENSEX; template model stores max profit/loss as free text strings (`strategy_templates.py`), not computed. Wording: "AI-powered recommendations" (strategy_wizard.py:4), "Recommended Strategies" (`components/strategy/StrategyWizardModal.vue:30`) — **HR ADR-003** ("Strategies you could consider"). No versions / definition-vs-live-state split (REQ-038, REQ-039).
- Verdict: templates catalogue **ADAPT** (the 22-template list with leg shapes and outlook tags is useful seed data for REQ-028 — convert offsets to strike-step multiples, drop the text max-profit fields, re-word); strategy model + builder UI **REFERENCE**.

### I. Orders / execution — REQ-036, REQ-056, REQ-057, REQ-058, REQ-059
- Files: `api/routes/orders.py` (`/basket` :88, `/import-positions` :262, cancel :431, ltp/quote/ohlc), `services/autopilot/order_executor.py` (1,128).
- HR:
  - `BasketOrderRequest.strategy_id` is **Optional** (`schemas/strategies.py:184`) — orders without a strategy — **HR ADR-002**.
  - Order executor docstring advertises "Retry on failure" (order_executor.py:80); no retry loop found in the code (grep), but the claim must not be carried over — **ADR-017 no automatic retry**.
  - Live orders are recorded `status="placed"` (≈:727) — correct submitted≠executed pattern; paper orders recorded as "complete" at LTP.
  - Expiry calculation hard-codes Thursday weekly / last-Thursday monthly (order_executor.py:922-965) — NSE moved index expiries; must come from the instrument master.
  - No pre-execution margin check, no reconciliation gate (grep "reconcil" in services/api: 0 hits) — REQ-055, REQ-060 absent.
- Verdict: **REFERENCE** (market-snapshot-at-order capture, `capture_market_snapshot` :105, and the per-order audit row are worth copying as ideas for REQ-040/REQ-064).

### J. Positions screen — REQ-044, REQ-061
- Files: `api/routes/positions.py` (`/` :94, `/exit` :254, `/add` :304, `/exit-all` :354, `/grouped` :436, `/annotated` :487); `views/PositionsView.vue` (1,306), `stores/positions.js`.
- HR: `/exit` and `/add` place an arbitrary opposite/added order for any tradingsymbol (positions.py:263-270) and `/exit-all` sends MARKET orders for every position — **standalone order entry, HR ADR-002**; P&L filters in the store use float numbers.
- Verdict: **REFERENCE** for the grouping/annotation idea (grouping broker positions by underlying/expiry is close to REQ-061 "existing positions on connect"); the exit/add endpoints are **SKIP**.

### K. Monitoring, rules, adjustments, kill switch (AutoPilot) — REQ-041..REQ-047, REQ-071
- Files: `services/autopilot/` — `strategy_monitor.py` (1,876), `condition_engine.py` (1,096), `adjustment_engine.py` (1,388), `suggestion_engine.py` (933), `kill_switch.py` (410), `confirmation_service.py` (529), `delta_band_service.py`, `dte_zone_service.py`, `trailing_stop.py`, `whatif_simulator.py`, `trade_journal.py`; `models/autopilot.py` (1,130); frontend `stores/autopilot.js` (2,166). 60 backend test files under `backend/tests/backend/autopilot`. Feature flag OFF by default (`frontend/src/config/features.js`).
- HR: adjustment rules default to **`execution_mode = 'auto'`** (adjustment_engine.py:246) — automatic order placement; V1 automation is Alert + Prepare Orders only (**ADR-009, REQ-042**). All float (condition_engine 46 `float`, adjustment_engine 26, strategy_monitor 28).
- Verdict: **REFERENCE.** The condition vocabulary (delta bands, DTE zones, premium decay, trailing stop, what-if) is a good checklist for REQ-041/045/047; the confirmation-service pattern maps to "Prepare Orders"; do not copy code (float, auto execution, 1–2k-line files).

### L. Auth / users — REQ-012, REQ-013
- `models/users.py` has id, first_name, email, created_at, last_login only; no password, no email verification, no roles (grep "password|bcrypt" in routes/utils: 0 hits). Users exist only via broker login.
- Verdict: **SKIP** (nothing to reuse for the registration/identity layers).

### M. Subscriptions / payments / entitlement / admin — REQ-017..REQ-023, REQ-020
- grep `razorpay|stripe|subscription_plan|entitlement` in backend/app + frontend/src: **0 hits**. No admin role model.
- Verdict: **SKIP (absent).**

### N. Other modules
- AI regime/ML (`services/ai/*`, `api/v1/ai/*`), Watchlist, OFO "best combinations" ranker (`services/ofo_calculator.py` — "ranks by maximum profit", advice-like, HR ADR-003): **SKIP** (not in V1 spec).
- `services/legacy/`, `services/deprecated/`: dead code by its own README — **SKIP**.
- Reusable test fixtures: `backend/tests/fixtures/recorded/` holds recorded broker responses — **REFERENCE only**, they contain personal data (see §4).

## 4. Risks

- **Secrets committed in a PUBLIC repo (values not reproduced here):**
  - `docs/guides/database-setup.md:84-85` and `docs/features/watchlist/README.md:182-183` — a Kite Connect API key and API secret in plain text. They do **not** equal the values in the local `backend/.env` (compared in-shell without printing), so they may be an older/rotated app — **unverified whether still live; owner should revoke that Kite app/secret regardless**, since git history keeps them.
  - `docs/guides/database-troubleshooting.md:97` — a Postgres password; `scripts/debug/test_postgres_detailed.py:17,25` — password literals.
  - `frontend/.env.production` is tracked (content not inspected for values; no KEY/SECRET/PASSWORD names matched).
  - `backend/.env` and `frontend/.env.local` exist locally and are git-ignored (`git check-ignore`) — fine.
- **Personal data in the public repo:** the owner's email address appears in `backend/tests/fixtures/recorded/upstox/get_profile.json` and `raw_v2_profile.json` (recorded broker profile), and `5W-PRINCIPLES.md`; `backend/tests/fixtures/real_responses.py` also matched a client-id/email pattern. Do not copy these fixtures.
- **Licence:** the repo has no LICENSE (owner's own code, so copying into the owner's new repo is fine). No third-party licence headers found in `backend/app` or `frontend/src` (grep copyright/MIT/Apache: 0 hits). Dependency licences not audited; `upstox-totp` automates a broker login flow — a ToS risk, not a licence one.
- **Broker/vendor ToS:** platform-level TOTP auto-login for AngelOne/Upstox and serving one user's Kite data to others (see §E) — must not be carried over before ADR-034's written answer.
- **Quality debt carried by copying:** CI has never passed (0/238 Backend Tests runs); whatever is copied must be re-tested in the new repo from scratch, not trusted because tests exist.

## Top reuse candidates (ranked)

1. `ticker/models.py` NormalizedTick + `ticker/adapter_base.py` + `ticker/pool.py` + `ticker/router.py` — ADAPT (REQ-048/050)
2. `services/brokers/base.py` unified order/position/quote dataclasses + BrokerAdapter ABC — ADAPT (REQ-054; add strategy_id, margin preview)
3. `ticker/adapters/kite.py` KiteTicker→asyncio bridge — ADAPT (REQ-048)
4. `kite_adapter.py` Kite→Unified field converters (`_convert_kite_order/_position`, quote depth) — ADAPT (REQ-054/060)
5. `services/options/option_chain_cache.py` Redis cache + request coalescing — COPY/ADAPT (REQ-050)
6. `services/options/vectorized_greeks.py` numpy IV + Greeks batch — ADAPT into the one engine's "Estimated Now"/Greeks (REQ-032/034), outputs rounded to Decimal at the boundary
7. `backend/scripts/seed_strategies.py` 22-template catalogue — ADAPT (REQ-028; step-aware offsets, reworded)
8. `ticker/health.py` + `ticker/token_policy.py` — ADAPT (REQ-049 data health; drop auto-login)
9. `auth.py:60-175` Kite OAuth happy path — REFERENCE (REQ-015)
10. `services/instrument_master.py` instrument download/upsert with lot_size/tick_size — ADAPT (REQ-053; add BFO for SENSEX, make it the only lot-size source)

Explicitly not reusable: every P&L/payoff calculator (float, many copies), positions exit/add/exit-all, AutoPilot auto-execution, auth/users, OFO ranker.
