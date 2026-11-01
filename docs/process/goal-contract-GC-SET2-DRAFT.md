# Goal contract GC-SET2 (DRAFT): the exchange and broker facts parked from GC-SET

Status: DRAFT, written 2026-11-01 by the GC-SET run after the owner chose option A ("Go with your recommended option
A", ~08:05 IST): GC-SET finishes without these two items; they get their own contract. Not approved to run; the owner
sets it as `/goal` when wanted. Runs on `feature/adjustments` (owner rule: nothing to main).

Core: a market-hours fact read from settings at run time changes "is the market open now" and the time to expiry the
pricing maths uses, with no restart, for every caller.
Proof: step 1 - on a throwaway DB: `facts.session_close` 1530 -> 1500 makes a check at 15:10 IST answer "market
closed" and changes the time-to-expiry year fraction of a same-day expiry; reset -> back.

## Why it was parked (measured in GC-SET)

- `backend/ofo/timeutil.py:27-34` types SESSION_OPEN 09:15, SESSION_CLOSE 15:30, EXPIRY_CLOSE 15:30 IST,
  EXPIRY_DAY_SETTLE_FROM 15:39, HISTORY_FETCH_UNTIL 15:59; 70 backend modules import `ofo.timeutil`; the time to
  expiry in the pricing maths depends on EXPIRY_CLOSE. Every GC-SET batch builder covered about half its brief; this
  one is larger than any of them and Tier A.
- Step 5b (order and limit facts) touches order splitting and charges: freeze units and batch
  (`ofo/execution/sequence.py:85-86`, labelled "UNVERIFIED placeholders"), Zerodha rate limits
  (`ofo/broker/rate_limit.py:64`), feed limits (`ofo_app/kite_ws.py:72-73`), quote limit 500
  (`ofo_app/kite_reads.py:46`), tick 0.05 (`ofo/engine/orderbook.py:51`), stamp and SEBI caps
  (`ofo/charges/rates.py:33-34` - note "STAMP_CAP 0.0001 # real 0.00003" - and the migration-0014 DB caps).
- Also left by GC-SET (listed in `tests/test_settings_literal_guard.py` KNOWN_LEFTOVERS): the 06:00 stamped by the
  `broker_sessions` DB trigger (migration 0007; the app now works the expiry out from the setting and ignores that
  column), and market hours in `timeutil.py`.

## Steps (to be detailed before approval)

| Step | What | Review |
|---|---|---|
| 1 (core) | market hours + expiry close as settings (time unit HHMM, group "Exchange and broker facts", source = NSE/BSE circular); one per-request/per-tick read passed down as a required `MarketHours` object, like `ForwardQuality` and `FeedWindows` | Tier A |
| 2 | 5b order and limit facts, each with its source; the DB caps of migration 0014 read the same setting (or the setting is checked against them) | Tier A |
| 3 | the broker_sessions trigger stops stamping 06:00 (migration) or the column is dropped from the guard's reads | Tier B |
| 4 | remove the matching KNOWN_LEFTOVERS rows; prepush --full; merge into local feature/adjustments; push | none |

Open question for the owner before approval: none known; the defaults are today's code values.
