# Builder brief: W-064 Strategy Builder screen, first slice

Core: the browser shows exactly the numbers the outcome API returns for a real strategy priced on real recorded market
data - no number on the screen is computed in the browser.
Proof (step 1, before any styling): a test-only replay mode for the API (see 1 below) plus
`frontend/e2e/strategy-table.spec.ts` opening the screen for the W-063 NIFTY 13-Oct iron condor and asserting that
every scenario cell, max profit 4,754.75, max loss 8,245.25 and breakevens 22,326.85 / 22,873.15 on screen equal the
text of the API response the page received (read the response in the test - never typed expected numbers into the
page code). Commit green before anything else.

Budget: 60 min wall-clock, 75 tool calls. Commit after step 1 and after each item; at budget stop after a commit and
report done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), screenshot paths, under 300 words.
Tier: B.

## Spec basis
- REQ-035 AC-3: "Left-hand columns are sticky while the table scrolls horizontally; the current market level column is highlighted."
- REQ-035 AC-5: "Bid/Ask appear only in Advanced Details."
- REQ-035 AC-1 (one table), AC-2 (locked column order), AC-7 (UX level visibility) - already enforced by the
  backend table model (W-004/W-034); the screen renders the columns it is given, in that order.
- ADR-008 (one engine; no client-side P&L); ADR-068 (UX level is a request parameter, Standard by default;
  planned entry shown with its capture time; not-live labels per its consequences); REQ-067 AC-4 (desktop and mobile
  screenshots of every state); issue #159 (`/broker/connected`).
- Copy from: the legacy-reuse map rows listed in work/W-064.md (algochanakya `bf9faf7` at
  `D:\Abhay\Ventures\algochanakya` - read it there; never edit it). Every copied file starts with a provenance line
  naming repo, commit and path, and is changed to meet every hard rule (no client maths, decision-support wording).

## What to build
1. **Test-only replay mode (backend/ofo_app):** a setting that, only when `APP_ENV` is `test`, wires the W-059
   `KiteProvider` fed from the recorded frames file into the outcome route's provider dependency; any other
   `APP_ENV` refuses the setting at start-up. A test proves production settings cannot enable it.
2. **Screen (frontend/src):** route `/strategy/builder` - table (from the API's columns and cells, as given),
   payoff chart (from the API's payoff points), summary cards (plain-language summary first, detail expandable),
   data-health banner. Left columns sticky; the column the API flags as current is highlighted (AC-3). Bid/ask
   columns rendered only when the UX level is Advanced (AC-5) - the UX level is a request parameter (ADR-068).
   Money is displayed as the API's strings; the page parses no number to compute another.
3. **States:** loading; computed; "Draft - Live data not connected" (no provider); stale leg labelled; API error via
   the REQ-065 four-part message. Each state gets desktop (1280) and mobile (390) screenshots in Playwright.
4. **`/broker/connected` (#159):** a plain confirmation page (a heading saying Zerodha is connected, what is now
   available, a link to the Strategy Builder) and a page for the callback's refusals showing the catalogue message;
   a Playwright test for both. Wording is decision-support per ADR-003 (none of its banned advice phrases).
5. **Unit test (AC-5):** `frontend/tests/strategy-table.test.js` - bid/ask hidden at Standard and Guided, shown at
   Advanced; no column reorder.

## Standing items (run-discipline B4) and reviewer checklist
- (d) every answer state of the outcome API: COMPUTED, NOT_CONNECTED, a stale leg, a refused leg, an HTTP error, a
  slow answer - each renders its own state, never a blank or a stale number shown as live.
- Mutation tests first: compute a P&L in the browser; drop the sticky class; show bid/ask at Standard; render the
  not-connected state as numbers. Each must turn a test red.
- A grep test that `frontend/src` contains no arithmetic on money values from the API (closed list: no `parseFloat`/
  `Number(` on the outcome response fields) - as a second layer only; the first is that the page takes strings.

## Rules
- Branch `build/W-064-screen` from origin/main. Frontend: `cd frontend && npm ci` once; `npm run lint`,
  `npm run test:run`, `npm run build`, `npx playwright test` (the CI frontend job's steps). Backend suites: domain
  `python -m pytest -q -p no:cacheprovider`, app `python -m pytest -q -p no:cacheprovider -c pytest-app.ini`.
  Output to log files, summary lines read. Gates as their own tool calls, never piped before a commit/push.
- `python tools/ci_local.py` once, bare, before the push; push in a separate command; do not open a PR.
- Never edit kit files (.claude/, tools/, factory/schemas/, .github/workflows/ci.yml, KIT_VERSION) or spec/; never
  write evidence/; never mark anything verified. Never edit the algochanakya repo.
