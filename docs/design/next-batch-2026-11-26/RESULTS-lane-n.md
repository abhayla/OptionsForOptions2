# Lane N, 27 Nov 2026: one source for "the price to show and its time"

Branch `fix/last-close-1127`, cut from `origin/hotfix/index-quote-1127` 2244298. Paper only; no broker order endpoint;
no migration; no PR; no GitHub issues.

## Status lines (messages to the coordinator were refused: "elevated_session_untrusted_device")

- 16:10 IST LANE N ALIVE (send_message to @parent refused; lines kept here instead).
- 16:25 IST head (this docs commit) | gate: fast pre-check only, docs file | re-test: none yet.

## DECISION NEEDED FIRST (A1): the 15:30 closes are not stored anywhere durable

Finding (code read, 27 Nov): the ADR-330 (36) freeze lives only in the API process's feed book
(`backend/ofo/marketdata/feed_health.py` `BookEntry.close_quote`, set by `_close_after`, served by `_served`). An API
restart after 15:30 empties it, and nothing re-creates it: Redis holds only the tick stream (20,000 entries, read from the
newest entry after a restart), 10 s token snapshots and status keys; the `history_minute_bars` table (migration 0009)
exists but no running process writes it during the day (only `history_finalize.py`, after the close, from Kite candles);
no other table holds a per-contract close. So the exact (36) figure cannot be recovered after a restart without a
design decision. Options (coordinator / owner to choose; I have not built any of them):

| Option | What | Migration | Matches (36) exactly | Cost / risk |
|---|---|---|---|---|
| 1 (recommended) | A small table `last_close (instrument_id, trade_date, price, price_at)` written once at 15:30:00 by the feed book for every contract it holds, read at start-up when the market is closed | yes (one new table) | yes | one writer at 15:30; needs a decision row and the coordinator's migration number |
| 2 | Use the existing `history_minute_bars` table: write held contracts' 15:29 bar at 15:30 and read its close after a restart | no (table exists) | nearly (the bar's close is the last trade up to 15:30, from the feed) | the table's three write rules (W-067) apply; a writer must be wired into the API process |
| 3 | A Redis key per contract written at 15:30, kept until the next open | no | yes, until Redis restarts | lost on a PC reboot unless Redis persistence is on |
| 4 | After a restart, read Kite's one-minute 15:29 candle by REST | no | nearly | Kite historical rate limit (3/s), REST at start-up, needs REQ-118 budget check |

Until the choice: the interim rule built in this lane (A2 below) freezes the FIRST frame a contract gets after the close and
labels it with its own time, so after a restart a held leg shows a price "as of 15:50:12", not "no live quote". It is
honest about the time but it is not the 15:30 figure.

## Per item (root cause in one sentence)

| Item | Root cause | Fix (where) | Status |
|---|---|---|---|
| A1 | The 15:30 close is held only in the API's memory, so a restart after the close leaves every contract with no close and the legs unpriced. | Decision above; interim through A2's rule. | DECISION NEEDED; interim in build |
| B2 | `_index_spot_held` (adjustment_readers.py) requires a fresh index tick to store the entry's starting point, so a feed-down save is refused even after the user ticked "Prices are not live" and typed his own price. | Use the last held index value with its time when the user confirmed; refuse only when no value exists. | in build |
| A4 | The Add to Paper tick box shows only when the builder's `pricesLive` is false, and that flag does not count every not-live state (after close / pre-open). | One frontend price state (priceState.js) that counts closed, pre-open and feed down. | in build |
| A2 | The freeze holds only for a contract that had a frame at or before 15:30; a strike first read after the close is served its latest frame, which keeps moving. | Freeze the first frame after the close, with its own time (feed_health.py). | in build |
| B1 / A5 | `pausedText` always appends ", as of" + the time even when there is none ("Time not available"); the builder banner takes its time from a partial reply while loading; Home's `as_of` is None when the paused book has no quote time. | One as-of formatter; banner time only from a complete reply; server carries the last captured time. | in build |
| A3 | Live Strategies shows the closed banner only after a child card's own reply says `market_closed`, and cards start 8 s apart. | Page-level market answer, as Index View does. | in build |
| C | Create Strategy shows "Not available" when `/market/indices` has no live value before the open, instead of the last close (Lane J's 08:30 list fix is a separate cause). | Last close with its time. | in build |
| B3 | The no-what-if text needs a reply that carries `target_not_live_text`; with no reply nothing shows. | Folded into B1 / A5 (read under the PC's sweep). | to confirm |

## To file as deferred issues

(filled as found)

## Task | model

| Task | Model |
|---|---|
| Split, route, verify, report (this file) | Opus (coordinator session) |
| Root-cause search, backend and frontend | Sonnet (2 read-only helpers) |
| Test environment set-up | Haiku |
| A2, B2, A4/A5/B1, A3/C builds | Sonnet (4 builders) |
