---
work_item: W-152
ac: AC-4
requirement: REQ-133
ac_fp: "0b19e9a63200"
result: pass
verified_by: "independent verifier (Opus row 24 check on 7e9f5ee4, reproduced step 1 on the base)"
builder: "builders (Opus: row 24 20cdbbc1; Sonnet finisher 7e9f5ee4; orchestrator pin for outcome_waiting_first_price)"
date: '2026-10-24'
commands: "pytest tests_app/test_strategy_live_push.py -k req133 against the base backend and HEAD; vitest REQ-133 AC-2 tests; mut24-results.jsonl (4 killed, clean 41 passed)"
---

AC: AC-4
result: pass
commands: pytest tests_app/test_strategy_live_push.py -k req133 against the base backend and HEAD; vitest REQ-133 AC-2 tests; mut24-results.jsonl (4 killed, clean 41 passed)
observed: Both defects are tested as classes: out-of-order version frames (Builder and card) draw only the newer; a reconnect before the first tick shows no unhealthy inside the window and shows it after; the three feed-reconnect tests are red on the unfixed base and green on HEAD
attack: the after-window alarm is asserted at FEED_STALE + 1 ms with a controllable clock (no wall-clock sleep). MINOR (#532): a misleading test name at tests_app/test_strategy_live_push.py:955

Recorded by the orchestrator from the verifier's returned block.
