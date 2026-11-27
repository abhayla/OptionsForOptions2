STATUS 19:50 | item 1: PUSHED 903a0f30 (gate TOTAL PASS) | items 2+3: built, gate running for push 2 (about 20:50) | item 4: next in a worktree | blocker: send_message to @parent refused (auto-mode classifier); this line is the report

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
