# W-114 builder brief (GC-5S item 2): Underlying/index view on a new read-only index socket

Common brief: docs/process/builder-brief.md
Core: a NEW read-only index socket on the ONE shared fan-out pushes live NIFTY 50 and SENSEX values with their own health and timestamps to a browser page.
Proof: step 1 is the push class alone: a fake-fan-out test where two index quotes change and the fake channel receives 2 pushes with changing timestamps for both indices (no DB, no server); the orchestrator runs the live socket proof after the live order run ends.
Budget: 75 min wall-clock, 75 tool calls
Report: evidence-table
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Tier: A (live-data liveness: a new socket and route on the shared feed). Fresh Opus verifier, adversarial.
Findings checked: liveness-from-shared-subscribers, live-subscription-lost-on-release-reacquire, staleness-by-last-change-age
Copy from: none - no algochanakya module serves an index-only socket (legacy-reuse.md has no row for one); reuse this repo's `backend/ofo_app/live_push.py` (StrategyPush) and `routes/live.py` patterns, never copy them.
Design basis: docs/design/screens-research-2026-10-19.md section `Underlying / index view` (two panels: value, time, health word; Option Chain and Live Strategies links; no change figure, no order buttons).

## Work item
`work/W-114.md` is in your worktree (untracked): commit it unchanged, and add the row
`W-114: 4b           # GC-5S: Underlying/index view + index socket (REQ-072 AC-2)` to `docs/process/coverage-stages.yaml`.

## Spec basis (quoted)
- REQ-072 AC-2: "The live NIFTY 50 and SENSEX values carry the same health states as option prices (REQ-049 AC-2); a stale or
  missing index value is shown as such and is never used silently in a calculation."
- REQ-049 AC-2: "Each quote has a health state: available, stale, delayed, unhealthy or unavailable"
- REQ-049 AC-4: "Screens show when data is stale or unavailable instead of presenting old numbers as live."
- REQ-072 AC-1: "their identity is (segment, exchange token)"
- Not claimed: REQ-010 AC-1 (login) - V1 has one fixed owner (`routes/broker.py` `current_user_ref`), so no login exists to
  test; do exactly what `/api/strategies/live` does and say so in the report.

## What to build
Backend (`backend/ofo_app/`):
1. A pure push class (like `StrategyPush`, framework-free, tested with a fake channel and fake fan-out): on connect it
   subscribes the two index instruments (`provider.index_id('NIFTY')`, `provider.index_id('SENSEX')`) on the shared
   `FanOut`; it pushes at most once a second (reuse `MIN_PUSH_INTERVAL` from `live_push.py`) and only when a value or
   health changed; first push at once; releases its subscription when the connection ends (`finally`). The client sends
   nothing it needs; any client message is answered with `render('user_input_request_invalid')` and changes nothing.
2. Response models (`ApiModel`): one per index `{underlying: Literal['NIFTY','SENSEX'], instrument_id, value: Money or
   None, at: aware datetime or None, health: HealthCode or None}`, and the message `{state: Literal['LIVE',
   'NOT_CONNECTED'], indices: [..2 rows, NIFTY then SENSEX..], answered_at}`. Money leaves as a string (Decimal, never
   float). Register each new model in `tests_app/test_response_door.py` and run that file; regenerate
   `docs/api/openapi.json` with `python scripts/generate_openapi.py`.
3. Socket route `/api/market/indices/live` via `ClosedWebSocketRoute` + `errors.add_socket_route` exactly as
   `routes/live.py` / `create_app` do; the replay builder for `APP_ENV=test` the same way `set_replay_feed` works.
4. REST `GET /api/market/indices` (same message model) for first paint, and `?fallback=1` from a page whose own socket is
   down: the answer is `NOT_CONNECTED` with each index's last value time kept, whatever other sockets hold (finding
   liveness-from-shared-subscribers). No live feed at all -> `NOT_CONNECTED`, values null, never a stored old number shown
   as live.
