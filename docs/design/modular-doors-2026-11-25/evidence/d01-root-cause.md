# D-01 RCA: a crossed conditional exit was saved at 15:02 and refused at 15:11 (25 Nov 2026)

Read-only investigation of `fix/ic-live-test-1123` @ 5d9b53ca. No repo file edited. Reproduction script (fakes plus the
recorded real Kite frames of 2026-10-08, no DB, no network):
`C:\Users\itsab\AppData\Local\Temp\claude\b565dc95c8b87e64\42568038-88ec-4112-bad2-e5949976fb4d\scratchpad\repro_d01.py`

## 1. RCA in one sentence

The save guard `_already_crossed` reads the index from the API process's own quote book **without holding the index**,
and in bus mode that book drops every tick for a token nobody in the API process holds. So the guard sees "no index
price" (`spot=None` -> state `missing` -> `stops.crossed` False -> saved) unless some other consumer in the same process
(the paper monitor's watch list, a screen's push) happens to hold NIFTY at that moment. The background process had
25,783.70 because it holds the index for its own watch. The verdict therefore depends on what else is running, not on
the market.

### Causal chain (file:line)

1. `backend/ofo_app/live_market.py:174-176`: in `FEED_MODE=bus` the API builds its own `KiteProvider` fed by
   `BusSocket` from Redis. A restarted API starts with an empty book.
2. `backend/ofo_app/feed_bus.py:333-334`: on connect the API reads only stream entries after "now" (no backlog), so a
   fresh API process has no NIFTY quote until a new tick arrives **and** is accepted.
