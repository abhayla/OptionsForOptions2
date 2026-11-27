STATUS 18:05 | item 1: join built, tests green, Opus review running, gate next | next push ~19:15 | blocker: send_message to @parent refused (elevated_session_untrusted_device); this line is the report

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
