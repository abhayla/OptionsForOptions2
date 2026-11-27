# Lane N, 27 Nov 2026: one source for "the price to show and its time"

Branch `fix/last-close-1127`, cut from `origin/hotfix/index-quote-1127` 2244298. Paper only; no broker order endpoint;
no migration; no PR; no GitHub issues. Highest status: **Fixed, not tested** (the owner's PC re-tests). DB route tests
could not run in this container (no PostgreSQL here): they are listed per item.

## Status lines (messages to the coordinator were refused: "elevated_session_untrusted_device")

- 16:10 IST LANE N ALIVE (send_message to @parent refused; lines kept here instead).
- First push: head = the commit that adds this file | gate: prepush on this head (see the commit's gate log) | re-test:
  the after-close and feed-down steps below.

## DECISION NEEDED FIRST (A1): the 15:30 closes are not stored anywhere durable

Finding (code read, 27 Nov): the ADR-330 (36) freeze lives only in the API process's feed book
(`backend/ofo/marketdata/feed_health.py`). An API restart after 15:30 empties it, and nothing re-creates it: Redis holds
only the tick stream (read from the newest entry after a restart), 10 s token snapshots and status keys; the
`history_minute_bars` table (migration 0009) exists but no running process writes it during the day (only
`history_finalize.py`, after the close, from Kite candles); no other table holds a per-contract close. So the exact (36)
figure cannot be recovered after a restart without a design decision. Options (not built):

| Option | What | Migration | Matches (36) exactly | Cost / risk |
|---|---|---|---|---|
| 1 (recommended) | A small table `last_close (instrument_id, trade_date, price, price_at)` written once at 15:30:00 by the feed book for every contract it holds, read at start-up when the market is closed | yes (one table) | yes | one writer at 15:30; needs a decision row and a migration number from the coordinator |
| 2 | Use the existing `history_minute_bars`: write held contracts' 15:29 bar at 15:30, read its close after a restart | no | nearly (the bar's close is the last trade up to 15:30) | the table's W-067 write rules apply; a writer must be wired into the API process |
| 3 | A Redis key per contract written at 15:30, kept until the next open | no | yes, until Redis restarts | lost on a PC reboot unless Redis persistence is on |
| 4 | After a restart, read Kite's one-minute 15:29 candle by REST | no | nearly | Kite historical rate limit, REST at start-up, REQ-118 budget |

Built meanwhile (A2): after a restart a held leg is priced from the FIRST frame it gets after the close, labelled with that
frame's own time, and that figure never moves until the next open. Honest about its time, but not the 15:30 figure.
Until a leg gets a frame it stays unpriced with its reason.

## Second decision for the owner (B2 / A4): entries outside market hours

The coordinator's brief asked for Add to Paper to follow ADR-330 (28) (tick box + as-of line) in every not-live state,
including after the close and before the open. ADR-212 says "A paper exit, entry or any fill stays refused outside market
hours", and the paper order route refuses with gate_market_closed before reading any price. The ADR wins (CLAUDE.md), so
built: in market hours with prices not live, the tick box and the line; after the close / before the open / on a holiday,
no tick box; Confirm sends once and the server's own market-closed sentence shows (the client holds no copy of it). If
the owner wants paper entries after hours, that is a SPEC CHANGE to ADR-212.

## Per item

| Item | Root cause (one sentence) | Fix | Tests (red first) | Status |
|---|---|---|---|---|
| A1 | The 15:30 close is held only in the API's memory, so a restart after the close leaves every contract with no close. | Decision above; interim through A2. | via A2 (`test_a1_fresh_book_after_a_restart...`) | DECISION NEEDED; interim fixed, not tested |
| B2 | `_index_spot_held` (adjustment_readers.py) required a fresh index tick for the entry's starting point, so a feed-down save was refused even after the user ticked the not-live line and typed his own price; it also ignored the (39) age rule when connected. | A new request field `prices_not_live_confirmed` (default false), sent only from the ticked box; with it the save uses the last held index value (any age), refusing only when no value exists; a fresh quote is health AVAILABLE only (the (39) rule). On a `paper_index_price_unavailable` refusal the dialog shows the tick so the user can send again (one action, one request). The value's time is NOT stored (no column; see deferred). | tests_app/test_entry_not_live_confirmed.py (unit, fakes), vitest per mount | Fixed, not tested. Tier A: FIX FIRST (tick never reached the server) -> fixed in A4's round 2. DB test tests_app/test_basket_facts_unheld_index.py not run here |
| A4 | The builder's live flag read only the builder reply's `market_closed`, so a reply without it or an index answer saying closed left Confirm active with no tick; the Drafts "Review and add" dialog had no tick at all. | One `priceNow` state in priceState.js (live / last_close / stale / unavailable) read by every Add to Paper mount; the dialog emits the tick; the flag is sent from the tick state only. | frontend/tests/price-state-now.test.js + 11 related files: 203 passed | Fixed, not tested |
| A2 | The freeze held only for a contract with a frame by 15:30, and the earlier-day rule ran only when a frame arrived, so a strike first read after the close (or every contract after a restart) moved, and an earlier day's close could be replaced or come back. | One function `_figure` in feed_health.py chooses every closed-market figure (price, depth, day values): the figure served first in a closed spell never moves until the next open; a frame made by that day's close wins if nothing was served yet; else the first frame after the close with its own time; else the contract's own last close with its date-time. The label dates a time from an earlier day. | tests/marketdata/test_close_freeze.py 24 passed (5 red first), tests/.../test_closed_label.py 10 passed; mutants: day check removed 12 failed, served-store disabled 3 failed | Fixed, not tested. Tier A round 1: FIX FIRST (F1-F4) -> fixed in round 2; DB route files test_closed_label_route.py / test_close_freeze_routes.py not run here |
| B1 / A5 | `pausedText` always appended ", as of" + the time, printing "Time not available" when there was none; the closed banner took its time from a partial reply while loading; Home's `as_of` is None when the paused leg's last quote time is gone (`snapshot.ended_times` is bounded). | One as-of formatter: the time when known, else no time clause; the banner shows no time until a complete reply; `as_of` is the last quote's own time, never an order time. | price-state-now, priceState, after-close-line-d64, tests/test_paused_as_of_quote_time.py (2 passed) | Fixed, not tested. A leg whose last quote time was evicted still shows the pause with no time (deferred) |
| A3 | Live Strategies showed the closed banner only after a child card's own reply said `market_closed`; an unpriced, queued or errored card never did. | The page reads GET /market/indices itself (as Index View does), re-read every 60 s. | frontend/tests/live-strategies.test.js | Fixed, not tested |
| C | `/market/indices` on a closed market with no socket holding the ids returned `value: null`, so Create Strategy said "Not available" instead of the last close (Lane J's 08:30 list fix is a separate cause). | `indices_read` fills the last close with its time (still marked stale); Create Strategy shows it under the shared banner; "Not available" only when no value is held. | tests_app/test_index_closed_market.py (2 red first), frontend/tests/create-strategy.test.js | Fixed, not tested. Open: whether the provider holds a close at 08:30 when no socket ever subscribed (PC check below) |
| B3 | The no-what-if text needs a reply carrying `target_not_live_text`; with no reply nothing shows. | Not changed; check under the PC's sweep. | none | Open |

## Sentences (pending owner read)

- "Market closed. Prices are from 15:30:00; 1 leg as of 26 Nov, 15:29:59." (only the date part is new; shown when a
  leg's time is from an earlier day)
- "Market closed. Prices are from 15:33:48; 1 leg as of 15:59:10." / "2 legs as of ..." (every leg first priced after
  the close at different times: the earliest time leads)
- "Paper P&L paused - prices not live" now shows with no ", as of ..." clause when no time is known (was "as of Time
  not available").
- The existing banner "Market closed. Prices are from <date>, 15:30:00 IST." now also on Live Strategies and the Create
  Strategy expiry step.
- The existing ADR-330 (28) line now also in the Drafts "Review and add" dialog, and after a paper_index_price_unavailable
  refusal.

## PC click steps

After the close, a later evening (market closed, API running since before 15:30):
1. Note one open paper trade's leg prices on Positions > Paper at 15:31. Wait to 15:45. Expected: the same figures, the
   banner "Market closed. Prices are from 15:30:00".
2. In the builder open the leg picker, open a strike with no leg. Watch it 2 minutes. Expected: the figure does not move;
   if it was first priced after 15:30 the banner says "1 leg as of HH:MM:SS".
3. Restart the API (as at 15:50 on 27 Nov). Reload Positions > Paper. Expected: legs priced "as of <first frame time>"
   (not "no live quote"); the figure does not move afterwards. (The exact 15:30 figure waits for the A1 decision.)
4. Live Strategies: expected the "Market closed. Prices are from ..." banner at once, also with a card still loading.
5. Builder: Add to Paper. Expected: no tick box; Confirm sends once and shows the server's market-closed sentence.
6. Paper panel: no "Time not available" anywhere; the banner never flashes a time other than the close while loading.

Monday before the open (08:00 to 09:15):
1. Create Strategy, pick NIFTY. Expected: the level from the last close under "Market closed. Prices are from <Fri date>,
   15:30:00 IST", not "Not available". If it still says "Not available", note the time and whether the strip shows a
   value (the open point under C).
2. Live Strategies and Positions > Paper: the banner and the close figures, each leg's time its own.

Market hours, feed stopped (as 27 Nov 15:06-15:12):
1. Stop the feed. Home: "Paper P&L paused - prices not live, as of <date>, <time> IST" (time of the last quote), or the
   sentence with no time if none is known; never "Time not available".
2. Builder: Add to Paper, type an entry price, tick "Prices are not live; the entry is the last captured price, as of
   HH:MM.", Confirm. Expected: saved; the entry is the typed price.
3. Same without ticking: Confirm stays grey.

## To file as deferred issues

| Title | Evidence | Spec basis | Done when |
|---|---|---|---|
| The 15:30 close is not stored durably | RESULTS-lane-n A1 | ADR-330 (36), ADR-212 | the owner's option is built and a restart after 15:30 shows the 15:30 figures |
| Entry facts do not keep the index value's time and kind | strategy_basket_facts (migration 0050) has no column | ADR-330 (28), (39) | nullable spot_at / spot_kind columns, written on a confirmed save |
| A confirmed save accepts an index quote flagged as faulty | adjustment_readers.py `_index_value_not_live` checks only ltp > 0 (Tier A B2 F2: a crossed quote returns 24000.05) | ADR-200 (4) | validation_errors refuse, as read_last_close does |
| First-fill entry facts take a stale index value without the tick | adjustment_readers.py `entry_facts_now` has no health check; record_basket_facts returns before the index check when the adjustment count cannot be read or a non-option leg is open (Tier A B2 F3) | ADR-330 (28), (39) | the same health rule on every path that stores entry_spot |
| The last-close branch of the confirmed save is unreachable from the route | paper.py may_act refuses gate_market_closed first (Tier A B2 F4) | ADR-212 | remove the branch or the owner changes ADR-212 |
| A first-after-close frame stamped on a weekend or before the open is labelled with the previous close's time | quote.py `price_at` F-19 rule (Tier A A2 F4) | ADR-330 (36) | the label shows the frame's own time |
| depth_after_close now returns the frozen frame's depth | feed_health.py (A2) | ADR-330 (36) | owner confirms the depth popup after hours shows the close's depth |
| A paused leg whose last quote time was evicted shows no time | `snapshot.ended_times` is bounded | REQ-109 AC-5 | the last quote time is kept per open leg |
| "Checked at Time not available" and Index View "Last updated <Time not available>" remain | checked-at.test.js, IndexViewPage.vue | REQ-049 AC-4 | the shared as-of formatter used there |
| The builder's confirmPending and PaperStrategies' Add to Paper have no own vitest for the flag | only the dialog emit and SaveDraftBar tests | ADR-330 (28) | a mount test each |

## Task | model

| Task | Model |
|---|---|
| Split, route, verify, report (this file) | Opus (coordinator session) |
| Root-cause search, backend and frontend | Sonnet (2 read-only helpers) |
| Test environment set-up, first gate run, Exit-path revert | Haiku |
| A2, B2, A4/A5/B1, A3/C builds (2 rounds each where reviewed) | Sonnet (4 builders) |
| Tier A reviews of A2 and B2 (price and order-entry paths) | Opus |
| Merges, pre-check, gate | Sonnet |
