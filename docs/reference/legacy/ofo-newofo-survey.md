<!-- Read-only survey, 2026-09-29, by an independent reader in the owner session. Secret VALUES were never copied; only file:line pointers. -->

# Legacy code survey: OFO and NewOFO (read-only, github.com/abhayla)

Surveyed 2026-09-29. Both shallow-cloned (`--depth 50`) read-only into the scratchpad; never cloned into
`D:\Abhay\Ventures`. Checkout required `git -c core.protectNTFS=false checkout HEAD` because both repos carry
Windows `:Zone.Identifier` junk files (colon in filename, invalid on Windows) — two files skipped, harmless,
not code.

Note on the brief's target: the brief text says "New project = `...OptionsForOptions2-spec-audit`" but the loaded
CLAUDE.md and repo state (`D:\Abhay\Ventures\OptionsForOptions2`, 71 requirements, 32 ADRs, no code, no `tests/`)
is what actually exists on disk. Judged fit against that spec/ADR set as the CLAUDE.md instructs.

## 0. How OFO, NewOFO and algochanakya relate (commit history / README / folder layout only, per instruction — not surveyed in depth)

| Repo | Created→last push | Commits | Stack | State |
|---|---|---|---|---|
| **NewOFO** | 2025-07-20 → 2025-07-25 (5 days) | 37 | Node/Express + TS, React 18 + Zustand, no DB/ORM | Last commit literally "Closing this temporarily"; `.backup`/`.old` files left in tree (`marketDataService.ts.backup`, `OptionChainPage.tsx.old`, `auth.ts.backup`) — abandoned mid-refactor |
| **OFO** | 2025-07-25 → 2025-08-02 (8 days) | 88 (in this depth-50 view) | Node/Express + TS, React 18 + Redux Toolkit, Prisma+PostgreSQL, Redis, Socket.io | Started the day NewOFO stopped — reads as a restart of the same idea in the same stack, narrower scope (holdings/brokers only), better engineered |
| **algochanakya** | 2025-12-02 → 2026-08-31 (9 months, still pushed to last month) | many (not counted, per instruction) | **Different stack**: Python 3.13 FastAPI backend + Vue 3/Pinia frontend, PostgreSQL+Redis on a VPS, multi-broker abstraction for 6 brokers (Zerodha/AngelOne/Upstox/Fyers/Dhan/Paytm), `docs/decisions/` (ADRs), `docs/api/` OpenAPI, Playwright E2E + pytest + Vitest | Actively maintained for 9 months, README describes "Options Trading Platform (like Sensibull)" — a full rewrite in a different language/framework, far more complete (dedicated docs tree, ADRs, real test pyramid) |

**Verdict: algochanakya is the newest and by far the most complete** of the three — it superseded both TS
prototypes roughly 4 months after OFO stopped, in a different stack (Python/FastAPI + Vue, not Node/React), and
has 9 months of continuous work vs. OFO/NewOFO's combined ~2 weeks. It was flagged as "survey separately" and
was NOT code-surveyed here (only README/metadata read via `gh api`), so no COPY/ADAPT verdicts are given for it
below — but any reuse decision should look there FIRST, not at OFO/NewOFO, given its stack maturity. OFO and
NewOFO are two short, abandoned TypeScript spikes of the same idea; NewOFO explicitly says "closing this
temporarily" and was picked back up as OFO days later, then OFO itself stopped after 8 days.

---

## 1. Identity

### OFO — https://github.com/abhayla/OFO
- Last commit (in this shallow view): `ebc5cde` 2025-08-02 "Merge pull request #8 from abhayla/test/holdings-debug"
- First commit visible: `05302e4` 2025-07-25
- Stack: Node.js + Express 4.19 + TypeScript 5, `kiteconnect` SDK ^4.0.3, Prisma 6.13 + PostgreSQL, Redis 4.6 (`redis` client), Socket.io 4.7, Winston logging, Joi validation, Helmet, express-rate-limit. Frontend: React 18.3 + Redux Toolkit 2.2 + redux-persist, ag-grid-community/react 31.3, Vite, Tailwind 3.4, react-router-dom 6.23, Cypress 13.12 + Jest 29 (frontend), Jest 29 (backend).
- Size (excluding node_modules/build): backend `src/` 12,614 LOC (.ts), frontend `src/` 10,386 LOC (.ts/.tsx) — **~23,000 LOC total**.
- Tests: 12 test files found (`backend/src/__tests__/*.test.ts` ×8, `backend/tests/unit/*` ×2, `frontend/src/__tests__/holdingsSlice.test.ts`, `frontend/tests/e2e/holdings-mcp.spec.ts`). Did not run them (no install/execute per rules); test scripts exist (`jest`, `cypress run`) and reference real source files, so they look wired, not stubs.
- DB: one Prisma model, `Holdings` (`backend/prisma/schema.prisma`) — `avg_cost`/`ltp` are `Decimal @db.Decimal(15,2)`, correctly NOT float. No models for strategies, orders, positions, or users — DB usage is minimal (holdings snapshot only).

