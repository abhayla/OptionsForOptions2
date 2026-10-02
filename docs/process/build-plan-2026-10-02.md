# Build plan (owner-approved 2026-10-02): end-to-end build from here, copy-first from algochanakya (map once, copy per work item)
Revised after independent review (Opus, fresh context, 2026-10-02): 5 CRITICAL, 10 MAJOR, 6 MINOR, all incorporated.

## Context
The domain layer (`backend/ofo/`, ~1,400 tests, pure stdlib, fakes only) is done for engine, scenario, rules,
versions, orders, execution gate/plan/partial, reconciliation, timeline, instruments catalogue, health, table, admin,
audit. There is no API, DB, UI or real Zerodha. Owner, 2026-10-02: never rebuild what algochanakya already has; map it
ONCE end to end so nobody searches again. Inventory: four read-only surveys of `D:\Abhay\Ventures\algochanakya` @
`bf9faf7` (backend services, backend API/models/scripts/tests, frontend, skills/docs/tooling).
Honest scope: engine + Greeks (ADR-043, legacy is float), templates (W-005/W-047) and instrument catalogue (W-006) are
already built here and are not redone. Copying still saves: frontend skeleton + components, ~1/3 of platform code, the
market-data pipeline (~3,500 lines) and broker adapter (both Zerodha-blocked), plus Kite knowledge (skill, docs).
Registration, entitlements, billing, admin, notifications exist in no legacy repo: written new.

## Governing order (ADR-030, REQ-067 AC-1/AC-5) - the review's main correction
ADR-030: "prove live data works on real input first ... then the core domain and one end-to-end vertical slice, verify
it, and only then run bounded parallel worktrees." So: no broad UI or feature build before the data proof and the slice
pass the verification gate (`spec/testing/core-invariants.md` §4). Work allowed BEFORE the Zerodha answer is limited to:
codify/map, deferred fixes, the platform base (DB, clock, audit), the instrument catalogue persistence (public list,
no login), and a frontend SKELETON only (build, shell, health page). Everything else waits for the slice.

## Rules every work item follows
- Copy per WORK ITEM (not bulk per phase: untraced copied files are dead code, core-invariants §5.8): each brief lists
  its map rows; copied files carry source repo/commit/path headers (ADR-043), are adapted to every hard rule in the
  same PR and get our own tests (legacy tests are not proof).
- Approval gate: the `deliver` skill runs only on Approved requirements (SKILL.md:4-6). Each phase lists the
  requirements you must approve first; none is built while Specified.
- Each API phase first commits its OpenAPI slice (`generate_openapi.py`, copied); the frontend builds only against it.
- Brief lines: Core/Proof first, Spec basis, `Copy from:` (map rows or `none - <why>`), Budget, run-discipline B4 items,
  `Report: evidence-table`; `check_brief.py` passes. Builder Sonnet; Opus only with `Why Opus:`; verifier fresh context.
- Layout keeps kit CI green: `backend/ofo/` stays stdlib; `backend/ofo_app/` (FastAPI, DB, repos, Alembic) imports `ofo`,
  never the reverse; `tests_app/` + `pytest-app.ini`; `frontend/`; all run by `app-tests.yml` (ADR-046 path filter).
  DB tests skip with a reason when no `TEST_DATABASE_URL`; never SQLite.
- The API capability check is the authority for entitlements (REQ-063 AC-2); route guards are UX only.
- UI verification carries desktop + mobile screenshots of every state (REQ-067 AC-4).
- Never copied: float money (`database.py:11-24`, `strategy_templates.py:62`, float schemas), optional `strategy_id`
  (`orders.py:147`, `schemas/strategies.py:184`), position exit/add/exit-all (`positions.py:254,304,354`),
  auto-execution (`autopilot.py:89,167,628`, `adjustment_engine.py:246`), retry (`order_executor.py:80`),
  TOTP/auto-login (`token_policy.py:7-36`, `platform_token_refresh.py`), multi-broker failover, stored broker
  secrets/plaintext tokens (`broker_connections.py:21`), client-side P&L (`stores/strategy.js:722-743` etc.),
  standalone order buttons (`OFOResultCard.vue:103`), advice wording (`StrategyLibraryView.vue:30` etc.), NSE scraping
  (`nse_fetcher.py`), legacy auth/JWT, the `str(exc)` error leak (`main.py:293-307`), SQLite test shims, Kite theme.

## Phases

### P0 - codify + the full map (one docs PR, Tier C) - first
- `spec/decisions/ADR-047.md` (owner 2026-10-02): copy-first, map once, copy per work item; test-DB decision (D3 below).
  `changes: "extends ADR-043"`. ADR-043 itself is not edited, so no re-pinning.
