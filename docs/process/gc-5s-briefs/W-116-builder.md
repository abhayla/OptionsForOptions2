# W-116 builder brief (GC-5S item 4a): Option Chain read route and live socket (no screen)

Common brief: docs/process/builder-brief.md
Core: a NEW read-only chain socket subscribes one expiry's contracts around ATM on the ONE shared fan-out and pushes Calls | Strike | Puts rows with live LTP, OI, volume and each quote's own health.
Proof: step 1 = a fake-fan-out test where a fake channel receives 2 pushes for a 5-strike chain with changing LTPs and per-cell health (no DB, no server); the orchestrator runs it on live ticks after the live order run ends.
Budget: 75 min wall-clock, 75 tool calls
Report: evidence-table
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Tier: A (live-data liveness; a new socket and route on the shared feed). Fresh Opus verifier.
Findings checked: liveness-from-shared-subscribers, live-subscription-lost-on-release-reacquire, staleness-by-last-change-age, db-role-limit-below-pool-size
Copy from: spec/technical-design/legacy-reuse.md row 88 (`services/options/option_chain_live_engine.py`: ADAPT, strip platform-wide assumptions) and row 114 (`app/api/routes/optionchain.py`: ADAPT, split into service + route, Decimal, lot size/strikes from the catalogue); the local checkout is the `algochanakya` folder next to this repo (READ ONLY), pinned bf9faf7; provenance header on any adapted file.
Design basis: docs/design/screens-research-2026-10-19.md section `Option Chain` (rows by strike, ATM marked, 15 strikes either side at first open, nearest expiry first).
Threat model: in scope - a socket receiving another client's liveness or a stale quote as live, a leaked subscription after disconnect or an expiry change, a push storm, an unbounded strike range (subscription flood on the one Kite connection); out of scope - authentication (V1 has no login), order placement (none exists on this route).

## Spec basis (quoted)
- REQ-029 AC-1: "The chain lays out Calls | Strike | Puts for a chosen underlying and expiry."
- REQ-029 AC-2: "Default columns: Strike, LTP, Change, OI, Volume (Q45); IV appears from the Advanced level only (Q232, ADR-056)."
- REQ-029 AC-4: "LTP and bid/ask stream live; OI and IV update at a lower frequency (Q46)."
- REQ-029 AC-6: "The chain never offers direct order placement."
- REQ-029 AC-8: "The ATM strike is highlighted, the underlying price is shown"
- REQ-049 AC-2: "Each quote has a health state: available, stale, delayed, unhealthy or unavailable"

## What to build (backend only; the screen is item 4b)
1. A pure push class like `live_push.StrategyPush` (reuse `MIN_PUSH_INTERVAL`): the client sends `{underlying, expiry,
   strikes_each_side}` (1..15, default 15; anything else -> `render('user_input_request_invalid')`); the class reads the
   expiry's contracts from the stored catalogue (`/api/catalogue/{u}/contracts` has the reader), picks the strikes around
   ATM from the live spot (`provider.index_id(u)` quote), subscribes those CE/PE contracts + the index on the shared
   `FanOut`, and pushes at most once a second when an input changed; a new request releases the old subscription AFTER
   taking the new one (same order as `StrategyPush._replace`); release on close.
2. Message model (`ApiModel`, money as strings): `{state: LIVE|NOT_CONNECTED, underlying, expiry, spot, spot_at,
   spot_health, atm_strike, rows: [{strike, ce: Cell, pe: Cell}], answered_at}`, Cell = `{instrument_id, ltp, change,
   oi, volume, health, at}`. `change`: only if the feed already carries the previous close for that contract; if it does
   not, `change` is null on every cell and you REPORT it (that is a finding for REQ-029 AC-2: never compute a change from
   anything else). No IV, no Greeks in this item (Advanced; engine only, ADR-008/056 - item 4b decides).
3. Socket `/api/market/chain/live` and REST `GET /api/market/chain?underlying=&expiry=&strikes_each_side=` (first paint;
   `fallback=1` -> NOT_CONNECTED whatever other sockets hold), registered the same way as `routes/live.py`; replay for
   `APP_ENV=test` the way `set_replay_feed` does. Register the new models in `tests_app/test_response_door.py`; regenerate
   `docs/api/openapi.json`.
4. No order, basket, margin or execute call anywhere in this code (AC-6).

## Tests (fakes only: no database, no server)
`tests_app/test_chain_live.py` with a fake channel and fake fan-out: AC-1 row order and CE/PE sides; AC-2 columns present
and `change` null when no previous close; AC-4 push rate (<= 1/s, none without change); AC-8 ATM strike = nearest to spot
on the catalogue grid (exact Decimal); per-cell health passed through for all five values; strikes_each_side 0, 16, -1,
'x' refused; expiry change releases the old contracts (subscriber_count 0) and keeps the index held; close releases all;
two holders + `fallback=1` -> NOT_CONNECTED. Route/door tests that need the database are written and collected only
(`--collect-only`); CI runs them. Mutation list: delete each guard (rate gate, range cap, release order, fallback) in a
scratch copy and name the red test.

## Standing items (B4)
(a) n/a; (b) n/a; (c) n/a; (d) answer states: LIVE, NOT_CONNECTED (no feed / fallback), spot missing (no ATM -> rows
empty with the state saying so, never a guessed ATM), expiry unknown, strikes out of range, catalogue empty.
No new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no
regenerated files in the PR except `docs/api/openapi.json`.

## Isolation (hard rules)
Work ONLY in `D:\Abhay\Ventures\OptionsForOptions2-gc5s-w116` (branch `build/W-116-chain-route`, from origin/main).
Never run git or npm in `D:\Abhay\Ventures\OptionsForOptions2`; no database, no API server; never touch ports
8765/4173/8766/4174 or execute/order/reconciliation code. Commit (with `work/W-116.md`, untracked in your worktree, and
its coverage row `W-116: 4b           # GC-5S: Option Chain route + socket (REQ-029)`) and push; do NOT open a PR.