### NewOFO — https://github.com/abhayla/NewOFO
- Last commit (in this shallow view): `8b2ba28` 2025-07-25 "Closing this temporarily"
- First commit visible: `e64de1c` 2025-07-20 "🚀 Initial release v0.1.0"
- Stack: Node.js + Express 4.18 + TypeScript 5, no broker SDK (raw `axios`/`cheerio` calls), `express-session` + `connect-redis` + `ioredis`, `googleapis` (Google OAuth), `bcryptjs`, `jsonwebtoken`, `node-cron`. **No ORM/DB migrations anywhere in the repo** — no Prisma/Sequelize/TypeORM, no schema file. Frontend: React 18.2 + **Zustand** (not Redux), Vite, Tailwind, recharts, no test libraries in `package.json` at all.
- Size: backend `src/` 8,113 LOC, frontend `src/` 6,810 LOC — **~15,000 LOC total**.
- Tests: **zero** test files (`*.test.*`/`*.spec.*` grep returned nothing outside node_modules; only a `test-grok/` folder of an OAuth experiment). Test scripts don't even exist in `package.json`.
- Debris in tree: `auth.ts.backup`, `authNew.ts` (parallel/duplicate of `auth.ts`), `marketDataService.ts.backup`, `OptionChainPage.tsx.old` — signs of an unstable, mid-rewrite codebase, not abandoned deliberately clean.

---

## 2. Feature inventory