- `spec/technical-design/legacy-reuse.md` rewritten as THE map: every algochanakya module -> REQ + phase -> COPY /
  ADAPT / REFERENCE / SKIP -> change/conflict (file:line), re-pinned to `bf9faf7`; skipped groups listed.
- `CLAUDE.md`: "Copy first (ADR-047): briefs cite map rows; never search algochanakya ad hoc." Memory files for
  copy-first and for "plan -> independent review -> one approval".
- Non-code reuse that needs no build (details below): OFO ranker spec + Kite/ticker/option-chain docs into
  `docs/reference/legacy/`, `kite-quirks` + `options-math-review` skills, two path-scoped project rules.

### P0.5 - HANDOVER NEXT item 1: deferred fixes needing no decision (Tier B each)
#62 Close Partial refusal before state change, #64 quadratic reconciliation compare, #61 fixture guard on f-strings,
#65 wall-clock guard gaps, #10 items 1/3/4. (Mapped later: #43 and #45 -> P5, #29 -> P3 strategy store.)
Copy from: none - these fix our own domain code.

### P1 - platform base + trusted clock + instrument persistence (core/foundation) - buildable now
Approval gate: REQ-064 and REQ-053 are already Approved.
Core: the database, not the caller, stamps `recorded_at` AND enforces ADR-023's skew window ("a new event's own date
must be within the clock-skew window of that stamp, both ways"). Proof (W-051 step 1), run as a NON-superuser app role
locally and in CI: (a) caller-supplied past `recorded_at` -> stored DB `now()`; (b) event date outside the skew window
-> insert rejected, transaction rolled back; (c) UPDATE/DELETE -> permission denied; (d) the app role cannot disable
the trigger. If any fails, stop and re-plan.
- W-051 platform + clock (REQ-064 AC-2, Tier A, Opus: DB privilege/trigger design). Copy: `app/database.py` (ADAPT),
  `server_default=func.now()`, `app/config.py` pattern, `routes/health.py`, conftest client fixture + pytest asyncio
  settings (Postgres + savepoint rollback), `backend-tests.yml` Postgres service -> `app-tests.yml`, pinned deps
  (fastapi 0.123.5, SQLAlchemy 2.0.44, alembic 1.17.2, asyncpg 0.31.0, pydantic 2.12.5, pydantic-settings 2.12.0, httpx
  0.28.1, uvicorn 0.38.0), `generate_openapi.py`, alembic migration guard, `.pre-commit-config.yaml` (ruff,
  detect-secrets, no-.env), `ruff.toml` (reference). New: async Alembic, fresh baseline migration, safe error handler
  returning generic messages only (REQ-065 mapping waits for the W-024 decision).
- W-052 DB audit log (REQ-064, Tier A): JSONB keeping `$decimal`/`$datetime` tags, `pg_advisory_xact_lock` appends,
  separate anchor table, re-verify on load; REFUSES any event type without a declared field allowlist (REQ-063 AC-5);
  broker-payload event types stay out until W-017. Copy from: none - no hash-chained log in legacy.
- W-053 instrument catalogue persistence (REQ-053, core): our W-006 parser's output into Postgres, NFO + BFO, unique
  (exchange, token), Numeric strike/tick. Copy: `models/instruments.py` (ADAPT), instrument-master test cases.
- W-007 entitlement engine unparked as PURE ENGINE + a stamping repository only (amend W-007 affected paths, core and
  proof in the same PR). The spec examples are replayed against Postgres-stamped rows. W-008/W-009/W-011 wait for
  identity (P2b), because the trial starts at registration (ADR-023, Q88).
- Build order: W-053 is "next" (core); W-051/W-052 carry `order_override: trusted clock + audit store are the DB
  foundation W-053 and every core item persists through (owner D-1 2026-10-02)`.

### P2 - frontend skeleton (foundation) and identity (foundation)
- P2a skeleton only (Approval gate: REQ-009 nav, REQ-004 responsive). Core: browser -> Vite proxy -> our `/api/health`
  -> DB, shown in one Playwright run with screenshots. Copy: `package.json` (vue 3.5, vue-router 4.6, pinia 3, axios,
  chart.js; styling per the styling ADR), `vite.config.js` (+ proxy), `eslint.config.js` (+ vendor-host ban), `main.js`,
  `router/index.js` (structure), `services/api.js` (same-origin, httpOnly cookie), layout shell from
  `KiteLayout/KiteHeader.vue` renamed and restyled, `useToast.js`, vitest setup, Playwright config + page objects
  (mocked backend). Prerequisite: a styling/visual-identity ADR (Tailwind or not, our own look, not Zerodha's;
  REQ-005 positioning).
