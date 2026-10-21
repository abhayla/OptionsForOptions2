# W-115 builder brief (GC-5S item 3): Home overview

Common brief: docs/process/builder-brief.md
Core: Home picks its state from the user's saved strategies (none -> create / explore / learn first; some -> My Strategies first) and shows the live index strip from W-114's index socket.
Proof: Vitest per state with a fake `GET /strategies` (0 strategies; 3 drafts), and the strip rendering two index pushes from a fake socket; the orchestrator checks the strip on live ticks later.
Budget: 45 min wall-clock, 60 tool calls
Report: evidence-table
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Tier: B (display only, no money computed, no new route).
Copy from: spec/technical-design/legacy-reuse.md row 153 (`DashboardView.vue`: ADAPT, strategy-scoped, reword advice) for layout ideas only; the index strip REUSES W-114's composable and panel pieces (import, never copy).
Design basis: docs/design/screens-research-2026-10-19.md section `Home / dashboard` (adaptive stack, one primary action first, small strip, quiet Zerodha line last).

## Work item
`work/W-115.md` is in your worktree (untracked): commit it unchanged; add the row
`W-115: 4b           # GC-5S: Home overview, states 1-2 + strip (REQ-008)` to `docs/process/coverage-stages.yaml`.

## Spec basis (quoted)
- REQ-008 AC-2: "Home adapts to the user (Q81 = C): no strategies → Create Strategy, Explore Option Chain, Learn prominent;
  strategies but none active → My Strategies, Create Strategy, recent results"
- REQ-008 AC-3: "A new user's Home shows: 'Welcome, [Name]', 'Plan your trade. Follow your strategy. Then execute.',"
- REQ-008 AC-4: "A small live market strip may be shown to logged-in users."
- REQ-008 AC-5: "Home offers Zerodha connection only in context, when a broker-dependent action is chosen."
- Not built (data does not exist; the orchestrator parks them): the active-strategies state (the store allows only
  status `draft`), Important Alerts (GC-4), the user's name and the 7-day Pro trial status (no profile/entitlement route).

## What to build
1. `/home/overview` -> new `HomeOverviewPage.vue` (see how the router maps nav entries; W-113 did the same for Live
   Strategies).
2. Load `GET /strategies`. 0 strategies -> state `new`: heading `Welcome`, the line `Plan your trade. Follow your
   strategy. Then execute.`, three prominent actions `Create Strategy` (`/strategies/create-strategy` if that route
   exists, else `/strategy/builder`), `Explore Option Chain` (`/market/option-chain`), `Learn` (the Learn section's first
   route in `nav.js`), the link `I already know my strategy` (to the Strategy Builder), and last a quiet line `Already
   trade with Zerodha? Connect when ready` that is plain text with NO connect button (AC-5). 1+ strategies -> state
   `has-strategies`: `My Strategies` first (`/strategies/my-strategies`), `Create Strategy`, and the 3 most recently
   updated saved strategies as plain rows (underlying, status, last saved, a link to open each in the Strategy Builder
   the way the Builder opens a saved draft). data-testid home with data-state new, has-strategies or error.
3. The strip (AC-4): a compact one-line component showing NIFTY 50 and SENSEX value, time and health word from W-114's
   index socket composable; reuse W-114's pieces; it shows the server's not-live state when the socket is down. On a
   failed `GET /strategies` the page shows the server's error and still shows the strip.
4. No Zerodha connect button, modal or redirect anywhere on Home (AC-5). No money figure. No advice wording (ADR-003:
   never `you should`, `best`).

## Tests
- `frontend/tests/home.test.js`: AC-2 state `new` (0 strategies: the three actions present in that order, the
  `I already know my strategy` link); AC-2 state `has-strategies` (3 drafts: `My Strategies` is the first action; rows
  newest first, at most 3); AC-4 strip renders two index pushes from a fake socket and the not-live state; AC-5 no element
  links to the broker login route (grep the rendered HTML for `/broker/zerodha/login` and any button with `Connect`);
  error state keeps the strip.
- `frontend/e2e/home.spec.ts` (replay; written and listed only, CI runs it): both states and the strip.
- Run: `npm run lint`, `npx vitest run tests/home.test.js`, `npm run build`, the brief's `Tests:` line.

## Reviewer checklist
States chosen only from `GET /strategies`; no state for data that does not exist; the strip reuses W-114 code (no copy);
no connect control; no money; wording decision-support only; every socket closed on unmount.

## Standing items (B4)
(a)-(c) n/a; (d) answer states: list empty, list with drafts, list failed, index LIVE, index NOT_CONNECTED, socket down.
No new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no
regenerated files in the PR.

## Isolation (hard rules)
Work ONLY in `D:\Abhay\Ventures\OptionsForOptions2-gc5s-w115` (branch `build/W-115-home`, based on W-114's pushed branch:
a stacked PR). Never run git or npm in `D:\Abhay\Ventures\OptionsForOptions2`; no database, no API server, no Playwright
run; never touch ports 8765/4173/8766/4174 or any execute/order file. Commit and push; do NOT open a PR.
