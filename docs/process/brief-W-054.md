# Builder brief: W-054 frontend skeleton with the seven-section navigation and a live health page

Core: a browser loads the app through the Vite server, which proxies /api to the FastAPI app, which reads PostgreSQL;
the health page shows the live database status, in one Playwright run.
Proof (step 1): in CI (app-tests.yml, which already has a postgres:16 service and runs `alembic upgrade head`), start
`uvicorn` with `ofo_app.main:create_app` (factory), start the frontend (Vite preview of the build, `/api` proxied to the
API), Playwright opens the health page and asserts it shows the database as OK from the real backend; a second check
points the proxy at a closed port and asserts the page shows the unavailable state. Screenshots at 390 and 1280 px are
uploaded as CI artifacts.

Budget: 60 min wall-clock, 80 tool calls. At budget, stop and report done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`).
Tier: B.

## Spec basis
- REQ-009 AC-1: "Home: Overview, Important alerts, Active strategies, Account status."
- REQ-009 AC-2: "Strategies: My Strategies, Create Strategy, Strategy Builder, Live Strategies, Adjustments, Completed Strategies."
- REQ-009 AC-3: "Positions: Current positions, Strategy-linked positions, Adjustment opportunities, P&L/risk."
- REQ-009 AC-4: "Market: Option Chain, Underlying/index view, Market context."
- REQ-009 AC-5: Orders lists "strategy-linked orders only, never an order-entry" form; sub-items Pending, Executed,
  Failed/partial, Execution history.
- REQ-009 AC-6: "Alerts: Active, History, Notification settings."
- REQ-009 AC-7: "Learn: Strategy education, Options concepts, Platform guidance."
- REQ-009 AC-8: the avatar menu opens Account & Settings with Profile, Zerodha connection, Subscription & Billing, Free
  Eligibility, Referrals, Notifications, Security, Preferences, Strategy Preferences, Broker & Market Data.
- ADR-049: Tailwind CSS 4 via `@tailwindcss/vite`, copied from algochanakya; light theme, neutral surfaces, thin 1px
  dividers, ONE accent cobalt about #2F5BFF; green/yellow/orange/red only for strategy health (ADR-010); no Zerodha or
  Kite branding.
- ADR-012: the browser never talks to a market-data vendor; only same-origin `/api`.
- ADR-030: skeleton only - each section is an empty placeholder page listing its sub-items; no feature screen.
- Backend facts: `GET /health` exists (backend/ofo_app/routes/health.py), app factory `ofo_app.main:create_app`.

## Copy from (legacy-reuse.md M7; source D:\Abhay\Ventures\algochanakya\frontend at bf9faf7)
Each copied file starts with a provenance comment `Copied/adapted from abhayla/algochanakya@bf9faf7:<path> (ADR-047)`.
- `package.json` (ADAPT): vue ^3.5, vue-router ^4.6, pinia ^3, axios, tailwindcss 4 + `@tailwindcss/vite`, vite 7,
  vitest (bumped to match vite 7), @vue/test-utils, happy-dom, eslint + eslint-plugin-vue, prettier, @playwright/test;
  drop autoprefixer, chart.js (not needed yet). Commit `package-lock.json`.
- `vite.config.js` (ADAPT): vue plugin, `@` alias, `@tailwindcss/vite`, dev and preview `server.proxy` for `/api` (rewrite
  to the API root) and `/ws`; vitest config.
- `eslint.config.js` (ADAPT): add a rule that bans literal vendor hosts (kite.trade, zerodha.com, nseindia.com,
  upstox, angelone, dhan) in source.
- `src/main.js`, `index.html` (ADAPT): no kite-theme.css; our `src/style.css` with Tailwind and tokens.
- `src/router/index.js` (ADAPT structure: lazy routes, meta flags, catch-all); NEW route table: the seven sections with
  one placeholder route per sub-item, `/settings/*` for the avatar menu items, `/health-status`.
- `src/services/api.js` (ADAPT): axios with same-origin base `/api`, `withCredentials`, no localStorage token, a generic
  error mapper that shows a neutral message (REQ-065 mapping waits for W-024).
- `src/components/layout/KiteLayout.vue` + `KiteHeader.vue` -> `AppLayout.vue` + `AppHeader.vue` (ADAPT: rename,
  restyle with our tokens, remove broker switching/market data source toggles; nav from the route table; avatar menu).
- `src/composables/useToast.js`, `useScrollIndicator.js` (COPY); `src/tests/setup.js` + `tests/helpers/*` (COPY).
- `playwright.config.js` + e2e page-object structure + `data-testid` convention (ADAPT: projects for 390x844 and
  1280x800, no real broker login, base URL of the preview server).
- Not copied: kite-theme.css, any broker/credential store or service, autopilot/ai/ofo/watchlist code.

## Tests
- `frontend/e2e/navigation.spec.ts`: one test per REQ-009 AC (AC-1..AC-8) asserting the exact section and sub-item
  labels from the spec text above (copy the strings from the spec, not from the app), plus: no route or component offers
  an order-entry form (AC-5); every nav link resolves to a page.
- `frontend/e2e/health.spec.ts`: the core proof above.
- Vitest unit test for the api client (same-origin, no token storage).
- CI: extend `.github/workflows/app-tests.yml` with a job (or steps) that installs Node 20, `npm ci` in `frontend/`,
  `npx playwright install --with-deps chromium`, runs lint + vitest, builds, starts uvicorn against the postgres service
  as `ofo_app` and the preview server, runs Playwright, uploads screenshots. Keep the existing Python job unchanged.

## Standing items (run-discipline B4)
- Fail closed: a nav item without a route fails the test; an unknown route shows the catch-all page.
- Kit CI stays green; nothing under `tests/` changes.

## Rules
- Branch from origin/main (W-051 is merged). Do not edit kit files. Never write `evidence/`. No secrets.
- Locally: `npm ci`, lint, vitest and a Playwright run against a stubbed `/api/health` are fine; the real-backend proof
  runs in CI (no local PostgreSQL). Say which ran where.
- Commit; do not push.
