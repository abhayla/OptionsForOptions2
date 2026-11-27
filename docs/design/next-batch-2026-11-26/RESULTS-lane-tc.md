STATUS 03:25 | items 1 PASS, 2 in progress (SW-1/4/5/6/7/8/9 read; SW-2/3 partly), 3-10 pending | next push: 04:00 | blocker: none

# Lane TC results: browser walk of the after-close screens (28 Nov 2026)

Standing direction step: a test lane over built screens ("a real defect in what is already built"); no new feature, no product file edited.
Base: `origin/integration/weekend-1127` + `origin/integration/conflicts-1127` (merge ran clean). Gate: see "Pushes".

## How this was set up (so the owner can repeat it)
- PostgreSQL 16 on this container, roles as in app-tests.yml, migrated to 0059 (`0059_last_close`). Two databases: `ofo_test` (store tests) and `ofo_tc` (the walk; the app refuses LIVE_MARKET on `ofo_test`, ADR-078).
- Catalogue: `tests_browser/r2_1128/seed_catalogue.py` loads the recorded instrument list with every expiry moved +56 days (so NIFTY 8 Dec / 14 Dec, SENSEX 3 Dec / 10 Dec are live on 28 Nov). 1090 contracts.
- Closes: `tests_browser/r2_1128/closes17.json` (17 synthetic rows: NIFTY 50 24187.35, SENSEX 79234.50, 15 NIFTY options, all `price_at 2026-11-27T15:29:58+05:30`, source `tc_synthetic_2026-11-28`). `python -m ofo_app.last_close_store seed <file> --check` then without `--check`: `written 17, unchanged 0, skipped 0` (run with the catalogue check ON).
- Strategies: `seed_strategies.py` creates 5 drafts through the routes; the routes then REFUSE every paper order with MARKET_DATA_102 "The market is closed. Orders can be placed once it opens." (correct per the rule "a paper entry stays refused"), so the fills go in by `seed_orders.sql` (insert-only table, same columns the store writes). Seeded: #1 TC Condor Running 1 (4 legs, priced), #2 TC Strangle Open (priced), #3 TC Unpriced Trade (24350 CE/PE have no close row: unpriced), #4 TC Completed Trade (opened and exited: Completed), #5 Wide Iron Condor 20x (name of exactly 20 characters).
- API: `tests_browser/r2_1128/serve_app.py` = the real `create_app` with `LIVE_MARKET=1`, but the market's socket is idle: it reports "connected" (as Kite's socket does on a weekend) and delivers no frame. No token is read and no Kite call is made. See "Decided for the owner" for why.
- Browser: `npm ci && npm run build`, `vite preview` on 4173 proxying /api to 8000; Playwright with the preinstalled Chromium; `tests_browser/r2_1128/shot.mjs <name> <path> [--btn X] [--click Y]` writes a JPEG (1366x768) and prints the page text and console errors.
- API restart for item 2: **03:18:09 IST** (after the seed; closes are read from the table at start).

