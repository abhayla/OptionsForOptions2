STATUS 23:05 | section 1: pushed (gate PASS, 837670d) | rest: complete, Opus review of sections 2 and 5 applied, gate running | next push when the gate passes

# Market on demand: replay a recorded market day (design, Lane D2, 27 Nov 2026)

Design only. No product code was changed. Sections 2 and 5 had one independent Opus review (verdict REVISE, ten findings); every finding is applied in the text, marked "Opus review" where it changed a claim. Times are IST. Cloud-session messaging to the coordinator was refused
(`elevated_session_untrusted_device`), so this top line is the report.

**Plain summary of section 1.** The feed already writes every price message it receives, untouched, into a Redis list
(`ofo:feed:owner:ticks`). That list is trimmed to the newest 20,000 entries (about 83 minutes). A small reader that runs
all day on the PC and appends each entry to a file BEFORE it is trimmed is enough to keep a whole market day. The file
format already exists in the repo (`iter_recording`), so a saved day can be played back by code that is already written
and tested. The script below needs no change to the app. I ran it here against a throwaway Redis with 200 real frames
from the 8 Oct fixture: output was byte-identical, and a restart added no duplicates.

## 1. What must be recorded

### 1.1 What the stream holds (verified by reading)

| Fact | Source |
|---|---|
| Stream key `ofo:feed:<user_ref>:ticks`, for the owner `ofo:feed:owner:ticks`. | `backend/ofo_app/feed_bus.py:81` |
| Each entry has `u` (user), `k` (kind: frame / connected / dropped / reconnected / ended), `t` (the time the FEED received it, epoch microseconds) and, for a frame, `d` = the raw Kite bytes, unparsed. | `feed_bus.py:3-4`, `encode_message` `feed_bus.py:116-120` |
| Capped at 20,000 entries per user, trimmed with `maxlen=..., approximate=True`. | `feed_bus.py:44`, `:558` |
| Every instrument is subscribed in Kite mode **full** (one mode only). A full packet is 184 bytes and carries last price, volume, open interest, day open/high/low/previous close, exchange time, and five bid and five ask levels (order-book depth). Index packets (28 or 32 bytes) arrive in the same frames. | `backend/ofo_app/kite_ws.py:306`; packet layout `backend/ofo/marketdata/kite_frames.py:11-15, 93-124` |
| The set of instruments wanted is a Redis key `ofo:feed:owner:want` (and `:want:bg` for the background worker), JSON `{"u":..,"tokens":[...]}`, with a 10 s expiry. | `feed_bus.py:84-85, 214-215` |
| The feed status (connected, last frame time) is the key `ofo:feed:owner:status`, 5 s expiry. | `feed_bus.py:88-89, 547-548` |
| A recording file format already exists: gzip of repeated `>qI` (receive time in nanoseconds, frame length) then the frame. `iter_recording` reads it, and `replay_mode._load_recording` plays one through `KiteProvider.on_frame`. | `kite_frames.py:16-17, 173-185`; `backend/ofo_app/replay_mode.py:48-52` |

So one stream entry of kind `frame` already holds everything a replay needs: the raw bytes (prices, depth, index
values) and the feed's own receive time. Converting an entry to the recording format is `t * 1000` (microseconds to
nanoseconds) plus the bytes.

### 1.2 What to record, in plain words

1. **Every frame** (raw bytes + receive time): ticks in full mode, index values and order-book depth ride inside.
2. **Every non-frame event** (connected, dropped, reconnected, ended) with its time. Needed so a replay can reproduce a
   feed drop, which is exactly what makes stop alerts go wrong. The existing file format cannot hold them, so they go
   in a sidecar `events.jsonl`.
3. **The instrument list of that day** (token, symbol, expiry, strike, lot size, tick size). Prices are meaningless
   without it. Same CSV columns as `tests/fixtures/kite_ws/instruments-2026-10-08-subscribed.csv`. Exported once at
   09:00 from the app's database with a read-only SELECT (see 1.5).
4. **The wanted-token snapshots and feed status, once a minute** (`side.jsonl`), so a replay knows which tokens were
   subscribed when.
5. **The exchange calendar facts**: nothing to record. The calendar is dated data in the repo
   (`backend/ofo/market_calendar.json`: NSE F&O holiday list, fetched 2026-10-19; it lists 24 Nov and 25 Dec as the
   late-2026 holidays, so Monday 30 Nov is a trading day). Record only the file's git commit id in the day's folder
   name or a `README`.

Not recorded in v1 (and why it is acceptable): Kite REST history (minute candles), margins, broker reads and orders.
A stop test needs prices only. History for charts can be added later from a one-off fetch.

### 1.3 How big is one day (measured, with honest limits)

Two real recordings exist in the repo (8 Oct 2026, owner's feed). I measured both with the repo's own parser:

| Sample | Frames | Seconds | Frames per second | Raw bytes per frame | Tokens in it | After gzip |
|---|---|---|---|---|---|---|
| `kite_ws/frames-2026-10-08-092000-10s` (opening burst) | 43 | 9.7 | 4.4 | 31,336 | 983 | 2.4x smaller |
| `kite_history/frames-2026-10-08-0920-0924-8tok` | 1,123 | 260 | 4.3 | 346 | 8 | 3.3x smaller |

Owner's PC on 27 Nov: 20,000 entries from 14:34:58 to 15:58:00 = 4,982 s, so **4.0 entries per second** (about 241
per minute), the same rate as the 8 Oct samples. A recorder window of 09:00 to 15:35 is 23,100 s, so **about 92,000
entries a day** (the exchange sends about one frame every quarter second whatever the instrument count; more
instruments make each frame bigger, not more frequent).

