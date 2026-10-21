# W-113 builder brief (GC-5S item 1, core): Live Strategies page

Common brief: docs/process/builder-brief.md
Core: the existing live outcome socket (/api/strategies/live) feeds a NEW screen with real ticks, not the Strategy Builder.
Proof: the orchestrator runs it on live ticks after you push (page on :4174, API on :8766); your part is a page that
renders every push it receives and a replay e2e that shows two pushes and the disconnect message.
Budget: 60 min wall-clock, 75 tool calls
Report: evidence-table
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Tier: B (frontend only; you must NOT edit backend/, live_push, or any route; if you find you must, STOP and report).
Copy from: spec/technical-design/legacy-reuse.md row 153 (`src/views/PositionsView.vue`, `components/autopilot/monitoring/*`: ADAPT, strategy-scoped, reword advice) for card layout ideas only; the socket client is already adapted (row 142, `frontend/src/composables/useStrategyLive.js`) - reuse it, never copy it.
Design basis: docs/design/screens-research-2026-10-19.md section `Live Strategies` is being written in parallel; build a plain, readable layout (one card per strategy, stacked at 390 px) and keep the markup in one component so the layout can follow the note in a later commit.

## Work item
`work/W-113.md` (already in your worktree, untracked: commit it unchanged) and add its row
`W-113: 4b           # GC-5S: Live Strategies page (REQ-049 AC-4..6)` under the work-item rows in
`docs/process/coverage-stages.yaml`.

## Spec basis (quoted)
- REQ-049 AC-4: "Screens show when data is stale or unavailable instead of presenting old numbers as live."
- REQ-049 AC-5: "When live data drops, affected strategies show 'Live market data disconnected. Last updated: <time>. Live
  strategy monitoring is paused.' and no trigger is claimed without the data proving it (Q182)."
- REQ-049 AC-6: "Monitoring availability is tracked per strategy (e.g. NIFTY strategy active, SENSEX strategy paused), not
  app-wide (Q184)." and "Paused shows the `⏸ Monitoring paused` badge and a grey"
- REQ-049 owner decision text: "when the browser's own live connection drops, the fallback also shows AC-5's message with
  the newest price time the strategy received"
  (the grey dot's label in AC-6 is the words Health unknown, quoted in the requirement)
- REQ-044 AC-2 (context only, not claimed in full): "After execution live monitoring appears in the Live Position / Live
  Strategy view"

## What to build
1. Route `/strategies/live-strategies` (nav entry exists: `frontend/src/router/nav.js:21`) to a new page
   `LiveStrategiesPage.vue` instead of the placeholder. Look at how the router maps nav entries to `PlaceholderPage.vue`.
2. On load: `GET /strategies` (list: id, underlying, status, created_at, updated_at), then `GET /strategies/{id}` for each
   (cap the page at the 20 most recently updated; say `Showing the 20 most recent` when capped). Build each strategy's
   outcome body exactly the way `StrategyBuilderPage.vue` builds it for `live.follow(...)` (line ~155) - reuse the same
   helper; if the conversion lives inside the page, move it to a small shared module and import it from both (no copy).
3. One `useStrategyLive` instance per strategy card (each is its own socket; the server fans out on ONE vendor feed).
   Stop every socket on unmount.
4. Each card shows, as given by the server (strings, never parsed into numbers, never computed - ADR-008): underlying,
   strategy status, the server's `status_label` / `reason`, `spot_level`, `spot_at` (formatted with the existing time
   helper the Builder uses for `Checked at`), `answered_at` (`Checked at`), each leg's symbol, ltp and `health`, and the
   summary figures the outcome already carries (whatever the Builder shows from `summary`; no new figure).
5. AC-4: a leg/quote whose `health` is not `available` is visibly marked with its health word (stale / delayed /
   unhealthy / unavailable); never shown as live.
6. AC-5: when the socket for a card goes down (onDown), do what the Builder does: ask the REST outcome route
   (`POST /api/strategies/outcome`) and show ITS label (the server writes AC-5's message, ADR-077). The page writes no
   copy of that sentence itself.
7. AC-6: per-card state. A card whose latest answer is not live (NOT_CONNECTED, or socket down/off) shows the
   `⏸ Monitoring paused` badge and a grey `Health unknown` dot; other cards keep their own state. Check
   `tests/test_wording_paths_issue89.py` and the frontend wording rules before adding a new UI string; if a rule forbids a
   literal in the page, put it where that rule allows and say so.
8. Empty state: no saved strategies -> one line pointing to the Strategy Builder (link), no fake rows.
9. `data-testid`s: `live-strategy-card`, `live-spot`, `live-spot-at`, `live-paused-badge`, `live-health-dot`,
   `live-status-label` (the orchestrator's live proof reads these).

## Tests (targeted only; CI runs the full suites)
- `frontend/tests/live-strategies.test.js` (Vitest, fake socket like `strategy-live.test.js`): AC-4 non-available health
  shown with its word; AC-5 onDown -> REST label rendered verbatim from the server reply; AC-6 two cards, one paused one
  live, badges independent; push values rendered untouched (a push with spot_level 25123.45 (as a string) shows exactly that
  text); every socket stopped on unmount; capped at 20.
- `frontend/e2e/live-strategies.spec.ts` (Playwright, `OUTCOME_REPLAY=1` like `strategy-live.spec.ts`): save a draft through
  the API, open the page, see two pushes with different `spot_at`, then force the socket down and see AC-5's message
  (reuse the `AC5` regex from `strategy-live.spec.ts`; import it, do not retype it).
- Run: `npm run lint`, `npx vitest run tests/live-strategies.test.js tests/strategy-live.test.js`, `npm run build`, the
  brief's `Tests:` line, `python scripts/ruff_ratchet.py`. Do not run the full Playwright suite; CI runs it.

## Reviewer checklist (the verifier checks exactly this)
- No number parsed or computed in the page (grep for `parseFloat`, `Number(`, `+` on values, `toFixed`).
- No new route, no backend edit, no edit to `useStrategyLive.js` behaviour (a refactor that keeps every existing test green is allowed only if needed for reuse).
- AC-5 sentence never written in frontend source.
- Every socket closed on unmount (test proves it).
- Per-card paused state (test with two cards).
- No order/execute link or button on the page (ADR-002); no advice wording (ADR-003).

## Attack cases to cover
Push arrives for a card after unmount (ignored); a strategy whose GET /strategies/{id} fails (that card shows the server's
error label, others still load); a REFUSED answer (shown as the server's reason, not paused); `spot_at` null (shown as
`-`, never the request time); 0 strategies; 25 strategies (20 shown).

## Standing items (B4)
(a) n/a (no time-budgeted job); (b) n/a (no CI step changed); (c) n/a (no static detector); (d) each server answer state is
listed above: COMPUTED, NOT_CONNECTED, REFUSED, socket down, socket off (gave up), GET failed, empty list.
No new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no
regenerated files in the PR.

Worktree (isolation, hard rule): work ONLY in `D:\Abhay\Ventures\OptionsForOptions2-gc5s` (branch
`build/W-113-live-strategies`, from origin/main a614b16; `frontend/node_modules` already installed). Never run any git or
npm command in `D:\Abhay\Ventures\OptionsForOptions2` (another session's live order run serves from it); never start or
stop anything on ports 8765/4173; start no servers at all except what `npx playwright test` needs for your one spec,
and stop them. Never touch `ExecuteStrategyPage.vue`, `ExecutionReturnedPage.vue` or any execute/order/reconciliation
file. Commit and `git push -u origin build/W-113-live-strategies`; do NOT open a PR.
