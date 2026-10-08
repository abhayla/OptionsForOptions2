# Builder brief: W-059 Kite market-data adapter, provider interface, internal fan-out

Core: the real Kite frames in tests/fixtures/kite_ws/frames-2026-10-08-092000-10s.bin.gz parse into normalised
quotes that match the values in work/W-059.md `proof`, for every contract that ticked.
Proof (step 1, before any interface, fan-out or app code): `tests/marketdata/test_kite_frames_fixture.py` replays the
fixture with the instrument rows beside it and asserts the exact values in the work item's `proof` (NIFTY 50
22,533.25; NIFTY26O1322550CE ltp 124.95 bid 124.20 ask 124.35 OI 2,679,040; ...), 7,301 ticks, 3 heartbeats, 983
contracts. Commit it green before step 2.

Budget: 60 min wall-clock, 80 tool calls. Commit after each stage; at budget stop after a commit and report done / not
done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`).
Tier: B.
Class: staleness by a contract's own age - any health rule that marks a quiet but current contract stale while its
feed is live (registry `staleness-by-last-change-age`).

## Spec basis
- REQ-048 AC-2: "The provider sits behind an interface offering: live quote stream, option-chain snapshot, instrument/contract
    master, underlying quote, futures quote, optional historical data, health/status, source metadata."
- REQ-048 AC-3: "A provider can be replaced, added as a secondary/fallback, or extended to new exchanges without changing
    product-domain logic (Q98)."
- REQ-048 AC-4: "Provider streams are shared and fanned out internally; there is no vendor subscription per user"
- REQ-049 AC-2: "Each quote has a health state: available, stale, delayed, unhealthy or unavailable"
- F-29 (spec/findings.md): bid/ask only in depth, 0 = absent, never a Rs 0 price; times get IST attached; no OI-change
  field. F-32: one connection carried 1,091 instruments; the feed's longest market-hours gap was 0.51 s; a median 59
  contracts had no tick for over 60 s while the feed was live.
- Copy from: legacy-reuse M3 rows `ticker/adapter_base.py`, `ticker/pool.py`, `ticker/router.py`, `ticker/models.py`
  (ADAPT), `ticker/adapters/kite.py` (ADAPT), `market_data/rate_limiter.py` (COPY). Pin `websockets==16.0` from
  algochanakya@bf9faf7 `backend/requirements.txt` in requirements-app.txt.

## Stage 1 - domain (backend/ofo/marketdata/, standard library only)
1. `kite_frames.py`: parse a binary frame (int16 packet count, then per packet int16 length and bytes; big-endian;
   1-byte frames are heartbeats; packets 8 = ltp, 28/32 = index, 44 = quote, 184 = full with 10 depth entries
   (qty int32, price int32, orders int16, 2 pad); prices / 100 for NFO/BFO/NSE/BSE segments). An unknown packet
   length is counted and skipped, never guessed. Step 1's test.
2. Normalisation into the existing `NormalizedQuote` (W-018): identity from the catalogue's per-broker table
   (instrument_token is Zerodha's broker token, ADR-050/W-056: load the fixture's instrument rows through the existing
   Zerodha parser); bid = depth buy[0], ask = depth sell[0], 0 -> None; exchange timestamp (epoch seconds) -> aware IST
   datetime; oi_change None (Kite has none); IV and Greeks None here. Index packets (NIFTY 50, SENSEX, INDIA VIX) are
   exposed as underlying quotes keyed by their broker token; their catalogue segments come in W-060 (REQ-072), so keep
   the index mapping in one small table W-060 will replace.
3. **Staleness by feed state (defect-fix contract).** RCA: `health.py` marks a quote stale when its timestamp is older
   than `stale_after` (60 s), but Kite sends nothing for an unchanged contract. Class: every contract on a live feed
   that has not changed for longer than the threshold (on the fixture: the 108 of 1,091 that sent nothing in 10 s;
   live: a median 59, max 354, F-32). Failing test first on the real function: replay the fixture, advance the clock
   61 s with the feed still live (heartbeats arriving) -> no contract may be stale (red today). Fix: a quote's health
   follows its feed's state - available while the feed is connected and a data frame or heartbeat arrived within
   FEED_STALE (3 s, about 6x the 0.51 s measured gap); stale for every contract of that feed beyond it; unavailable
   when disconnected beyond the reconnect window or the session has ended. The contract's own last-change time is
   kept as information (`last_changed_at`), never a health input. Real-data proof: the replay with an inserted 5 s
   gap -> all 1,091 stale, then available after data resumes. Detection: the replay test is the guard; set the
   registry entry's `detection.status` to "guarded" naming that test.
4. `provider.py`: the `MarketDataProvider` interface with the REQ-048 AC-2 operations (historical data and futures
   quote may raise NotSupported in V1). Domain code depends on this interface only.
5. `fanout.py`: one provider stream fanned out to N in-process subscribers; one vendor subscription per instrument no
   matter how many subscribers. Test (AC-4): replay the fixture to 1,000 subscribers; each receives every update in
   order; the provider's subscribe call count is 1 per instrument; count work, not time.
6. AC-3 test: a second, fake provider replaces Kite and the same domain consumer code (fan-out, health) runs
   unchanged; no import of the Kite module anywhere outside the adapter (an import test).

## Stage 2 - app (backend/ofo_app)
- `kite_ws.py`: the live client (websockets 16.0): connect `wss://ws.kite.trade?api_key=..&access_token=..`, send
  `{"a":"subscribe","v":[tokens]}` and `{"a":"mode","v":["full",[tokens]]}` (at most 3,000 per connection),
  reconnect with backoff 1, 2, 4 ... 30 s and re-subscribe; an HTTP 403 on connect ends the session (no retry) and
  reports "session ended". Never logs the URL or the token (the W-058 rule). Never places or sends an order.
- Tests with a fake WebSocket server: re-subscribe after a drop; 403 stops; the URL never appears in a log record.

## Standing items (run-discipline B4) and reviewer checklist
- (d) every answer state of Kite's socket: data frame, heartbeat, text message (order update or error - count by
  type, store nothing personal), unknown packet length, close, 403 at connect, network error; each has a stated
  behaviour and a test.
- Expected values from the fixture and the work item, never from running the new code.
- Money and prices as Decimal from integer paise (`type(x) is Decimal`).
- Kit CI stays green: tests/ imports no app packages; no wall-clock asserts (inject a clock).
- Do not touch backend/ofo/marketdata/disconnect.py or backend/ofo/errors/ (W-024 builder works there).

## Rules
- Branch `build/W-059-kite-adapter` from origin/main. Do not edit kit files or spec/. Never write `evidence/`.
- Copy work/W-059.md, docs/process/brief-W-059.md and tests/fixtures/kite_ws/* from the main checkout
  D:\Abhay\Ventures\OptionsForOptions2 (Read them) into your branch as the first commit.
- Domain suite + `python -m pytest -c pytest-app.ini -q` once at the end, output to a log file, tail only.
- Commit and push the branch; report the worktree path, branch and commits.