| Module | OFO | NewOFO |
|---|---|---|
| **Option chain** | `frontend/src/components/OptionChain.tsx`, `components/testpage/OptionChainGrid.tsx`, `store/slices/optionChainSlice.ts` — wired into a `TestPage`, not a real product page. Backend has no dedicated option-chain route (only `brokers/*/getOptionChain()` on the broker interface). | `frontend/src/pages/OptionChainPage.tsx` (266 lines, routed at `/option-chain`) + `OptionChainTable.tsx`, `NSEStyleOptionTable.tsx`, `SimpleOptionTable.tsx`, `ExpirySelector.tsx`, `FilterPanel.tsx` — a real, routed page with several table variants. Backend: `routes/market.ts`, `services/marketDataService.ts`, `services/nseIndiaAdapter.ts`, `services/freeMarketDataService.ts` (NSE scrape via `cheerio`, not just broker API). Maps loosely to REQ around option-chain display. |
| **Strategy builder / templates** | **None.** No route, no page, no slice for strategies. | `frontend/src/pages/StrategyBuilderPage.tsx` (66 lines, routed at `/strategy-builder`) — **a "Coming Soon" placeholder**: static cards listing "Iron Condor, Butterfly, Straddle…", "P&L Analysis", "Greeks Analysis" as *future* features. No logic. Unchanged since the initial commit. |
| **Payoff / scenario P&L / Greeks engine** | **None found anywhere in the repo** — grep for delta/gamma/theta/vega/blackscholes/payoff across `backend/src` + `frontend/src` hits only type definitions and mock-data generator field names (`MockDataGenerator.ts`), never a real formula. | **None found anywhere in the repo** either — same grep result: zero hits for any Greeks/payoff math; "Greeks" appears only as a label in the StrategyBuilderPage placeholder card and in mock/table column definitions. |
| **Positions** | No positions page/route beyond `BrokerInterface.getPositions()` (interface method only; check per-broker impl before reuse). | `frontend/src/pages/PositionPage.tsx` (206 lines, routed) + `routes/portfolio.ts` — a real page reading live portfolio data, mentions Greeks/delta as display columns (not computed here, presumably passed through from broker). |
| **Orders / execution** | **None.** No order routes/pages in either repo — neither project reached order placement. | **None.** Same — no order placement code in either repo. |
| **Broker adapters** | Strong: `backend/src/brokers/base/{BrokerInterface.ts, BrokerTypes.ts, BrokerErrors.ts}` — a real abstract class (`BrokerInterface extends EventEmitter`) with auth/data/WebSocket/portfolio method contracts; `brokers/zerodha/{ZerodhaAuth.ts, ZerodhaBroker.ts (720 lines), ZerodhaConfig.ts, ZerodhaWebSocket.ts (618 lines)}`; `brokers/stubs/{StubBroker.ts, ZerodhaStub.ts, MockDataGenerator.ts, RateLimiter.ts}` for a mock broker; `services/BrokerManager.ts` orchestrates multiple broker instances. Comments/DB reference angelone/upstox as planned but only Zerodha is implemented. | Weak/ad hoc: `services/kiteService.ts` (Zerodha), `services/angelOneService.ts` (AngelOne — present but unverified depth), `services/nseIndiaAdapter.ts`, `services/freeMarketDataService.ts` — no shared interface/abstract class; each service is its own shape, called directly from routes. `routes/brokers.ts` + `pages/BrokerManagementPage.tsx`, `components/BrokerCard.tsx`, `BrokerStatusOverview.tsx` give a broker-management UI NewOFO has that OFO lacks (`BrokersPage.tsx` in OFO is thinner). |
| **Zerodha login/session/token** | `ZerodhaAuth.ts` (144 lines): real Kite Connect flow — SHA-256 checksum(api_key+request_token+api_secret), POST `/session/token`, stores `access_token`/`refresh_token`; `services/TokenStorage.ts`, `services/SessionManager.ts` separate session concerns. Maps to ADR-016/017 (Zerodha as authority, submitted≠executed groundwork) reasonably. | `services/kiteService.ts`, `routes/auth.ts` + `authNew.ts` (duplicate/parallel, one likely dead) + `googleAuthService.ts` (separate Google OAuth for app login, mixed with broker OAuth) + `sessionService.ts`. Two auth route files for the same concern is a quality red flag. |
| **WebSocket / market data ticker** | `brokers/zerodha/ZerodhaWebSocket.ts` (618 lines) + `services/RedisPublisher.ts`/`RedisSubscriber.ts` (pub/sub fan-out pattern, decouples ticker from HTTP layer) + `services/StatusMonitor.ts`, `RateLimitManager.ts`. Docs mention explicit "memory optimization/websocket stability" fix sessions (`docs/memory-optimization-websocket-stability-*.md`, `docs/industry-standard-websocket-memory-cleanup-*.md`) — i.e. real production bugs were hit and fixed here. | `services/marketDataService.ts` (+ a `.backup` sibling — sign of an unresolved rewrite), Socket.io used but no Redis pub/sub decoupling seen. |
| **Monitoring/alerts, adjustments** | `services/StatusMonitor.ts` only (broker connection health, not trade alerts). No adjustment logic. | None found. |
| **Auth/users** | Session-token based (broker session only), no app-level user accounts/passwords. | App-level accounts via `bcryptjs` + `jsonwebtoken` + Google OAuth (`googleAuthService.ts`) — broader (has real user login), but mixes concerns with broker auth in the same route files. |
| **Subscriptions/payments** | None. | None. |
| **Admin** | None dedicated. | None dedicated. |

---

## 3. Verdicts