## Decided for the owner
1. The brief says "no Zerodha session, no feed process". With NO stored session the real app never builds a market book: `LiveMarket.start` returns at "no active Kite session" before the stored close is read (`live_market.py` start, `last_close_store.start`). So with the real code and no session the seeded closes cannot reach any screen (see Defect D-1). To test every other screen "from the last close" I used the harness above: a book that exists, a socket that connected and is silent. No broker call. Both states are in screenshots (`I-10b-*` = no session, everything else = harness).
2. Paper fills were inserted by SQL because the route refuses paper orders after the close (that refusal is the intended rule; the plan's SW-6 line "Add to Paper ... the entry is the last captured price" conflicts with it: owner question, see "For the owner lane").
3. "One settled" strategy: not seedable (a settlement needs an expiry day); #4 is Completed by an exit order instead. Marked in item 2 below.

## Items

| # | Item | Result |
|---|---|---|
| 1 | I-10 | **PASS (with defect D-1 for the no-session case)**. Harness: `I-10-home.jpg` Home banner `Market closed. Prices are from 27 Nov 2026, 15:29:58 IST.` NIFTY 50 24187.35 / SENSEX 79234.50, each with `27 Nov 2026, 15:29:58 IST`, no "Not available". No session (`I-10b-home-no-session.jpg`): banner `Market closed.`, NIFTY 50 `Not available`, SENSEX `Not available`; Option Chain (`I-10b-chain-no-session.jpg`) shows the page with `Market closed.` and no strike values. |
| 2 | I-26 | In progress: restart 03:18:09 IST, then SW-1 PASS (`SW-1-home.jpg`), SW-4 / SW-5 / SW-6 / SW-7 / SW-9 show closes (see "Screen texts"), SW-2 and SW-3 to finish. |
| 3-10 | I-27, I-28, I-43, I-75, I-91, I-92, I-113, I-116 | Pending in this push; I-113 and I-116 first reads are in "Screen texts". |

## Screen texts (exact, after the restart)
- Banner on Home, Positions, My Strategies, Live Strategies, Option Chain, Builder (same line on all): `Market closed. Prices are from 27 Nov 2026, 15:29:58 IST.` There is no "Checked at" line on Home, Positions or My Strategies (it is a Live Strategies card feature in the plan; none seen here).
- Home: Running strategies 4, Unread alerts 0, `Total P&L (after charges)` `−2,733.83`, `Includes 1 closed strategy.`, `1 strategy left out: its price is not live.` Sum check: #1 +3,027.52 + #2 +1,381.23 + #5 −7,600.51 (My Strategies rows) = −3,191.76; plus closed #4 +457.93 = −2,733.83 = the Home figure. AF-04/AF-05 shape holds.
- My Strategies rows: `P&L +3,027.52 (after charges)` (#1), `P&L +1,381.23 (after charges)` (#2), `P&L — · Paper P&L paused - prices not live` (#3, unpriced), `P&L −7,600.51 (after charges)` (#5).
- Live Strategies: one banner at the top, `⏸ Monitoring paused`, `Health unknown`, `Not being watched: no worker has reported in the last 2 minutes.`, `estimated from spot`, leg LTP `147.50`, unpriced legs `-`.
- Positions (all): Real P&L `—` with `Connect your Zerodha account to continue. We'll use your Zerodha account to verify availability, check margin and prepare/execute your strategy.`; Paper P&L `−2,733.83 (after charges) Includes 1 closed strategy.`; leg LTP cells `147.50` with `15:29:58` under it; unpriced legs `no price`, `No price for: NIFTY 8 Dec 24350 CE, NIFTY 8 Dec 24350 PE.`
- Stops panel: `Paper - exits are recorded in the app, not sent to Zerodha`, `NIFTY last 24187.35 as of 15:29:58`.
- Option Chain: `NIFTY24187.35as of 15:29:58`, the 15 seeded contracts show their close, every other cell `-` and Change `not available`.
- Alerts Active `No alerts yet. Alerts start when strategy monitoring rules are added.`; History records `No stops or expiry settlements yet.`

## Defects found
- **D-1 (I-10, high): with no stored Zerodha session the stored close is never read.** Real app, 17 rows in `last_close`, restart, `GET /market/indices` returns `value: null, at: null` for both indexes; Home shows `Not available` twice (`I-10b-home-no-session.jpg`). Cause (read, not fixed): `main.py` `_lifespan` -> `LiveMarket.start` returns at `no active Kite session` before any book exists, and `last_close_store.start(market)` seeds only a book. Should: the held close is served from the table whether or not a session exists (the owner's session is gone after the close on most days). For the owner lane: `ofo_app/main.py`, `ofo_app/live_market.py`, `ofo_app/last_close_store.py` (a table-backed fallback reader for the index and contract routes when `market.feed is None`).
- **D-2 (SW-0): red console error on every Positions load**: `Failed to load resource: the server responded with a status of 409 (Conflict)` (the Real read with no Zerodha session, shown to the user as the red box `Connect your Zerodha account...`). The test plan counts a red console error as a fail.
- **D-3 (test database, environment): 4 of 56 store tests fail here**: `tests_app/test_migration_0059_last_close.py::test_m6_a_time_off_the_trade_date_or_after_the_close_is_refused_by_the_check[...]` x3 and `::test_a_snapshot_row_keeps_its_own_later_time_only_the_feed_writer_stops_at_the_close`: the database raises SQLSTATE `22000` where the test expects `23514`. 52 pass. Not looked into further (no product edit allowed); may be the date or this PostgreSQL build.
- **D-4 (plan vs build, SW-6)**: plan says `Add to Paper` after the close shows "the entry is the last captured price" with a tick box; the route refuses with MARKET_DATA_102. Owner decision needed which is right.

## For the owner lane
- D-1 files above.
- Plan SW-2 expects `Real P&L is not shown yet: the server does not price Zerodha positions.`; the build shows the Connect-Zerodha box with `—` (no old figure, so I-113 holds; wording differs).

## To file as deferred issues
- D-1, D-2, D-3 (this file's wording).

## Models
| task | model | minutes |
|---|---|---|
| everything (set-up, seeds, walk, write-up) | Sonnet (main lane) | running |