3. `backend/ofo/marketdata/kite_provider.py:114-118`: `on_frame` keeps a tick only if `tick.token in self._wanted`.
   Otherwise it is parked or counted as `unwanted_tick` ("fail closed: a token nobody holds never reaches the book").
   NIFTY ticks do flow on the bus, because the background process's want key asks for them
   (`feed_bus.py:513-528` union of API and `:bg` wants; `background.py:1152-1160` adds each strategy's index token).
   But the API process drops them unless something in the API process subscribed NIFTY.
4. `backend/ofo/marketdata/kite_provider.py:259-261`: `underlying_quote` returns `book.get(...)`, which is None.
5. `backend/ofo_app/routes/paper.py:1647-1648`: `_already_crossed` calls `read_snapshot(...)` directly. It does
   **not** subscribe or hold anything. Compare `_snapshot` / `_hold_until_ready` (`paper.py:514-543`): the paper book
   read holds the index for up to 3 s, because GC-LIVE F-1 already found "with no other screen open the index had no
   quote". The trigger guard never got that fix.
6. `backend/ofo/outcome/snapshot.py:177`: `spot = provider.underlying_quote(underlying)` returns None.
7. `backend/ofo/tracking/paper.py:99-101`: `price_of(None, ...)` returns state `missing`.
8. `backend/ofo/tracking/stops.py:51-55`: `crossed` returns False on a price that is not live.
9. `backend/ofo_app/routes/paper.py:1661-1663`: the guard returns None, so the route saves the trigger
   (`paper.py:1678-1691`, 201 Created). No exception is raised, which is why the log has no "price read failed" line.
10. `backend/ofo_app/routes/paper.py:1692` `paper_monitor.notify()` -> `backend/ofo_app/paper_monitor.py:120-150`
    `reload` subscribes the NIFTY index **because of the trigger just saved** (an armed conditional exit). The next
    NIFTY tick is booked and crosses, and the trigger fires (`paper_monitor.py:183`). That was 15:02:36, about 10 s
    after the save.
    Correction to the brief: the paper monitor runs **inside the API process** (`backend/ofo_app/main.py:98`). It is
    not in `ofo_app.background`, and no `paper_monitor` reference exists in `background.py`. So the process that fired
    the stop is the same process whose guard said "no price". It began holding the index only because of the save.

Why 15:11 was refused: at that moment something in the API process already held NIFTY and strategy 170's 26000 CE
contract. The most likely holder is the paper monitor's watch: it holds the index for any armed conditional exit and
all open contracts of that strategy (`paper_monitor.py:136-150`). The leg refusal shows the leg contract was also held.
That fits an armed conditional exit on 170, or on another NIFTY strategy, from before the 15:09 restart. An open screen
push holding the index would also explain it. Not verified (no DB read in this task). See section 2.

### The same cause explains the 12:53 / 12:54 leg-stop alerts ("index value ... not available")

`paper_monitor.py:136-150`: a strategy with **only leg stops** gets only the leg contract in its watch. The index is
added only for a `conditional_exit`. At fire time `_index_now` (`paper_monitor.py:262-270`) reads
`provider.underlying_quote(underlying)` from the same API book. NIFTY is unheld, so the quote is None and the alert says
"the index value at that moment was not available". At 12:57:44 the index stop alert had the value, because an index
stop puts NIFTY in the watch. Same mechanism, same file, one shared root cause. It is not intermittent: the outcome is
fixed by **which triggers happen to be armed in the API process**. The reproduction's row 2 (legs held, index not)
gives `spot=None`. ADR-323 (4) allows that text only when the index is truly missing, and here it was not.

## 2. Confidence

**Mechanism: proven by reproduction.** `repro_d01.py` replays the real recorded frames into a `KiteProvider` and calls
the real `paper._already_crossed` with `tracked_contracts.resolve` stubbed. A conditional exit has no contract, so the
stub is never used. The level is "above 22500" and the recorded NIFTY ends at 22533.25, so the level is already crossed:

```
hold_index=False hold_legs=False spot=None     unwanted_tick= 7281 -> guard=None
hold_index=False hold_legs=True  spot=None     unwanted_tick= 4614 -> guard=None
hold_index=True  hold_legs=False spot=22533.25 unwanted_tick= 7241 -> guard='paper_trigger_already_crossed'
REPRODUCED: same price, same level; the save is accepted unless another consumer holds the index
```

**Which holder made 15:11 differ: strongly indicated, not proven.** To prove it, query `paper_triggers` for rows armed
between 15:09 and 15:11 on 25 Nov (any NIFTY strategy, `kind='conditional_exit'`, `fired_at/cancelled_at` null or later
than 15:11). Also query for no armed NIFTY conditional exit at 14:58-15:02. Optionally read the API's
`provider.counters['unwanted_tick']` or its subscribed tokens on a debug read. Not needed for the fix: the guard must
not depend on it either way.

## 3. Class: every save path that must refuse a level the live price has already crossed

Searched: `already_crossed`, `stops.crossed`, POST/PUT routes matching trigger|stop|exit|watch|plan, `gtt|GTT`,
`stop_loss|SL-M`, `underlying_quote(` in `backend/ofo_app`.

| Route / reader | file:line | Same fail-open shape? | Real money? |
|---|---|---|---|
| POST `/paper/strategies/{id}/triggers`, conditional exit (index) | `routes/paper.py:1637-1663`, caller `:1678` | **Yes**: reads the index unheld; None or not live means saved | No (paper) |
| same route, leg stop (contract LTP) | `routes/paper.py:1654-1655` | **Yes**: the leg contract is also read unheld; refused at 15:11 only because something held it | No (paper) |
| same guard, `except Exception` | `routes/paper.py:1661-1662` | **Yes**: any read error means saved (logged) | No |
| same guard, `ctx is None` / `market_closed` | `routes/paper.py:1641-1650` | By design (ADR-317 (2)): saved, arms at the next live tick | No |
| same guard, leg with no feed key | `routes/paper.py:1656-1657` | By design: saved | No |
| POST `/paper/.../triggers/{id}/keep` (D-03 re-store) | `routes/paper.py:1716-1743` | **No crossed check at all**. Low risk: the trigger was already armed and watched, so a crossed level would normally have fired | No |
| Paper monitor fire: index value in the alert (D-22) | `paper_monitor.py:262-270` | **Yes**: same unheld index read, and the 12:53 alert shows the wrong text | No (record text) |
| PUT `/api/strategies/{id}/level-watch/{direction}` | `routes/level_watch.py:75-90` | No crossed check. It is an alert-only watch, and whether a crossed level should be refused is not in the spec (not this class) | No |
| Real-order stop / GTT save route | none found | None exists: no GTT or stop reaches Zerodha (REQ-109 AC-8, ADR-165). Real exits are owner-pressed | n/a |

Before: 4 fail-open spots in the paper trigger save (index, leg, exception, keep) plus 1 record-text spot (monitor index
value). After the fix shape below: 0 that depend on another consumer holding the token.

Other unheld `underlying_quote` readers in the API process exist (`adjustment_readers.py:379,777,808`,
`leg_edit.py:459`, `ready_made.py:120`, `chain_push.py:305`, `index_push.py:84`, `live_push.py:170`). They are
display or advisory reads, and the push sockets hold their own ids. I did not audit each one. List them for a
follow-up `deferred` issue (B7), not for this fix.

## 4. Proposed fix shape (no code)

**Where the one structural guarantee goes:** the guard reads through the existing hold-and-read
(`live_push.hold_and_read`, the same door `_hold_until_ready` uses). It holds the index (conditional exit) or the leg's
feed key (leg stop) on the shared fan-out and polls until the price is live or `FORWARD_WAIT_S` (3 s) passes. Better
still, add one helper "a live price for these keys, held" that the trigger guard, `paper_monitor._index_now` and
`entry_facts` / exit-price reads all call. Then no price decision in the API process can read an unheld token (B8:
structural, not another detector). `_index_now` needs the same change, or simpler: the monitor's `reload` adds the
strategy's index to `extra` for leg stops too. That is a one-line structural fix for D-22.

What each answer state should do:

| State | Proposed behaviour | Spec status |
|---|---|---|
| Live price after the hold, crossed | Refuse with the ADR-317 (1) text | Settled (ADR-317 (1)) |
| Live price after the hold, not crossed | Save | Settled |
| Market closed (ADR-119 calendar) | Save, arms at 09:15 | Settled (REQ-109 AC-8, ADR-317 (2)) |
| No market context (feed not connected) | Save, arms at the next live tick | Settled by ADR-317 (2), but this is the hazard, see below |
| Market open, feed connected, still no live price after the 3 s hold (stale, missing) | **Recommend: refuse** with "Not saved: no live price yet, so this level cannot be checked. Press Save again in a moment." | **SPEC CHANGE** |
| Read raised an exception | **Recommend: refuse** with the ADR-317 (5) "could not get an answer" wording | **SPEC CHANGE** (ADR-317 (2) says "a failed read" means saved) |

**Business call for the owner (SPEC CHANGE):** ADR-317 (2) says *"With no live price (market closed, no feed, a stale
or failed read) it is saved and arms at the next live tick, as before."* During market hours "saved and arms at the
next live tick" is exactly the hazard. An already-crossed level fires on the first live tick, and that is the behaviour
ADR-317's own consequences reject: *"Option not chosen: save it and fire on the next tick (the behaviour before); a
mistyped digit closed the trade."*

