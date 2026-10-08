# Builder brief: W-062 one-minute history, live first, final from Kite's candles

Core: on the real 2026-10-08 frames, one-minute bars built by the recorder equal Kite's own candles for the same
minutes on close and OI, and the 15:09 minute lost to the laptop's network drop is filled from Kite's candle and marked
backfilled.
Proof (step 1, before anything else): `tests/history/test_minute_bars_replay.py` replays
tests/fixtures/kite_history/frames-2026-10-08-0920-0924-8tok.bin.gz and frames-2026-10-08-1506-1512-8tok.bin.gz
through the merged W-059 `KiteProvider` (instrument list tests/fixtures/kite_ws/instruments-2026-10-08-subscribed.csv;
see tests/marketdata/_kite_fixture.py for the replay pattern) into the bar builder, and compares the full minutes
(09:20-09:23 and 15:06-15:11; the first and last minute of each window are partial) with
tests/fixtures/kite_history/candles-2026-10-08.json. Assert: OI equal on every full minute of every option; the 15:09
minute absent from the live bars for all 8 instruments; and print the per-instrument close/OHLC/volume match counts
into the test's failure message. Then write the exact expected values for a few minutes as literal Decimals from the
candles file (never from running your code).

Budget: 60 min wall-clock, 90 tool calls. Commit step 1 green before steps 2-5; at budget stop after a commit and
report done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`).
Tier: B.

## Spec basis
- REQ-051 AC-2: "No complete tick-by-tick history is stored for every option (Q168)."
- REQ-051 AC-3: "Tiers: real-time, aggregated intraday (1-minute/5-minute), daily, strategy snapshots (active user strategies
    only). Derived metrics are computed on demand, or materialised only when expensive or useful; they are not stored
    for every timestamp (Q168; T2 #102)."
- REQ-051 AC-4: "Aggregated history is built from the live feed where practical and licensed (Q169); a separate historical
    provider can plug into the same abstraction (Q99)."
- REQ-051 AC-5: "Historical data and simulation never block live strategy creation, Option Chain, execution or monitoring
    (Q101 owner note, Q180)."
- ADR-067 (live bars provisional; after the close every minute replaced by Kite's candle from the same user's own
  connection; a minute Kite lacks keeps the live bar; a feed gap filled from Kite's candles marked backfilled, never
  live; 5-minute on demand; daily derived from the final one-minute bars; no raw ticks kept; source and exact paise on
  every bar; a day not made final stays provisional and says so). ADR-066 (internal use only, no user screen). F-34.
- Copy from: legacy-reuse map row `app/models/eod_option_snapshot.py` (ADAPT) - the Decimal field shape only. The
  builder and finalize logic are new.

## What to build
1. **Bar builder (backend/ofo/history/bars.py, stdlib):** a frozen `MinuteBar(instrument_id, minute, open, high, low,
   close, volume, oi, source)` - `minute` is the timezone-aware IST start of the minute; prices `Decimal`; `volume`
   int (contracts traded in that minute) or None for an index; `oi` int or None; `source` a closed enum
   LIVE / BACKFILLED / KITE. `MinuteBarBuilder.on_quote(NormalizedQuote)` returns the bars that closed.
   - Bucket by `quote.timestamp` (the exchange timestamp; F-34 measured this as good as or better than last-trade time).
   - Index quotes (`instrument_type is None`): every quote's `ltp` is a price point.
   - Options: a trade is a quote whose cumulative `volume` rose since the previous quote of that instrument; only
     trades move open/high/low/close; the bar's volume is the sum of the rises inside the minute; OI is the last OI
     seen in the minute (also from quotes with no trade). The first quote of an instrument seeds the cumulative volume
     and is not a trade.
   - A minute with no trade for an option produces no bar (Kite's candles skip such minutes too).
   - Quotes whose health is not AVAILABLE/live are not used for prices (W-059 health); count them.
   - `flush(now)` closes every open minute that ended at or before `now`.
2. **Kite candles (backend/ofo/history/candles.py, stdlib):** parse Kite's `/instruments/historical/<token>/minute`
   body with `json.loads(text, parse_float=Decimal)` (F-33: never through float) into `MinuteBar`s with source KITE.
   A `MinuteCandleSource` protocol (`minute_candles(instrument_id, start, end) -> list[MinuteBar]`) is the separate historical
   provider abstraction of REQ-051 AC-4; an in-memory fake for tests.
   App adapter (backend/ofo_app/kite_history.py): the HTTP call for the owner's own connection, behind the protocol,
   tested with the recorded bodies through a fake transport (no live call in tests). The token is never logged.
3. **Finalize and gap fill (backend/ofo/history/finalize.py):** `finalize_day(live, kite)` - per ADR-067, every minute
   Kite has becomes the KITE bar; a minute only in `live` stays LIVE; returns the day plus counts (replaced, kept
   live, kite-only). `fill_gaps(live, kite, gaps)` - minutes inside a recorded feed gap (from the W-059 feed-state
   events: disconnected/stale intervals) are filled from Kite's candles as BACKFILLED; a minute also present live
   inside a gap is replaced (the stale 15:08 close of F-34). `five_minute(bars)` and `daily_bar(bars)` derive on
   demand (open first, high max, low min, close last, volume sum, OI last); never stored by this item.
4. **Store port and recorder (backend/ofo/history/store.py, recorder.py):** `HistoryStore` protocol accepting only
   `MinuteBar` (structurally no way to store a quote or tick - AC-2) with `put_bars`, `bars(instrument_id, day)`,
   `day_status(day)` (PROVISIONAL / FINAL); `InMemoryHistoryStore`. `Recorder` listens on the W-059 `FanOut` for
   exactly the ids the feed already carries (never subscribes anything new; ADR-067) and writes closed bars. Any
   exception from the store is caught, counted and logged without values, and never propagates into the fan-out
   (AC-5); a test with a store that raises proves another listener still gets every quote.
5. **No raw ticks (AC-2):** a test asserts the store and recorder hold no `NormalizedQuote`/`RawTick` after a replay
   (only `MinuteBar`s, at most one per instrument per minute per source).

## Standing items (run-discipline B4) and reviewer checklist
- (a) the recorder adds no work on the fan-out's hot path beyond one dict update per quote; prove with the replay that
  the fan-out's delivered count to another listener is unchanged with the recorder attached.
- (d) every answer state of Kite's candle fetch: candles returned; empty list (no trades - keep live); HTTP error or
  timeout (day stays PROVISIONAL, counted, no exception into callers); malformed body (refuse, stays PROVISIONAL);
  a candle for a minute outside the requested range (ignored, counted).
- Mutation tests first: count the first quote as a trade; use received time instead of exchange time; mark a gap fill
  LIVE; let `finalize_day` keep a LIVE bar where Kite has one; let the store accept a quote. Each must turn a test red.
- Money Decimal at every boundary; JSON numbers parsed from text; no float anywhere in history/.
- Kit CI stays green: tests/ imports no ofo_app; app tests go in tests_app/; no wall-clock asserts.

## Rules
- Branch `build/W-062-history` from origin/main. Do not edit kit files or spec/. Never write `evidence/`. Never mark
  anything verified. Targeted tests while building; the full domain suite once at the end (summary line only, output to
  a log file). Run `python tools/ci_local.py` once before the push. Commit, push, report.
