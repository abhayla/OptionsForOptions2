STATUS 20:35 | item 1+2+3: PUSHED (head 18effe14, gate TOTAL PASS) | item 5: merged, gate for push 3 next | item 4: branch hotfix/builder-open-1127 fe4b6700 built, own gate next | blocker: send_message to @parent refused by the auto-mode classifier; this line is the report

# Lane J2 (27 Nov 2026), branch `hotfix/worker-join-1127` from `origin/hotfix/loss-stop-1127` (596c6562)

## Item 1: the join (`git merge origin/hotfix/index-quote-1127`, 709eb835)

Core / Proof: reproduced the two conflicts in `backend/ofo_app/background.py` `_check_unpaused`; wrote
`tests_app/test_worker_join_1127.py` (5 tests) BEFORE resolving; ran it against each side alone:
- Lane J's side: all 5 fail (`Worker.__init__() got an unexpected keyword argument 'rest_spot'`: no quote source).
- Lane U's side: all 5 fail (`readings() missing keyword-only argument 'stops'`: no plan-stop wiring, no skipped line).
- Joined: 5 passed.

| Hunk | Lane J meant | Lane U meant | Joined code |
|---|---|---|---|
| 1 (the read, ~l.1469) | not ticked: `return self._skipped(sid, "not_ticked")` (a logged reason); `read_prices(...)` | not ticked: `return False`; `await self._read_with_either_spot(...)` (feed index first, Zerodha quote second) | `return self._skipped(sid, "not_ticked")` and `read = await self._read_with_either_spot(...)` |
| 2 (the pause branch, ~l.1483) | after `_pause`, `return self._skipped(sid, "prices_<state>")` (a logged reason) | after `_pause`, `self.paused_why[sid] = read.why`, `return False` | `self.paused_why[sid] = read.why` (set after `_pause`, which clears it), then `return self._skipped(sid, f"prices_{state}")` |

Tests of the joined behaviour (each with a plan max-loss stop at its smallest percent, so any loss crosses it):
- index only from the feed: the stop alert opens.
- index only from the quote: the stop alert opens.
- neither source: nothing opens, state LEG_MISSING recorded, one log line `check skipped: prices_leg_missing`.
- stale quote (10 min): nothing opens, STALE, `paused_why == "rest_stale"`, line `prices_stale`.
- a second cycle with no tick: a skipped line.