The hold fix alone (fully within the spec) removes today's trigger: a connected feed with a live index will answer
within the 3 s hold. Only a real feed gap during market hours would still save unchecked. The owner chooses: keep (2)
as written for market hours (a protective stop is never blocked by a feed gap, but a typo can close the trade on
reconnect), or refuse during market hours when no live price can be checked (no unchecked level is ever armed, but the
trader must retry during a gap). Recommendation: refuse in market hours, keep "save and arm at 09:15" when the market
is closed. When a real-order stop path arrives later this becomes real money, and fail-closed is the house rule
(python-domain "Fail closed"; ADR-016..019 spirit).

## 5. The failing test to write first

`tests_app/test_paper_trigger_crossed_unheld.py::test_conditional_exit_already_crossed_is_refused_when_nothing_else_holds_the_index`

- **Setup:** a `KiteProvider` from `tests/marketdata/_kite_fixture.py` (`new_provider`). No `subscribe` call, so
  nothing holds NIFTY. Wrap it in a `LiveFeed(MarketContext(provider, clock, rate), FanOut(provider))`. The frames are
  replayed **while the guard holds** (a fake fan-out or a clock-driven feeder that pushes the recorded frames after the
  subscribe), so "a tick arrives only after the hold" is modelled the way bus mode behaves. Market open (2026-10-08
  09:20 IST). The level is "above 22500" and the recorded NIFTY is 22533.25. `tracked_contracts.resolve` is stubbed
  (no contract for a conditional exit).
- **Assertion:** `_already_crossed(...) == "paper_trigger_already_crossed"`. Today it returns None (the reproduction's
  row 1).
- **Companion (same file):** leg stop "below X" on `NSE_FO:44614` with the leg unheld must return
  `"paper_trigger_leg_already_crossed"`. A leg-stop-only fire must record the live index value, not "not available"
  (D-22). A mutation check: remove the hold and both go red.
- **Route-level twin (DB test, one file, via `db_run_fresh` in CI):** POST `/paper/strategies/{id}/triggers` with no
  armed trigger anywhere returns 422 "Not saved: the live price is already at or beyond this level...", and no row is
  stored.

Detection change: add `"_already_crossed"` and `_index_now` to whatever test asserts that price decisions use the held
read (none exists today). That counter is "unheld price-decision reads in `ofo_app`".
