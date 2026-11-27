# Lane U hotfix 27 Nov: index quote 429s, stale leg quotes, silent Exit

Branch `hotfix/index-quote-1127`, cut from `origin/integration/nb-1126` 206a9f0 (the head tested live on 27 Nov). Only these
fixes. Paper only; no broker order endpoint; no migration. Highest status: **Fixed, not tested** (the owner's PC re-tests).

Evidence: PR #722 comments 7209640570, 7209446658, 7209464776; PC notes 09:51 and 10:05 IST (relayed by the coordinator).

Spec basis: ADR-330 (39) (index age rule), REQ-049, REQ-100, REQ-114, REQ-118 (Kite rate budget), REQ-133, ADR-008, ADR-012,
ADR-016 to ADR-019, ADR-328 (4), REQ-065, ADR-330 (17), owner N-04 / N-05.

## Job A: Kite 429s on the index quote, leg quotes stale every 25-50 s

| | |
|---|---|
| Root cause 1 (the 429s) | Every route on a page poll awaited the Kite REST index quote BEFORE it looked at the live tick store: `run_check` (adjustment_check.py:497, which the builder's plan-watch calls on every 5 s paper tick), adjustment.py:617/801, playbooks.py:449; a second REST call in `_window_spot` when nobody held the index; no cache; the limiter is per process (quote 1/s, 10 s cooldown after a 429). One open builder = 12-24 REST index calls a minute. The worker's 56 cycles a minute were not the source. |
| Root cause 2 (stale legs) | Open legs were subscribed on the socket only for the length of one request (`hold_and_read` releases at the end; the fan-out is ref-counted, but nobody else held the legs), so each 5 s poll subscribed again and waited for a fresh tick; a quiet option takes 25-50 s. A 429 never reached the exit path: the two symptoms were simultaneous, not one cause. |
| Fix | One door `rest_spot_if_needed` (routes/outcome.py): the tick store is judged first with the age rule; REST only when the feed cannot give the spot. `live_market.index_spot` reads REST through one shared, single-flight, cached reading (`ofo/marketdata/shared_reading.py`: a good answer reused 5 s; a failed answer (the 429) kept 10 s, so nothing is sent inside Kite's cooldown; the fetch runs in its own task so one cancelled request does not abort the others). All callers rerouted. The paper monitor now holds every open paper leg and its index on the socket while the strategy is open (one query `open_legs`), set AFTER the stop watch and kept on a read failure, so stops are always watched. |
| Class | REST index calls a minute at 5 strategies + 1 open builder with fresh ticks: 12-24 -> 0. Request paths that released the only hold on an open leg: every poll -> 0. |
| Tests (red first) | tests_app/test_rest_spot_door.py (12 plan-watch requests with a fresh tick make 0 REST calls; index absent: 12 requests in the TTL make 1; a 429 sends 1 call and none in the cooldown; a 429 leaves leg subscriptions alone; held legs stay subscribed over 12 polls); tests_app/test_rest_spot_door_scan.py (repo scan: no route awaits REST outside the door; the worker, monitor, paper_exit and tracking never reach the REST spot); tests/test_shared_reading.py. |
| For Lane J (plan-watch) | Nothing to change: plan-watch gets the fix through `run_check`. It must not call `read_rest_spot` / `live_market.index_spot` itself; polling `/plan-watch` every 5 s is now free of Kite REST calls while the index ticks. |
| For Lane R | `paper.py` `_hold_until_ready` untouched; the standing hold lives in the paper monitor. |

## Job B: Exit > Confirm did nothing and said nothing; a done exit showed nothing

| | |
|---|---|
| Root cause | The Positions Exit had no single place that said why an Exit did not run: when a 5 s list re-read failed, the page closed the dialog itself and cleared the ticks with no sentence (partly Lane U's own NEW-T22 rule of 26 Nov), so Confirm did nothing and Exit was then dead with no reason; and a 201 (the exit stored) showed nothing, so the row stayed until a reload (T1-02 refined). Confirm could also be pressed while "Checking whether this exit leaves a sold option without protection..." still showed. |
| Fix | One door (`exitEndText` in lib/usePaperExit.js + `endExit` in PaperStrategies.vue): every Exit that ends without an order, with a refusal, or with a done names the leg(s) and why. A failed re-read keeps the dialog open with Confirm blocked and the not-live line; the dialog closes by itself only when the legs really changed (with the "changed elsewhere" note). A refusal shows all four parts. A 201 leaves "<legs>: Exit placed on paper (order n)." and re-reads the list at once. An unknown outcome (503, no answer, 408, 429, a cancelled request) keeps that strategy's exit unresolved: Confirm stays off, also after Cancel and re-open, until a good re-read decides "placed" or "The exit was not stored. You can try again." (ADR-017: never a blind second order). Confirm waits for the protection check. Exit says "Tick a leg to exit." when nothing is ticked. |
| Class | Exit paths that end with nothing done and nothing said: 11 -> 0; paths that re-arm Confirm after an unknown outcome: 2 -> 0. |
| Tests (red first) | frontend/tests/paper-strategies.test.js, paper-dialog-safe.test.js, paper-exit-warning.test.js; e2e EXIT-16, EXIT-21, EXIT-22 in screen-positions.spec.ts changed to the new rule (the dialog stays open and blocked on a failed re-read). |
| New wording (pending owner read) | "An exit is already being sent for this strategy.", "Tick a leg to exit.", "Exit placed on paper (order n).", "The exit was not stored. You can try again." |

Tier A reviews (Opus): Job B SHIP (round 1 fixed the unknown re-arm); Job A FIX FIRST -> fixed (shared read cancel; stop watch set before the hold).

## Re-test (PC, market hours)

1. Start the app as usual (FEED_MODE=bus as today). Open a running paper trade in the builder (plan-watch on) and leave it 10 minutes.
2. Expected: the API log has no new `kite read HTTP status 429` / `REST index quote failed` lines while NIFTY ticks on the strip.
3. Positions > Paper: watch a leg's price for 2 minutes. Expected: it does not go "not live" every 25-50 s; Exit stays blue.
4. Tick one leg, Exit, Confirm. Expected: "<leg>: Exit placed on paper (order n)." and the row updates without a reload.
5. Tick a leg, Exit; while "Checking whether this exit leaves a sold option without protection..." shows, Confirm is grey; it turns blue when the check answers.
6. Tick a leg, Exit, then stop the API for 10 s. Expected: the dialog stays open, Confirm grey, "<leg>: Prices are not live; try again when they update"; start the API: Confirm turns blue.

## To file as deferred issues

| Title | Evidence | Spec basis | Done when |
|---|---|---|---|
| Alerts exit door drops its done / changed note | Opus review: PaperStrategies.vue:387 emits `exit-closed` whenever the dialog closes; AlertsPage.vue:142 unmounts the component on it, so the note set in the same turn is never seen | ADR-016..019, owner T1-02 | the Alerts exit shows the same done / refused / unknown note as Positions |
| Done note's order numbers can name another order | usePaperExit.js takes the last N of the reply's `orders`; the reply re-reads the book after commit outside the lock (backend paper.py:1429), so a stop firing in between shows its id | ADR-016 | the order route returns the ids it stored and the note uses them |
| The REST spot cache is not cleared on Kite login | shared_reading.py `REST_SPOT` per process: a FAILED read (403 on an expired token) stays 10 s after re-login (falls back to last close: fails closed) | REQ-118 | login clears the shared readings |
| The Kite token read before a REST call has no time bound | `owner_kite_reads()` sits outside the 9 s bound (live_market.py); with one shared read every caller waits on it | REQ-118 | the token read is inside the bound |
| The builder's own Exit dialog still closes on a block with only the panel's reason line | StrategyBuilderPage.vue `cancelPaperDialog` on `exitBlocked`; not reachable from Positions | ADR-328 (4) | the builder uses the same endExit door |
| A leg stop does not follow a moved leg (issue #774) | confirmed on the PC 27 Nov 09:59 | ADR-330 (42) | (already filed) |

## Afternoon (27 Nov, after the PC's 11:34 re-test)

PC results on 6a5dc90e: 0 Zerodha 429 lines in 10 minutes; Exit placed / changed-elsewhere sentences shown. Still failing: leg
quotes "not live" now and then; the builder's Exit dialog closing silently (T2-08); one exit showing both "placed" and "not
placed" (T1-22). The diagnostic lines (b8297a96) showed no feed-health STALE change after start-up while 8 market reads were
"answered as not live" after > 4 s: the read side, not the feed.

| Item | Root cause (one sentence) | Fix | Commit |
|---|---|---|---|
| Slow reads -> "not live" (top blocker) | The API books a tick only for a token it holds, and every request held its tokens only for that request (`hold_and_read`: hold, wait for a NEW frame, release -> the quote is parked), so each read waited up to 3 s for a new tick while a fresh quote sat in the feed. | One read door `read_quotes` (backend/ofo_app/read_door.py): the book's quote returned at once when live; only known missing tokens are waited for, all in parallel under one deadline; tokens stay held on a standing 30 s lease per token (cap 500, a token a read is using is never evicted, expired first, one sweeper timer); an unknown token is never leased or waited for; `NO_TOKEN` is distinct from a read's own value. Every caller rerouted (market read, paper `_hold_until_ready` / `_snapshot`, adjustment readers, planned-entry holds, indices first paint). Measured with a 0.4 s tick: 0.40 s on every read before, 0.000 s on repeat reads after. | c0d64e49, 7d96029b, e069ff56, aeabedfc, 4067a811, 90606d3d |
| Builder Exit dialog closes silently (T2-08) | The builder's dialog was closed by `cancelPaperDialog` whenever its own book poll failed, never through the endExit door. | Stays open, Confirm grey, "<legs>: Prices are not live; try again when they update"; closes only when the trade changed, with a note. | 4f9958d8 |
| Two final sentences for one exit (T1-22) | Several writers (POST answer, re-read, page close) could each write an end. | One record per exit attempt (frontend/src/lib/exitRecord.js); a late answer replaces unknown / changed / not-stored with placed; placed and refused are never replaced. | bf2238eb |
| Diagnostics | - | "feed health <OLD> -> <NEW>: <reason>" on each change; "paper monitor holds N feed keys (open legs + indexes)"; the monitor's hold reads use the reload's own DB connection. | bcbaf015, b8297a96, a54e90e1 |

Tier A reviews (Opus): read door round 1 FIX FIRST (indices first paint answered LIVE when disconnected; unknown ids stuck;
a 3 s wait with one unknown id; no lease cap; a timer per read) -> fixed; round 2 FIX FIRST (the cap could evict a token a read
was waiting on) -> fixed with pinning (a third, small round, beyond the two-round rule, because it was the day's blocker).
DB evidence: the 17 caller test files each run alone on a fresh local PostgreSQL: all pass.

Feed health and the event loop: an option's health follows when the API processes the relay entry
(`FeedState.on_data` from `KiteProvider.on_frame`, called per bus entry), so a stalled API loop would lag it; the PC logs
showed no such STALE change today.

### Re-test (PC, market hours, after this push)

1. Restart the API as usual. Open a running paper trade in the builder and Positions > Paper; leave both 10 minutes.
2. Expected: the API log has no "plan watch: market read over 4.0 s" lines; leg prices do not flip "not live"; the request log
   has no plan-watch / adjustment / positions request over 1 s while prices tick.
3. Builder: tick a leg, Exit, stop the API for 10 s. Expected: the dialog stays open, Confirm grey, the not-live sentence; start
   the API: Confirm blue.
4. Positions: Exit, Confirm while the API is slow. Expected: exactly one final line: "<leg>: Exit placed on paper (order n)." or
   one refusal / unknown line, never two.

### To file as deferred issues (afternoon)

| Title | Evidence | Spec basis | Done when |
|---|---|---|---|
| The `streaming` predicate counts the read door's lease as a socket holder | Opus round 2: routes/chain.py:71, routes/outcome.py:1327 (outcome.py:1204: any fan-out subscriber); after an indices first paint `Held(feed)(NIFTY)` is True with no socket open; the indices route has its own `_without_the_door` | REQ-133, ADR-015 | one "held by a socket" predicate excludes the door's lease everywhere |
| `NO_TOKEN` is typed `Any` | read_door.py:37: a type checker cannot catch a future caller using it as a value | ADR-008 | a typed result (sentinel class) |
| A request-local read leaves a mixed read (one known missing + one unknown) not waiting | read_door.py:158-159: `done_known` unused in production; the first read after an idle spell reads the known leg not live (fails closed; the next read has it) | REQ-133 | decide whether exit reads pass `done_known` |
| Leg stops are premium levels, so a stop cannot follow Change expiry (#774) | built fail-closed on fix/stop-follows-leg-1127 (a013f2ee, not pushed): removed with a review line | ADR-330 (42) | owner chooses a contract-independent stop kind or keeps removal |