| Module | Verdict | Reason |
|---|---|---|
| OFO `BrokerInterface`/`BrokerTypes`/`BrokerErrors` (abstract broker contract) | **REFERENCE** | Clean shape (auth/data/WS/portfolio methods) worth reading before designing the ADR-012/029 adapter seam, but it predates the spec, has no strategy/order awareness, and is untyped in places (`any` for WS connection, quote data) — redesign against REQ, don't copy verbatim. |
| OFO `ZerodhaAuth.ts` (Kite Connect checksum + session/token flow) | **ADAPT** | The Kite Connect handshake (checksum formula, `/session/token` call, token fields) is standard and correct-looking; adapt into the new adapter's auth module, drop the class's coupling to `BrokerInterface`'s broader shape, add proper typed errors and no-auto-retry (ADR-016). |
| OFO `ZerodhaWebSocket.ts` + Redis pub/sub pattern (`RedisPublisher`/`RedisSubscriber`) | **ADAPT** | Real bugs were found and fixed here (see the two dated "websocket memory/stability" doc files) — that hard-won knowledge is worth reading even if the code is rewritten; the pub/sub decoupling (ticker process → Redis → app) is a reasonable pattern for the new ticker requirement. |
| OFO `prisma/schema.prisma` `Holdings` model (Decimal(15,2) money fields) | **REFERENCE** | Confirms the project already knew to use `Decimal` not float for money at the DB layer — follow that pattern for the new schema (ADR-008), but the model itself is too narrow (one table) to copy. |
| NewOFO `StrategyBuilderPage.tsx` | **SKIP** | It is a "Coming Soon" static placeholder with zero logic — nothing to reuse. |
| Both repos: payoff/scenario/Greeks calculation engine | **SKIP — does not exist** | Neither repo has any P&L, payoff, or Greeks math (verified by grep across both full trees). REQ for the single calculation engine (ADR-008, `scenario-calculations.md`) has **no prior art in either repo** and must be built from scratch. This is the single biggest gap: the two features owner remembered (strategy builder with payoff) are further along in spec form (ADR-008, business-rules doc) than they ever got in code. |
| Both repos: order entry/execution | **SKIP — does not exist** | Neither reached order placement, so ADR-002 ("every order belongs to a strategy") has nothing to violate or reuse — a clean slate. |
| NewOFO `OptionChainPage.tsx` + table variants (`NSEStyleOptionTable`, `OptionChainTable`, `SimpleOptionTable`) + `ExpirySelector`/`FilterPanel` | **REFERENCE** | Actually routed/used (unlike OFO's test-page-only option chain), gives UI layout ideas (columns, expiry/strike filter UX) for the option-chain requirement, but built on `nseIndiaAdapter.ts` (HTML-scraping NSE with `cheerio`) which conflicts with ADR-012/029 (browsers/adapters must not talk to a data vendor directly, and scraping NSE is fragile/ToS-risky) — do not copy the data-fetch path, only the UI layout as a guide. |
| NewOFO `PositionPage.tsx` + `routes/portfolio.ts` | **REFERENCE** | A real routed positions page exists (OFO has none) — useful as a UI/route-shape reference, but rebuild the data path per ADR-016/017 (Zerodha positions as authority, reconciliation). |
| NewOFO broker services (`angelOneService.ts`, `nseIndiaAdapter.ts`, `freeMarketDataService.ts`, `kiteService.ts`) | **SKIP** | No shared interface (unlike OFO's `BrokerInterface`), each is bespoke and called ad hoc from routes — directly contradicts ADR-012/029's adapter-seam requirement. Multiple duplicate/backup files (`auth.ts` + `authNew.ts` + `auth.ts.backup`, `marketDataService.ts` + `.backup`) are a maintainability red flag; not worth untangling. |
| NewOFO Google OAuth app-login (`googleAuthService.ts`) | **REFERENCE only if app auth is Google-based** | Concept (app-level login separate from broker auth) is right, but check the spec's decided auth mechanism (ADR set) before reusing; not checked here since it's outside this brief's module list. |
| Test suites (OFO: 12 files, backend+frontend) | **REFERENCE** | Worth skimming for edge cases the earlier team already found (e.g. holdings edge cases, broker-manager, WebSocket), but write fresh tests against the new REQ/AC structure per the kit's `deliver` skill — don't port test files as-is since they test OFO's own module shapes. |
| algochanakya (not code-surveyed, per instruction) | **investigate first, before OFO/NewOFO, at the next planning step** | Newest, most complete, matching stack ambition (multi-broker, real docs/ADRs/tests) — likely has real strategy/payoff/Greeks code that OFO/NewOFO never reached; a follow-up survey of algochanakya's `backend/app/services/` and `docs/features/` is the natural next step before deciding what "copy into OptionsForOptions2" even means. |

**Hard-rule flags:** Neither repo has order entry (ADR-002 n/a), and OFO's one DB money field already uses
`Decimal` (ADR-008 pattern respected at the one place money is persisted) — but since neither repo computes
P&L/payoff/Greeks, ADR-008's core requirement (one calc engine, exact decimal) is untested by either codebase.
NewOFO's `nseIndiaAdapter.ts` (scraping NSE HTML with `cheerio` directly from the backend, and per file grep this
is called from `routes/market.ts`) is closer to a data-vendor call happening outside a proper adapter boundary —
flag for ADR-012/029 review if any of that fetch logic were ever reused.

## 4. Risks

- **Licences:** both repos are private one-owner spikes using only standard MIT/Apache-licensed npm packages
  (React, Express, Prisma, Redux Toolkit, Zustand, kiteconnect, etc.) declared in `package.json`/`package-lock.json`
  — no vendored third-party source code found in either tree (no `vendor/`, no unattributed copy-pasted libraries
  seen while reading the surveyed files). OFO's root `package.json` has no `license` field; NewOFO's declares
  `"license": "MIT"`. Not a concern for reuse.
- **Secrets/credentials:** grepped both trees for API key/secret/password/PEM-key/AWS-key patterns and hardcoded
  Kite `api_key`/`api_secret` literals — **zero hits** in either repo (all credential fields are read from
  `process.env`, filtered out of the grep). No `.env` or `.env.*` files are tracked in either repo (git-ignored,
  as expected). Nothing to redact.
- **Personal data:** OFO's `docs/*.txt` session-log files (Claude Code session transcripts, e.g.
  `docs/2025-07-27-this-session-is-being-continued-from-a-previous-co.txt`) contain the developer's local machine
  path `/home/abhay/OFO/frontend` in npm error output — a local path, not PII/credentials, low sensitivity, but if
  any of these `docs/*.txt`/`docs/Grok-*.md` session logs are ever copied into the new repo, strip them; they are
  developer session transcripts, not project documentation. No emails, phone numbers, or user records found in
  either repo's tracked source.