5. Health is the quote's own `health` from the feed (same rule as option prices, REQ-072 AC-2). Do not invent a new
   staleness rule (finding staleness-by-last-change-age: per-instrument staleness is a known open gap; say so).

Frontend:
6. `/market/underlying-index-view` (nav entry `frontend/src/router/nav.js:41`) -> new page: two panels, NIFTY 50 and
   SENSEX: value as given, `as of <time>` with the existing time helper, health word whenever not `available`, a page
   label from the server's state when NOT_CONNECTED; links `Open Option Chain` (`/market/option-chain`) and
   `Live Strategies` (`/strategies/live-strategies`). A small composable for the index socket reusing
   `createLiveSocket`'s backoff from `useStrategyLive.js` (import, do not copy). No browser maths (ADR-008).
   `data-testid`: `index-panel-NIFTY`, `index-panel-SENSEX`, `index-value`, `index-at`, `index-health`, `index-state`.

## Tests (targeted only; CI runs the full suites)
- `tests_app/test_index_live.py`: AC-2 per health value (available, stale, delayed, unhealthy, unavailable -> the row's
  health equals it); push rate (two quotes 0.2 s apart -> one push; after 1 s -> second); no change -> no push; release on
  close (subscriber_count back to 0 for both index ids); a SECOND socket holding the indices + this page's `?fallback=1`
  -> NOT_CONNECTED (the shared-subscriber case); no feed -> NOT_CONNECTED with null values; a client message -> the
  catalogue error, no subscription change; SENSEX missing from the catalogue (index_id None) -> that row unavailable,
  NIFTY still live.
- `frontend/tests/index-view.test.js` and `frontend/e2e/index-view.spec.ts` (replay): two pushes with different `at`;
  socket down -> REST fallback state shown; a stale health shows its word.
- Mutation list in the report: each guard (rate gate, change gate, release, fallback flag, null index) deleted in a
  scratch copy and the test that goes red named.

## Reviewer checklist (the verifier checks exactly this)
- ONE shared fan-out; no vendor connection or Kite call per socket; subscription released on every exit path.
- At most one push a second; no push without a change.
- Fallback flag answers not-live regardless of other holders (test with two holders).
- Health passed through from the quote, never upgraded; null value never rendered as a number.
- Money as strings; new models registered; openapi regenerated; no order/execute/strategy code touched.
- Threat model: in scope - a browser socket receiving stale or another client's liveness as its own, a leaked
  subscription after disconnect, a push storm; out of scope - authentication (V1 has no login; same as the strategy socket).

## Standing items (B4)
(a) n/a; (b) n/a; (c) n/a; (d) answer states listed: LIVE, NOT_CONNECTED (no feed), NOT_CONNECTED (fallback), per-row
health x5, index unknown, client message. No new duplicated literal; reuse the existing helper; ruff/mypy baselines must
not rise; targeted tests only; no regenerated files in the PR except `docs/api/openapi.json`.

## Isolation (hard rules)
Work ONLY in `D:\Abhay\Ventures\OptionsForOptions2-gc5s-w114` (branch `build/W-114-index-view`, from origin/main;
run `npm ci` in its `frontend/` first). Never run git or npm in `D:\Abhay\Ventures\OptionsForOptions2`; never touch ports
8765/4173/8766/4174. Never edit execute/order/reconciliation code.
**No database at all** (owner decision 2026-10-19 ~10:58: build on fakes/replay only): the `ofo_app` role allows 5
connections and a live order run holds 3 (finding `db-role-limit-below-pool-size`). So: no API server, no Playwright
run, no `db_run.py`, no `tests_app` file that opens a database. Write `tests_app/test_index_live.py` so its push-class
tests use fakes (fake channel, fake fan-out, no DB) and run those with plain `python -m pytest -q -p no:cacheprovider
-c pytest-app.ini tests_app/test_index_live.py -k 'not db'` only if that file needs no database; anything needing the
database or a server (route tests, the e2e) is written and listed (`--collect-only` / `npx playwright test --list`) but
runs in CI. Step 1's replay proof moves to the orchestrator after the live run. Commit and push; do NOT open a PR.
