# Lane N, 27 Nov 2026: one source for "the price to show and its time"

Branch `fix/last-close-1127`, cut from `origin/hotfix/index-quote-1127` 2244298. Paper only; no broker order endpoint; no
PR; no GitHub issues. Highest status: **Fixed, not tested** (the owner's PC re-tests). No PostgreSQL in this container: every
DB test is listed per item and must run on the PC (`python scripts/orchestrator/db_run.py . python -m pytest -c pytest-app.ini
<file>`).

## For lane K (read first)

`backend/ofo_app/routes/paper.py:1321` and `:1404` call `entry_facts_now(...)` without the user's not-live confirmation. Since
the third push, `entry_facts_now` stores a live index value only through the one price rule and a not-live one only when
confirmed, so a ticked first fill while the index quote is STALE stores `entry=None` (fails closed: rolls refused with
`adjust_roll_entry_spot_unknown`, T-12 `missing_entry_spot`; nothing defaults). It is PERMANENT for that strategy
(`strategy_entry_facts` keeps one row per strategy; `record_first` never rewrites it). Change each call to
`entry_facts_now(ctx, underlying, sold, confirmed=body.prices_not_live_confirmed)` (and give `entry_facts` a `confirmed`
parameter if the call goes through it). `routes/execution_return.py:301` (real fills) has no confirmation and stays as is.
Tier A (Opus) review of the third push: SHIP, with this as its one MAJOR.

## Status lines

- 16:10 IST LANE N ALIVE (send_message refused until the owner allowed this session at about 16:55; sent then).
- First push: A2, A3, C, A4, A5, B1, B2 + gate fixes | gate: prepush PASS on that head | re-test: the after-close steps.
- Second push (this file's head): migration 0059 `last_close` + its module + the one-time seed command, ADR-330 (56) notice,
  picker freeze proof, `next_open_at` | gate: prepush PASS on that head | re-test: step 0 then the restart walk below.
- Second push head b6777ce7 (gate PASS).
- Third push (this file's head): one rule for the index value (a flagged / crossed / UNHEALTHY / non-positive index quote is
  refused with its reason, also when confirmed; a STALE valid one only on the tick; first-fill entry facts through the same
  rule); live pushes carry only what the feed book serves (never the raw frame, also during the seed wait); the Option
  Chain last-trade test; the faster gate (chore/gate-speed-1127) merged | gate: prepush PASS on that head.
- Option Chain "Last trade 15:39:59" (PC AX-05 note): already covered by the A2 freeze; the line reads QuoteBook._frame via
  chain_push._last_trade_at -> depth_after_close. Test: tests_app/test_chain_live.py::
  test_lane_n_chain_row_keeps_the_by_the_close_price_and_last_trade_after_a_later_frame.

## For the combined build (Lane Z)

- Migration **0059_last_close**, `down_revision = 0057_history_delete_entries`. With 0058 (plan acceptance) kept out of the
  weekend build, the build has exactly one head (`0059_last_close`). If 0058 lands later, whichever lands second re-points its
  `down_revision`. 0059 has never been pushed before this push nor applied anywhere; its CHECKs are final as first applied.
- Files of other lanes touched by Lane N (first push): `frontend/src/pages/StrategyBuilderPage.vue` (lane V owns it now): A4/A5,
  26 lines: the builder reads the one price state (`priceNow`) and mounts the index answer earlier; the closed banner takes its
  time only from a complete reply; Add to Paper passes the tick flag. `PaperStrategies.vue`, `HomeOverviewPage.vue`,
  `MyStrategiesPage.vue`: not changed by Lane N in either push.
- Changes Lane N needs in files it does not own: `docs/design/next-batch-2026-11-26/lane-n-for-lanes-v-l.md` (For lane V:
  the exact `PaperStrategies.vue` diff for ADR-330 (56) tile greying, with its 2 tests; For lane L: nothing needed).
- For lane U2 (ADR-330 (60)): GET /market/indices and its socket push now carry `next_open_at` (ISO, the next 09:15 IST open
  from the app's calendar; null while open or when the calendar has no next year), e.g. Fri 27 Nov 16:00 ->
  `"next_open_at": "2026-11-30T09:15:00+05:30"`.
- Paper-only path found: none. One price-read exemption added (tests/test_price_reads_one_door.py):
  `adjustment_readers.py::_index_value_not_live`, because the read door returns a price only when live and a confirmed
  not-live entry (ADR-330 (28)) needs the last held index value.

## Decision row text (proposed; the coordinator records it)

"The platform keeps each contract's and each index's last close of every trading day in one table, `last_close`, written a few
seconds after 15:30:00 from the last price the feed delivered at or before 15:30:00 (ADR-330 (36)), only if the app was
running at the close. While the market is closed, a restart reads the stored close back and every screen shows it with its own
date and time; if no close was stored for the last trading day the screens say prices are not available with the reason, and
an older day's close is shown only with its date. The stored close is never read while the market is open (the first live
tick wins), it never replaces a price the feed itself delivered that day, and the same module serves paper and real, indices
and contracts."

## Old-code-safe proof (migration 0059)

0059 adds one table (`last_close`) and grants on that table only (SELECT; INSERT; UPDATE of price, price_at, source; no DELETE
or TRUNCATE). It changes no existing table, column, constraint, trigger, function or grant, and does not rebuild the grant
allow-list function. No code before this push reads or writes `last_close`. So old code runs unchanged with the table present;
new code on an un-migrated database logs one error per write or read and serves no stored close (fails closed: "not
available"). Migrate-first and migrate-last are both safe. The PC applies it only with a verified backup.

## Open questions for the owner (decided meanwhile, reversible)

1. ADR-330 (36) says the close is the last price "received up to 15:30:00". The book uses the tick's exchange time: a tick
   stamped 15:29:59 that arrives at 15:30:03 counts as the close. Recommended: keep (the trade happened before the close; only
   the delivery was late).
2. Paper entries outside market hours: the brief asked for the ADR-330 (28) tick box after the close and before the open too;
   ADR-212 refuses every paper entry outside market hours and the route refuses first (gate_market_closed). Built to the ADR:
   the tick box in market hours only; after hours the server's market-closed sentence shows. A SPEC CHANGE to ADR-212 if the
   owner wants after-hours paper entries.
3. Once a price is shown after the close it never moves until the next open (A2 review, owner away): recorded as the rule;
   an earlier day's price carries its date ("1 leg as of 26 Nov, 15:29:59").

## Per item

| Item | Root cause (one sentence) | Fix | Tests (red first) | Status |
|---|---|---|---|---|
| A1 / AF-02 | The 15:30 close lived only in the API's memory, so a restart after the close left every contract unpriced. | Table `last_close` (0059) + one module `backend/ofo_app/last_close_store.py`: written once after 15:30 from the book's by-the-close frames; read while closed and seeded into the book (`QuoteBook.seed_close`); a book waits up to 30 s for its first seed so a read in that window never freezes a post-close frame; re-login seeds the new book; one-time seed command for tonight's snapshot. | tests_app/test_last_close_store.py, _seed_*.py (144 passed, fakes); tests_app/test_migration_0059_last_close.py (DB, PC) | Fixed, not tested. Tier A: store FIX FIRST -> SHIP; seed FIX FIRST -> fixed (round 2) |
| A2 / AF-01 | The freeze held only for a contract with a frame by 15:30, so a strike first read after the close moved. | One function `_figure` (feed_health.py) for every closed-market figure: the first figure served in a closed spell never moves until the open. The leg picker reads through it (proved). | tests/marketdata/test_close_freeze.py (24); tests_app/test_picker_closed_freeze.py | Fixed, not tested. Monday 15:30 check below |
| B2 | `_index_spot_held` required a fresh index tick, so a feed-down save was refused even after the tick and a typed price. | `prices_not_live_confirmed` sent only from the ticked box; the save then uses the last held index value; refused only when none exists; the (39) age rule applies when connected. | tests_app/test_entry_not_live_confirmed.py | Fixed, not tested (DB test test_basket_facts_unheld_index.py on the PC) |
| A4 | The live flag read only the builder reply's `market_closed`; the Drafts dialog had no tick. | One `priceNow` state for every Add to Paper mount; the dialog emits the tick. | frontend/tests/price-state-now.test.js + 11 files | Fixed, not tested |
| B1 / A5 | `pausedText` printed "as of Time not available"; the banner took a partial reply's time; `as_of` lost the quote time. | One as-of formatter (no time clause when unknown); banner time only from a complete reply; load times say "Checked at". | priceState tests, tests/test_paused_as_of_quote_time.py | Fixed, not tested |
| A3 / AX-05 | Live Strategies showed the closed banner only after a child card's reply said closed. | Page-level market answer. | frontend/tests/live-strategies.test.js | Fixed, not tested |
| C | `/market/indices` returned no value on a closed market with no socket, so Create Strategy said "Not available". | Last close with its time. | tests_app/test_index_closed_market.py, frontend/tests/create-strategy.test.js | Fixed, not tested |
| ADR-330 (56) | Each tile repeated the not-live sentence. | One `PriceNotice` at the top (layout mount for My Strategies; page mounts on Home strip, Index view, Live Strategies, Positions); tiles greyed; one affected -> only it carries the line. Positions Paper tiles need lane V's diff. | price-scope-adr330-56, strip-notice-adr330-56, layout-notice-adr330-56 | Fixed, not tested |
| B3 | The no-what-if text needs a reply carrying `target_not_live_text`. | Not changed. | none | Open |

## Sweep rows (PC, 27 Nov after the close, PR #722 comment 7216769012)

| Screen | Finding | Status |
|---|---|---|
| Home | banner 15:58:01 (feed-stop time), SENSEX "Not available", Total P&L dash | fixed by the stored close (the close time and figures come back after a restart); Total P&L: lane L |
| Positions Real | no banner | fixed (PriceNotice on PositionsPage) |
| Positions Paper | all "no price"; no banner; Exit with Confirm enabled | prices: fixed by the stored close; banner: fixed; tile greying: lane V diff; Exit: lane U |
| Live Strategies | "Checked at" load time moves | fixed (hidden under the notice) |
| My Strategies | no banner; "Select all 16 shown" over 17 | banner fixed (layout mount); 16/17 by design (REQ-070, only deletable rows) |
| Builder #209 | "as of Time not available"; "As of 16:13:47" load time; "Rule not checked" x17 | first two fixed; "Rule not checked": lane J (PlanWatch) |
| Option Chain | every LTP "- not available" | fixed by the stored close for held contracts; strikes never held keep "not available" with the reason |
| Alerts History | "The page could not get an answer from the server." | not mine (lane O) |
| Stops panel | "Index values unavailable."; Save disabled | index line fixed (PaperStops.vue reads the strip's answer); Save: plan save path (lanes J/R) |

## Sentences (pending owner read)

- "Prices are not live. Figures are as of HH:MM:SS IST." / "Prices are not live." (no time known)
- "Market closed. Prices are from 15:30:00; 1 leg as of 26 Nov, 15:29:59." (an earlier day's price carries its date)
- "Market closed. Prices are from 15:33:48; 1 leg as of 15:59:10." / "2 legs as of ..."
- "Checked at HH:MM:SS IST" (load / check time lines; "As of" is only a price's time)
- "NIFTY last 25,607.20 as of 15:58:01" (Stops panel, closed market)
- "Paper P&L paused - prices not live" with no ", as of" clause when no time is known
- The existing banner "Market closed. Prices are from <date>, 15:30:00 IST." also on Live Strategies, Create Strategy, Positions,
  My Strategies; the existing ADR-330 (28) line also in the Drafts "Review and add" dialog and after a
  paper_index_price_unavailable refusal.
- Seed command output lines (operator text, not product screens).

## PC steps (market closed, weekend)

Step 0, before any restart (tonight's snapshot, 17 rows expected: 15 open contracts + NIFTY 50 + SENSEX):
1. Take a verified database backup. Apply the migration: `alembic upgrade head` as usual (one head: 0059_last_close).
2. Run the DB tests: `python scripts/orchestrator/db_run.py . python -m pytest -c pytest-app.ini
   tests_app/test_migration_0059_last_close.py tests_app/test_basket_facts_unheld_index.py tests_app/test_close_freeze_routes.py
   tests_app/test_closed_label_route.py`. Expected: all pass.
3. Dry run: `set PYTHONPATH=backend` then `python -m ofo_app.last_close_store seed
   D:\Abhay\Ventures\ofo-snapshots\close-2026-11-27.json --check`. Read: the "database: host:port/dbname" line is the
   production database; "keys in the first row" and "mapping chosen" (price <- the tick price, price_at <- the tick's own
   time, never an export time); "first row" shows a 27 Nov 15:30:00 +05:30 time. Expected: "would write 17", "skipped 0". If a
   field is reported twice, re-run with `--map price_at=<key>` (or `price=`). If a row is skipped, read its reason.
4. Real run: the same command without `--check`. Expected: "written 17", "unchanged 0", "skipped 0", then the restart line.
   A second run prints "written 0", "unchanged 17".

Restart and walk (after step 0; market closed):
1. Restart the API. Within 30 s open each screen; expected on every one: the banner "Market closed. Prices are from 27 Nov 2026,
   15:30:00 IST." and the 27 Nov 15:30 figures; no "no live quote", no "Time not available", no load or feed-stop time
   labelled as a price time.
   - Home: NIFTY and SENSEX at their 27 Nov closes; paper rows priced.
   - Positions Real and Paper: the banner; the 9 running paper trades priced (tile greying waits for lane V).
   - Live Strategies: the banner at once, also while a card is loading; no moving "Checked at".
   - My Strategies: the banner at the top.
   - Builder #209: legs at the close; the panel "as of" is a price time; a load time, if shown, says "Checked at".
   - Option Chain: held contracts priced at the close; other strikes "not available" with the reason.
   - Leg picker: a strike with no leg shows one figure that does not move over 2 minutes.
   - Stops panel: "NIFTY last <close> as of 15:30:00" (not "Index values unavailable.").
   - Add to Paper: no tick box; Confirm sends once and the server's market-closed sentence shows.
2. Restart the API again: the same figures and times (read back from the table, not re-written).
3. Stop the feed while the API runs: the banner keeps the close time, never the stop time.

Monday 30 Nov, before the open (08:00 to 09:15):
1. Create Strategy, NIFTY: the level from Friday's close under the market-closed banner, not "Not available".
2. Positions Paper and Live Strategies: Friday's figures with their own times.
3. At 09:15:00 the first live tick replaces each figure; the banner goes; no stored price shows after the open.

Monday 30 Nov, across 15:30 (AF-01):
1. At 15:28 open the builder's leg picker on a strike with no leg and note its price and time; keep a paper trade open.
2. At 15:31 to 15:40: the picker strike and every held leg keep the figure of the last tick at or before 15:30:00 (or, for a
   strike first opened after 15:30, its first figure with its own time); the header "Market closed"; nothing moves.
3. At 15:31 run in the DB: `select count(*) from last_close where trade_date = '2026-11-30'`. Expected: one row per held
   contract and index (written at about 15:30:05).
4. Restart the API at 15:45: the same figures, from the table.

Market hours, feed stopped:
1. Home: "Prices are not live. Figures are as of <time> IST." once at the top (the last quote's time); tiles greyed.
2. Builder: Add to Paper, type a price, tick "Prices are not live; the entry is the last captured price, as of HH:MM.",
   Confirm: saved at the typed price. Without the tick Confirm stays grey.

## To file as deferred issues

| Title | Evidence | Spec basis | Done when |
|---|---|---|---|
| Entry facts do not keep the index value's time and kind | strategy_basket_facts has no column | ADR-330 (28), (39) | nullable spot_at / spot_kind written on a confirmed save |
| The last-close branch of the confirmed save is unreachable | paper.py refuses gate_market_closed first | ADR-212 | remove it or the owner changes ADR-212 |
| A first-after-close frame stamped on a weekend or before the open is labelled with the previous close's time | quote.py `price_at` F-19 rule | ADR-330 (36) | the label shows the frame's own time |
| An older-day leg label can take a newer leg's group | outcome.py ~299-306: legs TUE 15:29:59, MON 15:29:59, TUE 15:31:10 -> "2 legs as of 30 Nov, 15:29:59" | ADR-330 (36) | each leg's own day in the label |
| Option Chain banner time comes from the index spot only | chain_push.py `label_time(state, (spot_at,))` | ADR-330 (36) | the chain label uses the rows' own times |
| A seed answered after 09:15 is still applied to an empty book (hidden, replaced by the first tick) | last_close_store.py ~320 uses the pre-read time | ADR-212 | the open is checked after the read |
| The calendar ends 31 Dec 2026 | from 1 Jan 2027 no write and no seeding | ADR-119 | the 2027 calendar loaded |
| Start-up after the close could rebuild the close from the Redis stream | ofo:feed:owner:ticks outlives an API restart (coordinator, 27 Nov) | ADR-330 (36) | considered with the table as the durable copy |
| depth_after_close returns the frozen frame's depth | feed_health.py | ADR-330 (36) | the owner confirms |
| A paused leg whose last quote time was evicted shows no time | `snapshot.ended_times` is bounded | REQ-109 AC-5 | the last quote time kept per open leg |
| "Checked at Time not available" remains | checked-at.test.js | REQ-049 AC-4 | the shared formatter used there |
| The builder's confirmPending has no own vitest for the flag | only the dialog emit and SaveDraftBar tests | ADR-330 (28) | a mount test |

## Task | model

| Task | Model |
|---|---|
| Split, route, verify, report (this file) | Opus (coordinator session) |
| Root-cause search, backend and frontend | Sonnet (2 read-only helpers) |
| Environment set-up, gate runs, Exit-path revert, slot pin | Haiku |
| A2, B2, A4/A5/B1, A3/C, ADR-330 (56), last_close store + seed, picker / next_open_at builds | Sonnet (builders; 2 rounds where reviewed) |
| Merges, pre-check fixes, gate | Sonnet |
| Tier A reviews: A2, B2, store (2 rounds), seed command | Opus |

## Third push, Tier A minor findings (deferred)

| Title | Evidence | Done when |
|---|---|---|
| The index rule repeats the AVAILABLE check inline | adjustment_readers.py ~:970 instead of calling priced() (agrees today) | one call |
| Decimal NaN as ltp raises InvalidOperation instead of a refusal | is_live_price on both paths (Kite whole-paise frames cannot produce it) | a refusal with its reason |
| The seed-wait push path has no committed test with a real QuoteBook | test_push_is_what_the_book_serves.py fakes book.get | a real-book test |