**Measured on the PC (coordinator, 27 Nov 21:14, file read there, not by me):** 20,000 entries, 14:34:58 to 15:58:00,
about 241 per minute, 116.4 MB as JSON lines = **5,820 bytes per entry** (frame bytes saved as base64; 18,459 of the
20,000 entries carry binary `d`, the other 1,541 do not carry one I could classify: events or one-byte heartbeats, [Guessing]).
Only **17 instruments** were subscribed (15 open contracts plus NIFTY 50 and SENSEX). Base64 adds one third, so the raw
frame is roughly 4.2 KB, [Likely], and a full 375-minute day is about **90,000 entries, roughly 380 MB raw and 115 to 160
MB gzipped** (gzip ratio 2.4x to 3.3x measured on the repo's two samples). The coordinator's own figure for base64 JSON
lines is 525 MB a day. The recorder below stores raw bytes, so it is the smaller number. This replaces the guesses in
the table that follows for a day like 27 Nov; with more instruments the day grows in proportion (table).

Note for the 27 Nov file: the morning is gone (the cap overwrote it), the catalogue keeps no list versions, and so the
instrument rows must be saved WITH each recording (done by the `instruments.csv` step in 1.5).

The table below shows what the size would be for other subscription sizes. Bytes per entry depends on how many instruments the PC
had subscribed on the day; I could not measure it from the repo.
Range for a day of 92,000 entries:

| Instruments subscribed | Bytes per frame (about 186 per tick) | Raw per day | Gzip per day |
|---|---|---|---|
| 8 | 350 | 32 MB | 10 MB |
| about 200 (a few expiries of one index) | 7,500 | 0.7 GB | 0.3 GB |
| about 1,000 (full chain, two indices; the opening burst rate) | 31,000 | up to 2.9 GB | up to 1.2 GB |

The 1,000 row is an upper bound (the 10 s sample is the busiest moment of the day, and many ticks repeat). **The
measured 17-instrument figure is the one to plan on.** At the worst case a year of trading days
(about 250) is under 300 GB gzipped, which fits an ordinary disk; at the likely case it is tens of GB.

### 1.4 Where it is stored

Not in this repo: prices are licensed exchange/broker data. [Likely] Kite's data terms do not allow handing it on;
I did not read the licence text, so the owner should confirm before anything is shared. Recommendation: on the owner's PC at
`D:\Abhay\Ventures\market-days\<YYYY-MM-DD>\` (next to the competitor study folders, same "never in the repo"
rule), with `.gitignore` untouched because nothing there is inside the repo. A cloud session can only use a day if
the owner uploads that one folder to the session by hand or from private storage; do not add it to the repo or to an
artifact.

**Finding for the owner (not acted on):** the repo already holds real 8 Oct recordings
(`tests/fixtures/kite_ws/frames-2026-10-08-092000-10s.bin.gz`, `tests/fixtures/kite_history/frames-2026-10-08-*.bin.gz`,
`instruments-2026-10-08-subscribed.csv`, `candles-2026-10-08.json`). If the licence rule above is real, those are
already in a public repo. See open question Q1.

### 1.5 The Monday 30 Nov recorder (no product code changed)

What it does: reads the Redis stream with a blocking read from its own saved position, so nothing is skipped while it
runs, and appends each entry to disk. Tested here: 200 real frames, output byte-identical to input; killed mid-run,
every finished batch still readable (each batch is its own gzip member); restarted, no duplicates; Redis down, it
waits and resumes. **One thing found while testing:** the Redis client's default socket timeout equals the 5 s block
time, so the script sets 30 s; without it, the first run failed with `TimeoutError`.

Run on the PC (the app's own Python, which already has `redis`), started before 09:15 and stopped after 15:35:

```
python record_day.py --redis redis://localhost:6379/0 --out D:\Abhay\Ventures\market-days
```

Rules for the day: start it by **09:00**; leave it running; Ctrl+C after 15:35. The stream holds only ~83 minutes, so the recorder must not be off for more
than about an hour. The first entries in the file may be the previous session's tail (the stream is not emptied
overnight): their `t` stamps say so, and a replay keeps only the day's 09:00 to 15:35. If the Redis on the PC has a
password, put it in the URL (`redis://:password@localhost:6379/0`). If `--user` is not `owner`, pass it.

The day's instrument list, one read-only SELECT against the app's database, saved to `instruments.csv` in the same
day folder (run once at about 09:05; columns match the fixture CSV; I did not run it, it needs the PC's database; the
broker filter is not applied because the stored broker name was not verified):

```
psql "$DATABASE_URL" --csv -c "SELECT bi.broker_token AS instrument_token, cc.exchange_token, bi.broker_symbol AS tradingsymbol, cc.name, 0 AS last_price, cc.expiry, cc.strike, bi.tick_size, bi.lot_size, cc.instrument_type, bi.broker_segment AS segment, cc.exchange_segment AS exchange FROM public.catalogue_contracts cc JOIN public.broker_instruments bi ON bi.contract_id = cc.id WHERE NOT cc.retired AND NOT cc.delisted AND cc.currently_listed AND NOT bi.retired" > instruments.csv
```

(Tables and columns: `backend/ofo_app/models.py:47-70, 75-90`. Data on Windows: if `psql` is not installed, the same
SELECT can be run from any SQL client and exported as CSV.)

Check at 15:40: `frames.bin.gz` is more than a few MB; `side.jsonl` has about 380 lines; the last line's `frames` is
near 92,000 (more if the feed was busier than on 27 Nov). A playback check with the repo's own reader:
`python -c "import gzip,sys; sys.path.insert(0,'backend'); from ofo.marketdata.kite_frames import iter_recording as i; print(sum(1 for _ in i(gzip.open(r'D:\...\frames.bin.gz'))))"`.

The script (44 lines):

```python
"""Save the owner's Redis feed stream to disk, untrimmed. Reads only; writes only under --out. No product code touched.
   python record_day.py --redis redis://localhost:6379/0 --out D:\\Abhay\\Ventures\\market-days   (stop: Ctrl+C after 15:35)"""
import argparse, datetime, gzip, json, os, struct, time
import redis  # the app's own dependency, already on the PC

ap = argparse.ArgumentParser()
ap.add_argument("--redis", default="redis://localhost:6379/0")
ap.add_argument("--user", default="owner")
ap.add_argument("--out", required=True)
a = ap.parse_args()
ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
day = datetime.datetime.now(ist).date().isoformat()
d = os.path.join(a.out, day); os.makedirs(d, exist_ok=True)
key = f"ofo:feed:{a.user}:ticks"
idf = os.path.join(d, "last_id")
last = open(idf).read().strip() if os.path.exists(idf) else "0-0"      # restart-safe: resume after the last saved entry
r = redis.Redis.from_url(a.redis, socket_timeout=30)  # longer than the 5 s block below
fpath = os.path.join(d, "frames.bin.gz")   # gzip members appended batch by batch: a crash keeps every finished batch readable
                                           # format = ofo.marketdata.kite_frames.iter_recording
events = open(os.path.join(d, "events.jsonl"), "a", encoding="utf-8")  # connected / dropped / reconnected / ended
side = open(os.path.join(d, "side.jsonl"), "a", encoding="utf-8")      # wanted tokens + feed status, once a minute
n = nxt = 0
while True:
    try:
        got = r.xread({key: last}, count=1000, block=5000)
        buf = bytearray()
        for _, entries in got:
            for eid, f in entries:
                eid = eid.decode(); k = f[b"k"].decode(); t = int(f[b"t"])   # t = feed receive time, epoch microseconds
                if k == "frame":
                    buf += struct.pack(">qI", t * 1000, len(f[b"d"])) + f[b"d"]; n += 1
                else:
                    events.write(json.dumps({"id": eid, "k": k, "t": t}) + "\n")
                last = eid
        if buf:
            with open(fpath, "ab") as fh: fh.write(gzip.compress(bytes(buf), 6)); fh.flush(); os.fsync(fh.fileno())
        events.flush(); open(idf, "w").write(last)
        if time.time() >= nxt:
            nxt = time.time() + 60
            side.write(json.dumps({"at": time.time(), "frames": n, "last": last,
                "want": [(x or b"").decode() for x in r.mget(f"ofo:feed:{a.user}:want", f"ofo:feed:{a.user}:want:bg")],
                "status": (r.get(f"ofo:feed:{a.user}:status") or b"").decode()}) + "\n"); side.flush()
    except (redis.RedisError, OSError) as e:      # Redis down: wait and carry on from the saved id; never exit during the day
        print("redis problem, retrying:", type(e).__name__); time.sleep(2)
```

Gaps and doubling (asked by the coordinator): the script reads with `XREAD` from the last saved entry id (`last_id`, written after every batch
is on disk). A Redis stream id is unique and increasing, so a restart resumes exactly after the last saved entry: no loss while the gap is
under the cap (about 83 minutes at 241 per minute; about 20 minutes if 1,000 instruments were subscribed), no doubling ever. If the gap is longer
the first entry read has an id far past `last_id`; the `side.jsonl` line and the entry `t` stamps show the hole. I tested the resume (second run added 0 entries).

What the entry fields mean (from `feed_bus.py:3-4, 116-120`): `u` user, `k` kind, `t` the feed's receive time in epoch microseconds,
`d` the raw Kite WebSocket message. The decoder is `ofo.marketdata.kite_frames.parse_frame` (called from `KiteProvider.on_frame`; `KiteProvider` is
fed the same bytes by the live socket and by `replay_mode._fed_provider`), so a replay that feeds `d` to a stand-in Kite socket reaches the real parser at the same point.

Why a plain file reader and not a change to the app: the app already publishes the full raw record to Redis for its own
use (ADR-012: the feed process holds the vendor connection; browsers and the rest never do), so a second reader on that
bus adds no vendor connection and no new write path.

## 2. The replay side

**Plain summary.** To replay a day the app must believe it is that day, at that time, and hear prices from a stand-in
exchange instead of Zerodha. Most of the app already asks for the time as an input ("what time is it?" is passed in),
so one shared replay clock can be plugged in at a few places. Four places cannot be reached today (database stamps,
the browser's own clock, two background timers, and the test feed launcher). The hard part is not the clock; it is
making it impossible for a replay to be mistaken for the real thing.

### 2.1 The clock: how every part of the app learns "now"

Inventory by a Haiku helper (grep-led, then I checked the entries that matter: `background.py:253`, `may_act.py:68-104`,
`scenario_mode.py:725-835`, `feed_launcher.py:44-51`). Rows marked "unverified" were not opened.

| Class | Where | Takes an injected clock? | Today under `APP_ENV=test` |
|---|---|---|---|
| Stop worker | `Worker(clock=...)`, `background.py:897-911`; every check does `now = self._clock()` (`:1348`) | **Yes** | `_serve_scenario` passes the scenario clock (`:2030-2049`). The live path builds `datetime.now(IST)` inline (`:2065`), so a replay needs a third branch next to `_serve_scenario`/`_serve_live`. |
| "Market closed, skip" | `feed_state` -> `market_closed_for(provider, now)` (`background.py:253`, `feed_health.py:204-210`) | **Yes** (`now` is an argument; no wall clock in `market_calendar.py` or `feed_health.py`) | Nothing to change. Replay day must be a trading day in `market_calendar.json` (2026 only; another year answers `NO_CALENDAR` = closed). |
| `may_act` gate (ADR-212) | `may_act(ctx, action, at)`, `market_open(ctx, at)` (`may_act.py:68-104`); there is no function named `gate_market_closed`, only the constant `:41` | **Yes** (`at` argument) | Routes give `at` from the request's answer clock (`routes/outcome.py:155-157` `get_answer_clock`, "tests override this dependency"). `scenario_mode.overrides` already swaps it (`scenario_mode.py:739`). |
| Feed, feed bus, Kite socket | `KiteSocket(clock=)`, `BusSocket(clock=)`, `FeedRelay(clock)`, `run_feed(clock=)` (`kite_ws.py:105`, `feed_bus.py:261`, `feed_main.py:104`) | **Yes** | `tests_app/feed_launcher.py:44-45` hard-wires `datetime.now(IST)`: the launcher needs a replay variant. Cadence timers (`time.monotonic()` at `feed_bus.py:338-350, 417`, `feed_main.py:346-348`) are NOT injected: they run in real seconds, which is correct for pacing but means "status refresh every 0.5 s" is wall time at 10x. |
| Paper stop/trigger monitor | `paper_monitor.py:68, 202-204` use `ctx.clock()` of the LiveMarket context | **Yes in form only** | that context's clock is the INLINE `datetime.datetime.now(IST)` in `live_market.py:170-171` (it feeds the KiteProvider, the BusSocket and the LiveFeed context, `:99-105`). Overriding only the answer clock is not enough: `may_act` would pass at replay 13:28 while prices and the stop monitor are judged on wall time (on a Saturday `market_open` is false, stops never fire; exits refuse `tracking_exit_prices_not_live`). The seam must sit inside `live_market._launch` (a production file). |
| Paper fills, exits, limits | `paper_exit.py`, `paper_book.py`, `paper_limit.py`, `ofo/tracking/paper*.py` | read no clock (times arrive as arguments; grep-based, not confirmed function by function) | no change expected |
| Paper settlement | `paper_settlement.py:244-248` | optional parameter, default `datetime.now(UTC)` | needs the replay clock passed in |
| API routes | `routes/outcome.py:133-157` `server_now()` is wall clock; `get_answer_clock` is the one seam | **Yes, through `Depends`** | `scenario_mode.overrides` is the model. Unverified: `routes/paper.py:1824` calls `now()` when there is no context. |
| Other inline wall clocks (Opus review) | `worker_watch.py:154`; margin clock `server_now` (`live_market.py:466`, `background.py:2088`); `catalogue.get_shown_now` (`scenario_mode.py:799-806`) | no | each needs the replay clock or is switched off in replay |
| Other wall-clock defaults | `paper_settlement.py:248`, `actionable_alerts.py:323`, `adjustment_readers.py:214, 702`, `ofo/entitlements/ledger.py:56`, `daily_candles.py:28`, `kite_period_reads.py:40`, `broker_sync.py:16`, `catalogue_refresh.py:124`, `history_finalize.py:95`, `live_market.py:170, 269` | optional or no | each needs the same replay clock or is accepted as real time (see 2.1.1) |
| **Database stamps** | `clock_timestamp()` / `now()` in migrations and models (`models.py:31, 62-94`; migrations 0001, 0002, 0003, 0007, 0008, 0019, 0031 ...; `audit_store.py:53`, `charge_rates_store.py:28`, `freeze_store.py:30`, `paper_store.py:54`) | **No** | Rows get the real time. Also `catalogue_load.run` judges expiry on the database clock unless `as_of` is passed: I loaded the 8 Oct list into the test database: `added=2` (everything else was already expired on 27 Nov) and `added=1090` with `as_of=2026-10-08 09:00`. |
| **Browser** | `displayFormat.js:161, 174`, `LiveStrategyCard.vue:56, 66, 133`, `SettingsPage.vue:82` use `Date.now()` / `new Date()` | **No** | Server as-of strings and stale flags are server-driven. A page that compares "now" in the browser needs Playwright's own clock (`page.clock`), set to the replay time. |
| `pinned_clock` (`pinned_clock.py`, `config.py:36-57`) | the catalogue's "today" only | partial | does not reach worker, feed, paper or outcome paths |
| `replay_mode` (`OUTCOME_REPLAY`) | outcome route only; clock fixed at the last frame (`replay_mode.py:55-57`) | n/a | too narrow; shows one instant, not a day |
| `scenario_mode` (`OFO_SCENARIO`) | whole app but a stepped snapshot: clock = the scenario's, frame index in `public.scenario_frames` (`scenario_mode.py:810-835`). Only the two REAL order routes are refused; the five PAPER order routes (incl. `/strategies/{id}/tracking/exit`) are allowed on a strategy whose `scenario_id` matches (`scenario_mode.py:81-94`, `scenario_guard.py`) | **Yes** | Not usable for a moving day for two other reasons (Opus review): its provider is a stepped snapshot, not the real feed, and `require_no_live_market` refuses `LIVE_MARKET` (`main.py:178`, `background.py:2127`), so the paper stop monitor and settlement never run under a scenario. Its two-list order guard is the model to copy. |

#### 2.1.1 Proposed seam (one function, one file)

`ofo_app/replay_clock.py` (new, test/dev only): `now()` returns `anchor_day_time + (wall_now - wall_anchor) * speed`,
read from a small JSON file named by `OFO_REPLAY_ANCHOR` and re-read when its modification time changes (the same
pattern as `holdback.py`). Every process (API, worker, stand-in feed) computes the same answer from the same file with
no network between them; "jump to 13:28" and "pause" are one rewrite of that file; "10x" is one number. Plug-in points:
the `get_answer_clock` override (only the clock, not the whole context as `scenario_mode.overrides` does, because the real `LiveMarket` stays), a clock
argument into `live_market._launch` (`:170-171`), `worker_watch.start_if`, the `main.py` lifespan wiring, a third branch in `background._serve`
that hands the replay clock to the KiteProvider, the BusSocket AND the Worker (as `_serve_live` does at `background.py:2063-2071`), and a
replay variant of `feed_launcher.clock`. **Do not change the `paper_settlement` / `actionable_alerts` defaults** (`:248`, `:323`): a
production default that consults a file named by an environment variable puts a replay branch on every production call that omits the
clock. Pass the clock from the wiring instead (`main.py:101`), and add a source-scan test (like `tests/test_no_order_placement.py`) that
only the replay launch selector imports `replay_clock`.

What stays real time (accepted, and listed so nobody is surprised): database row stamps, Redis expiry (`want` 10 s,
`status` 5 s), the feed's own cadence timers, and the browser unless Playwright's clock is set. Consequence at 10x: a
status key written every 0.5 s of real time covers 5 s of replay time; feed-health windows are judged in replay seconds,
so at 10x a feed that is merely slow can read "stale". Stop-fix tests should therefore run at 1x; 10x is for walking to
the minute of interest.

**Whole-machine alternative, tried:** `libfaketime` (installable here with `apt-get update && apt-get install -y libfaketime`).
`FAKETIME="@2026-11-30 09:14:50"` made Python's `datetime.now()` and `time.time()` read the shifted date (1x only; sleeps
stay real). `redis-cli` under the preload hit "Unexpected recursive calls to clock_gettime()" and did not return;
my "x10" speed-up settings did not speed anything up in two tries; PostgreSQL was not tried. It would cover database
stamps without code changes, but it is fragile and cannot jump. Treat as a possible helper for database stamps only,
not as the clock.

### 2.2 The stand-in feed

What exists: `tests_app/feed_launcher.py feed <config.json>` runs the REAL `feed_main.run_feed` over the REAL
`KiteSocket` against any `ws_url` (`feed_launcher.py:57-58`), inside the egress gate's test mode, loopback only
(`feed_launcher.py:28-31`, "the only place that enters the egress gate's test mode"); `KITE_WS_URL` is refused under
`APP_ENV=test` unless it is a local fake (`config.py:33`); `tests/test_feed_caps.py` and `tests_app/test_feed_restart_core.py`
serve frames with a ~20-line `websockets.serve` handler. I ran `test_feed_restart_core.py` here: 1 passed in 17 s with
Redis and PostgreSQL started (real feed process, fake Kite socket, real bus, real API-side reader).

What a replay needs on top (all under `tests_app/` or `scripts/`, nothing in `backend/`):

1. **`replay_kite_server.py`**, a WebSocket server that speaks Kite's side: accepts the connection, reads the
   `subscribe` and `mode` messages the real socket sends (`kite_ws.py:304-306`), then sends recorded frames.
2. **Pacing**: frame i is due at replay time `recv_ns_i`; the server waits until `replay_clock.now()` reaches it. At 1x that is
   real speed; at 10x ten times faster; paused: undefined until measured (Opus review): with every process on the paused replay clock, health ages never grow so nothing reads stale, and the
   feed's silence watchdog (`kite_ws.py:79, 187-189`) may instead drop the link, which reads DISCONNECTED; do not promise "stale" for a pause.
   Sleeping by the clock, not by a fixed delay, makes a speed change take effect at once.
3. **Only what was subscribed**: send only subscribed tokens (rewrite the packet count: the logic is already in
   `holdback.filter_frame`, Lane Q2, `origin/test/live-day-gaps-1127`).
4. **Jump to 13:28 (forward only within a run)**: a backward jump is not safe: `BusSocket` drops frames at or before its floor (`feed_bus.py:356-358`), recorded reconnects at or before the last one are ignored (`:379`), a heartbeat more than 120 s ahead reads UNREADABLE (`:201-202`), and the worker keeps `max(kept, now)` (`background.py:1340`). To repeat a minute, restart every process and clear the user's `ofo:feed:*` keys and the heartbeat. A forward jump or 10x also breaks the closed-market reconnect wait (computed in replay seconds, slept in real seconds, `kite_ws.py:196-222`). The anchor file carries a generation counter read on every call (not mtime alone), so processes cannot disagree about the time for long. Mechanism: binary-search an index of (receive time, file offset) built once per day file. The app then
   holds no price for any contract until that contract's next tick (a quiet strike may not tick for minutes), so a
   naive jump leaves legs "unpriced". Fix: before the target, send in one burst the LAST packet of each subscribed
   token since the start of the day ("pre-roll"), then continue at pace. The cost is one pass over the file, once.
5. **Feed events**: the recorded `dropped` / `reconnected` / `ended` events (`events.jsonl`) are replayed by closing and
   re-accepting the socket at those times, so a real drop of the day can be reproduced.
6. **Hold-back rules** (silence a token, silence the index, delay a route) from Q2's `holdback.py` apply on top, so one
   recorded day can be replayed "clean" and then again with the index silenced for 70 s.

### 2.3 Paper fills

ADR-212 refuses a paper entry, exit or fill outside market hours (`may_act.py:41, 88-96`: market closed -> `gate_market_closed`).
Under replay no rule changes: the answer is computed from the replay clock and the calendar, so at replay time 13:28 on
a trading day the market is open and the gate allows, and at 15:31 it refuses exactly as live. The fill price is the
replay quote, and a quote is "live" only if the feed's state reads available at the replay time (ADR-015), so a stale or
withheld price refuses with the same `tracking_exit_prices_not_live` as live. Two traps: (1) `OFO_SCENARIO` must not
be used for a moving day (it forbids `LIVE_MARKET`, so the paper stop monitor never runs; see the table in 2.1); (2) the calendar file has holidays for 2026 only
(`market_calendar.json`, fetched 2026-10-19), so a recorded day from 2027 or 2025 reads closed.

### 2.4 What must be impossible, and what makes it so

**Correction after the Opus review (my first draft was wrong here).** The egress gate does NOT stop Kite REST calls. It allows
loopback, the database endpoint, the Notifier address and any Kite door call after its URL check, in every mode
(`ofo/broker/egress.py:13-39, 204-220`); test mode only allows spawning named programs and lets doors take a test transport
(`egress.py:193-197`); `tests_app/conftest.py:43-44` enters test mode as well as the launcher. The real API also cannot run the
paper stop monitor without `LIVE_MARKET`, and `LiveMarket.start` refuses to start without the owner's stored token
(`live_market.py:141-148`); with a token it calls Kite REST (positions every cycle and on each `reconnected` event `:175-224`,
margins `:425-466`, the index quote `:492`). So the broker wall must be built, not assumed.

| Must be impossible | Separation (hard, not a convention) | Decisions served | Exists today? |
|---|---|---|---|
| A replay reaches a broker or data vendor over REST | (a) no stored token in `ofo_replay`; (b) a replay-only API launch that starts the `BusSocket` WITHOUT a token, and every Kite REST door (`KiteReads`, `KiteMargin`, `kite_history`, index quote) refuses in replay mode before it sends; (c) the replay worker branch has no `stored_login`, no `margin_of`, no `daily_iv`; (d) a test that counts zero connects to the Kite API host over a full replay | ADR-012, ADR-029, ADR-016 to ADR-019 | None of (a) to (d): new, part of step 2 |
| A replay reaches the Kite socket | the replay launcher accepts only `ws://127.0.0.1` or `ws://[::1]`; the existing check refuses only a URL starting `wss://ws.kite.trade`, and only when `LIVE_MARKET` is on under `APP_ENV=test` (`config.py:64-65`, `live_market.py:71-73`): a weak guard | ADR-029 | Weak; strengthen in the launcher |
| A live order from a replay | every REAL order route refuses in replay (as `REAL_ORDER_ROUTES` do in scenario mode, `scenario_mode.py:81-84`); paper routes allowed only on a strategy carrying the replay marker (`scenario_guard.py` pattern); an unclassified mutating route fails start-up (`unclassified_mutating_routes`) | ADR-002, ADR-016 to ADR-019 | Pattern exists; replay version new |
| A replay sends the owner a real alert (Opus review) | `NOTIFIER_URL` egress is allowed in every mode (`egress.py:17-18`, `config.py:48-52`); `worker_watch` runs in bus mode on wall-clock market hours and a replayed heartbeat is hours old, so it reads STALE (`feed_bus.py:190-204`): on a weekday morning a replay would send a real "worker stopped". Replay start-up refuses a non-empty `NOTIFIER_URL`/project/key, and `worker_watch` runs on the replay clock or is off | ADR-286 | New |
| A replay figure shown as live to a real user | `APP_ENV=test` only: the settings validator refuses the replay setting elsewhere (as `OUTCOME_REPLAY`, `config.py:60`); the process starts only when the database name ends `_replay`, a `replay_marker` row exists AND the Redis database index holds a marker key; every API answer carries `X-OFO-Replay: <date>`; the frontend shows a fixed, non-dismissable banner "REPLAY of 27 Nov 2026, not live" on every screen. "Local host" proves nothing: `CLAUDE.md` says the owner's host serves production | ADR-003, ADR-015, ADR-177, ADR-330 (58) | Validator pattern yes; banner, header, markers new |
| Replay data in a production or shared store | separate PostgreSQL database `ofo_replay`; a dedicated Redis database index with a marker key, checked at start-up. A key namespace does NOT separate: `KEY_PREFIX` is a constant (`feed_bus.py:42`) and `heartbeat_key()` is global (`feed_bus.py:181-183`), so a replay worker on a shared Redis would overwrite another worker's heartbeat | ADR-012, ADR-048, ADR-029 | New guard in the launcher |
| Replay paper trades counted as real or reconciled with Zerodha | no broker token, so broker reads fail as "unavailable" (the real failure state); no reconciliation runs; rows live only in the replay database | ADR-016 to ADR-019 | By construction once the above hold |
| A real price file outside the test machine | day files live outside the repo (1.4); the launcher reads a path from the environment | licensing | policy; Q1 |

Redis TTLs are safe (Opus review): the `want` key (10 s, refreshed every 1 s) and the `status` key (5 s, written every 0.5 s) both
run on real monotonic time, and the API never judges the status key's age (it only reads that the key is present and says
connected, `feed_bus.py:235-255, 394-409`), so speed and jumps do not make the real API read the feed as down.

