STATUS 21:55 | section 1: written, pushing now | rest: not started | next push by Sat 28 Nov 12:00 (sections 2-8)

# Market on demand: replay a recorded market day (design, Lane D2, 27 Nov 2026)

Design only. No product code was changed. Times are IST. Cloud-session messaging to the coordinator was refused
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

Bytes per entry is the one number I cannot measure from the repo, because it depends on how many instruments the PC
had subscribed on the day. Range for a day of 92,000 entries:

| Instruments subscribed | Bytes per frame (about 186 per tick) | Raw per day | Gzip per day |
|---|---|---|---|
| 8 | 350 | 32 MB | 10 MB |
| about 200 (a few expiries of one index) | 7,500 | 0.7 GB | 0.3 GB |
| about 1,000 (full chain, two indices; the opening burst rate) | 31,000 | up to 2.9 GB | up to 1.2 GB |

The 1,000 row is an upper bound (the 10 s sample is the busiest moment of the day, and many ticks repeat). **The
coordinator's saved stream settles it:** divide the file size by 20,000. At the worst case a year of trading days
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

Why a plain file reader and not a change to the app: the app already publishes the full raw record to Redis for its own
use (ADR-012: the feed process holds the vendor connection; browsers and the rest never do), so a second reader on that
bus adds no vendor connection and no new write path.

---
*Sections 2 to 8 follow in the second push.*