- P2b identity (Approval gate: REQ-012, REQ-002, REQ-003, REQ-013, REQ-014): users/accounts + Google sign-in +
  WhatsApp OTP via the shared Notifier gateway (ADR-040). Copy: `LoginView.vue` shell, `AuthCallbackView.vue` (no token
  in URL). Then W-008, W-009, W-011.

### P3 - data proof and pipeline (core) - BLOCKED on Zerodha's written answer (ADR-034, Q210)
- P3a throwaway proof script (HANDOVER NEXT 3): real login, 3 real option quotes per index, margin; plus ADR-030
  Phase-0 tests (live ticks, chain rebuild, own Greeks, stale/missing detection, reconnect, history, 100/1,000 users on
  one feed, licence). Output recorded. A failure stops everything that follows.
- P3b copy after Q204/Q205 are answered (Approval gate: REQ-048, REQ-052, REQ-054, REQ-015): ticker core (`models.py`,
  `adapter_base.py`, `pool.py` without auto-refresh, `router.py` + auth, `adapters/kite.py`, `health.py`,
  `token_policy.py` without TOTP), `market_data_base.py` + `market_data/kite_adapter.py` (user's own token),
  `rate_limiter.py`, `exceptions.py`, `option_chain_live_engine.py`, `option_chain_cache.py` (no cross-user sharing
  until ADR-034), `utils/market_hours.py` (holidays, BSE hours), `tests/factories/ticks.py`, broker tests, the recorder
  pattern for Kite fixtures (no PII). Frontend: `useWebSocket.js` + test (token off the query string), `priceService.js`
  fallback, `stores/optionchain.js`, `MarketStatusBanner`/`DataSourceBadge` -> data health. Skill
  `option-chain-debug` (adapted).

### P4 - the ADR-030 vertical slice (core/foundation) - after P3a passes
Create Strategy -> Configure Legs -> Calculate -> Save Draft -> Connect Zerodha -> Validate -> Prepare Execution Plan ->
Review -> Execute -> Confirm Broker Execution -> Reconcile -> Active Monitoring, through the existing `ofo` domain.
Approval gate: REQ-015, REQ-054, REQ-055, REQ-061, REQ-043 (others in the slice are Approved/Verified).
Added 2026-10-02 (ADR-050, owner-approved research): the broker brief carries the eight order-path safeguards - our tag
on every order with lookup on timeout (never resend); persist intent before send; websocket + verified postbacks +
polling; external orders recorded; per-key rate limits; re-login on token expiry; kill switch; Zerodha API-order rules
(market protection, 10 slices, 25 modifications) - and stays blocked until Zerodha answers Q258 (SEBI algo provider,
static IP). Instrument identity is (exchange, exchange_token) from W-056 (P1).
Copy: `brokers/base.py` + `brokers/kite_adapter.py` behind `send_guard._Transport` only (mandatory strategy_id, no public
place_order); `auth.py:60-175` callback (reference; token via the secure mechanism, never plaintext);
`utils/encryption.py` (reference; own key); `orders.py` margins/import-positions (reference, REQ-055/061; #43 placeholders
and #45 price check resolved here); `models/autopilot.py` order/batch tables (reference: NOT NULL strategy_id, Numeric);
frontend `StrategyBuilderView` (split, backend numbers only), `PayoffChart`/`PnLCell`/`SummaryCards`, `StrategyLegRow`
(no P&L math), `strategy-table.css`, `stores/strategy.js` (no client P&L, no basket call; #29 fixed here), `KiteSettings.vue`,
`BasketOrderModal` -> execution-plan review. Ends with the verification gate (domain, calculations, broker, execution,
reconciliation, UI screenshots).

### P5 - bounded parallel features (feature layer) - only after the P4 gate passes
Each needs its requirements approved first (REQ-024, REQ-025, REQ-026, REQ-027, REQ-029/030/031, REQ-037, REQ-041/042,
REQ-044-047, REQ-051, REQ-062, REQ-068/069, REQ-071, REQ-017-023, REQ-008). Copy per item: strategy wizard + template
schemas (REQ-024/069, no deploy), optionchain find-by-delta/premium + options routes (REQ-027/029), `OptionChainView`,
`StrikeFinder` (logic in the backend), `StrategyLibraryView` (wording), `seed_strategies.py` (fill only missing
templates), `eod_option_snapshot.py` (REQ-051), `PositionsView` (strategy-scoped), monitoring components (reworded),
`DashboardView`. Reference only: condition/adjustment/monitor engines, ConditionBuilder, adjustment wizards. OFO ranker:
reference only; any ranking rule ("top 3 unique P/L", filters) is put to you as a SPEC CHANGE question, because REQ-069
asks for curated Conservative/Balanced/Aggressive sets.

### P6 - release gate and first deploy (owner-authorised)
Hosting decision (open question "final cloud/stack"), staging windows, Redis, TLS/domain, backups, `releases/R-001.md`
with rollback written first, pre-deploy brief; REQ-066 compliance gates, Q211 legal review before go-live, REQ-067
AC-7/AC-8, core-invariants §4 security/vulnerability/secret scans. No deploy without your explicit go.

## Changes made while building P0 (2026-10-02)
- No `kite-quirks` skill: every listed fact is already in the user-level `zerodha-expert` skill with kite.trade links
  and a "Last verified" table; a copy would duplicate it. The map names that skill as the Kite source.
- `token-auto-refresh` rule moved to P3b (it governs `token_policy.py`, which does not exist yet).
- ADR-047 records copy-first only; the test-database decision (D-3) waits for the owner's explicit statement at P1.
- The legacy greeks reviewer's 7% rate / 252 days were replaced by the spec's values in `options-math-review`.

## Non-code reuse (from the skills/docs/tooling survey)
- OFO ranker spec: algochanakya `docs/features/ofo/REQUIREMENTS.md`, `README.md`, `docs/plans/ofo-implementation-plan.md`
  -> `docs/reference/legacy/ofo/` (reference for P5).
- Skills: the user-level `zerodha-expert` skill is used as is (ignore its AlgoChanakya section). New
  `.claude/skills/kite-quirks/` with each fact citing its source and checked date (REQ-067 AC-9): token expiry ~6 AM and
  NOT_REFRESHABLE, `token api_key:access_token` header, WS int32 paise vs REST rupees, 3000 tokens x 3 connections,
  `NFO:`/`BFO:` prefixes, ~80 MB CSV, no chain/greeks API, 500 quotes per call, 60-day minute history, no webhooks, 10
  req/s, index tokens. `options-greeks-reviewer` -> `.claude/skills/options-math-review/`. `option-chain-debug` in P3b.
- Rules: `decimal-not-float-prices`, `token-auto-refresh` -> `.claude/rules/project/` with `paths:` (budget-safe).
- Hooks/tooling: `secret-scanner.py` patterns -> project PreToolUse hook via `.claude/project/hooks.json` +
  `kit_settings.py`, with tests; pre-commit in W-051.
- Docs -> `docs/reference/legacy/` after a secret scrub: zerodha-oauth-login-issues (verify 4 key-like hits),
  authentication.md (P4); TICKER-DESIGN-SPEC, websocket.md, option-chain-performance-spec, cmp-fallback (P3). Never
  copied: database-setup, database-troubleshooting, vps-postgres-config (secrets).
- Not reused: legacy workflow/learning skills, agents and hooks (clash with the kit's deliver/intake), autopilot/ai
  scaffolding, `settings.local.json`.

## Owner decisions this plan needs (asked one at a time, when the phase starts)
- D-1 copy-first (given). D-2 layers (merged #99).
- D-3 test DB on VPS 103.118.16.189: you chose it, but the plan needs your EXPLICIT statement that it serves no live
  traffic. Then a separate `ofo_test` database and an app role with NO access to other databases on it (algochanakya's
  Postgres may live there). No Docker on the laptop (your rule); CI uses its own service.
- D-4 clock-skew value for ADR-023 (the spec names the window but no number): P1.
- D-5 W-024 (REQ-065 error messages) unpark with the recommended allowlist design, or keep generic messages: P1/P2.
- D-6 styling/visual-identity ADR (Tailwind or not, our own look): before P2a.
- D-7 requirement approvals listed in each phase's gate.
- D-8 Q204/Q205 (Zerodha feed model) and Zerodha's written answer: P3 (external).
- D-9 hosting and the release window: P6.
- Credentials only you hold: a VPS Postgres role (checked in `GLOBAL.env` first; algochanakya's `.env` is never read).
- Not blocking: W-048/W-049 builder trees hold uncommitted work; rotate the public-repo secrets in algochanakya.

## Verification
- Each phase's core proof recorded as evidence before its other items merge; the P4 verification gate before P5.
- Kit `ci_local.py` all PASS/SKIP on every push (domain suite 1,399+); `app-tests.yml` green, its DB proof run as a
  non-superuser role.
- Locally: `python -m pytest -c pytest-app.ini tests_app` against the tunnel DB; `npm run test` + Playwright with screenshots.
- `trace_check.py` / `build_order.py --may-start` before each item; provenance header on every copied file.