ADR-330 (58) (paper and real order doors behave the same): as named in the brief; I did not find that item number in the ADR-330
text on this base, so I cite it as given. Replay exercises the PAPER door only, so a replay pass proves paper exit behaviour and
the shared price/market rules (`may_act`), not the real order door.

## 3. Running it in a cloud session: what I tried (read-only on code; services in this container only)

**Plain summary.** Everything below the browser works in a cloud session today (with a dummy token-less API; the replay-only launch is new work): PostgreSQL, Redis, the database
structure, the real feed process talking to a fake exchange, the API, the built screens, and one browser test. What is
missing is the glue: a replay clock, a replay stand-in exchange, a seed of the day's trades, and the banner.

Commands, in order, with what happened (container: 4 cores; no repo file changed; database `ofo_test` and Redis here are throwaway):

| # | Command (abridged) | Result |
|---|---|---|
| 1 | `pg_ctlcluster 16 main start` | **Worked.** PostgreSQL 16 online on 5432. |
| 2 | `redis-server --port 6379 --save "" --appendonly no --dir /tmp/... --daemonize yes` | **Worked.** (the recorder test used port 6390) |
| 3 | `su postgres -c "psql -c \"CREATE ROLE ofo_admin LOGIN SUPERUSER ...\" -c \"CREATE DATABASE ofo_test OWNER ofo_admin\""` | Worked. |
| 4 | `python -m alembic -c backend/ofo_app/alembic.ini upgrade head` with `ALEMBIC_DATABASE_URL=...ofo_admin...` | **First try failed:** `app role allowlist refused for ofo_app: role does not exist (ADR-048)`. The migration checks that the limited role exists first. After `CREATE ROLE ofo_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE` the upgrade ran to head (57 migrations). |
| 5 | `TEST_DATABASE_URL=...ofo_app... TEST_ADMIN_DATABASE_URL=...ofo_admin... python -m pytest -c pytest-app.ini tests_app/test_pinned_clock.py` | **37 passed in 3.7 s.** Do NOT use `scripts/orchestrator/db_run.py` in a cloud session: it reads `D:\Abhay\GLOBAL.env` and an SSH tunnel to the host that serves prod (its own docstring, and `CLAUDE.md`); set the variables by hand as here. |
| 6 | `python -m pytest -c pytest-app.ini tests_app/test_feed_restart_core.py` (Redis up) | **1 passed in 17 s.** A real feed process, a fake Kite socket, the real bus and an API-side reader, all in this container. This is the nearest thing to the replay stack that already runs. |
| 7 | Catalogue seed with the day's list: `catalogue_load.run(conn, csv_text, as_of=...)` on the 8 Oct fixture CSV, in a rolled-back transaction | Worked, with a catch: without `as_of` only 2 of 1,091 rows were added (the rest were already expired on today's database clock); with `as_of=2026-10-08 09:00 IST` 1,090 were added. A replay must pass the replay day as `as_of`. |
| 8 | `uvicorn ofo_app.main:create_app --factory --port 8000` with `APP_ENV=test` | **First try failed:** `broker routes refuse to start: missing KITE_API_KEY, KITE_API_SECRET, KITE_REDIRECT_URL, FRONTEND_ORIGIN, KITE_EXPECTED_USER_ID, BROKER_TOKEN_KEY`. With six dummy values (a random 32-byte urlsafe key for `BROKER_TOKEN_KEY`) it started: `/health` -> `{"status":"healthy","database":"connected"}`. |
| 9 | `cd frontend && OFO_API_TARGET=http://127.0.0.1:8000 npx vite preview --port 4173` (the build exists after `npm ci` and the gate's build) | **Worked;** `/api/health` through the preview returned healthy. |
| 10 | `PW_CHROMIUM_PATH=/opt/pw-browsers/chromium npx playwright test e2e/health.spec.ts --trace off --project desktop-1280` | **1 passed, 1 failed.** The failure is the "API unreachable" case: it needs the second preview on 4174 pointed at a closed port (`frontend/README.md:12-13`), which I did not start. So the browser, the preview, the proxy and the API are connected. |
| 11 | libfaketime (see 2.1.1) | Partly worked (Python date shifted, 1x only). |

Not tried, so not claimed: a seeded set of paper trades (needs the routes or a store-level seed; not read in
depth), the stand-in feed replaying a file, the worker in a replay branch, the other 25 Playwright specs, speed. Each
needs the new pieces in section 5.

Order of start for a replay session (the target of step 4 of the build plan):
PostgreSQL -> Redis -> migrate -> seed catalogue (day list, `as_of` = day) -> seed trades -> write the anchor file ->
stand-in Kite server -> feed (replay launcher) -> API (replay app, started with no broker token: the real `LiveMarket.start` refuses without one, section 2.4) -> background worker (replay branch) -> `vite preview`
-> Playwright. About eleven processes; a single `scripts/replay_up.sh` should own the order and write each PID to a file
(so stopping kills by PID, never by name).

## 4. What replay would prove that today only Monday can

**Plain summary.** I could not find the text of the 27 Nov checks (T1-05 and the rest) anywhere in the repo; Lane Q2
also wrote "I have not seen the check texts". So the table below sorts each check by what it needs, using only the
names the brief gave and what the repo knows, and every row marked "(guess)" must be confirmed by whoever holds the
checklist. The honest summary by kind of need:

| Kind of check | Replayable? | Why |
|---|---|---|
| A stop alert fires, or fires only once, when a price crosses a line | **Yes** | needs a price path and a worker clock; both are replayable. A recorded day contains real crossings. |
| An exit completes (paper) and the screen shows it | **Yes, with one limit** | the paper exit door is replayed; the real order door is not (no broker). |
| The market-closed rules (nothing computed, no fill) | **Yes** | the replay clock can be set to 15:31. |
| A feed gap or silent index causes a stale warning | **Yes** | recorded `dropped` events plus Q2's hold-back rules produce it. |
| Speed under load (slow pages, many users) | **Partly** | replay gives the real price traffic, not real users; load needs its own load test (`tests_app/test_load_live_day.py` exists). |
| Anything that talks to Zerodha (login, real orders, margin, reconciliation) | **No** | forbidden by design (section 2.4). |
| Screens that read the browser's own clock | **Partly** | needs Playwright's clock set as well. |

| Check (as named in the brief) | Replayable? | Reason |
|---|---|---|
| T1-05 to T1-09 (plan-stop alerts, guess) | yes | the stop worker needs prices and a clock only; today it computes nothing while the calendar says closed (`background.py:253`). |
| T1-20 to T1-22 (exits that complete, guess) | yes (paper) | `may_act` is clock-driven; the fill price comes from replay quotes. |
| T1-23 (a leg live in the feed but silent on screen) | yes | Q2: produced by `holdback.withhold_tokens`; replay adds a real day around it. |
| T2-01, T2-02, T2-04 (guess) | partly | depends on whether they use the browser clock or real users. |
| T2-08 (a slow answer for one page) | partly | Q2: produced by the route delay alone, replay adds nothing for the delay itself; it adds the real price load around it. |
| T2-16 (guess) | partly | unknown text. |
| AF-01 to AF-08 (after-hours, guess from the prefix) | yes | the clock can be set to 15:31, 16:00 or the next morning; ADR-212 shows the last close. |
| AX-01 (index older than 60 s while options tick) | yes | Q2: `holdback.silence`. |

Confidence: [Guessing] for every row marked guess; [Certain] for T1-23, AX-01 and T2-08 only because Q2's note
(`RESULTS-lane-q2.md` line 70) maps them. Open question Q6 asks for the checklist.

## 5. Build plan: each step delivers something usable

Sizes: S = a day or less of builder time, M = two to four days, L = a week or more. "Review" = independent review
needed because the step touches a stop, exit, price or money path (CLAUDE.md: Opus for Tier A).

| # | Step | Delivers | Size | Risk | Touches stop / exit / price / money? | Independent review |
|---|---|---|---|---|---|---|
| 0 | **Recorder** (section 1; a script outside the app) | Real day files from Monday 30 Nov. Usable on its own: any later question can be asked of a saved day. | S (done as a design; needs one run) | low: reads Redis only | No (reads the price bus, writes a file) | No |
| 1 | **Day-file tools** (`tools/replay_dayfile.py`: reader, per-day index of time -> offset, a "what is in this day" summary: tokens, frames per minute, gaps, events) | Owner can see a recorded day's shape; the 83-minute 27 Nov file becomes a first sample. | S | low | No | No |
| 2 | **Clock seam and broker wall** (`replay_clock.py` with a generation counter; plug-ins from 2.1.1 incl. `live_market._launch`, `worker_watch`, the `main.py` lifespan and the worker's third branch; replay-only API launch with no token; every Kite REST door refusing in replay; empty-Notifier refusal; source-scan test that only the replay selector imports the clock; all behind `APP_ENV=test`) | The whole app can be told "it is 13:28 on 27 Nov" and cannot reach Kite REST or the Notifier. With the existing fake feed the stop worker and paper stop monitor run "in market hours" at midnight. | L (was M: the Opus review found four more seams) | **medium-high**: it changes how the worker, the may-act gate and the answer clock learn the time; a leak into production would shift live stops | **Yes: stop and exit and price (worker clock, `may_act` `at`, answer clock)** | **Yes (Opus)**: prove `live_market._launch`, `worker_watch.start_if`, the `main.py` lifespan and `background._serve_live` are unchanged when replay is off (each still builds `datetime.now(IST)`), the replay branch cannot start outside test, and a full replay makes zero connects to the Kite API host |
| 3 | **Stand-in feed replay** (needs Lane Q2's `holdback.py` from `origin/test/live-day-gaps-1127` merged first; forward jumps only) (`replay_kite_server.py`: pacing by the replay clock, 1x/10x/pause, jump with pre-roll, recorded drops, hold-back rules) | A recorded day played through the REAL feed process into Redis: a live-like price stream at any hour, repeatable. | M | medium: wrong pre-roll gives wrong prices on screen (a replay-only danger) | Prices, in test only | Yes, light: a second reader checks pre-roll and pacing against the file (replay a known window, compare every price the API serves with the file; needs steps 2 and 4: the no-token API launch and the `as_of` catalogue, since `live_market._launch` loads the catalogue) |
| 4 | **Seeded database + one-command start** (`scripts/replay_up.sh`: database `ofo_replay`, migrate, catalogue with `as_of`, paper trades seeded, anchor file, processes in order, PIDs recorded) | `replay_up.sh 2026-11-27 13:20` brings up the day in a cloud session. | M | medium: seeds paper money rows; a seed run against the wrong database would be bad | Money rows (paper) | Yes: the guard (database name `*_replay`, local host, marker row) is the review target |
| 5 | **Safety wall + banner** (header `X-OFO-Replay`, frontend banner "REPLAY of <date>, not live", real order routes refuse and paper routes need the replay marker on the strategy, settings validator, `replay_marker` row and Redis marker key; the broker and Notifier walls are in step 2, not here) | The separations of 2.4 as running code, each with a failing-first test. | M | **high if skipped**; medium as built | Order routes (refusal), screens | **Yes (Opus)**: attack it: each way a replay figure could be mistaken for live |
| 6 | **One end-to-end stop test** (Playwright drives the screen; the replay runs the 27 Nov minute the stop failed; assert the alert shows, once, with the replay time) | The first proof: a stop fix seen on a screen on a Saturday. | M | low once 2-5 stand | Stop path (as a test) | Yes: the assertion text and the "ran the right minute" counter |
| 7 | **Full screen suite on replay** (the 26 existing specs plus replay-only ones: after-hours, silent index, dropped feed) | The Monday checks (section 4) runnable at will. | L | low | tests only | No, beyond step 6's review of the harness |
| 8 | **Nightly run** (a scheduled cloud session: pull the latest day file from the owner's private store, run steps 6-7, post the result) | A regression net that sees real market behaviour every night without anyone at the PC. | M | medium: the storage and licence answer (Q1, Q8) | No | No |

Cheapest useful stopping points: after step 1 (a recorded day you can inspect), after step 3 (live-like prices at any
hour), after step 6 (a Saturday-testable stop fix). Steps 2 and 5 are the ones where a mistake could reach production,
so they are the ones to build slowest.

Dependencies: 0 -> 1 -> 3; 2 -> 4 -> 3 (the price proof); 2 -> 5; the broker and Notifier walls (step 2) come before the first full-stack run of steps 3 and 4; 3 + 4 + 5 -> 6 -> 7 -> 8. Step 6's "alert shows, once" holds only with forward jumps or a restart per run.
Build order rule (`build_order.py --may-start`) was not run: these are design steps, not REQs.

## 6. The product angle (kept separate, decision-support wording only, ADR-003)

**Idea:** "Replay a market day against my strategy": a trader picks a past day, picks their own strategy, and watches
what the plan's price, stop and adjustment lines would have shown minute by minute.

What the repo text already says:
- REQ-051 AC-6 and AC-7: "Simulation, when built, is simple strategy simulation (EOD default, intraday later), not
  quant backtesting", with results "always labelled historical/simulation, never a future guarantee".
- REQ-034 and REQ-084/ADR-151: the builder already has "what-if" at a target level and date, computed by the one server
  engine (ADR-008). ADR-120 (19 Oct) said no what-if sliders in V1; the later REQ-084 re-opened target-day what-if.
- `spec/open-questions.md` (the RA-exposure note, Q211) lists "any backtest or simulation result (REQ-051)" among the
  features exposed to the Research Analyst rule, and F-15 records SEBI penalising a broker over a platform's return
  claims. REQ-005 leaves open whether past-performance or backtest display needs a further rule.
- `spec/technical-design/legacy-reuse.md:130`: the legacy `backtest` and `whatif_simulator` code is SKIP ("second calculator").

What would differ between the test tool and a feature:

| | Test tool (this document) | Trader feature |
|---|---|---|
| Data licence | owner's own recorded feed, on the owner's machine, for testing | showing recorded exchange prices to other people is redistribution; [Likely] needs a licence (Q1); nothing here was checked |
| Speed controls | 1x, 10x, jump, pause, hold-back rules, for a tester | pause / step / 1x / 10x for a learner; no hold-back rules |
| Whose trades | seeded paper trades chosen by the tester | the user's own strategies, read-only copies, never touching the real book |
| Numbers | any price the file holds | every P&L from the one engine (ADR-008); labelled "as of the replay time" |
| Words | internal | "what this plan would have shown on that day"; never "would have earned" or "you should"; always the historical label (REQ-051 AC-7) |
| Safety | banner "REPLAY of <date>" | the same banner is the product's honesty rule |
| Granularity | ticks | EOD or minute bars (REQ-051 AC-6 says EOD default): ticks cost 0.3 to 1+ GB a day (section 1.3) |

Entrepreneur's view (a recommendation, not a decision): the test tool is worth having for its own sake. The trader
feature is a separate bet whose gate is the data licence, not engineering: with licensed minute bars it could be cheap,
with ticks it is not. Do not let the feature's appeal pull steps 5 and 6 of the test tool forward.

## 7. Open questions for the owner (nothing decided here)

| # | Question | Sits beside | Recommendation |
|---|---|---|---|
| Q1 | Are Kite/NSE prices allowed to be stored and shown outside your own machine? The repo already holds real 8 Oct recordings (`tests/fixtures/kite_ws/`, `kite_history/`, `candles-2026-10-08.json`). | ADR-012, ADR-029, REQ-051 AC-7; `spec/open-questions.md` licence items | Check the Kite Connect and NSE terms yourself. Until then no new day file goes into git, an artifact or a chat. Treat the existing fixtures as a separate cleanup question for you. I removed nothing. |
| Q2 | Run the recorder on Monday 30 Nov, 09:00 to 15:35? | none (a tool, no product decision) | Yes. It costs a script and about a few hundred MB to 1.2 GB; it keeps every option open. Start before 09:15, stop after 15:35, keep the PC awake. |
| Q3 | Where do day files live and for how long? | ADR-012, ADR-029 | `D:\Abhay\Ventures\market-days\<date>\`, newest 20 trading days plus any day you label "keep" (a failing day). |
| Q4 | Build how far? | none | Steps 0, 1, 2, 3, 4, 5, 6 only, then stop and decide on 7 and 8 after one stop fix has been seen on a screen on a Saturday. |
| Q5 | Which recording first? 13:28 on 27 Nov is mentioned as the minute to jump to, but the saved Redis stream only covers 14:34:58 to 15:58:00. | none | Use the 27 Nov tail to build steps 1 to 3 (it holds the close, which tests the closed-market rules). The 13:28 minute is lost; only Monday's recording can hold such a minute. |
| Q6 | Please paste the text of checks T1-05 to T1-09, T1-20 to T1-23, T2-01, T2-02, T2-04, T2-08, T2-16 and AF-01 to AF-08; I could not find them in the repo. | none | Needed to firm up section 4 (every "guess" there). |
| Q7 | May replay run in `development` (as `OFO_SCENARIO` may) or in `test` only? | ADR-003, ADR-177 | `test` only, and only on a machine that never holds a real broker session. |
| Q8 | How do cloud sessions get a day file? | ADR-012, ADR-029 | By you uploading one day to one session, until Q1 is answered. A permanent private store only after Q1. |
| Q9 | Accept that replay proves the paper door and shared price rules, not the real order door? | ADR-330 (58) as named by the coordinator, ADR-016 to ADR-019 | Yes: the real order door must never be reachable from a replay. |
| Q10 | Seed the replay with your real paper trades of the day, or invented ones? | ADR-002 (every order belongs to a strategy) | Export that day's paper strategies from your database; invented ones miss real shapes. |

## 8. The strongest reason NOT to build this

The clock seam (and the broker wall that must come with it) is a change to the code that decides when stops fire and whether an exit is allowed, and its whole
purpose is to make that code believe it is some other time; if it is built even slightly wrong, the people who pay are
real users on a live day, and the only way to prove it right is the very thing replay was meant to avoid (a real
market morning). Meanwhile most of what it would find may be found more cheaply: the app already has a stepped scenario
mode with its own clock and a frame index, Lane Q2's hold-back rules (silence a token, silence the index, delay a
route), and a feed rig that runs in a cloud session today (I ran it). Scenario mode already allows paper orders on a marked strategy; what it lacks is a moving day and the paper stop monitor
(it forbids the live market). Adding those might carry less risk to the stop path than a general clock seam, but nobody has measured it. Replay also gives you
real prices but not real state (sessions, broker answers, database timing, the browser, real users), so a green replay
can still be followed by a red Monday, and a team that trusts the green will test Monday less. And the owner can get a
free, perfectly realistic test every week by being at the PC: replay buys flexibility, not truth. If this goes ahead,
build the recorder (free), then steps 1 to 3, and stop; build the clock seam only when a specific failing minute can
be named that no cheaper rig reproduces.