Q2's tests (merged `origin/test/live-day-gaps-1127`):
- Its stop-chain test called `readings(ev)` without `stops` (Lane J's later signature): fixed in the test.
- Its strict xfails for the daily cap (#200) and the rupee dip (#202) now XPASS: marks removed.
- Its quiet-time guards (a stop held until 09:30; ADR-236) contradict ADR-330 (47) (no quiet time after open): changed to
  "opens at once" (`test_plan_stop_to_alert_chain.py`, `test_clock_boundary_candle_and_quiet.py`).
- Left: its two 08:30 strict xfails (item 4).

## Independent Opus review of the joined worker (Why Opus: the stop path): PASS, 6 minor findings
No path drops a crossed plan stop without a stop alert or a visible reason; `paused_why` order correct; REST once per
cycle per underlying; 20 mutations, 14 killed.
- F4, F5 (test gaps): fixed, 2 new tests (stale `paused_why` cleared by a later fresh read; a raising REST reader at the worker).
- F1 (not fixed; also in Lane U's branch): with a held-but-stale feed index, a REST stand-in that goes stale is not re-read until the
  IST minute changes (the tick key reads held book quotes only). Bounded to ~59 s, no false alert. To file as deferred issue.
- F2 (not fixed): index missing + fresh REST + a stale option leg reports LEG_MISSING / "REST not usable" instead of STALE
  (`background.py` `return again if again.why else read`). Fails closed, reason slightly wrong. To file as deferred issue.
- F3 (item 3): nothing reads `paused_why`; it is stored as "" for non-REST pauses. Item 3 builds the returned state.
- F6 (not fixed): no worker test with a plan body's own custom stop rule (T-06 is already in the fixed set), so
  `stops=frozenset()` at the readings call survives. To file as deferred issue.

## Item 2: ADR-330 (47) remainder
- Built by Lane J and joined (items already in the tree): every plan exit alerts at once (no candle close, no quiet
  time, no daily cap); the 5-minute at-entry period delays and never swallows; a stop already crossed when saved.
- **Fixed, not tested (real database proof here): a fired stop never executes while the monitor clock is ahead of the
  database clock.** RCA (one sentence): migration 0054's guard refuses a suggestion row with `shown_at` after
  `clock_timestamp()`, so the paper stop's `stop_fired` note (and the worker's plan-stop alert) rolled back every tick.
  Class: a record time (a stamp) taken from a clock that is not the database's, written into a column the database
  guards against the future; both writers fixed (`actionable_alerts._INSERT_NOTE`, `playbook_store._INSERT_SUGGESTION`:
  `LEAST(<time>, clock_timestamp())`, no migration). Failing test first: `tests_app/test_clock_ahead_records.py` (a
  record one hour ahead): 2 failed with "a suggestion is never shown in the future" before, 2 passed after; mutation
  (the `LEAST` removed from both) fails both. Real PostgreSQL 16 built as CI does, one file per fresh database:
  test_actionable_alerts 36, test_background_worker 33, test_plan_rupee_worker 1 passed. Detection change: the two
  tests above; the guard itself stays.
- **Not reproduced: "closing the last leg closes the trade's alerts" (T1-09 FAIL of 27 Nov).** The path exists:
  `owner_lister` catches `TrackedExited` and lapses the strategy's open records (`_lapse_exited`, reason
  strategy_closed) at each re-list (every 30 s, `REBUILD_SECONDS`). I could not find the T1-09 step text in the repo, so
  I cannot say which alert stayed open. Needs: the T1-09 step and the alert row (rule id, kind) that stayed open.
  Candidates, not proven: the 30 s re-list delay; a kind `close_by_system` leaves open (answered rows are not open).
  Not built.

## Item 3: "this trade is not being watched" (server side; spec exists, no owner question)
Coordinator correction: no owner question; build to REQ-115 AC-4 / AC-6, REQ-049 line 38, REQ-165 lines 52 and 72,
domain-model line 71, ADR-330 (44) and (58).
- New module `backend/ofo_app/monitoring_state.py` (one capability): the worker writes, per strategy, status
  (active / paused), reason code (its own price state: `leg_missing`, `stale`, `disconnected`, `check_failed`,
  `user_paused`, ...), why (the REST stand-in's reason, e.g. `rest_stale`) and since (kept while status and reason stay
  the same) to the heartbeat's Redis (no migration), at the end of each cycle, only when changed or every 10 s.
  `read_states(client, strategy_ids, now)` answers EVERY asked strategy and never "active" without a fresh heartbeat
  and a fresh snapshot naming it: heartbeat not fresh -> paused `workers_down` (AC-6); snapshot missing, corrupt, older
  than 2 minutes or ahead of the clock -> paused `state_unreadable`; strategy not in the snapshot -> paused
  `not_listed`. Codes only; the words are the screens' ("Monitoring paused", grey "Health unknown").
- Tests (`tests_app/test_monitoring_state.py`, 10, citing the REQ lines): stored with reason, why and since; since kept /
  restarted; no rewrite each cycle but refreshed; workers down; 7 kinds of unreadable snapshot; not listed; a failing
  store never stops a cycle; the real Worker publishing neither-source (`leg_missing`), a stale quote (`stale` +
  `rest_stale`) and a priced trade (active). `test_background_wire_want.py` counts want writes only (as it does for the
  heartbeat).
- NOT built (other lanes' files, needs in RESULTS): the API route and the screens. A route (for example
  `GET /api/monitoring`) calling `read_states` with `feed_bus.new_client`, and the "Monitoring paused" badge and grey
  "Health unknown" dot on Live Strategies, Positions and Home cards from it (Lane K / V / L; REQ-049 line 38, REQ-165
  lines 52 and 72). The paper monitor's paper exits are separate (ADR-330 (44) already alerts there).
- Cases the requirements do not cover (no wording invented): (a) ADR-330 (44)'s alert "Your exit at <level> could not run"
  for a PLAN stop whose level is hit while unpriced: the worker cannot know a level is hit with no price (it pauses,
  nothing is computed), so there is nothing to fire on; the paused state above is what the trader sees. If the owner
  means "the last known price crossed the level", that is a spec row. (b) A trade the worker never lists (no plan,
  nothing traded): `not_listed`; REQ-049 does not say whether such a trade shows paused or nothing. (c) `since` is when
  the worker first noticed (its clock), not when the market data last arrived.

## Item 4: the instrument list (`hotfix/builder-open-1127`, cut from `origin/lanej/builder-open-0827`, 4812a3f; ADR-330 (61))
Owner decision (61): from 08:30 until today's list has loaded the builder keeps working on yesterday's list and says so
in one line; contracts that expired yesterday are left out; every leg is checked again before any order.
- The two review findings: (1) the window opening is the setting `facts.contract_list_publish_time` + 5 minutes
  (`catalogue_refresh.window_open`; the scheduler re-reads the setting each step; a failed read keeps the last value and
  logs the type); no constant 08:35 is left. (2) A run that did not load (failed, refused, timed out) is tried again after 3
  minutes (`RETRY_INTERVAL`); one that loaded waits its hour.
- (61) built: restored the carry-over of `ea4f5188` (the picker keeps yesterday's list, logged once a day); the ONE line is
  catalogue text `contract_list_earlier` ("Contract list of 26 Nov. Today's list loads at about 08:35."), returned as
  `list_notice` on the expiries reply, null once today's list is in; `/health` carries `instrument_list`
  (today | earlier | none | unknown) and `instrument_list_day`; the log says which list is in use. Expired contracts are
  already filtered by `expiry >= today`. The pre-order check is unchanged: `execute._list_health` and the add-time
  eligibility check still call yesterday's list stale (tested).
- Tests first: `tests_app/test_builder_open_1127.py` (8: window from the setting, retry in minutes for failed, refused,
  timed out, no loop faster than the retry, notice text, pre-order stale), the DB test carries the notice assertions.
  PostgreSQL 16, one file per fresh database: carries_over 5, health 2, catalogue_refresh 27, picker_api 25, eligibility 33,
  scenario_clock_routes 5 passed; `tests/errors` 710 passed (new template pin, "pending owner read"); ruff ratchet flat;
  openapi regenerated.
- Q2's `tests_app/test_clock_boundary_0830.py` is not on this branch (it is on the join branch). When the two meet:
  its first strict xfail (08:07 start reloads at 08:35) will XPASS, delete the mark; its second (list loaded 08:07 usable at
  08:31) asserts `loaded_before` is false, which (61) keeps true on purpose (the pre-order check must refuse it): that
  test's premise is replaced by the picker test above.
- Pending owner read: the line "Contract list of <date>. Today's list loads at about <time>." Not built: the builder page
  showing the line (Lane V; it reads `list_notice`).
- Status: Fixed, not tested on the owner's PC. Not yet gated or pushed at this line's time.

## Item 5: the adjustment check's price wait (Lane Q2 leftover 1)
RCA: `adjustment_check` awaited `market_reader` and the REST index quote with no limit. Class: a screen check that
waits on a vendor read with no budget. Fix: new module `backend/ofo_app/price_budget.py` (one budget of 4 s for both reads;
a cut read answers not live: the market as when not connected, the quote FAILED; the quote is not asked at all once the
market is cut); the route wraps its readers. Tests first: `tests_app/test_price_budget.py` (6; the route wiring test
fails without the wiring, shown by mutation). Q2's strict xfail in `test_load_live_day.py` is removed with the fix.
Caveat, honest: on this machine (PostgreSQL 16, scenario ADJ-01) Q2's two strict xfails XPASS even on the unmodified join
branch, because the scenario feed holds the index so the stalled REST quote is never asked; that load test cannot prove
this fix here, which is why the route wiring test exists. Plan watch keeps its own `_budgeted` (on
`hotfix/plan-watch-load-1127`); when merged, it should call `price_budget.budgeted`. Status: Fixed, not tested.

## Item 6: no "P0 for the worker lane" message arrived.

## Monday 09:15 steps (market open; the PC cannot test plan stops with the market closed)
Set the levels on Sunday on real trades named "T1-05a" etc. (use the trade names you have; one trade per row). Alert
minutes are IST, from the SQL in Lane J's RESULTS (`adjustment_suggestions.shown_at`); the worker's first cycle after
09:15 is within one second of the first price.
| Step | Trade and level set Sunday | Expected alert |
|---|---|---|
| T1-05 rupee stop | Stop Rs set BELOW Friday's close loss (already crossed at Friday's close) | first check after the first price: 09:15 to 09:16, no wait for 09:20 candle or 09:30 quiet time |
| T1-05 percent stop (monthly row) | T-06 % of max loss on a monthly trade, set below Friday's loss % | 09:15 to 09:16 |
| T1-06 stop saved already crossed, accepted Monday | accept the plan at 09:40 with the level already crossed | entry + 5 minutes = 09:45, once (never swallowed) |
| T1-07 profit target Rs 1 | target of 1 rupee | first check where the P&L is at least Rs 1; if already in profit at open, 09:15 to 09:16 |
| T1-08 time exit 09:25 | time exit set to 09:25 | 09:25 to 09:26 (no candle close) |
| T1-09 close last leg | close the last leg at 10:00 | the trade's open alerts close at the next re-list, at most 30 s (not reproduced here, see item 2) |
Also check, for any trade the worker cannot price: the worker log line `check skipped: prices_<state>`.

## To file as deferred issues (the coordinator files them)
1. A stale REST stand-in is not re-read within the IST minute when the held feed index is stale and frozen (review F1; also on Lane U's branch).
2. Index missing + fresh REST + a stale option leg reports LEG_MISSING / "REST not usable" instead of STALE (review F2).
3. A worker test with a plan body's own custom stop rule (review F6; `stops=frozenset()` survives).
4. Closing the last leg: T1-09 not reproduced; needs the step text and the alert row that stayed open.
5. `monitoring_state`: the API route and the screens (badge, grey dot) are not built (Lane K / V / L).
6. The worker's `status` dict keeps entries of strategies that left the list: the published snapshot may still name them.
7. Q2's load test XPASSes on the unmodified branch in a local database (the stalled quote is never asked in scenario mode).

## Paper-only path found
None met. The worker, the alert gate stores and the stop write are one path for paper and real (ADR-330 (58)). The
paper monitor's `_tell_exit_not_run` (#732) is a paper-exit alert; the plan stop has no counterpart because it cannot
know a level is hit with no price (item 3, case (a)).

## Pending owner read (new on-screen words)
`contract_list_earlier`: "Contract list of {day}. Today's list loads at about {time}." Nothing else new on a screen.

## Today's work by model
| Task | Model | Minutes (about) |
|---|---|---|
| Join, tests, items 2, 3, 4, 5 (build, test runs, gates, pushes) | Sonnet (this session) | 175 |
| Independent review of the joined worker (Tier A: the stop path) | Opus (reviewer) | 18 |
| Helpers for mechanical work | none used | 0 |
