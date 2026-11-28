STATUS 16:05 | item 1: fixed, not tested | next push 16:40 | blocker: none

# Lane RA: round 3 leftovers (base integration/weekend-r2-1128 17385d88 + merge of fix/r4-worker-4-1128, merged cleanly, no conflict)

Highest claimable status: Fixed, not tested.

## Item 1: failing tests and the timing test
Core: `test_a_position_whose_kind_cannot_be_read_is_not_stopped_either` alone on a fresh database (local PostgreSQL 16, as the CI
job builds it): failed with `ofo_app.strategy_refused.StrategyRefused: real_position_exit_refused` at `paper_store.py:140`,
raised from the `_strategy` helper's `paper_store.place`, because the tests patched `strategy_store.kinds_of` to "unknown"
BEFORE building the strategy through the order door. Green after: 5 passed (file `tests_app/test_real_position_stops_fe2_1128.py`).
- Fix (tests only, the door is untouched): the strategy and its armed exit are built first, `kinds_of` is patched after,
  so the monitor reads a kind that cannot be read while the order door never sees it. The three assertions are unchanged.
- Pool test, which one it is: machine speed, not a hold. Measured with a probe: the fixed `sleep(0.3)` snapshot fell inside
  each request's own database phase (about 25 queries, 150 to 335 ms), where short holds are expected and /health waits
  for one of 4 pooled connections; the same code read `checkedout=4` once and `0` once. Under 6 busy CPU loops the OLD
  test failed 3 of 5 (both the paper mix, the plan-watch measure and the executor test); the NEW one passes 5 of 5 under
  the same load and 3 of 3 idle. Fix: the measurement starts only after every stalled reader was reached (event-driven,
  up to 20 s, a clear failure message otherwise); the 0.5 s /health bound is unchanged. After that point /health takes
  0.01 s and the pool reads 0 checked out. `reads == 0` on FE4's Saturday clock could not be reproduced here (Saturday
  clock, 3 of 3 green before the change); the wait now turns "not reached" into a stated timeout instead of a flat failure.
  No code hold was found: plan-watch's `run_check` releases its connection before the REST read (D-36 (c)).

## For the owner lane
(nothing yet)

## Decided for the owner
- Item 1: tests built in the order "state first, patch second" instead of inserting rows directly (same state, smaller diff).

## Question for the owner
(none yet)

## Not done
(items 2 to 5 pending)