---

## Top-10 reuse candidates (ranked)

1. Investigate **algochanakya** first (newest, most complete, matching multi-broker ambition) before committing to any OFO/NewOFO reuse — not surveyed here, flagged as the real next step.
2. OFO `brokers/zerodha/ZerodhaAuth.ts` — Kite Connect checksum + session/token handshake (ADAPT).
3. OFO `brokers/zerodha/ZerodhaWebSocket.ts` + `RedisPublisher`/`RedisSubscriber` pub/sub ticker pattern, plus its two "memory/stability fix" docs (ADAPT — read the bugs before rebuilding).
4. OFO `brokers/base/BrokerInterface.ts` abstract adapter shape — as a REFERENCE starting point for the ADR-012/029 broker seam.
5. OFO `prisma/schema.prisma` Holdings model's `Decimal(15,2)` money-field pattern (REFERENCE for ADR-008).
6. NewOFO `OptionChainPage.tsx` + table components — UI/layout REFERENCE only (not the NSE-scrape data path).
7. NewOFO `PositionPage.tsx` + `routes/portfolio.ts` — UI/route-shape REFERENCE.
8. OFO's 12 test files (holdings, broker-manager, WebSocket) — REFERENCE for edge cases, not portable as-is.
9. NewOFO `BrokerManagementPage.tsx`/`BrokerCard.tsx`/`BrokerStatusOverview.tsx` — multi-broker status UI concept (REFERENCE); OFO's equivalent page is thinner.
10. **Nothing exists to copy for the strategy builder / payoff / Greeks engine** — both `StrategyBuilderPage.tsx` (NewOFO, placeholder) and the total absence of any payoff math in OFO confirm this must be built new against `spec/business-rules/scenario-calculations.md`.

## Evidence table

| Claim | Evidence (tool call this run) |
|---|---|
| Both repos have Windows-invalid `:Zone.Identifier` paths blocking normal checkout | `git clone` errored `invalid path 'docs/OFO-main.zip:Zone.Identifier'` (OFO) and `invalid path 'images/OFO-google auth issue.jpeg:Zone.Identifier'` (NewOFO); fixed with `git -c core.protectNTFS=false checkout HEAD`, confirmed by `ls` showing full trees |
| OFO: 88 commits in shallow view, last `2025-08-02`, first visible `2025-07-25` | `git log -5 --format='%h %ad %s'` and `git rev-list --count HEAD` in OFO |
| NewOFO: 37 commits, last `2025-07-25` "Closing this temporarily", first `2025-07-20` | same commands in NewOFO |
| OFO LOC: backend 12,614 / frontend 10,386; NewOFO: backend 8,113 / frontend 6,810 | `find ... -name "*.ts" -o -name "*.tsx" \| xargs wc -l \| tail -1` in each repo |
| OFO has 12 test files; NewOFO has 0 | `find . -iname "*.test.*" -o -iname "*.spec.*" \| grep -v node_modules` in each repo |
| No hardcoded secrets, no tracked `.env*` files in either repo | `grep -rnE "api_key\|api_secret\|password\|BEGIN.*KEY\|AKIA..."` (excluding `process.env`) and `find . -iname "*.env*"` in each repo — both empty |
| Neither repo has any payoff/Greeks/strategy calculation code | `grep -rliE "delta\|gamma\|theta\|vega\|blackscholes\|payoff" backend/src frontend/src` in each repo — hits only type defs / mock-data field names / a placeholder UI card, never a formula |
| NewOFO's StrategyBuilderPage is a static placeholder, unchanged since initial commit | `cat frontend/src/pages/StrategyBuilderPage.tsx` (66 lines, "Coming Soon") + `git log --oneline -- frontend/src/pages/StrategyBuilderPage.tsx` shows 1 commit |
| OFO's Holdings Prisma model uses `Decimal(15,2)`, not float, for money | `cat backend/prisma/schema.prisma` |
| algochanakya is a different stack, created 2025-12-02, pushed as recently as 2026-08-31 | `gh repo view abhayla/algochanakya --json description,pushedAt,createdAt,languages` and `gh api repos/abhayla/algochanakya/contents/README.md` |
